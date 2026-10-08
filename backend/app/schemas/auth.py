from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, EmailStr


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    """Public registration schema strictly restricted to non-privileged roles."""

    email: EmailStr
    password: str
    full_name: str
    role: Literal["viewer", "reviewer"] = "reviewer"
    tenant_slug: Optional[str] = "default"


class AdminUserCreate(BaseModel):
    """Admin-only user provisioning schema supporting all tenant roles."""

    email: EmailStr
    password: str
    full_name: str
    role: Literal["admin", "ops_manager", "reviewer", "viewer"] = "reviewer"


class DevTokenRequest(BaseModel):
    """Development-only role switching request."""

    role: Literal["admin", "ops_manager", "reviewer", "viewer"]


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TenantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    plan: str
