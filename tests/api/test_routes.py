"""Tests for Route endpoints."""
import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from tests.api.conftest import make_mock_result


class TestListRoutes:

    async def test_list_returns_200(self, client, mock_session):
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalars_list=[])
        )
        mock_session.scalar = AsyncMock(return_value=0)

        response = await client.get("/api/v1/routes")
        assert response.status_code == 200


class TestGetRoute:

    async def test_not_found_returns_404(self, client, mock_session):
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=None)
        )

        response = await client.get(f"/api/v1/routes/{uuid4()}")
        assert response.status_code == 404
