"""
Kait Sidekick - Web Browser Module (browser-use integration)

Gives Kait full autonomous internet access: browsing, searching, content
extraction, and multi-step web tasks.  Wraps the `browser-use` library
(https://github.com/browser-use/browser-use) with:

  - Async-to-sync bridging (Kait's main loop is synchronous / threaded)
  - Lazy Chromium initialization (browser only spins up when needed)
  - Graceful degradation when browser-use is not installed
  - Result caching for repeat queries
  - Structured output suitable for LLM context injection
  - Thread-safe singleton design

LLM priority (zero-config with Ollama):
  1. Ollama local (default — uses Kait's existing Ollama, no API keys needed)
  2. BROWSER_USE_API_KEY  - For ChatBrowserUse (optimised browser model)
  3. ANTHROPIC_API_KEY    - For ChatAnthropic (higher quality)
  4. GOOGLE_API_KEY       - For ChatGoogle
  5. OPENAI_API_KEY       - For ChatOpenAI

Environment variables (optional):
  KAIT_BROWSER_MODEL    - Override Ollama model for browsing (default: auto-detect)
  KAIT_BROWSER_HEADLESS - "0" to show the browser window (default headless)
  KAIT_BROWSER_TIMEOUT  - Max seconds per browsing task (default 120)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("kait.sidekick.web_browser")

# ---------------------------------------------------------------------------
# Feature detection
# ---------------------------------------------------------------------------

_BROWSER_USE_AVAILABLE = False
_BROWSER_USE_IMPORT_ERROR: Optional[str] = None

try:
    from browser_use import Agent as BrowserAgent, Browser  # noqa: F401
    _BROWSER_USE_AVAILABLE = True
except ImportError as exc:
    _BROWSER_USE_IMPORT_ERROR = str(exc)
except Exception as exc:
    _BROWSER_USE_IMPORT_ERROR = str(exc)


def is_browser_available() -> bool:
    """Return True if the browser-use library is importable."""
    return _BROWSER_USE_AVAILABLE


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_CACHE_DIR = Path.home() / ".kait" / "browser_cache"
_DEFAULT_TIMEOUT = int(os.environ.get("KAIT_BROWSER_TIMEOUT", "120"))
_HEADLESS = os.environ.get("KAIT_BROWSER_HEADLESS", "1") != "0"
_MAX_CACHE_AGE_S = 600  # 10 minutes
_MAX_RESULT_CHARS = 500_000  # 500 KB text cap for LLM injection


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class BrowseResult:
    """Structured result from a web browsing operation."""

    success: bool = True
    task: str = ""
    url: Optional[str] = None
    title: Optional[str] = None
    content: str = ""
    extracted_data: Dict[str, Any] = field(default_factory=dict)
    screenshots: List[str] = field(default_factory=list)
    urls_visited: List[str] = field(default_factory=list)
    error: Optional[str] = None
    elapsed_s: float = 0.0
    cached: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "task": self.task,
            "url": self.url,
            "title": self.title,
            "content": self.content[:_MAX_RESULT_CHARS] if self.content else "",
            "extracted_data": self.extracted_data,
            "urls_visited": self.urls_visited,
            "error": self.error,
            "elapsed_s": round(self.elapsed_s, 2),
            "cached": self.cached,
        }

    def for_llm_context(self) -> str:
        """Format this result for injection into an LLM prompt."""
        parts = []
        if self.title:
            parts.append(f"Page: {self.title}")
        if self.url:
            parts.append(f"URL: {self.url}")
        if self.urls_visited and len(self.urls_visited) > 1:
            parts.append(f"Pages visited: {len(self.urls_visited)}")
        if self.content:
            trimmed = self.content[:_MAX_RESULT_CHARS]
            parts.append(f"Content:\n{trimmed}")
        if self.extracted_data:
            parts.append(f"Extracted data: {json.dumps(self.extracted_data, default=str)}")
        if self.error:
            parts.append(f"Error: {self.error}")
        return "\n".join(parts) if parts else "(no content retrieved)"


# ---------------------------------------------------------------------------
# LLM resolver — picks the best available LLM for browser-use
# ---------------------------------------------------------------------------

def _detect_ollama_model() -> Optional[str]:
    """Detect the best available Ollama model for browser tasks.

    Prefers larger, more capable models for web browsing.
    """
    override = os.environ.get("KAIT_BROWSER_MODEL")
    if override:
        return override

    try:
        import urllib.request
        import urllib.error

        host = os.getenv("KAIT_OLLAMA_HOST", "localhost")
        port = int(os.getenv("KAIT_OLLAMA_PORT", "11434"))
        url = f"http://{host}:{port}/api/tags"
        resp = urllib.request.urlopen(url, timeout=3)
        data = json.loads(resp.read().decode())
        models = [m["name"] for m in data.get("models", [])]
    except Exception:
        return None

    if not models:
        return None

    # Prefer models roughly by capability for web browsing tasks.
    # Larger instruction-tuned models handle complex web navigation better.
    preference = [
        # Large general-purpose (best for browsing)
        "qwen2.5:32b", "qwen2.5-coder:32b", "llama3.1:70b", "llama3.3:70b",
        "deepseek-r1:32b", "mistral-large",
        # Medium (good enough)
        "qwen2.5:14b", "llama3.1:8b", "llama3.2:8b", "gemma2:9b",
        "mistral:7b", "mistral",
        # Small (workable for simple tasks)
        "qwen2.5:7b", "qwen2.5-coder:7b", "llama3.2:3b", "llama3:latest",
        "phi3:mini", "gemma2:2b",
    ]

    for preferred in preference:
        if preferred in models:
            return preferred

    # Fall back to first available model
    return models[0]


def _resolve_browser_llm():
    """Return a langchain-compatible ChatModel for browser-use.

    Priority:
      1. Ollama local (zero config — uses Kait's existing Ollama instance)
      2. ChatBrowserUse (if BROWSER_USE_API_KEY set)
      3. ChatAnthropic (if ANTHROPIC_API_KEY set)
      4. ChatGoogle (if GOOGLE_API_KEY set)
      5. ChatOpenAI (if OPENAI_API_KEY set)
    """
    # 1. Ollama local — zero config, uses existing Kait infrastructure
    ollama_model = _detect_ollama_model()
    if ollama_model:
        host = os.getenv("KAIT_OLLAMA_HOST", "localhost")
        port = int(os.getenv("KAIT_OLLAMA_PORT", "11434"))
        base_url = f"http://{host}:{port}"

        # Try the newer langchain-ollama package first, fall back to community
        try:
            from langchain_ollama import ChatOllama
            llm = ChatOllama(model=ollama_model, base_url=base_url, temperature=0.0)
            log.info("Browser LLM: Ollama/%s (local, no API keys needed)", ollama_model)
            return llm
        except ImportError:
            pass
        except Exception as exc:
            log.debug("langchain_ollama.ChatOllama init failed: %s", exc)

        try:
            from langchain_community.chat_models import ChatOllama as CommunityChatOllama
            llm = CommunityChatOllama(model=ollama_model, base_url=base_url, temperature=0.0)
            log.info("Browser LLM: Ollama/%s (local, no API keys needed)", ollama_model)
            return llm
        except ImportError:
            log.debug("langchain-community not installed, skipping Ollama")
        except Exception as exc:
            log.debug("ChatOllama (community) init failed: %s", exc)

    # 2. browser-use's native model (cloud, needs BROWSER_USE_API_KEY)
    if os.environ.get("BROWSER_USE_API_KEY"):
        try:
            from browser_use import ChatBrowserUse
            log.info("Browser LLM: ChatBrowserUse (cloud)")
            return ChatBrowserUse()
        except Exception as exc:
            log.debug("ChatBrowserUse init failed: %s", exc)

    # 3. Anthropic (cloud, needs ANTHROPIC_API_KEY)
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from browser_use import ChatAnthropic
            log.info("Browser LLM: ChatAnthropic/claude-sonnet-4-6 (cloud)")
            return ChatAnthropic(model="claude-sonnet-4-6")
        except Exception:
            try:
                from langchain_anthropic import ChatAnthropic as LCAnthropic
                log.info("Browser LLM: ChatAnthropic/claude-sonnet-4-6 (cloud)")
                return LCAnthropic(model="claude-sonnet-4-6")
            except Exception as exc:
                log.debug("ChatAnthropic init failed: %s", exc)

    # 4. Google (cloud, needs GOOGLE_API_KEY)
    if os.environ.get("GOOGLE_API_KEY"):
        try:
            from browser_use import ChatGoogle
            log.info("Browser LLM: ChatGoogle/gemini-2.0-flash (cloud)")
            return ChatGoogle(model="gemini-2.0-flash")
        except Exception:
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                log.info("Browser LLM: ChatGoogle/gemini-2.0-flash (cloud)")
                return ChatGoogleGenerativeAI(model="gemini-2.0-flash")
            except Exception as exc:
                log.debug("ChatGoogle init failed: %s", exc)

    # 5. OpenAI (cloud, needs OPENAI_API_KEY)
    if os.environ.get("OPENAI_API_KEY"):
        try:
            from langchain_openai import ChatOpenAI
            log.info("Browser LLM: ChatOpenAI/gpt-4o-mini (cloud)")
            return ChatOpenAI(model="gpt-4o-mini")
        except Exception as exc:
            log.debug("ChatOpenAI init failed: %s", exc)

    return None


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class _ResultCache:
    """Simple file-backed cache for browse results."""

    def __init__(self, cache_dir: Path = _CACHE_DIR, max_age_s: int = _MAX_CACHE_AGE_S):
        self._dir = cache_dir
        self._max_age = max_age_s
        self._dir.mkdir(parents=True, exist_ok=True)

    def _key(self, task: str) -> str:
        return hashlib.sha256(task.strip().lower().encode()).hexdigest()[:24]

    def get(self, task: str) -> Optional[BrowseResult]:
        """Return cached result or None."""
        fp = self._dir / f"{self._key(task)}.json"
        if not fp.exists():
            return None
        try:
            data = json.loads(fp.read_text())
            cached_at = data.get("_cached_at", 0)
            if time.time() - cached_at > self._max_age:
                fp.unlink(missing_ok=True)
                return None
            result = BrowseResult(
                success=data.get("success", True),
                task=data.get("task", task),
                url=data.get("url"),
                title=data.get("title"),
                content=data.get("content", ""),
                extracted_data=data.get("extracted_data", {}),
                urls_visited=data.get("urls_visited", []),
                error=data.get("error"),
                elapsed_s=data.get("elapsed_s", 0),
                cached=True,
            )
            return result
        except Exception:
            return None

    def put(self, task: str, result: BrowseResult) -> None:
        """Store a result in the cache."""
        try:
            data = result.to_dict()
            data["_cached_at"] = time.time()
            fp = self._dir / f"{self._key(task)}.json"
            fp.write_text(json.dumps(data, default=str))
        except Exception as exc:
            log.debug("Cache write failed: %s", exc)

    def clear(self) -> int:
        """Remove all cached results. Returns count removed."""
        count = 0
        for fp in self._dir.glob("*.json"):
            try:
                fp.unlink()
                count += 1
            except Exception:
                pass
        return count


# ---------------------------------------------------------------------------
# Async event-loop bridge
# ---------------------------------------------------------------------------

class _AsyncBridge:
    """Manages a dedicated asyncio event loop in a background thread.

    This lets Kait's synchronous main loop call async browser-use functions
    without blocking or conflicting with an existing event loop.
    """

    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or not self._loop.is_running():
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(
                    target=self._loop.run_forever,
                    daemon=True,
                    name="kait-browser-loop",
                )
                self._thread.start()
            return self._loop

    def run(self, coro, timeout: float = _DEFAULT_TIMEOUT):
        """Run an async coroutine from synchronous code and return the result."""
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    def shutdown(self):
        """Stop the background event loop."""
        with self._lock:
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread:
                self._thread.join(timeout=5)
            self._loop = None
            self._thread = None


# ---------------------------------------------------------------------------
# Core WebBrowser class
# ---------------------------------------------------------------------------

class WebBrowser:
    """High-level web browsing interface for Kait.

    Thread-safe singleton that lazily initializes a Chromium browser and
    provides search, browse, extract, and autonomous task capabilities.

    Usage::

        browser = get_web_browser()

        # Autonomous task
        result = browser.run_task("Find the latest Python release date")

        # Direct URL browsing
        result = browser.browse_url("https://python.org")

        # Web search
        result = browser.search("Python 3.13 release date")

        # Content extraction
        result = browser.extract_content("https://python.org", "release date")
    """

    def __init__(self):
        self._bridge = _AsyncBridge()
        self._cache = _ResultCache()
        self._browser = None
        self._llm = None
        self._lock = threading.Lock()
        self._initialized = False
        self._init_error: Optional[str] = None

        # Stats
        self._total_tasks = 0
        self._total_successes = 0
        self._total_errors = 0
        self._total_time_s = 0.0

    # -- Initialization ------------------------------------------------------

    def _ensure_init(self) -> bool:
        """Lazy-initialize the browser and LLM on first use."""
        if self._initialized:
            return self._init_error is None

        with self._lock:
            if self._initialized:
                return self._init_error is None

            if not _BROWSER_USE_AVAILABLE:
                self._init_error = (
                    f"browser-use not installed: {_BROWSER_USE_IMPORT_ERROR}. "
                    "Install with: pip install 'browser-use>=0.11.0'"
                )
                self._initialized = True
                log.warning("WebBrowser unavailable: %s", self._init_error)
                return False

            # Resolve LLM
            self._llm = _resolve_browser_llm()
            if self._llm is None:
                self._init_error = (
                    "No LLM available for web browsing. Ensure Ollama is running "
                    "(ollama serve) with at least one model pulled (ollama pull llama3.2:3b). "
                    "Or set ANTHROPIC_API_KEY / OPENAI_API_KEY for cloud LLM."
                )
                self._initialized = True
                log.warning("WebBrowser LLM unavailable: %s", self._init_error)
                return False

            # Initialize browser (lazy — will create Chromium on first task)
            try:
                self._browser = Browser(
                    config={
                        "headless": _HEADLESS,
                    }
                ) if _BROWSER_USE_AVAILABLE else None
            except TypeError:
                # Older API — try without config dict
                try:
                    self._browser = Browser()
                except Exception as exc:
                    self._init_error = f"Browser init failed: {exc}"
                    self._initialized = True
                    log.warning(self._init_error)
                    return False
            except Exception as exc:
                self._init_error = f"Browser init failed: {exc}"
                self._initialized = True
                log.warning(self._init_error)
                return False

            self._initialized = True
            log.info("WebBrowser initialized (headless=%s)", _HEADLESS)
            return True

    @property
    def available(self) -> bool:
        """Check if web browsing is ready to use."""
        return self._ensure_init()

    @property
    def init_error(self) -> Optional[str]:
        """Return initialization error message, if any."""
        self._ensure_init()
        return self._init_error

    # -- Public API ----------------------------------------------------------

    def run_task(
        self,
        task: str,
        *,
        use_cache: bool = True,
        timeout: float = _DEFAULT_TIMEOUT,
        max_steps: int = 25,
    ) -> BrowseResult:
        """Execute an autonomous browsing task.

        The browser-use Agent receives the task in natural language, navigates
        the web, and returns structured results.

        Args:
            task: Natural language description of what to do.
            use_cache: Check cache first (default True).
            timeout: Max seconds to wait (default from env).
            max_steps: Maximum browser actions the agent can take.
        """
        if use_cache:
            cached = self._cache.get(task)
            if cached:
                log.debug("Cache hit for task: %s", task[:60])
                return cached

        if not self._ensure_init():
            return BrowseResult(
                success=False,
                task=task,
                error=self._init_error or "Browser not available",
            )

        start = time.monotonic()
        self._total_tasks += 1

        try:
            result = self._bridge.run(
                self._async_run_task(task, max_steps=max_steps),
                timeout=timeout,
            )
            result.elapsed_s = time.monotonic() - start
            self._total_successes += 1
            self._total_time_s += result.elapsed_s

            if result.success and use_cache:
                self._cache.put(task, result)

            return result

        except TimeoutError:
            elapsed = time.monotonic() - start
            self._total_errors += 1
            return BrowseResult(
                success=False,
                task=task,
                error=f"Task timed out after {elapsed:.0f}s",
                elapsed_s=elapsed,
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            self._total_errors += 1
            log.warning("Browser task failed: %s", exc)
            return BrowseResult(
                success=False,
                task=task,
                error=f"{type(exc).__name__}: {exc}",
                elapsed_s=elapsed,
            )

    def search(
        self,
        query: str,
        *,
        num_results: int = 5,
        use_cache: bool = True,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> BrowseResult:
        """Search the web for a query and return results.

        Args:
            query: The search query.
            num_results: Target number of results (hint, not guaranteed).
            use_cache: Check cache first.
            timeout: Max seconds.
        """
        task = (
            f"Search the web for: '{query}'. "
            f"Return the top {num_results} results with their titles, URLs, "
            f"and a brief summary of each. Format as a numbered list."
        )
        return self.run_task(task, use_cache=use_cache, timeout=timeout)

    def browse_url(
        self,
        url: str,
        *,
        instruction: str = "",
        use_cache: bool = True,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> BrowseResult:
        """Navigate to a URL and extract its content.

        Args:
            url: The URL to visit.
            instruction: What to extract or do on the page.
            use_cache: Check cache first.
            timeout: Max seconds.
        """
        if instruction:
            task = f"Go to {url} and {instruction}"
        else:
            task = (
                f"Go to {url} and extract the main content of the page. "
                f"Return the page title, key information, and any important "
                f"data found on the page."
            )
        result = self.run_task(task, use_cache=use_cache, timeout=timeout)
        if not result.url:
            result.url = url
        return result

    def extract_content(
        self,
        url: str,
        query: str,
        *,
        use_cache: bool = True,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> BrowseResult:
        """Extract specific information from a web page.

        Args:
            url: The URL to visit.
            query: What specific information to extract.
            use_cache: Check cache.
            timeout: Max seconds.
        """
        task = (
            f"Go to {url} and extract the following information: {query}. "
            f"Return only the relevant information in a clear, structured format."
        )
        result = self.run_task(task, use_cache=use_cache, timeout=timeout)
        if not result.url:
            result.url = url
        return result

    def multi_search(
        self,
        queries: List[str],
        *,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> List[BrowseResult]:
        """Execute multiple search queries.

        Args:
            queries: List of search queries.
            timeout: Max seconds per query.
        """
        return [self.search(q, timeout=timeout) for q in queries]

    # -- Async internals -----------------------------------------------------

    async def _async_run_task(
        self,
        task: str,
        *,
        max_steps: int = 25,
    ) -> BrowseResult:
        """Internal async implementation of a browsing task."""
        from browser_use import Agent as BUAgent

        agent = BUAgent(
            task=task,
            llm=self._llm,
            browser=self._browser,
            max_actions_per_step=5,
        )

        try:
            agent_result = await agent.run(max_steps=max_steps)
        except Exception as exc:
            return BrowseResult(
                success=False,
                task=task,
                error=f"Agent execution error: {type(exc).__name__}: {exc}",
            )

        # Parse agent result
        content = ""
        extracted = {}
        urls_visited = []
        title = None

        if agent_result:
            # browser-use returns AgentHistoryList
            if hasattr(agent_result, "final_result"):
                content = str(agent_result.final_result()) if callable(
                    getattr(agent_result, "final_result", None)
                ) else str(getattr(agent_result, "final_result", ""))
            elif hasattr(agent_result, "history"):
                # Extract from history
                for step in agent_result.history:
                    if hasattr(step, "result") and step.result:
                        for r in step.result:
                            if hasattr(r, "extracted_content") and r.extracted_content:
                                content += str(r.extracted_content) + "\n"
                            if hasattr(r, "url") and r.url:
                                urls_visited.append(str(r.url))
            else:
                # Fallback: stringify
                content = str(agent_result)

            # Try to get final answer
            if hasattr(agent_result, "model_output"):
                mo = agent_result.model_output
                if hasattr(mo, "action") and mo.action:
                    for a in mo.action:
                        if hasattr(a, "done") and a.done:
                            content = str(getattr(a.done, "text", content))

        return BrowseResult(
            success=True,
            task=task,
            url=urls_visited[-1] if urls_visited else None,
            title=title,
            content=content.strip() if content else "(no content extracted)",
            extracted_data=extracted,
            urls_visited=urls_visited,
        )

    # -- Stats & lifecycle ---------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return usage statistics."""
        llm_name = "none"
        if self._llm is not None:
            llm_cls = type(self._llm).__name__
            model = getattr(self._llm, "model", getattr(self._llm, "model_name", ""))
            llm_name = f"{llm_cls}/{model}" if model else llm_cls

        return {
            "available": self.available,
            "init_error": self._init_error,
            "llm": llm_name,
            "total_tasks": self._total_tasks,
            "total_successes": self._total_successes,
            "total_errors": self._total_errors,
            "success_rate": (
                round(self._total_successes / self._total_tasks, 3)
                if self._total_tasks > 0 else 0.0
            ),
            "total_time_s": round(self._total_time_s, 1),
            "avg_time_s": (
                round(self._total_time_s / self._total_tasks, 1)
                if self._total_tasks > 0 else 0.0
            ),
            "headless": _HEADLESS,
            "cache_dir": str(_CACHE_DIR),
        }

    def clear_cache(self) -> int:
        """Clear the result cache. Returns count removed."""
        return self._cache.clear()

    def shutdown(self) -> None:
        """Cleanly shut down the browser and event loop."""
        try:
            if self._browser and hasattr(self._browser, "close"):
                try:
                    self._bridge.run(self._browser.close(), timeout=10)
                except Exception:
                    pass
        except Exception:
            pass
        self._bridge.shutdown()
        self._browser = None
        self._initialized = False
        self._init_error = None
        log.info("WebBrowser shutdown complete")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: Optional[WebBrowser] = None
_instance_lock = threading.Lock()


def get_web_browser() -> WebBrowser:
    """Return the singleton WebBrowser instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = WebBrowser()
    return _instance


# ---------------------------------------------------------------------------
# Convenience functions (used by tools.py and agents.py)
# ---------------------------------------------------------------------------

def web_search(query: str, num_results: int = 5, timeout: float = _DEFAULT_TIMEOUT) -> BrowseResult:
    """Search the web. Convenience wrapper."""
    return get_web_browser().search(query, num_results=num_results, timeout=timeout)


def web_browse(url: str, instruction: str = "", timeout: float = _DEFAULT_TIMEOUT) -> BrowseResult:
    """Browse a URL. Convenience wrapper."""
    return get_web_browser().browse_url(url, instruction=instruction, timeout=timeout)


def web_extract(url: str, query: str, timeout: float = _DEFAULT_TIMEOUT) -> BrowseResult:
    """Extract content from a URL. Convenience wrapper."""
    return get_web_browser().extract_content(url, query, timeout=timeout)


def web_task(task: str, timeout: float = _DEFAULT_TIMEOUT) -> BrowseResult:
    """Run an autonomous browsing task. Convenience wrapper."""
    return get_web_browser().run_task(task, timeout=timeout)
