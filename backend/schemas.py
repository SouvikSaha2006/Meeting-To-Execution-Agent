"""
schemas.py — Pydantic v2 request / response schemas and LLM structured-output schemas.

Sections
--------
1. LLM Output Schemas  (strict JSON structures the Gemini model must produce)
2. API Request Schemas
3. API Response Schemas
"""
from __future__ import annotations

import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ═══════════════════════════════════════════════════════════════════════════════
# 1. LLM OUTPUT SCHEMAS  (fed directly to Gemini as response_schema)
# ═══════════════════════════════════════════════════════════════════════════════


class LLMDecision(BaseModel):
    """A single decision extracted by the LLM."""

    model_config = ConfigDict(extra="ignore")

    topic_key: str = Field(
        description="Short machine-readable slug, e.g. 'database_choice' or 'launch_date'"
    )
    statement: str = Field(description="Full decision statement in one clear sentence")
    decided_by: Optional[str] = Field(
        default=None,
        description="Name of the person who made the decision, or null if ambiguous",
    )
    verbatim_quote: str = Field(
        description="Exact verbatim quote from the transcript supporting this decision"
    )
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        description="Confidence that this is a real committed decision vs. speculation"
    )


class LLMActionItem(BaseModel):
    """A single action item extracted by the LLM."""

    model_config = ConfigDict(extra="ignore")

    title: str = Field(description="Short imperative title, e.g. 'Set up CI/CD pipeline'")
    description: str = Field(description="Detailed description of what must be done")
    owner: Optional[str] = Field(
        default=None,
        description="Assigned person's name. MUST be null if not explicitly stated in transcript.",
    )
    deadline_iso: Optional[str] = Field(
        default=None,
        description="ISO 8601 deadline date string (YYYY-MM-DD). MUST be null if not stated.",
    )
    deadline_raw: Optional[str] = Field(
        default=None,
        description="Raw deadline text as spoken, e.g. 'by end of sprint', 'next Friday'",
    )
    priority: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        description="Task priority inferred from urgency language"
    )
    depends_on_task_title: Optional[str] = Field(
        default=None,
        description="Title of another action item this task depends on, or null",
    )
    verbatim_quote: str = Field(
        description="Exact verbatim quote from the transcript supporting this action item"
    )
    status: Literal["READY_TO_APPROVE", "NEEDS_CLARIFICATION"] = Field(
        description=(
            "NEEDS_CLARIFICATION if owner or deadline is null/ambiguous. "
            "READY_TO_APPROVE only when both are explicitly stated."
        )
    )
    missing_fields: Optional[List[Literal["owner", "deadline"]]] = Field(
        default=None,
        description="List of fields that are missing and prevent approval",
    )
    clarification_prompt: Optional[str] = Field(
        default=None,
        description="Human-readable question to resolve missing info, or null",
    )


class LLMExtractionResult(BaseModel):
    """Full structured output from Stage 2 extraction."""

    model_config = ConfigDict(extra="ignore")

    decisions: List[LLMDecision] = Field(default_factory=list)
    action_items: List[LLMActionItem] = Field(default_factory=list)


# ── Speaker Segment (Stage 1 output) ─────────────────────────────────────────
class SpeakerSegment(BaseModel):
    speaker: str
    text: str
    line_start: int
    line_end: int


# ── Blast Radius Simulation ──────────────────────────────────────────────────
class BlastRadiusTaskImpact(BaseModel):
    task_id: Optional[int] = None
    title: str
    owner: Optional[str] = None
    current_deadline: Optional[str] = None
    impact_reason: str


class BlastRadiusReport(BaseModel):
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    impacted_tasks: List[BlastRadiusTaskImpact] = Field(default_factory=list)
    estimated_delay_days: int
    mitigation_suggestion: str


# ── Stale Commitment (Watchdog) ──────────────────────────────────────────────
class StaleCommitment(BaseModel):
    task_id: int
    title: str
    owner: Optional[str] = None
    deadline_iso: Optional[str] = None
    meeting_id: int
    meeting_title: str
    meeting_date: str
    days_overdue: int
    urgency: Literal["OVERDUE", "DUE_TODAY", "CRITICAL"]
    nudge_draft: Optional[str] = None


# ── Lineage Graph Schemas ─────────────────────────────────────────────────────
class LineageNode(BaseModel):
    id: str
    type: Literal["MEETING", "DECISION", "TASK", "CONFLICT", "STAGING_ITEM"]
    label: str
    status: Optional[str] = None
    meta: dict[str, Any] = Field(default_factory=dict)


class LineageEdge(BaseModel):
    source: str
    target: str
    relation: Literal["PRODUCED", "SUPERSEDES", "CONFLICTS_WITH", "BLOCKS", "DEPENDS_ON", "STAGED_FROM"]


class LineageGraphResponse(BaseModel):
    nodes: List[LineageNode]
    edges: List[LineageEdge]
    summary: dict[str, Any]


# ── Conflict / Duplicate meta ─────────────────────────────────────────────────
class ConflictMeta(BaseModel):
    conflict_type: Literal["CONFLICT", "DUPLICATE", "BLOCKER_RISK"]
    conflicting_decision_id: Optional[int] = None
    conflicting_task_id: Optional[int] = None
    previous_meeting_title: Optional[str] = None
    previous_meeting_date: Optional[str] = None
    previous_quote: Optional[str] = None
    conflict_explanation: str


# ── Agent Trace Step ──────────────────────────────────────────────────────────
class AgentTraceStep(BaseModel):
    stage: int
    name: str
    status: Literal["running", "success", "error"]
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    timestamp: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. API REQUEST SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════


class MeetingIngestRequest(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    meeting_date: str = Field(
        description="ISO 8601 date string, e.g. '2024-11-14'",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    raw_transcript: str = Field(min_length=10)


class ResolveItemRequest(BaseModel):
    """Payload for PATCH /api/staging/{item_id}/resolve"""

    owner: Optional[str] = None
    deadline_iso: Optional[str] = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    title: Optional[str] = None
    conflict_resolution: Optional[Literal["SUPERSEDE_OLD", "KEEP_ORIGINAL"]] = None
    notes: Optional[str] = None


class RejectItemRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=1024)


class UpdateTaskStatusRequest(BaseModel):
    status: Literal["TODO", "IN_PROGRESS", "DONE"]


class SendNudgeRequest(BaseModel):
    target_type: Optional[str] = "TASK"
    target_id: Optional[int] = None
    recipient: str = "team"
    channel: Optional[str] = "slack"
    message: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# 3. API RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════


class MeetingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    meeting_date: str
    created_at: datetime.datetime
    agent_trace_json: Optional[str] = None
    readiness_score: Optional[int] = 100
    score_breakdown_json: Optional[str] = None


class DecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    meeting_id: int
    topic_key: str
    statement: str
    decided_by: Optional[str]
    verbatim_quote: Optional[str]
    confidence: Optional[str]
    status: str
    superseded_by_id: Optional[int]
    created_at: datetime.datetime

    # Convenience: include meeting title for the memory log view
    meeting_title: Optional[str] = None
    meeting_date: Optional[str] = None


class StagingItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    meeting_id: int
    item_type: str
    payload_json: str
    state: str
    conflict_meta_json: Optional[str]
    missing_fields_json: Optional[str]
    clarification_prompt: Optional[str]
    blast_radius_json: Optional[str] = None
    blast_radius: Optional[BlastRadiusReport] = None
    nudge_draft: Optional[str] = None
    nudged: bool = False
    nudge_receipt_json: Optional[str] = None
    verbatim_quote: Optional[str]
    rejection_reason: Optional[str]
    created_at: datetime.datetime


class ExecutionTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    staging_item_id: Optional[int]
    meeting_id: int
    title: str
    description: Optional[str]
    owner: Optional[str]
    deadline_iso: Optional[str]
    priority: str
    status: str
    depends_on_id: Optional[int]
    external_execution_receipt_json: Optional[str]
    nudge_draft: Optional[str] = None
    nudged: bool = False
    nudge_receipt_json: Optional[str] = None
    reminder_sent: bool = False
    approved_at: Optional[datetime.datetime]


class IngestResponse(BaseModel):
    meeting: MeetingResponse
    staging_items: List[StagingItemResponse]
    agent_trace: List[AgentTraceStep]
    stale_commitments: List[StaleCommitment] = Field(default_factory=list)
    summary: dict[str, Any]


class HealthResponse(BaseModel):
    status: str
    database: str
    gemini_api: str
    demo_mode: bool
    github_integration: str
    webhook_integration: str
    version: str
    timestamp: str


class SendNudgeResponse(BaseModel):
    status: str = "dispatched"
    receipt_id: Optional[str] = None
    success: bool = True
    target_type: Optional[str] = "TASK"
    target_id: Optional[int] = None
    recipient: str = "team"
    channel: str = "slack"
    message: str = ""
    receipt: Optional[dict[str, Any]] = None
    nudged_at: Optional[str] = None


class AnalyticsHealthResponse(BaseModel):
    execution_velocity: dict[str, Any]
    overall_readiness_avg: float
    readiness_trend: List[dict[str, Any]]
    stale_tasks_count: int
    stale_tasks: List[StaleCommitment]
    active_conflicts_count: int
    unresolved_clarifications_count: int
    total_meetings: int
    total_tasks: int
    total_decisions: int


class ApproveResponse(BaseModel):
    staging_item: StagingItemResponse
    execution_task: Optional[ExecutionTaskResponse] = None
    decision: Optional[DecisionResponse] = None
    execution_receipt: Optional[dict] = None


class BulkApproveResponse(BaseModel):
    approved_count: int
    skipped_count: int
    results: List[ApproveResponse]


class WeeklyDigestOwner(BaseModel):
    owner: str
    completed_tasks: List[dict] = []
    newly_assigned: List[dict] = []
    upcoming_deadlines: List[dict] = []
    resolved_conflicts: List[dict] = []


class WeeklyDigestResponse(BaseModel):
    generated_at: str
    period: str
    summary_stats: Optional[dict] = None
    owners: List[WeeklyDigestOwner] = []
    by_owner: Optional[List[WeeklyDigestOwner]] = None
    resolved_conflicts: Optional[List[dict]] = None
    markdown: str
    markdown_digest: Optional[str] = None


# ── Proactive Deadline Reminder Engine Schemas ────────────────────────────────
class UpcomingReminderItem(BaseModel):
    task_id: int
    task_title: str
    owner: Optional[str] = None
    deadline_iso: str
    hours_remaining: int
    countdown_label: Optional[str] = None
    urgency: Literal["OVERDUE", "CRITICAL_DUE_SOON", "UPCOMING"]
    reminder_sent: bool
    suggested_message: str


class UpcomingRemindersResponse(BaseModel):
    scanned_at: str
    within_hours: int
    upcoming_count: int
    reminders: List[UpcomingReminderItem]


class ReminderLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    owner: Optional[str] = None
    task_title: str
    deadline_iso: Optional[str] = None
    hours_remaining: int
    channel: str
    message: str
    sent_at: datetime.datetime


class DispatchRemindersResponse(BaseModel):
    status: Optional[str] = "dispatched"
    dispatched_count: int
    skipped_count: Optional[int] = 0
    reminders: List[ReminderLogResponse]


# ── Natural Language Memory Query Schemas ─────────────────────────────────────
class MemoryAskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000, description="Natural language question about organizational memory")


class MemoryCitation(BaseModel):
    meeting_title: str
    meeting_date: str
    speaker: str
    quote: str


class MemoryAskResponse(BaseModel):
    answer: str
    citations: List[MemoryCitation] = Field(default_factory=list)
    related_task_ids: List[int] = Field(default_factory=list)
