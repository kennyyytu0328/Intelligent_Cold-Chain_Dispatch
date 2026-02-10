"""Tests for Shipment CRUD endpoints."""
import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from tests.api.conftest import make_mock_result, make_mock_shipment


class TestListShipments:

    async def test_list_returns_200(self, client, mock_session):
        shipment = make_mock_shipment()
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalars_list=[shipment])
        )
        mock_session.scalar = AsyncMock(return_value=1)

        response = await client.get("/api/v1/shipments")
        assert response.status_code == 200


class TestGetShipment:

    async def test_found_returns_200(self, client, mock_session):
        shipment = make_mock_shipment()
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=shipment)
        )

        response = await client.get(f"/api/v1/shipments/{shipment.id}")
        assert response.status_code == 200

    async def test_not_found_returns_404(self, client, mock_session):
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=None)
        )

        response = await client.get(f"/api/v1/shipments/{uuid4()}")
        assert response.status_code == 404


class TestDeleteShipment:

    async def test_delete_returns_204(self, client, mock_session):
        shipment = make_mock_shipment(status="PENDING")
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=shipment)
        )

        response = await client.delete(f"/api/v1/shipments/{shipment.id}")
        assert response.status_code == 204

    async def test_delete_not_found_returns_404(self, client, mock_session):
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=None)
        )

        response = await client.delete(f"/api/v1/shipments/{uuid4()}")
        assert response.status_code == 404
