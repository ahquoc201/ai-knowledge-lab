from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_user_by_email(
    session: AsyncSession,
    email: str,
) -> User | None:
    result = await session.execute(
        select(User).where(User.email == email)
    )

    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    full_name: str | None,
    hashed_password: str,
) -> User:
    user = User(
        email=email,
        full_name=full_name,
        hashed_password=hashed_password,
    )

    session.add(user)
    await session.commit()
    await session.refresh(user)

    return user

async def get_user_by_id(
    session: AsyncSession,
    user_id: UUID,
) -> User | None:
    return await session.get(User, user_id)