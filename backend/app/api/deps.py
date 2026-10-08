from typing import Annotated, Callable
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.errors import AuthenticationError, AuthorizationError
from app.core.rbac import Permission, check_permission
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Authenticates the user from the Bearer JWT token."""
    if not credentials:
        raise AuthenticationError("Authorization header is missing")

    token = credentials.credentials
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")

    if not user_id or not tenant_id:
        raise AuthenticationError("Malformed token payload")

    stmt = select(User).where(User.id == user_id, User.tenant_id == tenant_id, User.is_active == True)  # noqa: E712
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise AuthenticationError("User not found or deactivated")

    return user


def require_permission(perm: Permission) -> Callable:
    """FastAPI dependency factory enforcing RBAC permission."""
    async def permission_dependency(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        check_permission(current_user.role, perm)
        return current_user

    return permission_dependency


async def get_request_id(x_request_id: Annotated[str | None, Header()] = None) -> str:
    """Extracts or returns correlation request ID."""
    return x_request_id or "req_autogen"
