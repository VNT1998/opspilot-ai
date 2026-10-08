from typing import Annotated
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.core.errors import AuthenticationError, ConflictError
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import TokenResponse, UserCreate, UserLogin, UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin, db: Annotated[AsyncSession, Depends(get_db)]):
    """Authenticates user with email and password, returning JWT access token."""
    stmt = select(User).where(User.email == credentials.email)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise AuthenticationError("Invalid email or password")

    if not user.is_active:
        raise AuthenticationError("User account is inactive")

    token = create_access_token(
        subject=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        extra_claims={"email": user.email, "name": user.full_name},
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    """Registers a new user within a tenant."""
    # Check existing user
    stmt = select(User).where(User.email == payload.email)
    if (await db.execute(stmt)).first():
        raise ConflictError(f"User with email '{payload.email}' already exists.")

    # Find or create tenant
    slug = payload.tenant_slug or "default"
    t_stmt = select(Tenant).where(Tenant.slug == slug)
    tenant = (await db.execute(t_stmt)).scalar_one_or_none()
    if not tenant:
        tenant = Tenant(name=f"{slug.capitalize()} Corp", slug=slug)
        db.add(tenant)
        await db.flush()

    user = User(
        tenant_id=tenant.id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return UserResponse.model_validate(user)


@router.get("/me", response_model=UserResponse)
async def get_profile(current_user: Annotated[User, Depends(get_current_user)]):
    """Returns the authenticated user's profile and active permissions."""
    return UserResponse.model_validate(current_user)
