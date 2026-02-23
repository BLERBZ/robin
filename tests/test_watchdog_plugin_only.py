from pathlib import Path

import kait_watchdog


def test_plugin_only_mode_from_env(monkeypatch, tmp_path):
    sentinel = tmp_path / "plugin_only_mode"
    monkeypatch.setattr(kait_watchdog, "PLUGIN_ONLY_SENTINEL", sentinel)
    monkeypatch.setenv("KAIT_PLUGIN_ONLY", "1")
    assert kait_watchdog._plugin_only_mode_enabled() is True


def test_plugin_only_mode_from_sentinel(monkeypatch, tmp_path):
    sentinel = tmp_path / "plugin_only_mode"
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("1", encoding="utf-8")
    monkeypatch.setattr(kait_watchdog, "PLUGIN_ONLY_SENTINEL", sentinel)
    monkeypatch.delenv("KAIT_PLUGIN_ONLY", raising=False)
    assert kait_watchdog._plugin_only_mode_enabled() is True


def test_restart_allowed_keeps_core_services_in_plugin_only():
    assert kait_watchdog._restart_allowed("kaitd", plugin_only_mode=True) is True
    assert kait_watchdog._restart_allowed("scheduler", plugin_only_mode=True) is True
    assert kait_watchdog._restart_allowed("bridge_worker", plugin_only_mode=True) is False
    assert kait_watchdog._restart_allowed("pulse", plugin_only_mode=True) is False

