# backend/routers/finpulse.py
"""FinPulse finance news cards API."""

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from services.finpulse_service import build_finpulse_payload

router = APIRouter()


@router.get("/finpulse")
def get_finpulse(force_refresh: bool = Query(False, description="Bypass short TTL cache")):
    try:
        data = build_finpulse_payload(force_refresh=force_refresh)
        return {"success": True, "data": data, "error": None}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "data": None, "error": str(e)},
        )
