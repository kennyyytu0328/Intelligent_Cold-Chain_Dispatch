"""Authentication endpoints."""
import logging
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.db.database import get_async_session
from app.models.user import User
from app.schemas.auth import Token

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)


@router.post("/token", response_model=Token)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> Token:
    """Login endpoint - validates credentials and returns JWT token.

    Request (OAuth2PasswordRequestForm via form-data):
        - username: User's username
        - password: User's password

    Response:
        - access_token: JWT token (valid for 24 hours)
        - token_type: "bearer"

    Raises:
        401 Unauthorized: If credentials are invalid
    """
    # Fetch user by username
    result = await session.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()

    # Validate credentials
    if user is None:
        logger.warning(f"Login attempt failed: User '{form_data.username}' not found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(form_data.password, user.hashed_password):
        logger.warning(f"Login attempt failed: Invalid password for user '{form_data.username}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is active
    if not user.is_active:
        logger.warning(f"Login attempt failed: User '{form_data.username}' account is disabled")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    # Create JWT token
    settings = get_settings()
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires,
    )

    logger.info(f"User '{user.username}' logged in successfully")
    return Token(access_token=access_token, token_type="bearer")
