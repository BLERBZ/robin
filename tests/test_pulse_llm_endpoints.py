"""Tests for Pulse LLM API endpoints."""

from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock


class TestApiLLMEndpoint:
    """Test /api/llm endpoint structure."""

    @pytest.fixture
    def client(self):
        try:
            from fastapi.testclient import TestClient
            from kait.pulse.app import app
            return TestClient(app)
        except ImportError:
            pytest.skip("FastAPI test client not available")

    def test_llm_endpoint_returns_json(self, client):
        with patch("lib.llm_observability.get_observer") as mock:
            obs = MagicMock()
            obs.enabled = True
            obs.get_summary.return_value = {
                "total_calls": 5,
                "error_rate": 0.0,
                "error_count": 0,
                "p50_latency_ms": 100,
                "p99_latency_ms": 500,
                "total_cost_usd": 0.001,
            }
            obs.get_provider_stats.return_value = {}
            obs.get_recent.return_value = []
            obs.get_lifetime_stats.return_value = {}
            mock.return_value = obs

            resp = client.get("/api/llm")
            assert resp.status_code == 200
            data = resp.json()
            assert data["enabled"] is True
            assert "summary" in data

    def test_llm_endpoint_disabled(self, client):
        with patch("lib.llm_observability.get_observer") as mock:
            obs = MagicMock()
            obs.enabled = False
            mock.return_value = obs

            resp = client.get("/api/llm")
            assert resp.status_code == 200
            data = resp.json()
            assert data["enabled"] is False


class TestApiStatusWithLLM:
    """Test /api/status includes llm_providers."""

    @pytest.fixture
    def client(self):
        try:
            from fastapi.testclient import TestClient
            from kait.pulse.app import app
            return TestClient(app)
        except ImportError:
            pytest.skip("FastAPI test client not available")

    def test_status_includes_llm_providers(self, client):
        with patch("lib.service_control.service_status", return_value={}), \
             patch("lib.sidekick.llm_gateway.get_llm_gateway") as mock_gw, \
             patch("lib.llm_circuit_breaker.get_circuit_breaker_registry") as mock_cb:
            gw = MagicMock()
            gw.health.return_value = {"local": {"available": True}, "claude": {"available": False}}
            mock_gw.return_value = gw
            cb = MagicMock()
            cb.get_status.return_value = {}
            mock_cb.return_value = cb

            resp = client.get("/api/status")
            assert resp.status_code == 200
            data = resp.json()
            assert "llm_providers" in data
