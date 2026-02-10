"""Tests for POST /api/v1/auth/token."""
import pytest
from unittest.mock import AsyncMock

from app.core.security import get_password_hash
from tests.api.conftest import make_mock_result


class TestLoginEndpoint:

    async def test_login_success(self, client, mock_session, mock_user):
        mock_user.hashed_password = get_password_hash("correct_password")
        mock_user.is_active = True
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=mock_user)
        )

        response = await client.post(
            "/api/v1/auth/token",
            data={"username": "testuser", "password": "correct_password"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_user_not_found(self, client, mock_session):
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=None)
        )

        response = await client.post(
            "/api/v1/auth/token",
            data={"username": "nobody", "password": "password"},
        )
        assert response.status_code == 401

    async def test_login_wrong_password(self, client, mock_session, mock_user):
        mock_user.hashed_password = get_password_hash("real_password")
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=mock_user)
        )

        response = await client.post(
            "/api/v1/auth/token",
            data={"username": "testuser", "password": "wrong_password"},
        )
        assert response.status_code == 401

    async def test_login_inactive_user(self, client, mock_session, mock_user):
        mock_user.hashed_password = get_password_hash("correct_password")
        mock_user.is_active = False
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=mock_user)
        )

        response = await client.post(
            "/api/v1/auth/token",
            data={"username": "testuser", "password": "correct_password"},
        )
        assert response.status_code == 403
