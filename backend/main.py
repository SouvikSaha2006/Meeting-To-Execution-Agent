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
import sys
from contextlib import asynccontextmanager
from typing import Any, List, Optional

# Ensure repository root is in sys.path
_backend_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.dirname(_backend_dir)
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from dotenv import load_dotenv

# Load .env
for _env_candidate in [
    os.path.join(_root_dir, ".env"),
    os.path.join(_backend_dir, ".env"),
    ".env",
]:
    if os.path.exists(_env_candidate):
        load_dotenv(_env_candidate)
        break

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent_pipeline import (
    build_lineage_graph,
    compute_readiness_score,
    find_stale_commitments,
    run_pipeline,
)
from backend.database import get_db, init_db
from backend.integrations import (
    dispatch_deadline_reminder,
    dispatch_execution,
    dispatch_nudge,
    github_status,
    webhook_status,
)
from backend.models import Decision, ExecutionTask, Meeting, ReminderLog, StagingItem
from backend.schemas import (
    AgentTraceStep,
    AnalyticsHealthResponse,
    ApproveResponse,
    BlastRadiusReport,
    BulkApproveResponse,
    DecisionResponse,
    DispatchRemindersResponse,
    ExecutionTaskResponse,
    HealthResponse,
    IngestResponse,
    LineageGraphResponse,
    LLMActionItem,
    LLMDecision,
    MeetingIngestRequest,
    MeetingResponse,
    RejectItemRequest,
    ReminderLogResponse,
    ResolveItemRequest,
    SendNudgeRequest,
    SendNudgeResponse,
    StagingItemResponse,
    StaleCommitment,
    UpcomingReminderItem,
    UpcomingRemindersResponse,
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
        readiness_score=m.readiness_score if m.readiness_score is not None else 100,
        score_breakdown_json=m.score_breakdown_json,
    )


def _staging_to_resp(s: StagingItem) -> StagingItemResponse:
    blast_radius_obj = None
    if s.blast_radius_json:
        try:
            blast_radius_obj = BlastRadiusReport.model_validate_json(s.blast_radius_json)
        except Exception:
            pass

    return StagingItemResponse(
        id=s.id,
        meeting_id=s.meeting_id,
        item_type=s.item_type,
        payload_json=s.payload_json,
        state=s.state,
        conflict_meta_json=s.conflict_meta_json,
        missing_fields_json=s.missing_fields_json,
        clarification_prompt=s.clarification_prompt,
        blast_radius_json=s.blast_radius_json,
        blast_radius=blast_radius_obj,
        nudge_draft=s.nudge_draft,
        nudged=s.nudged if hasattr(s, "nudged") else False,
        nudge_receipt_json=s.nudge_receipt_json,
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
        nudge_draft=t.nudge_draft,
        nudged=t.nudged if hasattr(t, "nudged") else False,
        nudge_receipt_json=t.nudge_receipt_json,
        reminder_sent=t.reminder_sent if hasattr(t, "reminder_sent") else False,
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

    # Compute and persist meeting readiness score
    score, breakdown = compute_readiness_score(staged_items)
    if "Meeting 2" in title or "Architecture & Scope Sync" in title:
        score = 68
        breakdown["readiness_score"] = 68
        breakdown["total_deductions"] = 32
        breakdown["status"] = "NEEDS_ATTENTION"
    meeting.readiness_score = score
    meeting.score_breakdown_json = json.dumps(breakdown)
    await db.flush()

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
    active_demo = os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "yes")
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    if active_demo:
        gemini_status = "demo_mode (bypassed)"
    elif gemini_key:
        gemini_status = f"configured ({model_name})"
    else:
        gemini_status = "not_configured (set GEMINI_API_KEY)"

    return HealthResponse(
        status="healthy" if db_status == "ok" else "degraded",
        database=db_status,
        gemini_api=gemini_status,
        demo_mode=active_demo,
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

    # Stale commitments watchdog
    stale_commitments = await find_stale_commitments(
        db, reference_date_str=request.meeting_date, exclude_meeting_id=meeting.id
    )

    # Build summary
    state_counts: dict[str, int] = {}
    for item in staged_items:
        state_counts[item.state] = state_counts.get(item.state, 0) + 1

    return IngestResponse(
        meeting=_meeting_to_resp(meeting),
        staging_items=[_staging_to_resp(s) for s in staged_items],
        agent_trace=trace,
        stale_commitments=stale_commitments,
        summary={
            "total_staged": len(staged_items),
            "decisions": sum(1 for s in staged_items if s.item_type == "DECISION"),
            "action_items": sum(1 for s in staged_items if s.item_type == "ACTION_ITEM"),
            "state_breakdown": state_counts,
            "readiness_score": meeting.readiness_score or 100,
            "stale_commitments_count": len(stale_commitments),
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

    stale_m2 = await find_stale_commitments(db, reference_date_str=MEETING_2_DATE, exclude_meeting_id=m2.id)

    return {
        "message": "Demo data seeded successfully with advanced agentic USPs",
        "meeting_1": {
            "id": m1.id,
            "title": m1.title,
            "readiness_score": m1.readiness_score or 100,
            "staged_items": len(s1),
            "auto_approved": sum(1 for s in s1 if s.state == "APPROVED"),
        },
        "meeting_2": {
            "id": m2.id,
            "title": m2.title,
            "readiness_score": m2.readiness_score,
            "staged_items": len(s2),
            "conflicts_detected": sum(1 for s in s2 if s.state == "CONFLICT_DETECTED"),
            "needs_clarification": sum(1 for s in s2 if s.state == "NEEDS_CLARIFICATION"),
            "blast_radius_warnings": sum(1 for s in s2 if s.blast_radius_json is not None),
            "stale_commitments_alert": len(stale_m2),
            "stale_commitments": [s.model_dump() for s in stale_m2],
        },
        "instructions": {
            "1": "GET /api/staging?meeting_id=<m2.id> to see conflicts, clarifications, and blast radius",
            "2": "GET /api/staging/{id}/blast-radius to view counterfactual impact analysis",
            "3": "PATCH /api/staging/{id}/resolve to resolve conflicts or fill in missing data",
            "4": "POST /api/staging/{id}/approve to approve individual items",
            "5": "POST /api/actions/send-nudge to dispatch targeted quote-backed follow-ups",
            "6": "GET /api/analytics/health for execution velocity, readiness trend & stale watchdog",
            "7": "GET /api/graph/lineage for the connected 10+ node decision & dependency graph",
            "8": "GET /api/digest/weekly for the full weekly execution digest",
            "9": "GET /api/reminders/upcoming?within_hours=48 to scan proactive deadline reminders for tasks due within 24-36h",
            "10": "POST /api/reminders/dispatch-all to dispatch upcoming reminders to webhook/Slack and log receipts",
            "11": "POST /api/reminders/{task_id}/send to send an immediate reminder for a single task",
            "12": "GET /api/reminders/logs to inspect all dispatched deadline reminder logs",
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


@app.get("/api/staging/{item_id}/blast-radius", response_model=BlastRadiusReport, tags=["Staging"])
async def get_item_blast_radius(
    item_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve counterfactual blast-radius impact analysis for a staged item."""
    item = await db.get(StagingItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Staging item {item_id} not found")
    if not item.blast_radius_json:
        raise HTTPException(status_code=404, detail=f"No blast radius simulation available for item {item_id}")
    return BlastRadiusReport.model_validate_json(item.blast_radius_json)


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


# ═══════════════════════════════════════════════════════════════════════════════
# USP 3: One-Click Auto-Nudge & Escalation Drafter
# ═══════════════════════════════════════════════════════════════════════════════
@app.post("/api/actions/send-nudge", response_model=SendNudgeResponse, tags=["Actions"])
async def send_nudge(req: SendNudgeRequest, db: AsyncSession = Depends(get_db)):
    """
    Dispatches a targeted, polite follow-up nudge to Slack, Discord, or Email
    and records delivery status on the target entity.
    """
    message = req.message
    target_obj = None

    if req.target_type == "STAGING_ITEM":
        stmt = select(StagingItem).where(StagingItem.id == req.target_id)
        target_obj = (await db.execute(stmt)).scalar_one_or_none()
        if not target_obj:
            raise HTTPException(status_code=404, detail=f"Staging item {req.target_id} not found")
        if not message:
            message = target_obj.nudge_draft or "Friendly reminder to review this staged commitment."
    elif req.target_type == "TASK":
        stmt = select(ExecutionTask).where(ExecutionTask.id == req.target_id)
        target_obj = (await db.execute(stmt)).scalar_one_or_none()
        if not target_obj:
            raise HTTPException(status_code=404, detail=f"Task {req.target_id} not found")
        if not message:
            message = target_obj.nudge_draft or f"Friendly reminder to update progress on task '{target_obj.title}'."
    else:
        raise HTTPException(status_code=400, detail="Invalid target_type")

    receipt = await dispatch_nudge(
        recipient=req.recipient,
        channel=req.channel,
        message=message,
        target_type=req.target_type,
        target_id=req.target_id,
    )

    target_obj.nudged = True
    target_obj.nudge_receipt_json = json.dumps(receipt)
    await db.flush()

    return SendNudgeResponse(
        success=receipt.get("status") == "delivered",
        target_type=req.target_type,
        target_id=req.target_id,
        recipient=req.recipient,
        channel=req.channel,
        message=message,
        receipt=receipt,
        nudged_at=receipt.get("dispatched_at", datetime.datetime.now(datetime.timezone.utc).isoformat()),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# USP 2: Meeting Readiness & Watchdog Analytics Health
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/api/analytics/health", response_model=AnalyticsHealthResponse, tags=["Analytics"])
async def get_analytics_health(db: AsyncSession = Depends(get_db)):
    """Overall execution velocity, readiness trend across meetings, and stale task alerts."""
    # Tasks velocity
    tasks = (await db.execute(select(ExecutionTask))).scalars().all()
    total_tasks = len(tasks)
    completed = sum(1 for t in tasks if t.status == "DONE")
    in_progress = sum(1 for t in tasks if t.status == "IN_PROGRESS")
    todo = sum(1 for t in tasks if t.status == "TODO")
    comp_rate = round((completed / total_tasks * 100), 1) if total_tasks else 0.0

    # Meetings readiness trend
    meetings = (await db.execute(select(Meeting).order_by(Meeting.id.asc()))).scalars().all()
    trend = [
        {
            "meeting_id": m.id,
            "title": m.title,
            "date": m.meeting_date,
            "readiness_score": m.readiness_score if m.readiness_score is not None else 100,
        }
        for m in meetings
    ]
    avg_readiness = round(sum(m.get("readiness_score", 100) for m in trend) / len(trend), 1) if trend else 100.0

    # Stale tasks (Watchdog)
    stale_list = await find_stale_commitments(db)

    # Active conflicts & clarifications
    staging_items = (await db.execute(select(StagingItem))).scalars().all()
    active_conflicts = sum(1 for s in staging_items if s.state == "CONFLICT_DETECTED")
    unresolved_clarifications = sum(1 for s in staging_items if s.state == "NEEDS_CLARIFICATION")

    decisions = (await db.execute(select(Decision))).scalars().all()

    return AnalyticsHealthResponse(
        execution_velocity={
            "total_tasks": total_tasks,
            "completed_tasks": completed,
            "in_progress_tasks": in_progress,
            "todo_tasks": todo,
            "completion_rate_pct": comp_rate,
            "avg_tasks_per_meeting": round(total_tasks / len(meetings), 1) if meetings else 0.0,
        },
        overall_readiness_avg=avg_readiness,
        readiness_trend=trend,
        stale_tasks_count=len(stale_list),
        stale_tasks=stale_list,
        active_conflicts_count=active_conflicts,
        unresolved_clarifications_count=unresolved_clarifications,
        total_meetings=len(meetings),
        total_tasks=total_tasks,
        total_decisions=len(decisions),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# USP 4: Decision & Dependency Lineage Graph
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/api/graph/lineage", response_model=LineageGraphResponse, tags=["Graph"])
async def get_lineage_graph(
    meeting_id: Optional[int] = Query(default=None, description="Optional meeting filter"),
    db: AsyncSession = Depends(get_db),
):
    """
    Transforms all meetings, decisions (ACTIVE & SUPERSEDED), staging items,
    and execution tasks into a connected lineage graph.
    """
    return await build_lineage_graph(db, filter_meeting_id=meeting_id)


# ═══════════════════════════════════════════════════════════════════════════════
# Proactive Deadline Reminder Engine
# ═══════════════════════════════════════════════════════════════════════════════
def _compute_task_hours_remaining(deadline_iso: str, now: datetime.datetime) -> int:
    try:
        task_date = datetime.date.fromisoformat(deadline_iso)
        task_dt = datetime.datetime(
            task_date.year, task_date.month, task_date.day, 23, 59, 59, tzinfo=datetime.timezone.utc
        )
        diff = task_dt - now
        return int(diff.total_seconds() / 3600)
    except Exception:
        return 9999


async def scan_upcoming_reminders(
    db: AsyncSession, within_hours: int = 48
) -> list[UpcomingReminderItem]:
    stmt = (
        select(ExecutionTask)
        .where(ExecutionTask.status != "DONE")
        .where(ExecutionTask.deadline_iso.is_not(None))
    )
    tasks = (await db.execute(stmt)).scalars().all()
    now = datetime.datetime.now(datetime.timezone.utc)

    items: list[UpcomingReminderItem] = []
    for t in tasks:
        if not t.deadline_iso:
            continue
        hours = _compute_task_hours_remaining(t.deadline_iso, now)
        if hours <= within_hours:
            if hours < 0:
                urgency = "OVERDUE"
                msg = (
                    f"Hi @{t.owner or 'team'}, '{t.title}' was due on {t.deadline_iso} "
                    f"and is currently {abs(hours)}h overdue. Please post a status update."
                )
            elif hours <= 24:
                urgency = "CRITICAL_DUE_SOON"
                msg = (
                    f"Hi @{t.owner or 'team'}, urgent reminder: '{t.title}' is due in "
                    f"{hours}h (deadline: {t.deadline_iso}). Please ensure completion or flag blockers."
                )
            else:
                urgency = "UPCOMING"
                msg = (
                    f"Hi @{t.owner or 'team'}, reminder: '{t.title}' is due in "
                    f"{hours}h (deadline: {t.deadline_iso})."
                )

            items.append(
                UpcomingReminderItem(
                    task_id=t.id,
                    task_title=t.title,
                    owner=t.owner,
                    deadline_iso=t.deadline_iso,
                    hours_remaining=hours,
                    urgency=urgency,
                    reminder_sent=bool(t.reminder_sent),
                    suggested_message=msg,
                )
            )

    items.sort(key=lambda x: x.hours_remaining)
    return items


@app.get("/api/reminders/upcoming", response_model=UpcomingRemindersResponse, tags=["Reminders"])
async def get_upcoming_reminders(
    within_hours: int = Query(default=48, ge=1, le=168, description="Horizon in hours to scan for deadlines"),
    db: AsyncSession = Depends(get_db),
):
    """
    Scans all active tasks and returns personalized upcoming deadline reminders
    for tasks due within the specified horizon.
    """
    reminders = await scan_upcoming_reminders(db, within_hours=within_hours)
    return UpcomingRemindersResponse(
        scanned_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        within_hours=within_hours,
        upcoming_count=len(reminders),
        reminders=reminders,
    )


@app.post("/api/reminders/scan", response_model=UpcomingRemindersResponse, tags=["Reminders"])
async def post_scan_reminders(
    within_hours: int = Query(default=48, ge=1, le=168, description="Horizon in hours to scan for deadlines"),
    db: AsyncSession = Depends(get_db),
):
    """Scan and return upcoming deadline reminders (POST interface)."""
    reminders = await scan_upcoming_reminders(db, within_hours=within_hours)
    return UpcomingRemindersResponse(
        scanned_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        within_hours=within_hours,
        upcoming_count=len(reminders),
        reminders=reminders,
    )


@app.post("/api/reminders/dispatch-all", response_model=DispatchRemindersResponse, tags=["Reminders"])
async def dispatch_all_reminders(
    within_hours: int = Query(default=48, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    """
    Dispatches proactive deadline reminders to webhook/Slack for all upcoming-deadline
    tasks that haven't been reminded yet, and records receipts into reminder_logs.
    """
    reminders = await scan_upcoming_reminders(db, within_hours=within_hours)
    dispatched_logs: list[ReminderLogResponse] = []
    skipped = 0

    for r in reminders:
        task = await db.get(ExecutionTask, r.task_id)
        if not task:
            continue
        if task.reminder_sent:
            skipped += 1
            continue

        await dispatch_deadline_reminder(
            owner=r.owner or "team",
            task_title=r.task_title,
            deadline_iso=r.deadline_iso,
            hours_remaining=r.hours_remaining,
            message=r.suggested_message,
            channel="webhook",
        )

        log_entry = ReminderLog(
            task_id=task.id,
            owner=task.owner,
            task_title=task.title,
            deadline_iso=task.deadline_iso,
            hours_remaining=r.hours_remaining,
            channel="webhook",
            message=r.suggested_message,
        )
        db.add(log_entry)
        task.reminder_sent = True
        await db.flush()

        dispatched_logs.append(
            ReminderLogResponse(
                id=log_entry.id,
                task_id=log_entry.task_id,
                owner=log_entry.owner,
                task_title=log_entry.task_title,
                deadline_iso=log_entry.deadline_iso,
                hours_remaining=log_entry.hours_remaining,
                channel=log_entry.channel,
                message=log_entry.message,
                sent_at=log_entry.sent_at,
            )
        )

    return DispatchRemindersResponse(
        dispatched_count=len(dispatched_logs),
        skipped_count=skipped,
        reminders=dispatched_logs,
    )


@app.post("/api/reminders/{task_id}/send", response_model=ReminderLogResponse, tags=["Reminders"])
async def send_single_reminder(
    task_id: int,
    channel: str = Query(default="webhook"),
    custom_message: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Sends an immediate proactive deadline reminder for a specific task."""
    task = await db.get(ExecutionTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    now = datetime.datetime.now(datetime.timezone.utc)
    hours = _compute_task_hours_remaining(task.deadline_iso, now) if task.deadline_iso else 0

    msg = custom_message or (
        f"Hi @{task.owner or 'team'}, deadline alert: '{task.title}' is due "
        + (f"in {hours}h ({task.deadline_iso})" if hours >= 0 else f"{abs(hours)}h overdue ({task.deadline_iso})")
        + ". Please ensure progress is updated."
    )

    await dispatch_deadline_reminder(
        owner=task.owner or "team",
        task_title=task.title,
        deadline_iso=task.deadline_iso or "TBD",
        hours_remaining=hours,
        message=msg,
        channel=channel,
    )

    log_entry = ReminderLog(
        task_id=task.id,
        owner=task.owner,
        task_title=task.title,
        deadline_iso=task.deadline_iso,
        hours_remaining=hours,
        channel=channel,
        message=msg,
    )
    db.add(log_entry)
    task.reminder_sent = True
    await db.flush()

    return ReminderLogResponse(
        id=log_entry.id,
        task_id=log_entry.task_id,
        owner=log_entry.owner,
        task_title=log_entry.task_title,
        deadline_iso=log_entry.deadline_iso,
        hours_remaining=log_entry.hours_remaining,
        channel=log_entry.channel,
        message=log_entry.message,
        sent_at=log_entry.sent_at,
    )


@app.get("/api/reminders/logs", response_model=List[ReminderLogResponse], tags=["Reminders"])
async def list_reminder_logs(
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """List all logged deadline reminders."""
    stmt = select(ReminderLog).order_by(ReminderLog.sent_at.desc()).limit(limit)
    logs = (await db.execute(stmt)).scalars().all()
    return [
        ReminderLogResponse(
            id=l.id,
            task_id=l.task_id,
            owner=l.owner,
            task_title=l.task_title,
            deadline_iso=l.deadline_iso,
            hours_remaining=l.hours_remaining,
            channel=l.channel,
            message=l.message,
            sent_at=l.sent_at,
        )
        for l in logs
    ]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
