"""Tests for Depot endpoints."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime
from decimal import Decimal

from tests.api.conftest import make_mock_result


def make_mock_depot(depot_id=None):
    depot = MagicMock()
    depot.id = depot_id or uuid4()
    depot.name = "Test Depot"
    depot.code = "DEP-001"
    depot.address = "456 Depot St"
    depot.latitude = Decimal("25.0330")
    depot.longitude = Decimal("121.5654")
    depot.is_active = True
    depot.contact_person = "Manager"
    depot.contact_phone = "0912345678"
    depot.created_at = datetime.now()
    depot.updated_at = datetime.now()
    depot.location = None
    return depot


class TestListDepots:

    async def test_list_returns_200(self, client, mock_session):
        depot = make_mock_depot()
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalars_list=[depot])
        )
        mock_session.scalar = AsyncMock(return_value=1)

        response = await client.get("/api/v1/depots")
        assert response.status_code == 200


class TestGetDepot:

    async def test_not_found_returns_404(self, client, mock_session):
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=None)
        )

        response = await client.get(f"/api/v1/depots/{uuid4()}")
        assert response.status_code == 404
