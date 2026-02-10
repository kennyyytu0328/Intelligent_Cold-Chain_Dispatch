"""Tests for health check and root endpoints."""
import pytest


class TestHealthEndpoint:

    async def test_health_returns_200(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    async def test_root_returns_200(self, client):
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "docs" in data
        assert "version" in data
