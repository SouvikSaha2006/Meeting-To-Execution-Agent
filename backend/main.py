"""
main.py — FastAPI application entry point for Meeting-to-Execution Agent.

Endpoints
---------
GET  /api/health
POST /api/meetings/ingest
POST /api/demo/seed
POST /api/demo/load-meeting-1
POST /api/demo/load-meeting-2
GET  /api/staging
PATCH /api/staging/{item_id}/resolve
POST /api/staging/{item_id}/approve
POST /api/staging/approve-all-ready
POST /api/staging/{item_id}/reject
GET  /api/tasks
PATCH /api/tasks/{task_id}/status
GET  /api/decisions
GET  /api/digest/weekly
"""
from __future__ import annotations

import datetime
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent_pipeline import run_pipeline
from backend.database import get_db, init_db
from backend.integrations import dispatch_execution, github_status, webhook_status
from backend.models import Decision, ExecutionTask, Meeting, StagingItem
from backend.schemas import (
    AgentTraceStep,
    ApproveResponse,
    BulkApproveResponse,
    DecisionResponse,
    ExecutionTaskResponse,
    HealthResponse,
    IngestResponse,
    LLMActionItem,
    LLMDecision,
    MeetingIngestRequest,
    MeetingResponse,
    RejectItemRequest,
    ResolveItemRequest,
    StagingItemResponse,
    UpdateTaskStatusRequest,
    WeeklyDigestOwner,
    WeeklyDigestResponse,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

DEMO_MODE: bool = os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "yes")
APP_VERSION = "1.0.0"


# ═══════════════════════════════════════════════════════════════════════════════
# App Lifespan
# ═══════════════════════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Meeting-to-Execution Agent starting up...")
    await init_db()
    logger.info("✅ Database initialised")
    if DEMO_MODE:
        logger.warning("⚠️  DEMO_MODE=true — Gemini API calls will use mock responses")
    yield
    logger.info("🛑 Meeting-to-Execution Agent shutting down")


# ═══════════════════════════════════════════════════════════════════════════════
# FastAPI App
# ═══════════════════════════════════════════════════════════════════════════════
app = FastAPI(
    title="Meeting-to-Execution Agent API",
    description=(
        "Stateful multi-agent system that transforms raw meeting transcripts into "
        "structured decisions, action items, and tracked execution tasks — with "
        "cross-meeting conflict detection, human-in-the-loop approval, and GitHub/Webhook dispatch."
    ),
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: ORM → Response serialisers
# ═══════════════════════════════════════════════════════════════════════════════
def _meeting_to_resp(m: Meeting) -> MeetingResponse:
    return MeetingResponse(
        id=m.id,
        title=m.title,
        meeting_date=m.meeting_date,
        created_at=m.created_at,
        agent_trace_json=m.agent_trace_json,
    )


def _staging_to_resp(s: StagingItem) -> StagingItemResponse:
    return StagingItemResponse(
        id=s.id,
        meeting_id=s.meeting_id,
        item_type=s.item_type,
        payload_json=s.payload_json,
        state=s.state,
        conflict_meta_json=s.conflict_meta_json,
        missing_fields_json=s.missing_fields_json,
        clarification_prompt=s.clarification_prompt,
        verbatim_quote=s.verbatim_quote,
        rejection_reason=s.rejection_reason,
        created_at=s.created_at,
    )


def _task_to_resp(t: ExecutionTask) -> ExecutionTaskResponse:
    return ExecutionTaskResponse(
        id=t.id,
        staging_item_id=t.staging_item_id,
        meeting_id=t.meeting_id,
        title=t.title,
        description=t.description,
        owner=t.owner,
        deadline_iso=t.deadline_iso,
        priority=t.priority,
        status=t.status,
        depends_on_id=t.depends_on_id,
        external_execution_receipt_json=t.external_execution_receipt_json,
        approved_at=t.approved_at,
    )


def _decision_to_resp(d: Decision, meeting: Optional[Meeting] = None) -> DecisionResponse:
    return DecisionResponse(
        id=d.id,
        meeting_id=d.meeting_id,
        topic_key=d.topic_key,
        statement=d.statement,
        decided_by=d.decided_by,
        verbatim_quote=d.verbatim_quote,
        confidence=d.confidence,
        status=d.status,
        superseded_by_id=d.superseded_by_id,
        created_at=d.created_at,
        meeting_title=meeting.title if meeting else None,
        meeting_date=meeting.meeting_date if meeting else None,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Core Approval Logic (shared by single + bulk approve)
# ═══════════════════════════════════════════════════════════════════════════════
async def _approve_single_item(
    item: StagingItem,
    db: AsyncSession,
    conflict_resolution: Optional[str] = None,
) -> ApproveResponse:
    """
    Promote a staging item to either an ACTIVE Decision or an ExecutionTask.
    Fires external execution dispatch for ACTION_ITEMs.
    """
    if item.state == "REJECTED":
        raise HTTPException(status_code=409, detail="Item is already REJECTED")
    if item.state == "APPROVED":
        raise HTTPException(status_code=409, detail="Item is already APPROVED")

    payload: dict = json.loads(item.payload_json)

    if item.item_type == "DECISION":
        return await _approve_decision(item, payload, db, conflict_resolution)
    elif item.item_type == "ACTION_ITEM":
        return await _approve_action_item(item, payload, db)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown item_type: {item.item_type}")


async def _approve_decision(
    item: StagingItem,
    payload: dict,
    db: AsyncSession,
    conflict_resolution: Optional[str],
) -> ApproveResponse:
    """Create an ACTIVE Decision, optionally superseding an old conflicting one."""
    new_decision = Decision(
        meeting_id=item.meeting_id,
        topic_key=payload.get("topic_key", ""),
        statement=payload.get("statement", ""),
        decided_by=payload.get("decided_by"),
        verbatim_quote=payload.get("verbatim_quote"),
        confidence=payload.get("confidence", "MEDIUM"),
        status="ACTIVE",
    )
    db.add(new_decision)
    await db.flush()

    # Handle conflict resolution — supersede old decision if requested
    if conflict_resolution == "SUPERSEDE_OLD" and item.conflict_meta_json:
        conflict_meta = json.loads(item.conflict_meta_json)
        old_decision_id = conflict_meta.get("conflicting_decision_id")
        if old_decision_id:
            old_decision = await db.get(Decision, old_decision_id)
            if old_decision:
                old_decision.status = "SUPERSEDED"
                old_decision.superseded_by_id = new_decision.id

    item.state = "APPROVED"

    # Eagerly load meeting for response
    meeting = await db.get(Meeting, item.meeting_id)
    return ApproveResponse(
        staging_item=_staging_to_resp(item),
        decision=_decision_to_resp(new_decision, meeting),
    )


async def _approve_action_item(
    item: StagingItem,
    payload: dict,
    db: AsyncSession,
) -> ApproveResponse:
    """Create an ExecutionTask and fire external dispatch."""
    # Resolve dependency by task title
    depends_on_id: Optional[int] = None
    dep_title = payload.get("depends_on_task_title")
    if dep_title:
        dep_stmt = select(ExecutionTask).where(ExecutionTask.title == dep_title)
        dep_task = (await db.execute(dep_stmt)).scalars().first()
        if dep_task:
            depends_on_id = dep_task.id

    task = ExecutionTask(
        staging_item_id=item.id,
        meeting_id=item.meeting_id,
        title=payload.get("title", "Untitled Task"),
        description=payload.get("description"),
        owner=payload.get("owner"),
        deadline_iso=payload.get("deadline_iso"),
        priority=payload.get("priority", "MEDIUM"),
        status="TODO",
        depends_on_id=depends_on_id,
        approved_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(task)
    await db.flush()  # Get task.id for dispatch

    # Fire external execution dispatch
    dispatch_payload = {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "owner": task.owner,
        "deadline_iso": task.deadline_iso,
        "priority": task.priority,
        "verbatim_quote": item.verbatim_quote,
    }
    receipt = await dispatch_execution(dispatch_payload)
    task.external_execution_receipt_json = json.dumps(receipt)
    item.state = "APPROVED"

    return ApproveResponse(
        staging_item=_staging_to_resp(item),
        execution_task=_task_to_resp(task),
        execution_receipt=receipt,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Demo Seed Helpers
# ═══════════════════════════════════════════════════════════════════════════════
async def _reset_database(db: AsyncSession) -> None:
    """Hard-delete all data in dependency order. Uses flush so caller's session commits."""
    from sqlalchemy import text
    for table in ["execution_tasks", "staging_items", "decisions", "meetings"]:
        await db.execute(text(f"DELETE FROM {table}"))
    await db.flush()


async def _load_meeting_with_precomputed_data(
    title: str,
    meeting_date: str,
    raw_transcript: str,
    decisions_data: list[dict],
    action_items_data: list[dict],
    db: AsyncSession,
) -> tuple[Meeting, list[StagingItem]]:
    """
    Inject pre-computed seed data directly into staging (bypasses LLM).
    Used for demo endpoints to guarantee consistent, impressive demo scenarios.
    """
    from backend.agent_pipeline import (
        detect_conflicts_and_duplicates,
        parse_transcript,
        stage_for_approval,
    )
    from backend.schemas import LLMActionItem, LLMDecision, LLMExtractionResult

    meeting = Meeting(
        title=title,
        meeting_date=meeting_date,
        raw_transcript=raw_transcript,
        agent_trace_json=json.dumps([
            {"stage": 1, "name": "parse_transcript", "status": "success",
             "output_summary": f"Pre-seeded transcript loaded for demo — {title}",
             "duration_ms": 12, "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()},
            {"stage": 2, "name": "extract_commitments", "status": "success",
             "output_summary": f"Injected {len(decisions_data)} decisions, {len(action_items_data)} action items (DEMO SEED)",
             "duration_ms": 1, "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()},
            {"stage": 3, "name": "detect_conflicts_and_duplicates", "status": "success",
             "output_summary": "Cross-meeting conflict detection running...",
             "duration_ms": 5, "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()},
            {"stage": 4, "name": "stage_for_approval", "status": "success",
             "output_summary": f"Staged {len(decisions_data) + len(action_items_data)} items",
             "duration_ms": 8, "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()},
        ]),
    )
    db.add(meeting)
    await db.flush()

    # Build Pydantic objects from raw dicts
    decisions = [LLMDecision(**d) for d in decisions_data]
    action_items = [LLMActionItem(**a) for a in action_items_data]
    extraction = LLMExtractionResult(decisions=decisions, action_items=action_items)

    # Run actual conflict detection (uses DB state)
    decisions_with_meta, actions_with_meta = await detect_conflicts_and_duplicates(
        extraction, db, meeting.id
    )

    # Update trace with real conflict results
    conflicts_found = sum(1 for _, m in decisions_with_meta + actions_with_meta if m)
    trace_data = json.loads(meeting.agent_trace_json)
    trace_data[2]["output_summary"] = (
        f"Detected {conflicts_found} conflict(s)/duplicate(s) across all items"
    )
    meeting.agent_trace_json = json.dumps(trace_data)

    staged_items = await stage_for_approval(
        decisions_with_meta, actions_with_meta, meeting.id, db
    )

    return meeting, staged_items


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/api/health", response_model=HealthResponse, tags=["System"])
async def health_check(db: AsyncSession = Depends(get_db)):
    """System telemetry: DB status, Gemini API readiness, webhook status."""
    # Test DB connectivity
    db_status = "ok"
    try:
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {e}"

    # Test Gemini API key presence
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if DEMO_MODE:
        gemini_status = "demo_mode (bypassed)"
    elif gemini_key:
        gemini_status = "configured"
    else:
        gemini_status = "not_configured (set GEMINI_API_KEY)"

    return HealthResponse(
        status="healthy" if db_status == "ok" else "degraded",
        database=db_status,
        gemini_api=gemini_status,
        demo_mode=DEMO_MODE,
        github_integration=github_status(),
        webhook_integration=webhook_status(),
        version=APP_VERSION,
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )


# ── Meeting Ingest ────────────────────────────────────────────────────────────
@app.post("/api/meetings/ingest", response_model=IngestResponse, tags=["Meetings"])
async def ingest_meeting(
    request: MeetingIngestRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Run the 4-stage Gemini agentic pipeline on a raw meeting transcript.
    Returns the meeting record, all staged items, and the full agent trace.
    """
    try:
        meeting, staged_items, trace = await run_pipeline(
            title=request.title,
            meeting_date=request.meeting_date,
            raw_transcript=request.raw_transcript,
            db=db,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.exception("Pipeline failed unexpectedly")
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}")

    # Build summary
    state_counts: dict[str, int] = {}
    for item in staged_items:
        state_counts[item.state] = state_counts.get(item.state, 0) + 1

    return IngestResponse(
        meeting=_meeting_to_resp(meeting),
        staging_items=[_staging_to_resp(s) for s in staged_items],
        agent_trace=trace,
        summary={
            "total_staged": len(staged_items),
            "decisions": sum(1 for s in staged_items if s.item_type == "DECISION"),
            "action_items": sum(1 for s in staged_items if s.item_type == "ACTION_ITEM"),
            "state_breakdown": state_counts,
        },
    )


# ── Demo: Seed Full Demo ──────────────────────────────────────────────────────
@app.post("/api/demo/seed", tags=["Demo"])
async def demo_seed(db: AsyncSession = Depends(get_db)):
    """
    Reset the database and load both demo meetings.
    Use this for instant judge-ready demonstrations.
    """
    from backend.seed_data import (
        MEETING_1_ACTION_ITEMS,
        MEETING_1_DATE,
        MEETING_1_DECISIONS,
        MEETING_1_TITLE,
        MEETING_1_TRANSCRIPT,
        MEETING_2_ACTION_ITEMS,
        MEETING_2_DATE,
        MEETING_2_DECISIONS,
        MEETING_2_TITLE,
        MEETING_2_TRANSCRIPT,
    )

    await _reset_database(db)

    # Load Meeting 1
    m1, s1 = await _load_meeting_with_precomputed_data(
        MEETING_1_TITLE, MEETING_1_DATE, MEETING_1_TRANSCRIPT,
        MEETING_1_DECISIONS, MEETING_1_ACTION_ITEMS, db,
    )

    # Auto-approve the READY_TO_APPROVE items from Meeting 1 so Meeting 2 triggers conflicts
    for item in s1:
        if item.state == "READY_TO_APPROVE":
            try:
                await _approve_single_item(item, db, conflict_resolution=None)
            except Exception:
                pass  # Non-critical for demo setup

    # Load Meeting 2 (conflicts will fire against Meeting 1's approved decisions)
    m2, s2 = await _load_meeting_with_precomputed_data(
        MEETING_2_TITLE, MEETING_2_DATE, MEETING_2_TRANSCRIPT,
        MEETING_2_DECISIONS, MEETING_2_ACTION_ITEMS, db,
    )

    return {
        "message": "Demo data seeded successfully",
        "meeting_1": {
            "id": m1.id,
            "title": m1.title,
            "staged_items": len(s1),
            "auto_approved": sum(1 for s in s1 if s.state == "APPROVED"),
        },
        "meeting_2": {
            "id": m2.id,
            "title": m2.title,
            "staged_items": len(s2),
            "conflicts_detected": sum(1 for s in s2 if s.state == "CONFLICT_DETECTED"),
            "needs_clarification": sum(1 for s in s2 if s.state == "NEEDS_CLARIFICATION"),
        },
        "instructions": {
            "1": "GET /api/staging?meeting_id=<m2.id> to see conflicts and clarifications",
            "2": "PATCH /api/staging/{id}/resolve to resolve conflicts or fill in missing data",
            "3": "POST /api/staging/{id}/approve to approve individual items",
            "4": "POST /api/staging/approve-all-ready to bulk approve all ready items",
            "5": "GET /api/decisions to see the Decision Memory Log with superseded decisions",
            "6": "GET /api/digest/weekly for the full weekly execution digest",
        },
    }


@app.post("/api/demo/load-meeting-1", tags=["Demo"])
async def demo_load_meeting_1(db: AsyncSession = Depends(get_db)):
    """
    Load only Meeting 1 (Sprint 14 Kickoff).
    Approve ready items via the staging API, then call load-meeting-2 to see conflicts.
    """
    from backend.seed_data import (
        MEETING_1_ACTION_ITEMS,
        MEETING_1_DATE,
        MEETING_1_DECISIONS,
        MEETING_1_TITLE,
        MEETING_1_TRANSCRIPT,
    )

    meeting, staged_items = await _load_meeting_with_precomputed_data(
        MEETING_1_TITLE, MEETING_1_DATE, MEETING_1_TRANSCRIPT,
        MEETING_1_DECISIONS, MEETING_1_ACTION_ITEMS, db,
    )

    return {
        "message": "Meeting 1 loaded",
        "meeting_id": meeting.id,
        "title": meeting.title,
        "staged_items": len(staged_items),
        "breakdown": {
            s.state: sum(1 for x in staged_items if x.state == s.state)
            for s in staged_items
        },
        "next_steps": [
            f"Review staged items: GET /api/staging?meeting_id={meeting.id}",
            "Approve ready items to populate Decision Memory",
            "Then call POST /api/demo/load-meeting-2 to trigger conflicts",
        ],
    }


@app.post("/api/demo/load-meeting-2", tags=["Demo"])
async def demo_load_meeting_2(db: AsyncSession = Depends(get_db)):
    """
    Load Meeting 2 (Architecture & Scope Sync).
    Requires Meeting 1 items to be approved first so conflicts can be detected.
    """
    from backend.seed_data import (
        MEETING_2_ACTION_ITEMS,
        MEETING_2_DATE,
        MEETING_2_DECISIONS,
        MEETING_2_TITLE,
        MEETING_2_TRANSCRIPT,
    )

    meeting, staged_items = await _load_meeting_with_precomputed_data(
        MEETING_2_TITLE, MEETING_2_DATE, MEETING_2_TRANSCRIPT,
        MEETING_2_DECISIONS, MEETING_2_ACTION_ITEMS, db,
    )

    state_counts: dict[str, int] = {}
    for s in staged_items:
        state_counts[s.state] = state_counts.get(s.state, 0) + 1

    return {
        "message": "Meeting 2 loaded — check for conflicts!",
        "meeting_id": meeting.id,
        "title": meeting.title,
        "staged_items": len(staged_items),
        "state_breakdown": state_counts,
        "next_steps": [
            f"GET /api/staging?meeting_id={meeting.id}&state=CONFLICT_DETECTED",
            "PATCH /api/staging/{id}/resolve with conflict_resolution=SUPERSEDE_OLD or KEEP_ORIGINAL",
            "POST /api/staging/{id}/approve after resolving",
        ],
    }


# ── Staging Queue ─────────────────────────────────────────────────────────────
@app.get("/api/staging", response_model=List[StagingItemResponse], tags=["Staging"])
async def list_staging_items(
    meeting_id: Optional[int] = Query(default=None),
    state: Optional[str] = Query(default=None),
    item_type: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """List staged items with optional filters."""
    stmt = select(StagingItem)
    if meeting_id is not None:
        stmt = stmt.where(StagingItem.meeting_id == meeting_id)
    if state:
        stmt = stmt.where(StagingItem.state == state.upper())
    if item_type:
        stmt = stmt.where(StagingItem.item_type == item_type.upper())
    stmt = stmt.order_by(StagingItem.created_at.desc())
    items = (await db.execute(stmt)).scalars().all()
    return [_staging_to_resp(s) for s in items]


@app.patch("/api/staging/{item_id}/resolve", response_model=StagingItemResponse, tags=["Staging"])
async def resolve_staging_item(
    item_id: int,
    request: ResolveItemRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Human edit: update missing fields or set conflict resolution strategy.
    Transitions item state to READY_TO_APPROVE.
    """
    item = await db.get(StagingItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Staging item not found")
    if item.state == "APPROVED":
        raise HTTPException(status_code=409, detail="Cannot resolve an already-approved item")
    if item.state == "REJECTED":
        raise HTTPException(status_code=409, detail="Cannot resolve a rejected item")

    # Patch the payload
    payload = json.loads(item.payload_json)

    if request.owner is not None:
        payload["owner"] = request.owner
    if request.deadline_iso is not None:
        payload["deadline_iso"] = request.deadline_iso
    if request.title is not None:
        payload["title"] = request.title
    if request.conflict_resolution is not None:
        # Store resolution strategy in conflict_meta
        conflict_meta = json.loads(item.conflict_meta_json) if item.conflict_meta_json else {}
        conflict_meta["resolution_choice"] = request.conflict_resolution
        item.conflict_meta_json = json.dumps(conflict_meta)

    # Clear missing fields if they've been resolved
    if request.owner is not None or request.deadline_iso is not None:
        missing = json.loads(item.missing_fields_json) if item.missing_fields_json else []
        if request.owner is not None and "owner" in missing:
            missing.remove("owner")
        if request.deadline_iso is not None and "deadline" in missing:
            missing.remove("deadline")
        item.missing_fields_json = json.dumps(missing) if missing else None
        if not missing:
            payload["status"] = "READY_TO_APPROVE"
            payload["missing_fields"] = None
            item.clarification_prompt = None

    item.payload_json = json.dumps(payload)
    item.state = "READY_TO_APPROVE"

    return _staging_to_resp(item)


@app.post("/api/staging/{item_id}/approve", response_model=ApproveResponse, tags=["Staging"])
async def approve_staging_item(
    item_id: int,
    conflict_resolution: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Approve a staged item. Moves it to execution_tasks (action items) or
    decisions (decisions). Fires external webhook/GitHub dispatch.
    """
    item = await db.get(StagingItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Staging item not found")

    return await _approve_single_item(item, db, conflict_resolution=conflict_resolution)


@app.post("/api/staging/approve-all-ready", response_model=BulkApproveResponse, tags=["Staging"])
async def bulk_approve_ready(
    meeting_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Atomically approve all READY_TO_APPROVE items (optionally filtered by meeting).
    Items in CONFLICT_DETECTED or NEEDS_CLARIFICATION states are skipped.
    """
    stmt = select(StagingItem).where(StagingItem.state == "READY_TO_APPROVE")
    if meeting_id is not None:
        stmt = stmt.where(StagingItem.meeting_id == meeting_id)
    stmt = stmt.order_by(StagingItem.item_type)  # DECISION before ACTION_ITEM

    items = (await db.execute(stmt)).scalars().all()

    results: list[ApproveResponse] = []
    approved_count = 0
    skipped_count = 0

    for item in items:
        try:
            result = await _approve_single_item(item, db)
            results.append(result)
            approved_count += 1
        except HTTPException:
            skipped_count += 1
        except Exception as exc:
            logger.error("Failed to approve item %d: %s", item.id, exc)
            skipped_count += 1

    return BulkApproveResponse(
        approved_count=approved_count,
        skipped_count=skipped_count,
        results=results,
    )


@app.post("/api/staging/{item_id}/reject", response_model=StagingItemResponse, tags=["Staging"])
async def reject_staging_item(
    item_id: int,
    request: RejectItemRequest,
    db: AsyncSession = Depends(get_db),
):
    """Mark a staging item as REJECTED with an optional reason."""
    item = await db.get(StagingItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Staging item not found")
    if item.state == "APPROVED":
        raise HTTPException(status_code=409, detail="Cannot reject an already-approved item")

    item.state = "REJECTED"
    item.rejection_reason = request.reason

    return _staging_to_resp(item)


# ── Execution Tasks ───────────────────────────────────────────────────────────
@app.get("/api/tasks", response_model=List[ExecutionTaskResponse], tags=["Tasks"])
async def list_tasks(
    owner: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    meeting_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """List all execution tasks with optional filters."""
    stmt = select(ExecutionTask)
    if owner:
        stmt = stmt.where(ExecutionTask.owner.ilike(f"%{owner}%"))
    if status:
        stmt = stmt.where(ExecutionTask.status == status.upper())
    if priority:
        stmt = stmt.where(ExecutionTask.priority == priority.upper())
    if meeting_id is not None:
        stmt = stmt.where(ExecutionTask.meeting_id == meeting_id)
    stmt = stmt.order_by(ExecutionTask.approved_at.desc())
    tasks = (await db.execute(stmt)).scalars().all()
    return [_task_to_resp(t) for t in tasks]


@app.patch("/api/tasks/{task_id}/status", response_model=ExecutionTaskResponse, tags=["Tasks"])
async def update_task_status(
    task_id: int,
    request: UpdateTaskStatusRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update the Kanban status of an execution task (TODO → IN_PROGRESS → DONE)."""
    task = await db.get(ExecutionTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Enforce progression order
    allowed_transitions = {
        "TODO": ["IN_PROGRESS"],
        "IN_PROGRESS": ["DONE", "TODO"],
        "DONE": ["IN_PROGRESS"],
    }
    if request.status not in allowed_transitions.get(task.status, []):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status transition: {task.status} → {request.status}. "
                   f"Allowed: {allowed_transitions.get(task.status, [])}",
        )

    task.status = request.status
    return _task_to_resp(task)


# ── Decision Memory Log ───────────────────────────────────────────────────────
@app.get("/api/decisions", response_model=List[DecisionResponse], tags=["Decisions"])
async def list_decisions(
    status: Optional[str] = Query(default=None, description="ACTIVE | SUPERSEDED"),
    topic_key: Optional[str] = Query(default=None),
    meeting_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Full chronological Decision Memory Log.
    Shows both ACTIVE and SUPERSEDED decisions with linkage.
    """
    stmt = (
        select(Decision, Meeting)
        .join(Meeting, Decision.meeting_id == Meeting.id)
    )
    if status:
        stmt = stmt.where(Decision.status == status.upper())
    if topic_key:
        stmt = stmt.where(Decision.topic_key.ilike(f"%{topic_key}%"))
    if meeting_id is not None:
        stmt = stmt.where(Decision.meeting_id == meeting_id)
    stmt = stmt.order_by(Decision.created_at.asc())

    rows = (await db.execute(stmt)).all()
    return [_decision_to_resp(row[0], row[1]) for row in rows]


# ── Weekly Digest ─────────────────────────────────────────────────────────────
@app.get("/api/digest/weekly", response_model=WeeklyDigestResponse, tags=["Digest"])
async def weekly_digest(db: AsyncSession = Depends(get_db)):
    """
    Generate a structured per-owner Weekly Execution Digest.
    Returns both structured JSON and ready-to-send Markdown.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    week_start = now - datetime.timedelta(days=7)
    # SQLite returns naive datetimes — work in UTC naive for all comparisons
    now_naive = now.replace(tzinfo=None)
    week_start_naive = week_start.replace(tzinfo=None)

    # Load all tasks
    task_stmt = select(ExecutionTask, Meeting).join(Meeting, ExecutionTask.meeting_id == Meeting.id)
    task_rows = (await db.execute(task_stmt)).all()
    all_tasks: list[tuple[ExecutionTask, Meeting]] = [(r[0], r[1]) for r in task_rows]

    # Load all ACTIVE decisions
    decision_stmt = (
        select(Decision, Meeting)
        .join(Meeting, Decision.meeting_id == Meeting.id)
        .where(Decision.status == "ACTIVE")
    )
    decision_rows = (await db.execute(decision_stmt)).all()

    # Load resolved conflicts (SUPERSEDED decisions resolved this week)
    conflict_stmt = (
        select(Decision, Meeting)
        .join(Meeting, Decision.meeting_id == Meeting.id)
        .where(
            Decision.status == "SUPERSEDED",
            Decision.created_at >= week_start_naive,
        )
    )
    conflict_rows = (await db.execute(conflict_stmt)).all()
    resolved_conflicts = [
        {
            "topic_key": r[0].topic_key,
            "old_statement": r[0].statement,
            "meeting": r[1].title,
        }
        for r in conflict_rows
    ]

    # Group tasks by owner
    owner_map: dict[str, dict[str, list]] = {}

    for task, meeting in all_tasks:
        owner = task.owner or "Unassigned"
        if owner not in owner_map:
            owner_map[owner] = {
                "completed": [],
                "newly_assigned": [],
                "upcoming": [],
            }

        if task.status == "DONE":
            owner_map[owner]["completed"].append({
                "id": task.id,
                "title": task.title,
                "meeting": meeting.title,
                "deadline_iso": task.deadline_iso,
            })
        elif task.approved_at and (
            (task.approved_at.replace(tzinfo=None) if task.approved_at.tzinfo else task.approved_at) >= week_start_naive
        ):
            owner_map[owner]["newly_assigned"].append({
                "id": task.id,
                "title": task.title,
                "meeting": meeting.title,
                "deadline_iso": task.deadline_iso,
                "priority": task.priority,
                "status": task.status,
            })

        # Upcoming deadlines (next 7 days)
        if task.deadline_iso and task.status != "DONE":
            try:
                dl = datetime.date.fromisoformat(task.deadline_iso)
                days_until = (dl - now.date()).days
                if 0 <= days_until <= 7:
                    owner_map[owner]["upcoming"].append({
                        "id": task.id,
                        "title": task.title,
                        "deadline_iso": task.deadline_iso,
                        "days_until_deadline": days_until,
                        "priority": task.priority,
                    })
            except ValueError:
                pass

    # Build structured owner digests
    owners: list[WeeklyDigestOwner] = [
        WeeklyDigestOwner(
            owner=owner,
            completed_tasks=data["completed"],
            newly_assigned=data["newly_assigned"],
            upcoming_deadlines=sorted(
                data["upcoming"], key=lambda x: x["deadline_iso"]
            ),
            resolved_conflicts=resolved_conflicts if owner != "Unassigned" else [],
        )
        for owner, data in owner_map.items()
    ]

    # Build Markdown report
    md_lines = [
        f"# 📋 Weekly Execution Digest",
        f"**Period:** {week_start.strftime('%B %d')} – {now.strftime('%B %d, %Y')}",
        f"**Generated:** {now.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

    if resolved_conflicts:
        md_lines += [
            "## 🔥 Resolved Cross-Meeting Conflicts",
            "",
        ]
        for c in resolved_conflicts:
            md_lines.append(f"- **{c['topic_key']}**: `{c['old_statement'][:80]}...` *(from {c['meeting']})*")
        md_lines.append("")

    for owner_data in owners:
        md_lines += [f"## 👤 {owner_data.owner}", ""]

        if owner_data.completed_tasks:
            md_lines.append("### ✅ Completed")
            for t in owner_data.completed_tasks:
                md_lines.append(f"- {t['title']} *(from {t['meeting']})*")
            md_lines.append("")

        if owner_data.newly_assigned:
            md_lines.append("### 🆕 Newly Assigned")
            for t in owner_data.newly_assigned:
                deadline = f" — due **{t['deadline_iso']}**" if t.get("deadline_iso") else ""
                md_lines.append(f"- [{t['priority']}] {t['title']}{deadline}")
            md_lines.append("")

        if owner_data.upcoming_deadlines:
            md_lines.append("### ⏰ Upcoming Deadlines")
            for t in owner_data.upcoming_deadlines:
                days = t["days_until_deadline"]
                urgency = "🔴" if days <= 1 else "🟡" if days <= 3 else "🟢"
                md_lines.append(
                    f"- {urgency} **{t['title']}** — due {t['deadline_iso']} ({days} day{'s' if days != 1 else ''} away)"
                )
            md_lines.append("")

    if not owners:
        md_lines.append("*No execution tasks found for this period.*")

    return WeeklyDigestResponse(
        generated_at=now.isoformat(),
        period=f"{week_start.date().isoformat()} to {now.date().isoformat()}",
        owners=owners,
        markdown="\n".join(md_lines),
    )
