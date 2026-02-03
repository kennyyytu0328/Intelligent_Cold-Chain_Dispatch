"""FastAPI dependencies for authentication and authorization."""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.database import get_async_session
from app.models.user import User

# HTTP Bearer token extractor (reads Authorization: Bearer <token>)
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> User:
    """Dependency to get current authenticated user from JWT token.

    Usage:
        @router.get("/protected")
        async def protected_route(
            current_user: Annotated[User, Depends(get_current_user)]
        ):
            return {"message": f"Hello {current_user.username}"}

    Raises:
        HTTPException 401: If token is missing, invalid, or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Check if token is present
    if credentials is None:
        raise credentials_exception

    # Decode token
    username = decode_access_token(credentials.credentials)
    if username is None:
        raise credentials_exception

    # Fetch user from database
    result = await session.execute(
        select(User).where(User.username == username, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user
