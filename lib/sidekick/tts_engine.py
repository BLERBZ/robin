"""Multi-backend text-to-speech engine for the Kait AI sidekick.

Supports four backends with automatic fallback:
1. **ElevenLabs** -- Cloud, exceptional voice quality (``ELEVEN_LABS_API_KEY``)
2. **OpenAI TTS** -- Cloud, high quality (``OPENAI_API_KEY``)
3. **Piper** -- Local neural TTS, zero latency
4. **macOS Say** -- System TTS, zero setup (``/usr/bin/say``)

Audio playback uses ``sounddevice`` + ``soundfile`` when available,
falling back to subprocess ``afplay`` (macOS) / ``aplay`` (Linux).
No pygame dependency.

Configuration via environment variables::

    KAIT_TTS_BACKEND=auto          # auto|elevenlabs|openai|piper|say
    KAIT_TTS_VOICE=                # backend-specific voice name
    KAIT_TTS_SPEED=1.0             # speech speed multiplier
    ELEVEN_LABS_API_KEY=            # ElevenLabs API key
    OPENAI_API_KEY=                 # OpenAI API key

Usage::

    engine = TTSEngine()
    engine.speak("Hello, I am Kait!", callback=on_tts_ready)
    if engine.is_speaking():
        pos = engine.get_playback_position_ms()
    engine.stop()
"""

from __future__ import annotations

import io
import logging
import os
import pathlib
import platform
import subprocess
import tempfile
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("kait.sidekick.tts")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_SAMPLE_RATE = 22050
_MODEL_DIR = pathlib.Path.home() / ".kait" / "models" / "piper"
_DEFAULT_MODEL = "en_US-lessac-medium"

# Phoneme weight categories for proportional duration distribution.
_VOWELS = set("aeiouAEIOUæɑɒɔəɛɪʊʌɐɜːˈˌ")
_STOPS = set("pbtdkgʔ")
_NASALS = set("mnŋɲ")

_VOWEL_WEIGHT = 1.4
_STOP_WEIGHT = 0.6
_NASAL_WEIGHT = 1.0
_DEFAULT_WEIGHT = 1.0

# Optional audio playback libraries
_SOUNDDEVICE_AVAILABLE = False
try:
    import sounddevice as sd  # type: ignore[import-untyped]
    import soundfile as sf  # type: ignore[import-untyped]
    _SOUNDDEVICE_AVAILABLE = True
except ImportError:
    sd = None  # type: ignore[assignment]
    sf = None  # type: ignore[assignment]


# ===================================================================
# Data types
# ===================================================================

@dataclass
class PhonemeEvent:
    """A single phoneme with its timing within the utterance."""

    phoneme: str
    start_ms: int
    duration_ms: int


@dataclass
class TTSResult:
    """Result of a TTS synthesis operation."""

    audio_bytes: bytes
    sample_rate: int
    phonemes: List[PhonemeEvent]
    duration_ms: int
    backend: str = "unknown"


# ===================================================================
# Abstract TTSBackend
# ===================================================================

class TTSBackend(ABC):
    """Abstract base class for all TTS backends."""

    @abstractmethod
    def synthesize(self, text: str, voice: Optional[str] = None, speed: float = 1.0) -> TTSResult:
        """Synthesize text to audio.

        Parameters
        ----------
        text:
            The text to speak.
        voice:
            Optional voice name/ID (backend-specific).
        speed:
            Speech speed multiplier (1.0 = normal).

        Returns
        -------
        A TTSResult with audio bytes and metadata.
        """
        ...

    @property
    @abstractmethod
    def available(self) -> bool:
        """Whether this backend is ready for synthesis."""
        ...

    @property
    def name(self) -> str:
        return self.__class__.__name__


# ===================================================================
# ElevenLabsBackend
# ===================================================================

class ElevenLabsBackend(TTSBackend):
    """Cloud TTS via the ElevenLabs API.

    Requires ``ELEVEN_LABS_API_KEY`` environment variable and the
    ``elevenlabs`` Python package.
    """

    _DEFAULT_VOICE = "Rachel"
    _DEFAULT_MODEL_ID = "eleven_monolingual_v1"

    def __init__(self) -> None:
        self._available = False
        self._client: Any = None
        self._api_key = os.environ.get("ELEVEN_LABS_API_KEY", "")
        if self._api_key:
            try:
                from elevenlabs.client import ElevenLabs  # type: ignore[import-untyped]
                self._client = ElevenLabs(api_key=self._api_key)
                self._available = True
                logger.info("ElevenLabs TTS backend available")
            except ImportError:
                logger.info("ElevenLabs package not installed")
            except Exception as exc:
                logger.info("ElevenLabs init failed: %s", exc)

    @property
    def available(self) -> bool:
        return self._available

    def synthesize(self, text: str, voice: Optional[str] = None, speed: float = 1.0) -> TTSResult:
        if not self._available or self._client is None:
            raise RuntimeError("ElevenLabs backend not available")

        voice_name = voice or self._DEFAULT_VOICE
        start = time.monotonic()

        try:
            audio_gen = self._client.generate(
                text=text,
                voice=voice_name,
                model=self._DEFAULT_MODEL_ID,
            )
            # Collect streamed audio bytes
            audio_bytes = b"".join(audio_gen)
        except Exception as exc:
            raise RuntimeError(f"ElevenLabs synthesis failed: {exc}") from exc

        elapsed_ms = int((time.monotonic() - start) * 1000)

        # ElevenLabs returns MP3 by default; estimate duration from byte size
        # Approximate: ~16kbps mono MP3 -> 2000 bytes/sec
        estimated_duration = max(100, len(audio_bytes) * 1000 // 2000) if audio_bytes else 0

        phonemes = FallbackPhonemeEstimator().estimate(text, estimated_duration)

        return TTSResult(
            audio_bytes=audio_bytes,
            sample_rate=44100,
            phonemes=phonemes,
            duration_ms=estimated_duration,
            backend="elevenlabs",
        )


# ===================================================================
# OpenAITTSBackend
# ===================================================================

class OpenAITTSBackend(TTSBackend):
    """Cloud TTS via the OpenAI API.

    Requires ``OPENAI_API_KEY`` environment variable and the ``openai``
    Python package.
    """

    _DEFAULT_VOICE = "alloy"
    _DEFAULT_MODEL = "tts-1"

    def __init__(self) -> None:
        self._available = False
        self._client: Any = None
        self._api_key = os.environ.get("OPENAI_API_KEY", "")
        if self._api_key:
            try:
                from openai import OpenAI  # type: ignore[import-untyped]
                self._client = OpenAI(api_key=self._api_key)
                self._available = True
                logger.info("OpenAI TTS backend available")
            except ImportError:
                logger.info("OpenAI package not installed")
            except Exception as exc:
                logger.info("OpenAI TTS init failed: %s", exc)

    @property
    def available(self) -> bool:
        return self._available

    def synthesize(self, text: str, voice: Optional[str] = None, speed: float = 1.0) -> TTSResult:
        if not self._available or self._client is None:
            raise RuntimeError("OpenAI TTS backend not available")

        voice_name = voice or self._DEFAULT_VOICE
        start = time.monotonic()

        try:
            response = self._client.audio.speech.create(
                model=self._DEFAULT_MODEL,
                voice=voice_name,
                input=text,
                speed=speed,
                response_format="pcm",
            )
            audio_bytes = response.content
        except Exception as exc:
            raise RuntimeError(f"OpenAI TTS synthesis failed: {exc}") from exc

        # OpenAI PCM is 24kHz 16-bit mono
        sample_rate = 24000
        num_samples = len(audio_bytes) // 2
        duration_ms = int(num_samples / sample_rate * 1000)
        phonemes = FallbackPhonemeEstimator().estimate(text, duration_ms)

        return TTSResult(
            audio_bytes=audio_bytes,
            sample_rate=sample_rate,
            phonemes=phonemes,
            duration_ms=duration_ms,
            backend="openai",
        )


# ===================================================================
# PiperTTSBackend
# ===================================================================

class PiperTTSBackend(TTSBackend):
    """Backend that wraps the ``piper`` CLI for neural TTS synthesis."""

    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        self._model = model
        self._model_path: Optional[pathlib.Path] = None
        self._available: bool = False
        self._fallback = FallbackPhonemeEstimator()
        self._check_availability()

    def _check_availability(self) -> None:
        try:
            result = subprocess.run(
                ["piper", "--version"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode != 0:
                logger.info("piper binary found but returned non-zero; TTS unavailable")
                return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.info("piper binary not found; TTS will use fallback")
            return

        self._ensure_model()
        if self._model_path is not None and self._model_path.exists():
            self._available = True
            logger.info("Piper TTS ready with model %s", self._model)
        else:
            logger.warning("Piper model not available at %s", self._model_path)

    def _ensure_model(self) -> None:
        _MODEL_DIR.mkdir(parents=True, exist_ok=True)
        model_file = _MODEL_DIR / f"{self._model}.onnx"
        config_file = _MODEL_DIR / f"{self._model}.onnx.json"

        if model_file.exists() and config_file.exists():
            self._model_path = model_file
            return

        logger.info("Downloading Piper model %s ...", self._model)
        try:
            subprocess.run(
                [
                    "piper",
                    "--download-dir", str(_MODEL_DIR),
                    "--model", self._model,
                    "--update-voices",
                ],
                capture_output=True,
                timeout=120,
            )
            if model_file.exists():
                self._model_path = model_file
                logger.info("Model downloaded to %s", model_file)
            else:
                logger.warning("Model download did not produce expected file")
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("Failed to download Piper model: %s", exc)

    @property
    def available(self) -> bool:
        return self._available

    def synthesize(self, text: str, voice: Optional[str] = None, speed: float = 1.0) -> TTSResult:
        if not self._available or self._model_path is None:
            raise RuntimeError("Piper TTS backend is not available")

        try:
            proc = subprocess.run(
                [
                    "piper",
                    "--model", str(self._model_path),
                    "--output_raw",
                ],
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise RuntimeError(f"Piper synthesis failed: {exc}") from exc

        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"Piper returned {proc.returncode}: {stderr}")

        audio_bytes = proc.stdout
        num_samples = len(audio_bytes) // 2
        duration_ms = int(num_samples / _SAMPLE_RATE * 1000)
        phonemes = self._get_phonemes(text, duration_ms)

        return TTSResult(
            audio_bytes=audio_bytes,
            sample_rate=_SAMPLE_RATE,
            phonemes=phonemes,
            duration_ms=duration_ms,
            backend="piper",
        )

    def _get_phonemes(self, text: str, duration_ms: int) -> List[PhonemeEvent]:
        try:
            proc = subprocess.run(
                ["espeak-ng", "--ipa", "-q", text],
                capture_output=True,
                timeout=5,
            )
            ipa_output = proc.stdout.decode("utf-8", errors="replace").strip()
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return self._fallback.estimate(text, duration_ms)

        if not ipa_output:
            return self._fallback.estimate(text, duration_ms)

        raw_phonemes: List[str] = [
            ch for ch in ipa_output if ch not in (" ", "\n", "\t")
        ]
        if not raw_phonemes:
            return []
        return _distribute_phoneme_timing(raw_phonemes, duration_ms)


# ===================================================================
# MacOSSayBackend
# ===================================================================

class MacOSSayBackend(TTSBackend):
    """Backend that uses the macOS ``say`` command for speech synthesis."""

    def __init__(self) -> None:
        self._available: bool = False
        self._check_availability()

    def _check_availability(self) -> None:
        if platform.system() != "Darwin":
            return
        try:
            result = subprocess.run(
                ["say", "-v", "?"],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                self._available = True
                logger.info("macOS say backend available")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    @property
    def available(self) -> bool:
        return self._available

    def synthesize(self, text: str, voice: Optional[str] = None, speed: float = 1.0) -> TTSResult:
        if not self._available:
            raise RuntimeError("macOS say backend is not available")

        with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tmp:
            aiff_path = tmp.name
        raw_path = aiff_path + ".wav"

        try:
            cmd = ["say", "-o", aiff_path]
            if voice:
                cmd.extend(["-v", voice])
            if speed != 1.0:
                rate = int(200 * speed)
                cmd.extend(["-r", str(rate)])
            cmd.append(text)
            subprocess.run(cmd, capture_output=True, timeout=30)

            subprocess.run(
                [
                    "afconvert",
                    "-f", "WAVE", "-d", "LEI16@22050", "-c", "1",
                    aiff_path, raw_path,
                ],
                capture_output=True, timeout=15,
            )

            raw_bytes = b""
            with open(raw_path, "rb") as f:
                wav_data = f.read()
                data_offset = wav_data.find(b"data")
                if data_offset >= 0 and data_offset + 8 <= len(wav_data):
                    raw_bytes = wav_data[data_offset + 8:]
                elif len(wav_data) > 44:
                    raw_bytes = wav_data[44:]

            num_samples = len(raw_bytes) // 2
            duration_ms = int(num_samples / _SAMPLE_RATE * 1000)
            phonemes = FallbackPhonemeEstimator().estimate(text, duration_ms)

            return TTSResult(
                audio_bytes=raw_bytes,
                sample_rate=_SAMPLE_RATE,
                phonemes=phonemes,
                duration_ms=duration_ms,
                backend="say",
            )
        finally:
            for p in (aiff_path, raw_path):
                try:
                    os.remove(p)
                except OSError:
                    pass


# ===================================================================
# FallbackPhonemeEstimator
# ===================================================================

class FallbackPhonemeEstimator:
    """Pure-Python phoneme estimator for when no TTS backend is available."""

    _G2P: Dict[str, str] = {
        "a": "æ", "b": "b", "c": "k", "d": "d", "e": "ɛ",
        "f": "f", "g": "g", "h": "h", "i": "ɪ", "j": "dʒ",
        "k": "k", "l": "l", "m": "m", "n": "n", "o": "ɒ",
        "p": "p", "q": "k", "r": "ɹ", "s": "s", "t": "t",
        "u": "ʌ", "v": "v", "w": "w", "x": "ks", "y": "j",
        "z": "z",
    }

    def estimate(self, text: str, duration_ms: int = 0) -> List[PhonemeEvent]:
        phonemes: List[str] = []
        for char in text.lower():
            if char in self._G2P:
                phonemes.append(self._G2P[char])
            elif char == " ":
                phonemes.append(" ")

        if not phonemes:
            return []

        if duration_ms <= 0:
            duration_ms = len(phonemes) * 80

        return _distribute_phoneme_timing(phonemes, duration_ms)


# ===================================================================
# Shared phoneme timing distribution
# ===================================================================

def _distribute_phoneme_timing(
    phonemes: List[str],
    total_duration_ms: int,
) -> List[PhonemeEvent]:
    """Distribute *total_duration_ms* across *phonemes* proportionally."""
    if not phonemes or total_duration_ms <= 0:
        return []

    weights: List[float] = []
    for p in phonemes:
        if any(ch in _VOWELS for ch in p):
            weights.append(_VOWEL_WEIGHT)
        elif any(ch in _STOPS for ch in p):
            weights.append(_STOP_WEIGHT)
        elif any(ch in _NASALS for ch in p):
            weights.append(_NASAL_WEIGHT)
        else:
            weights.append(_DEFAULT_WEIGHT)

    total_weight = sum(weights)
    if total_weight <= 0:
        total_weight = 1.0

    events: List[PhonemeEvent] = []
    cursor_ms = 0
    for i, phoneme in enumerate(phonemes):
        dur = int(total_duration_ms * weights[i] / total_weight)
        dur = max(dur, 1)
        events.append(PhonemeEvent(phoneme=phoneme, start_ms=cursor_ms, duration_ms=dur))
        cursor_ms += dur

    if events:
        remainder = total_duration_ms - cursor_ms
        events[-1].duration_ms = max(1, events[-1].duration_ms + remainder)

    return events


# ===================================================================
# Audio Playback (no pygame)
# ===================================================================

class _AudioPlayer:
    """Cross-platform audio playback without pygame.

    Uses sounddevice+soundfile when available, falls back to subprocess
    (afplay on macOS, aplay on Linux).
    """

    def __init__(self) -> None:
        self._playing = False
        self._play_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def play_pcm(self, audio_bytes: bytes, sample_rate: int) -> None:
        """Play raw PCM 16-bit signed mono audio."""
        self.stop()
        self._stop_event.clear()

        if _SOUNDDEVICE_AVAILABLE:
            self._play_thread = threading.Thread(
                target=self._play_sounddevice,
                args=(audio_bytes, sample_rate),
                daemon=True,
            )
        else:
            self._play_thread = threading.Thread(
                target=self._play_subprocess,
                args=(audio_bytes, sample_rate),
                daemon=True,
            )

        self._playing = True
        self._play_thread.start()

    def play_file_bytes(self, audio_bytes: bytes, fmt: str = "mp3") -> None:
        """Play encoded audio (MP3, WAV, etc.) from bytes."""
        self.stop()
        self._stop_event.clear()

        self._play_thread = threading.Thread(
            target=self._play_encoded_subprocess,
            args=(audio_bytes, fmt),
            daemon=True,
        )
        self._playing = True
        self._play_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._playing = False

    @property
    def playing(self) -> bool:
        return self._playing

    def _play_sounddevice(self, audio_bytes: bytes, sample_rate: int) -> None:
        try:
            import numpy as np  # type: ignore[import-untyped]
            data = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            sd.play(data, samplerate=sample_rate, blocking=True)
        except Exception as exc:
            logger.warning("sounddevice playback failed: %s", exc)
        finally:
            self._playing = False

    def _play_subprocess(self, audio_bytes: bytes, sample_rate: int) -> None:
        """Play PCM audio via subprocess fallback."""
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
                # Write minimal WAV header + PCM data
                import struct
                num_samples = len(audio_bytes) // 2
                data_size = len(audio_bytes)
                header = struct.pack(
                    "<4sI4s4sIHHIIHH4sI",
                    b"RIFF", 36 + data_size, b"WAVE",
                    b"fmt ", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
                    b"data", data_size,
                )
                tmp.write(header + audio_bytes)

            if platform.system() == "Darwin":
                cmd = ["afplay", tmp_path]
            else:
                cmd = ["aplay", "-q", tmp_path]

            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            while proc.poll() is None:
                if self._stop_event.is_set():
                    proc.terminate()
                    break
                time.sleep(0.05)
        except Exception as exc:
            logger.warning("Subprocess playback failed: %s", exc)
        finally:
            self._playing = False
            try:
                os.remove(tmp_path)
            except (OSError, UnboundLocalError):
                pass

    def _play_encoded_subprocess(self, audio_bytes: bytes, fmt: str) -> None:
        """Play encoded audio (MP3, etc.) via subprocess."""
        try:
            with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as tmp:
                tmp_path = tmp.name
                tmp.write(audio_bytes)

            if platform.system() == "Darwin":
                cmd = ["afplay", tmp_path]
            else:
                cmd = ["aplay", "-q", tmp_path]

            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            while proc.poll() is None:
                if self._stop_event.is_set():
                    proc.terminate()
                    break
                time.sleep(0.05)
        except Exception as exc:
            logger.warning("Encoded playback failed: %s", exc)
        finally:
            self._playing = False
            try:
                os.remove(tmp_path)
            except (OSError, UnboundLocalError):
                pass


# ===================================================================
# TTSEngine -- high-level API
# ===================================================================

class TTSEngine:
    """High-level text-to-speech engine for the Kait sidekick.

    Selects backend via ``KAIT_TTS_BACKEND`` env var (default: ``auto``).
    Backend hierarchy: ElevenLabs -> OpenAI -> Piper -> macOS Say.

    Usage::

        engine = TTSEngine()
        engine.speak("Hello!", callback=my_callback)
        while engine.is_speaking():
            pos = engine.get_playback_position_ms()
        engine.stop()
    """

    def __init__(self) -> None:
        self._backends: List[TTSBackend] = []
        self._active_backend: Optional[TTSBackend] = None
        self._fallback = FallbackPhonemeEstimator()
        self._player = _AudioPlayer()
        self._playback_start: float = 0.0
        self._playback_duration_ms: int = 0
        self._speaking: bool = False
        self._lock = threading.Lock()
        self._synth_thread: Optional[threading.Thread] = None

        # Read configuration
        self._preferred = os.environ.get("KAIT_TTS_BACKEND", "auto").lower()
        self._voice = os.environ.get("KAIT_TTS_VOICE", "")
        self._speed = float(os.environ.get("KAIT_TTS_SPEED", "1.0"))

        self._init_backends()

    def _init_backends(self) -> None:
        """Initialize backends based on preference."""
        if self._preferred == "auto":
            # Try all in priority order
            for cls in (ElevenLabsBackend, OpenAITTSBackend, PiperTTSBackend, MacOSSayBackend):
                try:
                    backend = cls()
                    self._backends.append(backend)
                    if backend.available and self._active_backend is None:
                        self._active_backend = backend
                except Exception as exc:
                    logger.info("Backend %s init failed: %s", cls.__name__, exc)
        else:
            backend_map = {
                "elevenlabs": ElevenLabsBackend,
                "openai": OpenAITTSBackend,
                "piper": PiperTTSBackend,
                "say": MacOSSayBackend,
            }
            cls = backend_map.get(self._preferred)
            if cls:
                try:
                    backend = cls()
                    self._backends.append(backend)
                    if backend.available:
                        self._active_backend = backend
                except Exception as exc:
                    logger.warning("Preferred backend %s failed: %s", self._preferred, exc)

            # Always add fallbacks
            for fallback_cls in (PiperTTSBackend, MacOSSayBackend):
                if fallback_cls != cls:
                    try:
                        fb = fallback_cls()
                        self._backends.append(fb)
                        if fb.available and self._active_backend is None:
                            self._active_backend = fb
                    except Exception:
                        pass

        if self._active_backend:
            logger.info("TTSEngine active backend: %s", self._active_backend.name)
        else:
            logger.info("TTSEngine: no audio backend available, using fallback estimator")

    @property
    def active_backend_name(self) -> str:
        """Name of the currently active TTS backend."""
        if self._active_backend:
            return self._active_backend.name
        return "none"

    # ---- public API --------------------------------------------------------

    def speak(
        self,
        text: str,
        callback: Optional[Callable[[TTSResult], None]] = None,
    ) -> None:
        """Synthesise and play *text* as speech."""
        if not text or not text.strip():
            return

        self.stop()

        thread = threading.Thread(
            target=self._synth_and_play,
            args=(text, callback),
            daemon=True,
            name="kait-tts-synth",
        )
        with self._lock:
            self._synth_thread = thread
        thread.start()

    def stop(self) -> None:
        """Stop current speech playback immediately."""
        with self._lock:
            self._speaking = False
            self._playback_duration_ms = 0
        self._player.stop()

    def is_speaking(self) -> bool:
        """Return True if speech audio is currently playing."""
        with self._lock:
            if not self._speaking:
                return False
            elapsed = (time.monotonic() - self._playback_start) * 1000
            if elapsed >= self._playback_duration_ms:
                self._speaking = False
                return False
            return True

    def get_playback_position_ms(self) -> int:
        """Return the current playback position in milliseconds."""
        with self._lock:
            if not self._speaking:
                return 0
            elapsed = int((time.monotonic() - self._playback_start) * 1000)
            return min(elapsed, self._playback_duration_ms)

    # ---- internal ----------------------------------------------------------

    def _synth_and_play(
        self,
        text: str,
        callback: Optional[Callable[[TTSResult], None]],
    ) -> None:
        """Background worker: synthesise text, start playback, invoke callback."""
        result: Optional[TTSResult] = None

        # Try active backend first, then iterate through all backends
        backends_to_try = []
        if self._active_backend:
            backends_to_try.append(self._active_backend)
        for b in self._backends:
            if b is not self._active_backend and b.available:
                backends_to_try.append(b)

        for backend in backends_to_try:
            try:
                result = backend.synthesize(text, voice=self._voice or None, speed=self._speed)
                break
            except Exception as exc:
                logger.warning("%s synthesis failed: %s", backend.name, exc)

        # Final fallback: produce phoneme timings without audio
        if result is None:
            phonemes = self._fallback.estimate(text)
            total_ms = sum(p.duration_ms for p in phonemes) if phonemes else 0
            result = TTSResult(
                audio_bytes=b"",
                sample_rate=_SAMPLE_RATE,
                phonemes=phonemes,
                duration_ms=total_ms,
                backend="fallback",
            )

        # Play audio
        if result.audio_bytes:
            with self._lock:
                self._playback_start = time.monotonic()
                self._playback_duration_ms = result.duration_ms
                self._speaking = True

            if result.backend == "elevenlabs":
                # ElevenLabs returns MP3
                self._player.play_file_bytes(result.audio_bytes, "mp3")
            elif result.backend in ("piper", "say"):
                # Raw PCM
                self._player.play_pcm(result.audio_bytes, result.sample_rate)
            elif result.backend == "openai":
                # Raw PCM at 24kHz
                self._player.play_pcm(result.audio_bytes, result.sample_rate)
            else:
                self._player.play_pcm(result.audio_bytes, result.sample_rate)
        else:
            # No audio -- mark speaking for duration-based tracking
            if result.duration_ms > 0:
                with self._lock:
                    self._playback_start = time.monotonic()
                    self._playback_duration_ms = result.duration_ms
                    self._speaking = True

        if callback is not None:
            try:
                callback(result)
            except Exception as exc:
                logger.warning("TTS callback raised: %s", exc)


# ===================================================================
# Module exports
# ===================================================================

__all__ = [
    "PhonemeEvent",
    "TTSResult",
    "TTSBackend",
    "ElevenLabsBackend",
    "OpenAITTSBackend",
    "PiperTTSBackend",
    "MacOSSayBackend",
    "FallbackPhonemeEstimator",
    "TTSEngine",
    "_distribute_phoneme_timing",
    "_VOWEL_WEIGHT",
    "_STOP_WEIGHT",
    "_SAMPLE_RATE",
]
