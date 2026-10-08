from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.db.session import get_db

settings = get_settings()
router = APIRouter(tags=["Health & Status"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Lightweight liveness probe for container orchestrators."""
    db_ok = False
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "healthy" if db_ok else "degraded",
        "service": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "database": "connected" if db_ok else "disconnected",
        "environment": settings.ENVIRONMENT,
    }


@router.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """Readiness probe checking database and storage subsystem status."""
    checks = {}
    is_ready = True

    # 1. Database connection check
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"
        is_ready = False

    # 2. Storage provider check
    try:
        from app.services.storage import get_storage_provider

        _ = get_storage_provider()
        checks["storage"] = f"ok ({settings.STORAGE_TYPE})"
    except Exception as e:
        checks["storage"] = f"error: {str(e)}"
        is_ready = False

    return {
        "status": "ready" if is_ready else "not_ready",
        "checks": checks,
        "environment": settings.ENVIRONMENT,
    }
