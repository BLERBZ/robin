#!/usr/bin/env python3
"""
Tests for lib/sidekick/web_browser.py

These tests verify the web browser module's structure, caching, result formatting,
async bridge, and graceful degradation without requiring browser-use to be installed.
"""

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.sidekick.web_browser import (
    BrowseResult,
    WebBrowser,
    _AsyncBridge,
    _ResultCache,
    get_web_browser,
    is_browser_available,
)


# ---------------------------------------------------------------------------
# BrowseResult
# ---------------------------------------------------------------------------

class TestBrowseResult:
    def test_default_values(self):
        r = BrowseResult()
        assert r.success is True
        assert r.task == ""
        assert r.url is None
        assert r.content == ""
        assert r.error is None
        assert r.cached is False

    def test_to_dict(self):
        r = BrowseResult(
            success=True,
            task="test task",
            url="https://example.com",
            title="Example",
            content="Hello world",
            elapsed_s=1.5,
        )
        d = r.to_dict()
        assert d["success"] is True
        assert d["task"] == "test task"
        assert d["url"] == "https://example.com"
        assert d["content"] == "Hello world"
        assert d["elapsed_s"] == 1.5

    def test_for_llm_context(self):
        r = BrowseResult(
            url="https://example.com",
            title="Example Domain",
            content="This domain is for use in illustrative examples.",
        )
        ctx = r.for_llm_context()
        assert "Example Domain" in ctx
        assert "https://example.com" in ctx
        assert "illustrative examples" in ctx

    def test_for_llm_context_error(self):
        r = BrowseResult(success=False, error="Connection refused")
        ctx = r.for_llm_context()
        assert "Connection refused" in ctx

    def test_for_llm_context_empty(self):
        r = BrowseResult()
        ctx = r.for_llm_context()
        assert ctx == "(no content retrieved)"

    def test_content_truncation_in_dict(self):
        long_content = "x" * 600_000
        r = BrowseResult(content=long_content)
        d = r.to_dict()
        assert len(d["content"]) == 500_000  # _MAX_RESULT_CHARS


# ---------------------------------------------------------------------------
# ResultCache
# ---------------------------------------------------------------------------

class TestResultCache:
    def test_put_and_get(self, tmp_path):
        cache = _ResultCache(cache_dir=tmp_path, max_age_s=60)
        result = BrowseResult(
            success=True,
            task="test query",
            content="cached content",
        )
        cache.put("test query", result)
        retrieved = cache.get("test query")
        assert retrieved is not None
        assert retrieved.content == "cached content"
        assert retrieved.cached is True

    def test_cache_miss(self, tmp_path):
        cache = _ResultCache(cache_dir=tmp_path, max_age_s=60)
        assert cache.get("nonexistent") is None

    def test_cache_expiry(self, tmp_path):
        cache = _ResultCache(cache_dir=tmp_path, max_age_s=0)  # Expire immediately
        result = BrowseResult(task="expire test", content="will expire")
        cache.put("expire test", result)
        # Cache entry should be expired
        time.sleep(0.1)
        assert cache.get("expire test") is None

    def test_clear(self, tmp_path):
        cache = _ResultCache(cache_dir=tmp_path, max_age_s=300)
        for i in range(5):
            cache.put(f"query {i}", BrowseResult(content=f"result {i}"))
        count = cache.clear()
        assert count == 5
        assert cache.get("query 0") is None

    def test_case_insensitive_keys(self, tmp_path):
        cache = _ResultCache(cache_dir=tmp_path, max_age_s=60)
        cache.put("Python News", BrowseResult(content="news"))
        # Same key lowercased should match
        retrieved = cache.get("python news")
        assert retrieved is not None


# ---------------------------------------------------------------------------
# AsyncBridge
# ---------------------------------------------------------------------------

class TestAsyncBridge:
    def test_run_simple_coroutine(self):
        import asyncio

        bridge = _AsyncBridge()

        async def add(a, b):
            return a + b

        result = bridge.run(add(2, 3), timeout=5)
        assert result == 5
        bridge.shutdown()

    def test_run_async_sleep(self):
        import asyncio

        bridge = _AsyncBridge()

        async def delayed():
            await asyncio.sleep(0.1)
            return "done"

        result = bridge.run(delayed(), timeout=5)
        assert result == "done"
        bridge.shutdown()

    def test_shutdown_idempotent(self):
        bridge = _AsyncBridge()
        bridge.shutdown()
        bridge.shutdown()  # Should not raise


# ---------------------------------------------------------------------------
# WebBrowser (mocked — no real browser-use needed)
# ---------------------------------------------------------------------------

class TestWebBrowserGracefulDegradation:
    """Test that WebBrowser degrades gracefully when browser-use is not installed."""

    def test_run_task_without_browser_use(self):
        browser = WebBrowser()
        # Force _initialized to False and set error
        browser._initialized = False
        with patch("lib.sidekick.web_browser._BROWSER_USE_AVAILABLE", False):
            with patch(
                "lib.sidekick.web_browser._BROWSER_USE_IMPORT_ERROR",
                "No module named 'browser_use'",
            ):
                # Reset to trigger re-init
                browser._initialized = False
                browser._init_error = None
                result = browser.run_task("test")
                assert result.success is False
                assert "not installed" in (result.error or "").lower() or "not available" in (result.error or "").lower()

    def test_search_without_browser(self):
        browser = WebBrowser()
        browser._initialized = True
        browser._init_error = "No browser available"
        result = browser.search("python")
        assert result.success is False

    def test_browse_url_without_browser(self):
        browser = WebBrowser()
        browser._initialized = True
        browser._init_error = "No browser available"
        result = browser.browse_url("https://example.com")
        assert result.success is False

    def test_stats_before_init(self):
        browser = WebBrowser()
        browser._initialized = True
        browser._init_error = "test error"
        stats = browser.get_stats()
        assert stats["total_tasks"] == 0
        assert stats["init_error"] == "test error"

    def test_clear_cache(self):
        browser = WebBrowser()
        count = browser.clear_cache()
        assert isinstance(count, int)

    def test_shutdown_safe(self):
        browser = WebBrowser()
        browser.shutdown()  # Should not raise


# ---------------------------------------------------------------------------
# is_browser_available
# ---------------------------------------------------------------------------

class TestFeatureDetection:
    def test_is_browser_available_returns_bool(self):
        result = is_browser_available()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_get_web_browser_returns_same_instance(self):
        b1 = get_web_browser()
        b2 = get_web_browser()
        assert b1 is b2


# ---------------------------------------------------------------------------
# BrowserAgent integration (from agents.py)
# ---------------------------------------------------------------------------

class TestBrowserAgentIntegration:
    """Test the BrowserAgent registered in the agent orchestrator."""

    def test_browser_agent_registered(self):
        from lib.sidekick.agents import AgentOrchestrator
        orch = AgentOrchestrator()
        result = orch.dispatch("browser", {"user_message": "hello"})
        assert result.agent == "browser"

    def test_browser_agent_detects_search_intent(self):
        from lib.sidekick.agents import AgentOrchestrator
        orch = AgentOrchestrator()
        result = orch.dispatch("browser", {
            "user_message": "search the web for Python 3.13 release date",
        })
        assert result.data.get("web_needed") is True

    def test_browser_agent_detects_url(self):
        from lib.sidekick.agents import AgentOrchestrator
        orch = AgentOrchestrator()
        result = orch.dispatch("browser", {
            "user_message": "Go to https://example.com and get the title",
        })
        assert result.data.get("web_needed") is True

    def test_browser_agent_no_web_needed(self):
        from lib.sidekick.agents import AgentOrchestrator
        orch = AgentOrchestrator()
        result = orch.dispatch("browser", {
            "user_message": "What is 2 + 2?",
        })
        assert result.data.get("web_needed") is False

    def test_browser_aliases(self):
        from lib.sidekick.agents import AgentOrchestrator
        orch = AgentOrchestrator()
        for alias in ("browser", "browse", "web", "search", "internet"):
            result = orch.dispatch(alias, {"user_message": "test"})
            assert result.agent == "browser", f"Alias '{alias}' did not route to browser agent"


# ---------------------------------------------------------------------------
# Web tools in ToolRegistry
# ---------------------------------------------------------------------------

class TestWebToolsRegistered:
    """Verify web tools are registered in the default ToolRegistry."""

    def test_web_tools_in_registry(self):
        from lib.sidekick.tools import create_default_registry
        registry = create_default_registry()
        for name in ("web_search", "web_browse", "web_extract", "web_task"):
            assert name in registry, f"Tool '{name}' not found in registry"

    def test_web_tools_metadata(self):
        from lib.sidekick.tools import create_default_registry
        registry = create_default_registry()
        tools = registry.list_tools()
        browser_tools = [t for t in tools if t["category"] == "browser"]
        assert len(browser_tools) == 4

    def test_web_search_missing_query(self):
        from lib.sidekick.tools import create_default_registry
        registry = create_default_registry()
        result = registry.execute("web_search", {})
        assert result["success"] is False
        assert "query" in result.get("error", "").lower()

    def test_web_browse_missing_url(self):
        from lib.sidekick.tools import create_default_registry
        registry = create_default_registry()
        result = registry.execute("web_browse", {})
        assert result["success"] is False
        assert "url" in result.get("error", "").lower()
