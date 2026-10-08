from typing import Annotated
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, require_permission
from app.core.config import get_settings
from app.core.errors import AuthenticationError, ConflictError, ForbiddenError, NotFoundError
from app.core.rate_limit import rate_limit
from app.core.rbac import Permission
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import (
    AdminUserCreate,
    DevTokenRequest,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: UserLogin,
    db: Annotated[AsyncSession, Depends(get_db)],
    _rl: bool = Depends(rate_limit(requests_per_minute=20)),
):
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
async def register(
    payload: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _rl: bool = Depends(rate_limit(requests_per_minute=10)),
):
    """
    Public self-registration. Strictly restricted to non-privileged roles (viewer, reviewer).
    Privileged roles (admin, ops_manager) cannot be self-provisioned.
    """
    # Check existing user
    stmt = select(User).where(User.email == payload.email)
    if (await db.execute(stmt)).first():
        raise ConflictError(f"User with email '{payload.email}' already exists.")

    # Find or create tenant
    slug = payload.tenant_slug or "default"
    t_stmt = select(Tenant).where(Tenant.slug == slug)
    tenant = (await db.execute(t_stmt)).scalar_one_or_none()
    if not tenant:
        if settings.ENVIRONMENT == "production":
            raise ForbiddenError(
                f"Tenant '{slug}' does not exist. Self-creation of new tenants is restricted in production."
            )
        tenant = Tenant(name=f"{slug.capitalize()} Corp", slug=slug)
        db.add(tenant)
        await db.flush()

    user = User(
        tenant_id=tenant.id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,  # Restricted by Pydantic to 'viewer' | 'reviewer'
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return UserResponse.model_validate(user)


@router.post("/admin/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    payload: AdminUserCreate,
    current_user: Annotated[User, Depends(require_permission(Permission.SYSTEM_CONFIG))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Admin-only user provisioning endpoint.
    Guarded by SYSTEM_CONFIG permission. Creates a user strictly within the caller's tenant.
    """
    stmt = select(User).where(User.email == payload.email)
    if (await db.execute(stmt)).first():
        raise ConflictError(f"User with email '{payload.email}' already exists.")

    new_user = User(
        tenant_id=current_user.tenant_id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        is_active=True,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return UserResponse.model_validate(new_user)


@router.post("/dev-token", response_model=TokenResponse)
async def dev_token(payload: DevTokenRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    """
    Development-only convenience route for testing role switching without hardcoded frontend passwords.
    Active ONLY when ENVIRONMENT=development.
    """
    if settings.ENVIRONMENT != "development":
        raise ForbiddenError("Development role switching is disabled in production environments.")

    stmt = select(User).where(User.role == payload.role).limit(1)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise NotFoundError("User", f"role:{payload.role}")

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


@router.get("/me", response_model=UserResponse)
async def get_profile(current_user: Annotated[User, Depends(get_current_user)]):
    """Returns the authenticated user's profile and active permissions."""
    return UserResponse.model_validate(current_user)
