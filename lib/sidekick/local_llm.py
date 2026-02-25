"""Local LLM integration via Ollama for 100% local AI inference.

Wraps the Ollama HTTP API (localhost:11434) using only Python stdlib.
No cloud dependencies, no third-party HTTP libraries.

Usage:
    from lib.sidekick.local_llm import get_llm_client
    llm = get_llm_client()
    if llm.health_check():
        response = llm.generate("Explain recursion in one sentence.")

Environment variables:
    KAIT_OLLAMA_HOST  - Ollama host (default: localhost)
    KAIT_OLLAMA_PORT  - Ollama port (default: 11434)
    KAIT_OLLAMA_MODEL - Override default model selection
"""

from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import threading
import urllib.error
import urllib.request
from typing import Any, Dict, Generator, List, Optional

from lib.diagnostics import log_debug
from lib.llm_observability import observed

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_OLLAMA_HOST = os.getenv("KAIT_OLLAMA_HOST", "localhost")
_OLLAMA_PORT = int(os.getenv("KAIT_OLLAMA_PORT", "11434"))
_OLLAMA_BASE = f"http://{_OLLAMA_HOST}:{_OLLAMA_PORT}"

# Olla proxy support: when enabled, route through Olla for load balancing
_OLLA_ENABLED = os.getenv("KAIT_OLLA_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
if _OLLA_ENABLED:
    _OLLA_HOST = os.getenv("KAIT_OLLA_HOST", "localhost")
    _OLLA_PORT = int(os.getenv("KAIT_OLLA_PORT", "11435"))
    _OLLAMA_BASE = f"http://{_OLLA_HOST}:{_OLLA_PORT}"

_HEALTH_TIMEOUT_S = 5
_GENERATE_TIMEOUT_S = 120
_EMBED_TIMEOUT_S = 30

# Model preference order: largest useful model first, then smaller fallbacks.
_MODEL_PREFERENCE = [
    "llama3.1:70b",
    "llama3.1:8b",
    "llama3:latest",
    "mistral",
]

_LOG_TAG = "local_llm"


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib-only, no requests/httpx)
# ---------------------------------------------------------------------------

def _post_json(
    path: str,
    payload: Dict[str, Any],
    *,
    timeout: float = _GENERATE_TIMEOUT_S,
    stream: bool = False,
) -> Any:
    """POST JSON to Ollama and return parsed response (or raw stream handle).

    Raises OllamaConnectionError on connection failures and
    OllamaAPIError on non-2xx responses.
    """
    url = f"{_OLLAMA_BASE}{path}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.URLError as exc:
        raise OllamaConnectionError(
            f"Cannot reach Ollama at {_OLLAMA_BASE}. "
            "Is Ollama running?  Start it with: ollama serve"
        ) from exc
    except socket.timeout as exc:
        raise OllamaConnectionError(
            f"Ollama request timed out after {timeout}s"
        ) from exc

    if stream:
        return resp  # caller reads line-by-line

    raw = resp.read().decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _get_json(path: str, *, timeout: float = _HEALTH_TIMEOUT_S) -> Any:
    """GET from Ollama and return parsed JSON."""
    url = f"{_OLLAMA_BASE}{path}"
    req = urllib.request.Request(url, method="GET")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.URLError as exc:
        raise OllamaConnectionError(
            f"Cannot reach Ollama at {_OLLAMA_BASE}. "
            "Is Ollama running?  Start it with: ollama serve"
        ) from exc
    except socket.timeout as exc:
        raise OllamaConnectionError(
            f"Ollama health check timed out after {timeout}s"
        ) from exc

    raw = resp.read().decode("utf-8")
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class OllamaError(Exception):
    """Base exception for Ollama operations."""


class OllamaConnectionError(OllamaError):
    """Raised when Ollama is unreachable (not running, wrong port, timeout)."""


class OllamaAPIError(OllamaError):
    """Raised on non-2xx API responses or malformed data."""


class OllamaNoModelsError(OllamaError):
    """Raised when no models are available locally."""


# ---------------------------------------------------------------------------
# OllamaClient
# ---------------------------------------------------------------------------

class OllamaClient:
    """Client for local Ollama inference.

    Wraps the Ollama REST API using only stdlib urllib.  Provides text
    generation, streaming, multi-turn chat, embeddings, and model/GPU
    introspection.

    Thread-safe: internal model cache is protected by a lock.
    """

    def __init__(
        self,
        host: str = _OLLAMA_HOST,
        port: int = _OLLAMA_PORT,
        default_model: Optional[str] = None,
    ) -> None:
        self._host = host
        self._port = port
        self._base = f"http://{host}:{port}"
        self._default_model = default_model or os.getenv("KAIT_OLLAMA_MODEL")
        self._cached_models: Optional[List[Dict[str, Any]]] = None
        self._cached_best_model: Optional[str] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Health & introspection
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """Return True if Ollama is running and responsive."""
        try:
            url = f"{self._base}/api/tags"
            req = urllib.request.Request(url, method="GET")
            resp = urllib.request.urlopen(req, timeout=_HEALTH_TIMEOUT_S)
            return 200 <= resp.status < 300
        except Exception:
            return False

    def list_models(self) -> List[Dict[str, Any]]:
        """Return available local models.

        Each dict contains at minimum: name, size, modified_at.
        Results are cached per-instance until invalidated.
        """
        with self._lock:
            if self._cached_models is not None:
                return self._cached_models

        try:
            data = _get_json("/api/tags")
        except OllamaError as exc:
            log_debug(_LOG_TAG, "Failed to list models", exc)
            return []

        models = data.get("models", []) if isinstance(data, dict) else []
        with self._lock:
            self._cached_models = models
        return models

    def detect_best_model(self) -> str:
        """Auto-detect the best available model.

        Preference order (configurable via _MODEL_PREFERENCE):
            llama3.1:70b > llama3.1:8b > llama3:latest > mistral > any available

        If KAIT_OLLAMA_MODEL is set, that takes absolute priority.

        Raises OllamaNoModelsError if no models are available.
        """
        # Env override always wins.
        env_model = os.getenv("KAIT_OLLAMA_MODEL")
        if env_model:
            return env_model

        with self._lock:
            if self._cached_best_model is not None:
                return self._cached_best_model

        models = self.list_models()
        if not models:
            raise OllamaNoModelsError(
                "No models found in Ollama. Pull one with: ollama pull llama3.1:8b"
            )

        available_names = {m.get("name", "") for m in models}

        # Walk preference list.
        for preferred in _MODEL_PREFERENCE:
            if preferred in available_names:
                with self._lock:
                    self._cached_best_model = preferred
                log_debug(_LOG_TAG, f"Selected preferred model: {preferred}", None)
                return preferred

        # Fallback: pick the largest available model by parameter size.
        best = _pick_largest_model(models)
        with self._lock:
            self._cached_best_model = best
        log_debug(_LOG_TAG, f"Selected fallback model: {best}", None)
        return best

    def get_gpu_info(self) -> Dict[str, Any]:
        """Detect GPU availability and return a summary dict.

        Keys returned:
            has_gpu (bool), gpu_name (str), vram_mb (int|None),
            backend (str: "cuda" | "metal" | "rocm" | "cpu")
        """
        info: Dict[str, Any] = {
            "has_gpu": False,
            "gpu_name": "none",
            "vram_mb": None,
            "backend": "cpu",
        }

        system = platform.system().lower()

        # macOS: Apple Silicon has unified memory exposed via Metal.
        if system == "darwin":
            try:
                out = subprocess.check_output(
                    ["sysctl", "-n", "hw.memsize"],
                    text=True,
                    timeout=5,
                ).strip()
                total_bytes = int(out)
                info["has_gpu"] = True
                info["gpu_name"] = "Apple Silicon (Metal)"
                info["vram_mb"] = total_bytes // (1024 * 1024)
                info["backend"] = "metal"
                return info
            except Exception:
                pass

        # Linux/Windows: try nvidia-smi for CUDA GPUs.
        try:
            out = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                timeout=5,
                stderr=subprocess.DEVNULL,
            ).strip()
            if out:
                parts = out.split(",", 1)
                info["has_gpu"] = True
                info["gpu_name"] = parts[0].strip()
                if len(parts) > 1:
                    try:
                        info["vram_mb"] = int(float(parts[1].strip()))
                    except ValueError:
                        pass
                info["backend"] = "cuda"
                return info
        except Exception:
            pass

        # Linux: check for ROCm (AMD GPUs).
        if system == "linux":
            try:
                out = subprocess.check_output(
                    ["rocm-smi", "--showproductname"],
                    text=True,
                    timeout=5,
                    stderr=subprocess.DEVNULL,
                ).strip()
                if out and "GPU" in out:
                    info["has_gpu"] = True
                    info["gpu_name"] = "AMD GPU (ROCm)"
                    info["backend"] = "rocm"
                    return info
            except Exception:
                pass

        return info

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def _resolve_model(self, model: Optional[str]) -> str:
        """Determine which model to use for a request."""
        if model:
            return model
        if self._default_model:
            return self._default_model
        return self.detect_best_model()

    def _try_smaller_model(self) -> Optional[str]:
        """Try to switch to a smaller model when current model fails (e.g. OOM).

        Walks _MODEL_PREFERENCE downward from current model.
        Returns the new model name, or None if no smaller model available.
        """
        current = self._default_model or self._cached_best_model
        if not current:
            return None

        # Find current position in preference list
        try:
            idx = _MODEL_PREFERENCE.index(current)
        except ValueError:
            # Current model not in preference list; try the smallest
            if _MODEL_PREFERENCE:
                smaller = _MODEL_PREFERENCE[-1]
                if smaller != current:
                    self._default_model = smaller
                    log_debug(_LOG_TAG, f"Switching to smaller model: {smaller} (current {current} not in preference list)", None)
                    return smaller
            return None

        # Try next smaller model
        for i in range(idx + 1, len(_MODEL_PREFERENCE)):
            candidate = _MODEL_PREFERENCE[i]
            models = self.list_models()
            available_names = {m.get("name", "") for m in models}
            if candidate in available_names:
                self._default_model = candidate
                log_debug(_LOG_TAG, f"Switching to smaller model: {candidate} (was {current})", None)
                return candidate

        return None

    @observed("ollama")
    def generate(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Generate a completion from a single prompt.

        Returns the full response text.  Raises OllamaError subclasses
        on connection or API failures.
        """
        resolved_model = self._resolve_model(model)
        payload: Dict[str, Any] = {
            "model": resolved_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        data = _post_json("/api/generate", payload, timeout=_GENERATE_TIMEOUT_S)

        if not isinstance(data, dict):
            raise OllamaAPIError(f"Unexpected response type: {type(data).__name__}")

        response_text = data.get("response", "")
        if not isinstance(response_text, str):
            response_text = str(response_text)

        return response_text.strip()

    @observed("ollama")
    def generate_stream(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
    ) -> Generator[str, None, None]:
        """Stream tokens from a generation request.

        Yields individual token strings as they arrive from Ollama.
        """
        resolved_model = self._resolve_model(model)
        payload: Dict[str, Any] = {
            "model": resolved_model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        resp = _post_json(
            "/api/generate", payload, timeout=_GENERATE_TIMEOUT_S, stream=True,
        )

        try:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip() if isinstance(raw_line, bytes) else raw_line.strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                token = chunk.get("response", "")
                if token:
                    yield token
                if chunk.get("done", False):
                    break
        finally:
            resp.close()

    # ------------------------------------------------------------------
    # Chat (multi-turn)
    # ------------------------------------------------------------------

    @observed("ollama")
    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
    ) -> str:
        """Multi-turn chat completion.

        Args:
            messages: List of {"role": "user"|"assistant"|"system", "content": "..."}.
            model: Override model selection.
            temperature: Sampling temperature.

        Returns the assistant's response text.
        """
        resolved_model = self._resolve_model(model)
        payload: Dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        data = _post_json("/api/chat", payload, timeout=_GENERATE_TIMEOUT_S)

        if not isinstance(data, dict):
            raise OllamaAPIError(f"Unexpected chat response type: {type(data).__name__}")

        message = data.get("message", {})
        if not isinstance(message, dict):
            raise OllamaAPIError("Malformed chat response: missing 'message' object")

        return message.get("content", "").strip()

    @observed("ollama")
    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
    ) -> Generator[str, None, None]:
        """Stream tokens from a multi-turn chat completion.

        Yields individual token strings as they arrive from Ollama.
        The caller can print them as they arrive for real-time UX.

        Args:
            messages: List of {"role": "user"|"assistant"|"system", "content": "..."}.
            model: Override model selection.
            temperature: Sampling temperature.

        Yields:
            Token strings as they arrive.
        """
        resolved_model = self._resolve_model(model)
        payload: Dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
            },
        }

        resp = _post_json(
            "/api/chat", payload, timeout=_GENERATE_TIMEOUT_S, stream=True,
        )

        try:
            for raw_line in resp:
                line = (
                    raw_line.decode("utf-8").strip()
                    if isinstance(raw_line, bytes)
                    else raw_line.strip()
                )
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                message = chunk.get("message", {})
                if isinstance(message, dict):
                    token = message.get("content", "")
                    if token:
                        yield token
                if chunk.get("done", False):
                    break
        finally:
            resp.close()

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    @observed("ollama")
    def embed(
        self,
        text: str,
        *,
        model: Optional[str] = None,
    ) -> List[float]:
        """Generate an embedding vector for the given text.

        Uses the /api/embed endpoint (Ollama >= 0.4).  Falls back to
        /api/embeddings for older versions.

        Returns a list of floats (embedding dimensions depend on model).
        """
        resolved_model = self._resolve_model(model)
        payload: Dict[str, Any] = {
            "model": resolved_model,
            "input": text,
        }

        # Try newer /api/embed endpoint first.
        try:
            data = _post_json("/api/embed", payload, timeout=_EMBED_TIMEOUT_S)
            if isinstance(data, dict):
                embeddings = data.get("embeddings")
                if isinstance(embeddings, list) and embeddings:
                    first = embeddings[0]
                    if isinstance(first, list):
                        return [float(x) for x in first]
                # Single-input shorthand: some Ollama versions return "embedding".
                embedding = data.get("embedding")
                if isinstance(embedding, list):
                    return [float(x) for x in embedding]
        except OllamaError:
            pass

        # Fallback to legacy /api/embeddings endpoint.
        legacy_payload: Dict[str, Any] = {
            "model": resolved_model,
            "prompt": text,
        }
        data = _post_json("/api/embeddings", legacy_payload, timeout=_EMBED_TIMEOUT_S)
        if isinstance(data, dict):
            embedding = data.get("embedding")
            if isinstance(embedding, list):
                return [float(x) for x in embedding]

        raise OllamaAPIError("Failed to extract embedding vector from Ollama response")

    # ------------------------------------------------------------------
    # Cache invalidation
    # ------------------------------------------------------------------

    def invalidate_cache(self) -> None:
        """Clear cached model list and best-model selection."""
        with self._lock:
            self._cached_models = None
            self._cached_best_model = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pick_largest_model(models: List[Dict[str, Any]]) -> str:
    """From a list of model dicts, pick the one with the largest size.

    Falls back to the first model if size metadata is unavailable.
    """
    if not models:
        raise OllamaNoModelsError("No models available")

    best_name = models[0].get("name", "")
    best_size = 0

    for m in models:
        size = m.get("size", 0)
        if isinstance(size, (int, float)) and size > best_size:
            best_size = size
            best_name = m.get("name", best_name)

    return best_name


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_singleton_lock = threading.Lock()
_singleton_instance: Optional[OllamaClient] = None


def get_llm_client(
    *,
    host: Optional[str] = None,
    port: Optional[int] = None,
    default_model: Optional[str] = None,
) -> OllamaClient:
    """Return the shared OllamaClient singleton.

    On the first call the client is created using the provided kwargs
    (or environment defaults).  Subsequent calls return the same instance
    regardless of arguments.

    Thread-safe via a module-level lock.
    """
    global _singleton_instance
    with _singleton_lock:
        if _singleton_instance is None:
            _singleton_instance = OllamaClient(
                host=host or _OLLAMA_HOST,
                port=port or _OLLAMA_PORT,
                default_model=default_model,
            )
        return _singleton_instance
