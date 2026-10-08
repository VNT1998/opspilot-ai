from enum import Enum
from typing import Dict, Set
from app.core.errors import AuthorizationError


class UserRole(str, Enum):
    ADMIN = "admin"
    OPS_MANAGER = "ops_manager"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class Permission(str, Enum):
    # Documents
    DOCUMENT_CREATE = "document:create"
    DOCUMENT_READ = "document:read"
    DOCUMENT_DELETE = "document:delete"
    DOCUMENT_REPROCESS = "document:reprocess"

    # Reviews
    REVIEW_READ = "review:read"
    REVIEW_APPROVE = "review:approve"
    REVIEW_REJECT = "review:reject"
    REVIEW_EDIT = "review:edit"

    # Knowledge / RAG
    KNOWLEDGE_INDEX = "knowledge:index"
    KNOWLEDGE_SEARCH = "knowledge:search"

    # Agents & Tools
    AGENT_RUN = "agent:run"
    AGENT_READ = "agent:read"

    # Audit & Observability
    AUDIT_READ = "audit:read"
    METRICS_READ = "metrics:read"

    # System configuration
    SYSTEM_CONFIG = "system:config"


# Role-to-Permissions Mapping matrix
ROLE_PERMISSIONS: Dict[UserRole, Set[Permission]] = {
    UserRole.ADMIN: {
        Permission.DOCUMENT_CREATE,
        Permission.DOCUMENT_READ,
        Permission.DOCUMENT_DELETE,
        Permission.DOCUMENT_REPROCESS,
        Permission.REVIEW_READ,
        Permission.REVIEW_APPROVE,
        Permission.REVIEW_REJECT,
        Permission.REVIEW_EDIT,
        Permission.KNOWLEDGE_INDEX,
        Permission.KNOWLEDGE_SEARCH,
        Permission.AGENT_RUN,
        Permission.AGENT_READ,
        Permission.AUDIT_READ,
        Permission.METRICS_READ,
        Permission.SYSTEM_CONFIG,
    },
    UserRole.OPS_MANAGER: {
        Permission.DOCUMENT_CREATE,
        Permission.DOCUMENT_READ,
        Permission.DOCUMENT_REPROCESS,
        Permission.REVIEW_READ,
        Permission.REVIEW_APPROVE,
        Permission.REVIEW_REJECT,
        Permission.REVIEW_EDIT,
        Permission.KNOWLEDGE_INDEX,
        Permission.KNOWLEDGE_SEARCH,
        Permission.AGENT_RUN,
        Permission.AGENT_READ,
        Permission.AUDIT_READ,
        Permission.METRICS_READ,
    },
    UserRole.REVIEWER: {
        Permission.DOCUMENT_READ,
        Permission.REVIEW_READ,
        Permission.REVIEW_APPROVE,
        Permission.REVIEW_REJECT,
        Permission.REVIEW_EDIT,
        Permission.KNOWLEDGE_SEARCH,
        Permission.AGENT_READ,
        Permission.AUDIT_READ,
    },
    UserRole.VIEWER: {
        Permission.DOCUMENT_READ,
        Permission.REVIEW_READ,
        Permission.KNOWLEDGE_SEARCH,
        Permission.AGENT_READ,
        Permission.AUDIT_READ,
        Permission.METRICS_READ,
    },
}


def check_permission(user_role: str, required_permission: Permission) -> None:
    """Validates if a given role possesses the required permission, raising AuthorizationError if not."""
    try:
        role_enum = UserRole(user_role.lower())
    except ValueError:
        raise AuthorizationError(f"Unknown user role: '{user_role}'")

    allowed_permissions = ROLE_PERMISSIONS.get(role_enum, set())
    if required_permission not in allowed_permissions:
        raise AuthorizationError(
            f"Role '{user_role}' does not possess required permission '{required_permission.value}'"
        )
