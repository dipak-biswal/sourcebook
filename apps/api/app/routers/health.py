from fastapi import APIRouter
from sqlalchemy import text

from app.db import engine

router = APIRouter(tags=["health"])


@router.get("/health")
def helath():
    return {"status": "ok", "service": "sourcebook"}


@router.get("/health/db")
def health_db():
    """Check DB connectivity + that core tables exist (for deploy debugging)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            rows = conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' ORDER BY tablename"
                )
            ).fetchall()
        tables = [r[0] for r in rows]
        return {
            "status": "ok",
            "tables": tables,
            "has_users": "users" in tables,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
