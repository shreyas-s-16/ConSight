from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pmis/stub", tags=["PMIS Stub (Demo)"])


class PMISPushPayload(BaseModel):
    ActivityId: str
    ActivityName: str
    ProjectId: int
    WBSCode: Optional[str] = None
    Discipline: Optional[str] = None
    ActualStartDate: Optional[str] = None
    ActualFinishDate: Optional[str] = None
    PhysicalPercentComplete: int
    SourceEventId: int
    SourceEventType: str
    ConfidenceScore: float
    SourceSystem: str
    Timestamp: str


class PMISPushResponse(BaseModel):
    success: bool
    message: str
    received_at: str
    activity_id: str
    note: str = "This is a DEMO STUB endpoint. In production, configure PMIS_PUSH_ENDPOINT_URL to point to your real Primavera P6 / MS Project REST API."


@router.post("/push", response_model=PMISPushResponse)
async def stub_pmis_push(payload: PMISPushPayload, request: Request):
    """Local stub PMIS receiver for demo purposes.
    
    This endpoint accepts PMIS push payloads when PMIS_PUSH_ENDPOINT_URL is not configured.
    It logs the received data and returns a realistic acknowledgment.
    
    DO NOT USE IN PRODUCTION - configure PMIS_PUSH_ENDPOINT_URL instead.
    """
    logger.info(f"PMIS STUB received push for activity {payload.ActivityId}: "
                f"start={payload.ActualStartDate}, finish={payload.ActualFinishDate}, "
                f"pct={payload.PhysicalPercentComplete}%, confidence={payload.ConfidenceScore}")

    return PMISPushResponse(
        success=True,
        message="PMIS push received and acknowledged (stub)",
        received_at=datetime.utcnow().isoformat() + "Z",
        activity_id=payload.ActivityId,
    )


@router.get("/push", summary="PMIS stub health check")
async def stub_pmis_health():
    """Health check for the PMIS stub endpoint."""
    return {
        "status": "ok",
        "service": "ConSight PMIS Stub",
        "note": "This is a DEMO STUB endpoint. Configure PMIS_PUSH_ENDPOINT_URL for production use.",
    }