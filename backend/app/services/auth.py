from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.user import create_user, get_user_by_email
from app.schemas.auth import RegisterRequest


class EmailAlreadyRegisteredError(Exception):
    pass


async def register_user(
    session: AsyncSession,
    data: RegisterRequest,
) -> User:
    email = str(data.email).strip().lower()

    existing_user = await get_user_by_email(
        session,
        email,
    )

    if existing_user is not None:
        raise EmailAlreadyRegisteredError

    return await create_user(
        session,
        email=email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
    )


async def authenticate_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
) -> User | None:
    normalized_email = email.strip().lower()

    user = await get_user_by_email(
        session,
        normalized_email,
    )

    if user is None:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    if not user.is_active:
        return None

    return user


def create_user_access_token(user: User) -> str:
    return create_access_token(str(user.id))