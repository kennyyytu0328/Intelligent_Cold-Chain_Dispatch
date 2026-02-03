"""Authentication request/response schemas."""
from pydantic import Field

from .base import BaseSchema


class Token(BaseSchema):
    """JWT token response."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type (always 'bearer')")


class TokenData(BaseSchema):
    """Decoded JWT token data."""

    username: str | None = None


class UserLogin(BaseSchema):
    """User login credentials (OAuth2 password flow compatible)."""

    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


class UserInDB(BaseSchema):
    """User data as stored in database."""

    id: str
    username: str
    is_active: bool
    created_at: str
