from typing import Optional
from app.core.errors import AuthorizationError, ValidationError
from app.core.rbac import Permission, check_permission
from app.services.tools.definitions import ToolCallContext, ToolRiskLevel


class ToolAuthorizer:
    """
    Centralized service-boundary tool authorization.
    Validates caller identity, tenant context, RBAC permission,
    cross-tenant resource ownership, risk level, and required confirmations.
    """

    @staticmethod
    def authorize(
        ctx: ToolCallContext,
        required_permission: Permission,
        resource_tenant_id: Optional[str] = None,
        risk_level: ToolRiskLevel = ToolRiskLevel.LOW,
        requires_confirmation: bool = False,
        confirmed: bool = False,
    ) -> None:
        # 1. Caller identity validation
        if not ctx.user_id or not ctx.user_id.strip():
            raise AuthorizationError("Missing required caller user_id in tool context.")

        # 2. Tenant context validation
        if not ctx.tenant_id or not ctx.tenant_id.strip():
            raise AuthorizationError("Missing required tenant_id in tool context.")

        # 3. Cross-tenant resource boundary validation
        if resource_tenant_id and resource_tenant_id != ctx.tenant_id:
            raise AuthorizationError(
                f"Tenant isolation breach: Caller tenant '{ctx.tenant_id}' cannot access resource owned by tenant '{resource_tenant_id}'."
            )

        # 4. RBAC role permission validation
        if not ctx.user_role:
            raise AuthorizationError("Missing user_role in tool context.")
        check_permission(ctx.user_role, required_permission)

        # 5. Elevated permission check for HIGH/CRITICAL risk operations
        if risk_level in (ToolRiskLevel.HIGH, ToolRiskLevel.CRITICAL):
            if ctx.user_role not in ("admin", "ops_manager"):
                raise AuthorizationError(
                    f"Tool operation at risk level {risk_level.value} requires ops_manager or admin privileges; caller role is '{ctx.user_role}'."
                )

        # 6. Explicit confirmation validation
        if requires_confirmation and not confirmed:
            raise ValidationError("Action requires explicit confirmation before executing side effect.")
