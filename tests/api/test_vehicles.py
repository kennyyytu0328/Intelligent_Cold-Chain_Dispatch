"""Tests for Vehicle CRUD endpoints."""
import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from tests.api.conftest import make_mock_result, make_mock_vehicle


class TestListVehicles:

    async def test_list_returns_200(self, client, mock_session):
        vehicle = make_mock_vehicle()
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalars_list=[vehicle])
        )
        mock_session.scalar = AsyncMock(return_value=1)

        response = await client.get("/api/v1/vehicles")
        assert response.status_code == 200


class TestGetVehicle:

    async def test_found_returns_200(self, client, mock_session):
        vehicle = make_mock_vehicle()
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=vehicle)
        )

        response = await client.get(f"/api/v1/vehicles/{vehicle.id}")
        assert response.status_code == 200

    async def test_not_found_returns_404(self, client, mock_session):
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=None)
        )

        response = await client.get(f"/api/v1/vehicles/{uuid4()}")
        assert response.status_code == 404


class TestDeleteVehicle:

    async def test_delete_returns_204(self, client, mock_session):
        vehicle = make_mock_vehicle()
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=vehicle)
        )

        response = await client.delete(f"/api/v1/vehicles/{vehicle.id}")
        assert response.status_code == 204

    async def test_delete_not_found_returns_404(self, client, mock_session):
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=None)
        )

        response = await client.delete(f"/api/v1/vehicles/{uuid4()}")
        assert response.status_code == 404
