from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_session
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth import (
    EmailAlreadyRegisteredError,
    authenticate_user,
    create_user_access_token,
    register_user,
)
from app.services.rate_limiter import extract_client_ip, get_rate_limiter

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    data: RegisterRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserResponse:
    settings = get_settings()
    rate_limiter = get_rate_limiter()
    ip = extract_client_ip(request)
    rate_limiter.enforce(
        identifier=ip,
        limit=settings.rate_limit_auth_per_minute,
        window_seconds=60,
        rule_name="auth_register",
    )

    try:
        user = await register_user(session, data)
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        ) from exc

    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
)
async def login(
    data: LoginRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TokenResponse:
    settings = get_settings()
    rate_limiter = get_rate_limiter()
    ip = extract_client_ip(request)
    rate_limiter.enforce(
        identifier=ip,
        limit=settings.rate_limit_auth_per_minute,
        window_seconds=60,
        rule_name="auth_login",
    )

    user = await authenticate_user(
        session,
        email=str(data.email),
        password=data.password,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return TokenResponse(
        access_token=create_user_access_token(user),
    )

@router.get(
    "/me",
    response_model=UserResponse,
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    return UserResponse.model_validate(current_user)