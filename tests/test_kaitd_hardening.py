import json

import kaitd


def test_rate_limiter_enforces_window(monkeypatch):
    monkeypatch.setattr(kaitd, "RATE_LIMIT_PER_MIN", 2)
    monkeypatch.setattr(kaitd, "RATE_LIMIT_WINDOW_S", 60)
    kaitd._RATE_LIMIT_BUCKETS.clear()

    ok, retry = kaitd._allow_rate_limited_request("127.0.0.1", now=100.0)
    assert ok is True
    assert retry == 0

    ok, retry = kaitd._allow_rate_limited_request("127.0.0.1", now=101.0)
    assert ok is True
    assert retry == 0

    ok, retry = kaitd._allow_rate_limited_request("127.0.0.1", now=102.0)
    assert ok is False
    assert retry >= 1

    ok, retry = kaitd._allow_rate_limited_request("127.0.0.1", now=161.0)
    assert ok is True
    assert retry == 0


def test_invalid_quarantine_is_bounded(monkeypatch, tmp_path):
    quarantine = tmp_path / "invalid_events.jsonl"
    monkeypatch.setattr(kaitd, "INVALID_EVENTS_FILE", quarantine)
    monkeypatch.setattr(kaitd, "INVALID_EVENTS_MAX_LINES", 3)
    monkeypatch.setattr(kaitd, "INVALID_EVENTS_MAX_PAYLOAD_CHARS", 12)

    for i in range(5):
        kaitd._quarantine_invalid({"payload": "x" * 200, "i": i}, f"reason-{i}")

    lines = quarantine.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3

    rows = [json.loads(line) for line in lines]
    assert [row["reason"] for row in rows] == ["reason-2", "reason-3", "reason-4"]
    assert isinstance(rows[-1]["payload"], str)
    assert rows[-1]["payload"].endswith("...<truncated>")

