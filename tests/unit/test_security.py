"""Tests for app.core.security module."""
import pytest
from datetime import timedelta

from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    decode_access_token,
)


class TestPasswordHashing:

    def test_hash_returns_bcrypt_format(self):
        hashed = get_password_hash("mypassword")
        assert hashed.startswith("$2b$")

    def test_different_salt_each_time(self):
        hash1 = get_password_hash("mypassword")
        hash2 = get_password_hash("mypassword")
        assert hash1 != hash2

    def test_verify_correct_password(self):
        hashed = get_password_hash("admin123")
        assert verify_password("admin123", hashed) is True

    def test_verify_wrong_password(self):
        hashed = get_password_hash("admin123")
        assert verify_password("wrong", hashed) is False

    def test_verify_empty_password(self):
        hashed = get_password_hash("admin123")
        assert verify_password("", hashed) is False


class TestJWTTokens:

    def test_create_returns_string(self):
        token = create_access_token(data={"sub": "testuser"})
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_valid_token(self):
        token = create_access_token(data={"sub": "testuser"})
        assert decode_access_token(token) == "testuser"

    def test_decode_expired_token(self):
        token = create_access_token(
            data={"sub": "testuser"},
            expires_delta=timedelta(seconds=-1),
        )
        assert decode_access_token(token) is None

    def test_decode_garbage_token(self):
        assert decode_access_token("not.a.valid.jwt") is None

    def test_decode_token_missing_sub(self):
        token = create_access_token(data={"user_id": 123})
        assert decode_access_token(token) is None

    def test_custom_expiry(self):
        token = create_access_token(
            data={"sub": "admin"},
            expires_delta=timedelta(hours=1),
        )
        assert decode_access_token(token) == "admin"
