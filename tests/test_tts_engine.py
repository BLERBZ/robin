"""Tests for lib/sidekick/tts_engine.py.

Covers PhonemeEvent, TTSResult, FallbackPhonemeEstimator,
phoneme timing distribution, and TTSEngine lifecycle.

Piper/espeak-ng are typically absent in CI, so these tests exercise
the fallback path and the pure-Python timing logic.

Run with:
    pytest tests/test_tts_engine.py -v
"""

import sys
import time
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from lib.sidekick.tts_engine import (
    PhonemeEvent,
    TTSResult,
    FallbackPhonemeEstimator,
    PiperTTSBackend,
    TTSEngine,
    _distribute_phoneme_timing,
    _VOWEL_WEIGHT,
    _STOP_WEIGHT,
    _SAMPLE_RATE,
)


# ===================================================================
# PhonemeEvent / TTSResult
# ===================================================================

class TestPhonemeEvent:
    def test_dataclass_fields(self):
        pe = PhonemeEvent(phoneme="æ", start_ms=100, duration_ms=50)
        assert pe.phoneme == "æ"
        assert pe.start_ms == 100
        assert pe.duration_ms == 50

    def test_equality(self):
        a = PhonemeEvent("m", 0, 80)
        b = PhonemeEvent("m", 0, 80)
        assert a == b


class TestTTSResult:
    def test_dataclass_fields(self):
        r = TTSResult(audio_bytes=b"\x00\x01", sample_rate=22050, phonemes=[], duration_ms=500)
        assert r.audio_bytes == b"\x00\x01"
        assert r.sample_rate == 22050
        assert r.duration_ms == 500

    def test_empty_phonemes(self):
        r = TTSResult(b"", 22050, [], 0)
        assert len(r.phonemes) == 0


# ===================================================================
# _distribute_phoneme_timing
# ===================================================================

class TestDistributePhonemeTimings:
    def test_empty_phonemes(self):
        assert _distribute_phoneme_timing([], 1000) == []

    def test_zero_duration(self):
        assert _distribute_phoneme_timing(["a"], 0) == []

    def test_single_phoneme(self):
        events = _distribute_phoneme_timing(["a"], 100)
        assert len(events) == 1
        assert events[0].phoneme == "a"
        assert events[0].start_ms == 0
        assert events[0].duration_ms == 100

    def test_monotonically_increasing_start_ms(self):
        phonemes = ["h", "ɛ", "l", "oʊ"]
        events = _distribute_phoneme_timing(phonemes, 400)
        for i in range(1, len(events)):
            assert events[i].start_ms > events[i - 1].start_ms

    def test_total_duration_approximately_preserved(self):
        phonemes = list("hello")
        events = _distribute_phoneme_timing(phonemes, 500)
        total = sum(e.duration_ms for e in events)
        assert abs(total - 500) <= 5  # allow small rounding

    def test_vowels_longer_than_stops(self):
        """Vowel phonemes should receive proportionally more time."""
        events = _distribute_phoneme_timing(["a", "p"], 200)
        vowel_dur = events[0].duration_ms
        stop_dur = events[1].duration_ms
        assert vowel_dur > stop_dur

    def test_minimum_1ms_per_phoneme(self):
        """When total > phoneme count, each non-last phoneme gets at least 1ms."""
        phonemes = ["a"] * 10
        events = _distribute_phoneme_timing(phonemes, 100)
        for e in events[:-1]:  # last absorbs rounding error
            assert e.duration_ms >= 1

    def test_vowel_gets_more_than_default(self):
        """A vowel phoneme paired with a default-weight phoneme should be longer."""
        # 'a' is a vowel (1.4x), 'l' is default (1.0x)
        events = _distribute_phoneme_timing(["a", "l"], 1000)
        assert events[0].duration_ms > events[1].duration_ms


# ===================================================================
# FallbackPhonemeEstimator
# ===================================================================

class TestFallbackPhonemeEstimator:
    def test_estimate_hello(self):
        est = FallbackPhonemeEstimator()
        events = est.estimate("hello")
        assert len(events) > 0
        assert all(isinstance(e, PhonemeEvent) for e in events)

    def test_estimate_empty(self):
        est = FallbackPhonemeEstimator()
        events = est.estimate("")
        assert events == []

    def test_estimate_with_duration(self):
        est = FallbackPhonemeEstimator()
        events = est.estimate("hi", duration_ms=200)
        total = sum(e.duration_ms for e in events)
        assert abs(total - 200) <= 5

    def test_estimate_without_duration(self):
        """When duration_ms=0, default 80ms per phoneme is used."""
        est = FallbackPhonemeEstimator()
        events = est.estimate("ab")
        assert len(events) == 2
        total = sum(e.duration_ms for e in events)
        assert total > 0

    def test_spaces_become_silence(self):
        est = FallbackPhonemeEstimator()
        events = est.estimate("a b")
        phoneme_strings = [e.phoneme for e in events]
        assert " " in phoneme_strings

    def test_unknown_chars_skipped(self):
        est = FallbackPhonemeEstimator()
        events = est.estimate("!@#")
        assert events == []

    def test_monotonic_start_ms(self):
        est = FallbackPhonemeEstimator()
        events = est.estimate("the quick brown fox", duration_ms=2000)
        for i in range(1, len(events)):
            assert events[i].start_ms >= events[i - 1].start_ms


# ===================================================================
# PiperTTSBackend
# ===================================================================

class TestDistributePhonemeTimingsEdgeCases:
    """Edge cases for phoneme timing distribution."""

    def test_negative_duration(self):
        """Negative total duration should return empty list."""
        assert _distribute_phoneme_timing(["a", "b"], -100) == []

    def test_very_small_duration_many_phonemes(self):
        """Duration smaller than phoneme count should give 1ms each."""
        phonemes = ["a"] * 100
        events = _distribute_phoneme_timing(phonemes, 10)
        # Each phoneme gets at least 1ms, so cursor overshoots
        for e in events[:-1]:
            assert e.duration_ms >= 1

    def test_single_phoneme_gets_all_duration(self):
        events = _distribute_phoneme_timing(["a"], 1000)
        assert len(events) == 1
        assert events[0].duration_ms == 1000

    def test_many_phonemes_stress(self):
        """Large phoneme count should not crash."""
        phonemes = list("abcdefghijklmnopqrstuvwxyz") * 100
        events = _distribute_phoneme_timing(phonemes, 10000)
        assert len(events) == 2600
        for i in range(1, len(events)):
            assert events[i].start_ms >= events[i - 1].start_ms


class TestFallbackPhonemeEstimatorEdgeCases:
    """Edge cases for FallbackPhonemeEstimator."""

    def test_unicode_text(self):
        """Unicode characters not in G2P map should be skipped."""
        est = FallbackPhonemeEstimator()
        events = est.estimate("hello 世界")
        # Only the ASCII chars produce phonemes
        assert len(events) > 0
        assert all(isinstance(e, PhonemeEvent) for e in events)

    def test_emoji_text(self):
        """Emoji characters should be skipped without crash."""
        est = FallbackPhonemeEstimator()
        events = est.estimate("hi 😀👋")
        assert len(events) > 0  # 'h' and 'i' produce phonemes

    def test_very_long_text(self):
        """Long text should not crash the estimator."""
        est = FallbackPhonemeEstimator()
        text = "hello world " * 1000
        events = est.estimate(text, duration_ms=100000)
        assert len(events) > 0
        # Start times should be monotonic
        for i in range(1, len(events)):
            assert events[i].start_ms >= events[i - 1].start_ms

    def test_all_spaces(self):
        """All-spaces text should produce silence phonemes."""
        est = FallbackPhonemeEstimator()
        events = est.estimate("   ")
        assert len(events) == 3
        for e in events:
            assert e.phoneme == " "

    def test_mixed_case(self):
        """Uppercase should be lowered and produce phonemes."""
        est = FallbackPhonemeEstimator()
        events = est.estimate("ABC")
        assert len(events) == 3


class TestPiperTTSBackend:
    def test_unavailable_when_piper_missing(self):
        """Backend should report unavailable when piper binary is absent."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            backend = PiperTTSBackend()
            assert not backend.available

    def test_synthesize_raises_when_unavailable(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            backend = PiperTTSBackend()
            with pytest.raises(RuntimeError, match="not available"):
                backend.synthesize("test")


# ===================================================================
# TTSEngine
# ===================================================================

class TestTTSEngine:
    def test_init_without_piper(self):
        """Engine initializes gracefully even without TTS backends."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            engine = TTSEngine()
            assert engine._active_backend is None

    def test_speak_empty_text(self):
        """speak() with empty text should be a no-op."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            engine = TTSEngine()
            engine.speak("")
            assert not engine.is_speaking()

    def test_speak_with_fallback(self):
        """speak() should work via fallback estimator when Piper is absent."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            engine = TTSEngine()
            received = []

            def on_ready(result):
                received.append(result)

            engine.speak("Hello world", callback=on_ready)
            # Wait for background thread
            time.sleep(0.5)

            assert len(received) == 1
            result = received[0]
            assert isinstance(result, TTSResult)
            assert len(result.phonemes) > 0
            assert result.audio_bytes == b""  # fallback produces no audio

    def test_stop(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            engine = TTSEngine()
            engine.stop()
            assert not engine.is_speaking()

    def test_get_playback_position_when_not_speaking(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            engine = TTSEngine()
            assert engine.get_playback_position_ms() == 0

    def test_callback_exception_does_not_crash(self):
        """If the callback raises, the engine should not crash."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            engine = TTSEngine()

            def bad_callback(result):
                raise ValueError("callback error")

            # Should not raise
            engine.speak("test", callback=bad_callback)
            time.sleep(0.5)

    def test_speak_replaces_current(self):
        """Calling speak() again should stop the current utterance first."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            engine = TTSEngine()
            results = []

            engine.speak("first", callback=lambda r: results.append("first"))
            time.sleep(0.2)
            engine.speak("second", callback=lambda r: results.append("second"))
            time.sleep(0.5)

            assert "second" in results

    def test_thread_is_daemon(self):
        """Synthesis thread should be daemonic so it doesn't block exit."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            engine = TTSEngine()
            engine.speak("hello")
            time.sleep(0.1)
            if engine._synth_thread is not None:
                assert engine._synth_thread.daemon
