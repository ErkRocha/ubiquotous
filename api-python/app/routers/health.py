from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db import pool

router = APIRouter(tags=["Health"])


@router.get("/health")
def health():
    try:
        with pool.connection(timeout=2) as conn:
            conn.execute("SELECT 1")
    except Exception:
        return JSONResponse({"status": "error", "database": "down"}, status_code=503)
    return JSONResponse({"status": "ok", "database": "up"})
