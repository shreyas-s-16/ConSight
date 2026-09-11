import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.confidence import AuditRecord, DecisionType, ActorType
from app.models.progress import ProgressEvent
from app.models.schedule import ScheduleActivity
from app.models.wbs_node import WBSNode
from app.models.audit_log import AuditLog, AuditAction

logger = logging.getLogger(__name__)


@dataclass
class PMISPushResult:
    success: bool
    target_url: str
    payload_summary: dict
    response_status: Optional[int]
    response_body: Optional[str]
    error_message: Optional[str]
    attempt_count: int
    duration_ms: int


@dataclass
class PMISActualsPayload:
    activity_code: str
    activity_name: str
    actual_start: Optional[date]
    actual_finish: Optional[date]
    percent_complete: int
    project_id: int
    wbs_code: Optional[str]
    discipline: Optional[str]
    event_id: int
    event_type: str
    confidence_score: float


def _build_primavera_payload(payload: PMISActualsPayload) -> dict:
    """Build payload in Primavera P6 EPPM REST API format for activity actuals update.
    
    This is a best-effort mapping based on publicly documented P6 EPPM API patterns.
    The exact schema may vary by P6 version and configuration.
    """
    return {
        "ActivityId": payload.activity_code,
        "ActivityName": payload.activity_name,
        "ProjectId": payload.project_id,
        "WBSCode": payload.wbs_code,
        "Discipline": payload.discipline,
        "ActualStartDate": payload.actual_start.isoformat() if payload.actual_start else None,
        "ActualFinishDate": payload.actual_finish.isoformat() if payload.actual_finish else None,
        "PhysicalPercentComplete": payload.percent_complete,
        "SourceEventId": payload.event_id,
        "SourceEventType": payload.event_type,
        "ConfidenceScore": payload.confidence_score,
        "SourceSystem": "ConSight",
        "Timestamp": datetime.utcnow().isoformat() + "Z",
    }


def _build_payload_summary(payload: PMISActualsPayload) -> dict:
    return {
        "activity_code": payload.activity_code,
        "actual_start": payload.actual_start.isoformat() if payload.actual_start else None,
        "actual_finish": payload.actual_finish.isoformat() if payload.actual_finish else None,
        "percent_complete": payload.percent_complete,
        "project_id": payload.project_id,
        "event_id": payload.event_id,
        "event_type": payload.event_type,
        "confidence_score": payload.confidence_score,
    }


async def _post_with_retry(
    url: str,
    payload: dict,
    api_key: str,
    timeout: int,
    max_retries: int,
    backoff: int,
) -> tuple[Optional[int], Optional[str], Optional[str], int]:
    """POST with retry logic. Returns (status_code, response_body, error_message, attempt_count)."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code < 500:
                    return response.status_code, response.text, None, attempt
                last_error = f"HTTP {response.status_code}: {response.text}"
        except httpx.TimeoutException:
            last_error = f"Timeout after {timeout}s"
        except httpx.RequestError as e:
            last_error = f"Request error: {str(e)}"
        except Exception as e:
            last_error = f"Unexpected error: {str(e)}"

        if attempt < max_retries:
            wait_time = backoff * (2 ** (attempt - 1))
            logger.warning(f"PMIS push attempt {attempt} failed: {last_error}. Retrying in {wait_time}s...")
            time.sleep(wait_time)

    return None, None, last_error, max_retries


def _check_optimistic_concurrency(
    db: Session,
    activity: ScheduleActivity,
    payload: PMISActualsPayload,
) -> tuple[bool, Optional[str]]:
    """Check for optimistic concurrency conflicts with PMIS-side edits.
    
    Returns (has_conflict, conflict_details).
    Conflict exists if PMIS has newer actuals than what we're trying to push.
    Since we don't have direct PMIS read access, we check if the activity
    already has actuals that differ from what we're pushing (indicating
    potential PMIS-side edit).
    """
    if not activity.actual_start and not activity.actual_finish:
        return False, None

    conflict_details = []
    if activity.actual_start and payload.actual_start and activity.actual_start != payload.actual_start:
        conflict_details.append(f"actual_start differs (local: {activity.actual_start}, push: {payload.actual_start})")
    if activity.actual_finish and payload.actual_finish and activity.actual_finish != payload.actual_finish:
        conflict_details.append(f"actual_finish differs (local: {activity.actual_finish}, push: {payload.actual_finish})")

    if conflict_details:
        return True, "; ".join(conflict_details)
    return False, None


async def push_actuals_to_pmis(
    db: Session,
    progress_event_id: int,
    activity_id: int,
    confidence_score: float,
) -> PMISPushResult:
    """Push approved actuals to PMIS (Primavera P6 / MS Project) on auto-commit or planner approval.
    
    This is called from the auto-commit path and from planner approval endpoints.
    If PMIS_PUSH_ENDPOINT_URL is not configured, falls back to local stub endpoint.
    """
    start_time = time.time()
    event = db.query(ProgressEvent).filter(ProgressEvent.id == progress_event_id).first()
    activity = db.query(ScheduleActivity).filter(ScheduleActivity.id == activity_id).first()

    if not event or not activity:
        return PMISPushResult(
            success=False,
            target_url="",
            payload_summary={},
            response_status=None,
            response_body=None,
            error_message=f"Event {progress_event_id} or Activity {activity_id} not found",
            attempt_count=0,
            duration_ms=int((time.time() - start_time) * 1000),
        )

    wbs_node = db.query(WBSNode).filter(
        WBSNode.project_id == event.project_id,
        WBSNode.activity_code == activity.activity_code
    ).first()

    percent_complete = 0
    if event.event_type == "START" and event.event_date:
        percent_complete = 50
    elif event.event_type == "COMPLETE" and event.event_date:
        percent_complete = 100
    elif event.event_type == "PROGRESS":
        percent_complete = 50

    payload = PMISActualsPayload(
        activity_code=activity.activity_code,
        activity_name=activity.activity_name,
        actual_start=activity.actual_start,
        actual_finish=activity.actual_finish,
        percent_complete=percent_complete,
        project_id=event.project_id,
        wbs_code=wbs_node.wbs_code if wbs_node else activity.wbs,
        discipline=activity.discipline,
        event_id=progress_event_id,
        event_type=event.event_type,
        confidence_score=confidence_score,
    )

    primavera_payload = _build_primavera_payload(payload)
    payload_summary = _build_payload_summary(payload)

    target_url = settings.PMIS_PUSH_ENDPOINT_URL
    use_stub = not target_url

    if use_stub:
        target_url = f"http://localhost:8000/pmis/stub/push"
        logger.info(f"PMIS_PUSH_ENDPOINT_URL not configured, using local stub at {target_url}")

    has_conflict, conflict_details = _check_optimistic_concurrency(db, activity, payload)
    if has_conflict:
        error_msg = f"Optimistic concurrency conflict detected: {conflict_details}. Routing to planner review instead of silent overwrite."
        logger.warning(error_msg)
        return PMISPushResult(
            success=False,
            target_url=target_url,
            payload_summary=payload_summary,
            response_status=409,
            response_body=error_msg,
            error_message=error_msg,
            attempt_count=0,
            duration_ms=int((time.time() - start_time) * 1000),
        )

    status_code, response_body, error_msg, attempt_count = await _post_with_retry(
        url=target_url,
        payload=primavera_payload,
        api_key=settings.PMIS_PUSH_API_KEY,
        timeout=settings.PMIS_PUSH_TIMEOUT_SECONDS,
        max_retries=settings.PMIS_PUSH_MAX_RETRIES,
        backoff=settings.PMIS_PUSH_RETRY_BACKOFF_SECONDS,
    )

    duration_ms = int((time.time() - start_time) * 1000)
    success = status_code is not None and 200 <= status_code < 300

    result = PMISPushResult(
        success=success,
        target_url=target_url,
        payload_summary=payload_summary,
        response_status=status_code,
        response_body=response_body,
        error_message=error_msg,
        attempt_count=attempt_count,
        duration_ms=duration_ms,
    )

    _record_pmis_push_audit(db, progress_event_id, activity_id, confidence_score, result, use_stub)

    return result


def _record_pmis_push_audit(
    db: Session,
    progress_event_id: int,
    activity_id: int,
    confidence_score: float,
    result: PMISPushResult,
    is_stub: bool,
) -> None:
    """Record PMIS push attempt in both audit_records and audit_logs tables."""
    event = db.query(ProgressEvent).filter(ProgressEvent.id == progress_event_id).first()
    activity = db.query(ScheduleActivity).filter(ScheduleActivity.id == activity_id).first()

    if not event or not activity:
        return

    push_details = {
        "pmis_push": {
            "target_url": result.target_url,
            "is_stub": is_stub,
            "payload_summary": result.payload_summary,
            "response_status": result.response_status,
            "response_body": result.response_body,
            "error_message": result.error_message,
            "attempt_count": result.attempt_count,
            "duration_ms": result.duration_ms,
            "success": result.success,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    }

    # Get confidence level from event or default to MEDIUM
    from app.models.confidence import ConfidenceLevel
    confidence_level = getattr(event, 'confidence_level', None)
    if confidence_level is None:
        from app.services.confidence_engine import classify_confidence
        confidence_level = classify_confidence(confidence_score)

    audit_record = AuditRecord(
        progress_event_id=progress_event_id,
        proposed_activity_id=activity_id,
        final_activity_id=activity_id,
        confidence_score=confidence_score,
        confidence_level=confidence_level,
        decision=DecisionType.AUTO_MATCH,
        actor_type=ActorType.SYSTEM,
    )
    db.add(audit_record)

    audit_log = AuditLog(
        organization_id=event.organization_id,
        project_id=event.project_id,
        user_id=event.user_id,
        action=AuditAction.UPDATE,
        entity_type="PMIS_PUSH",
        entity_id=activity_id,
        old_values=None,
        new_values=push_details,
    )
    db.add(audit_log)

    db.commit()


def push_actuals_to_pmis_sync(
    db: Session,
    progress_event_id: int,
    activity_id: int,
    confidence_score: float,
) -> PMISPushResult:
    """Synchronous wrapper for push_actuals_to_pmis for use in non-async contexts.
    
    Handles the case where an event loop is already running (e.g., in FastAPI tests)
    by running the coroutine in a separate thread.
    """
    import asyncio
    import concurrent.futures
    
    def run_in_new_loop():
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(
                push_actuals_to_pmis(db, progress_event_id, activity_id, confidence_score)
            )
        finally:
            new_loop.close()
    
    try:
        # Try to get the current loop
        loop = asyncio.get_running_loop()
        # If we get here, a loop is running - use a thread pool to run in a new loop
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_in_new_loop)
            return future.result(timeout=60)
    except RuntimeError:
        # No running loop - safe to create and run our own
        return run_in_new_loop()