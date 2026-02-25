"""Tests for Olla proxy integration."""

from __future__ import annotations
import os
import pytest
from unittest.mock import patch


class TestOllaURLResolution:
    """Test Olla-aware URL resolution in local_llm."""

    def test_default_url_without_olla(self):
        """Without KAIT_OLLA_ENABLED, base URL points to direct Ollama."""
        with patch.dict(os.environ, {"KAIT_OLLA_ENABLED": "false"}, clear=False):
            # Reimport to pick up env
            import importlib
            import lib.sidekick.local_llm as mod
            importlib.reload(mod)
            assert "11434" in mod._OLLAMA_BASE

    def test_olla_enabled_changes_url(self):
        """With KAIT_OLLA_ENABLED=true, base URL points to Olla proxy."""
        env = {
            "KAIT_OLLA_ENABLED": "true",
            "KAIT_OLLA_HOST": "localhost",
            "KAIT_OLLA_PORT": "11435",
        }
        with patch.dict(os.environ, env, clear=False):
            import importlib
            import lib.sidekick.local_llm as mod
            importlib.reload(mod)
            assert "11435" in mod._OLLAMA_BASE


class TestOllaConfig:
    """Test Olla configuration file."""

    def test_config_exists(self):
        from pathlib import Path
        config = Path(__file__).parent.parent / "config" / "olla.yaml"
        assert config.exists()

    def test_config_has_backends(self):
        from pathlib import Path
        config = Path(__file__).parent.parent / "config" / "olla.yaml"
        content = config.read_text()
        assert "backends" in content
        assert "11434" in content
