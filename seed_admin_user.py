"""Seed script to create default admin user.

Run this after database schema initialization:
    python seed_admin_user.py
"""
import asyncio

from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.database import async_session_maker
from app.models.user import User


async def seed_admin_user():
    """Create default admin user if not exists."""
    username = "admin"
    password = "admin123"  # Change this in production!

    async with async_session_maker() as session:
        # Check if admin already exists
        result = await session.execute(select(User).where(User.username == username))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            print(f"[X] User '{username}' already exists. Skipping.")
            print(f"    Username: {username}")
            print(f"    Password: {password}")
            print(f"    User ID: {existing_user.id}")
            return

        # Create admin user
        admin_user = User(
            username=username,
            hashed_password=get_password_hash(password),
            is_active=True,
        )

        session.add(admin_user)
        await session.commit()
        await session.refresh(admin_user)

        print(f"[OK] Admin user created successfully!")
        print(f"     Username: {username}")
        print(f"     Password: {password}")
        print(f"     User ID: {admin_user.id}")
        print(f"\n[!] IMPORTANT: Change the default password in production!")


if __name__ == "__main__":
    asyncio.run(seed_admin_user())
