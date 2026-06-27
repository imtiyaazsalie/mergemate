"""Tests for the health-check server."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


def _get_client() -> TestClient:
    """Import health app with current env state and return a TestClient."""
    import importlib

    import mergemate.server.health

    importlib.reload(mergemate.server.health)
    from mergemate.server.health import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ensure MERGEMATE_HEALTH_TOKEN is cleared between tests."""
    monkeypatch.delenv("MERGEMATE_HEALTH_TOKEN", raising=False)


class TestHealthEndpoint:
    def test_health_returns_ok_when_no_token(self):
        client = _get_client()
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_health_returns_ok_with_valid_token(self, monkeypatch):
        monkeypatch.setenv("MERGEMATE_HEALTH_TOKEN", "test-token-123")
        client = _get_client()
        resp = client.get("/health", headers={"X-MergeMate-Token": "test-token-123"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_health_returns_401_without_token_when_required(self, monkeypatch):
        monkeypatch.setenv("MERGEMATE_HEALTH_TOKEN", "test-token-123")
        client = _get_client()
        resp = client.get("/health")
        assert resp.status_code == 401
        assert "Unauthorized" in resp.json()["detail"]

    def test_health_returns_401_with_wrong_token(self, monkeypatch):
        monkeypatch.setenv("MERGEMATE_HEALTH_TOKEN", "test-token-123")
        client = _get_client()
        resp = client.get("/health", headers={"X-MergeMate-Token": "wrong-token"})
        assert resp.status_code == 401

    def test_health_token_check_is_case_sensitive(self, monkeypatch):
        monkeypatch.setenv("MERGEMATE_HEALTH_TOKEN", "test-token-123")
        client = _get_client()
        resp = client.get("/health", headers={"X-MergeMate-Token": "TEST-TOKEN-123"})
        assert resp.status_code == 401


class TestReadyEndpoint:
    def test_ready_returns_ok_when_no_token(self):
        client = _get_client()
        resp = client.get("/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["config_loaded"] is True

    def test_ready_returns_401_without_token_when_required(self, monkeypatch):
        monkeypatch.setenv("MERGEMATE_HEALTH_TOKEN", "test-token-123")
        client = _get_client()
        resp = client.get("/ready")
        assert resp.status_code == 401

    def test_ready_returns_ok_with_valid_token(self, monkeypatch):
        monkeypatch.setenv("MERGEMATE_HEALTH_TOKEN", "test-token-123")
        client = _get_client()
        resp = client.get("/ready", headers={"X-MergeMate-Token": "test-token-123"})
        assert resp.status_code == 200
        assert resp.json()["config_loaded"] is True


class TestHealthTokenFromEnv:
    def test_no_token_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("MERGEMATE_HEALTH_TOKEN", raising=False)
        _get_client()
        import mergemate.server.health

        assert mergemate.server.health.HEALTH_TOKEN == ""

    def test_token_set_from_env(self, monkeypatch):
        monkeypatch.setenv("MERGEMATE_HEALTH_TOKEN", "env-token")
        _get_client()
        import mergemate.server.health

        assert mergemate.server.health.HEALTH_TOKEN == "env-token"
