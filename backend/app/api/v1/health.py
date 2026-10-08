from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.db.session import get_db

settings = get_settings()
router = APIRouter(tags=["Health & Status"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health and readiness probe for container orchestrators and monitoring agents."""
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
