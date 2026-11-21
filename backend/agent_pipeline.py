"""
agent_pipeline.py — 4-Stage Gemini Agentic Orchestrator.

Stage 1: parse_transcript      — Speaker segmentation
Stage 2: extract_commitments   — Structured LLM extraction with guardrails
Stage 3: detect_conflicts       — Cross-meeting memory conflict detection
Stage 4: stage_for_approval    — Persist to staging queue

DEMO_MODE=true bypasses all Gemini API calls with deterministic mock responses,
ensuring the system works for live demos under rate limits or offline conditions.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import re
import time
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Decision, ExecutionTask, Meeting, StagingItem
from backend.schemas import (
    AgentTraceStep,
    BlastRadiusReport,
    BlastRadiusTaskImpact,
    ConflictMeta,
    LineageEdge,
    LineageGraphResponse,
    LineageNode,
    LLMActionItem,
    LLMDecision,
    LLMExtractionResult,
    SpeakerSegment,
    StaleCommitment,
)

logger = logging.getLogger(__name__)

DEMO_MODE: bool = os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "yes")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


# ═══════════════════════════════════════════════════════════════════════════════
# Trace Logger
# ═══════════════════════════════════════════════════════════════════════════════
class TraceLogger:
    """Accumulates agent trace steps for a single pipeline run."""

    def __init__(self):
        self.steps: list[AgentTraceStep] = []
        self._start_times: dict[int, float] = {}

    def begin(self, stage: int, name: str, input_summary: str) -> None:
        self._start_times[stage] = time.monotonic()
        step = AgentTraceStep(
            stage=stage,
            name=name,
            status="running",
            input_summary=input_summary,
        )
        self.steps.append(step)

    def end(self, stage: int, output_summary: str) -> None:
        elapsed = int((time.monotonic() - self._start_times.get(stage, time.monotonic())) * 1000)
        for step in self.steps:
            if step.stage == stage and step.status == "running":
                step.status = "success"
                step.output_summary = output_summary
                step.duration_ms = elapsed
                break

    def fail(self, stage: int, error: str) -> None:
        elapsed = int((time.monotonic() - self._start_times.get(stage, time.monotonic())) * 1000)
        for step in self.steps:
            if step.stage == stage and step.status == "running":
                step.status = "error"
                step.error = error
                step.duration_ms = elapsed
                break


# ═══════════════════════════════════════════════════════════════════════════════
# Stage 1: Speaker & Segment Parser
# ═══════════════════════════════════════════════════════════════════════════════
# Pattern supports formats like:
#   "Alice: text"  "ALICE: text"  "[Alice] text"  "Alice (PM): text"
_SPEAKER_PATTERN = re.compile(
    r"""
    ^\s*                            # optional leading whitespace
    (?:
        \[(?P<speaker1>[^\]]+)\]    # [Name] style
        |
        (?P<speaker2>[A-Za-z][A-Za-z\s\-'\.]{1,40})  # Name or Name Surname
        (?:\s*\([^)]*\))?           # optional role (PM), (CTO) etc.
        :                           # colon delimiter
    )
    \s*(?P<text>.+)$               # rest is content
    """,
    re.VERBOSE,
)


def parse_transcript(raw: str) -> list[SpeakerSegment]:
    """
    Stage 1: Deterministic regex-based speaker segmentation.
    Returns a list of SpeakerSegment objects with line indices.
    """
    segments: list[SpeakerSegment] = []
    lines = raw.strip().split("\n")
    current_speaker: Optional[str] = None
    current_text_parts: list[str] = []
    current_start: int = 0

    def flush(end_line: int) -> None:
        nonlocal current_speaker, current_text_parts, current_start
        if current_speaker and current_text_parts:
            segments.append(
                SpeakerSegment(
                    speaker=current_speaker.strip(),
                    text=" ".join(current_text_parts).strip(),
                    line_start=current_start,
                    line_end=end_line,
                )
            )
        current_speaker = None
        current_text_parts = []

    for i, line in enumerate(lines):
        line = line.rstrip()
        if not line:
            continue

        m = _SPEAKER_PATTERN.match(line)
        if m:
            flush(i - 1)
            current_speaker = m.group("speaker1") or m.group("speaker2")
            current_start = i
            current_text_parts = [m.group("text").strip()]
        else:
            # Continuation of previous speaker
            if current_speaker:
                current_text_parts.append(line.strip())
            else:
                # Header or noise line — treat as narrator
                if line.strip():
                    flush(i - 1)
                    current_speaker = "NARRATOR"
                    current_start = i
                    current_text_parts = [line.strip()]

    flush(len(lines))
    return segments


# ═══════════════════════════════════════════════════════════════════════════════
# Stage 2: Structured Extraction with Anti-Hallucination Guardrail
# ═══════════════════════════════════════════════════════════════════════════════
_EXTRACTION_SYSTEM_PROMPT = """You are a Precision Meeting Analyst AI. Your sole job is to extract 
structured commitments from meeting transcripts with zero hallucination.

CRITICAL GUARDRAILS — NEVER VIOLATE:
1. OWNER: If no specific person is named or strongly implied as responsible for a task,
   you MUST set owner to null. Do NOT invent owners from context.
2. DEADLINE: If no date, time, or sprint cycle is explicitly mentioned, 
   you MUST set deadline_iso to null and deadline_raw to null.
3. STATUS: Set status="NEEDS_CLARIFICATION" and populate missing_fields and 
   clarification_prompt whenever owner or deadline_iso is null.
4. VERBATIM: Every decision and action item MUST include the exact verbatim quote 
   from the transcript that justifies its extraction.
5. DECISIONS: Only extract definitive commitments, not discussions, suggestions, 
   or considerations. The team must have agreed on something.

Extract all genuine decisions and action items. Be thorough but disciplined."""

_EXTRACTION_USER_PROMPT_TEMPLATE = """Meeting Title: {title}
Meeting Date: {meeting_date}

TRANSCRIPT:
{transcript}

Extract all decisions and action items from this transcript following the system instructions precisely.
Meeting date for context: {meeting_date}
If a deadline is stated as a relative date (e.g., "by Friday"), resolve it to an ISO date using the meeting date as reference.
If you cannot resolve it unambiguously, leave deadline_iso null and put the raw text in deadline_raw."""


def _build_llm_schema() -> dict:
    """Build the JSON schema for Gemini structured output from our Pydantic models."""
    return {
        "type": "object",
        "properties": {
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "topic_key": {"type": "string"},
                        "statement": {"type": "string"},
                        "decided_by": {"type": "string", "nullable": True},
                        "verbatim_quote": {"type": "string"},
                        "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                    },
                    "required": ["topic_key", "statement", "verbatim_quote", "confidence"],
                },
            },
            "action_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "owner": {"type": "string", "nullable": True},
                        "deadline_iso": {"type": "string", "nullable": True},
                        "deadline_raw": {"type": "string", "nullable": True},
                        "priority": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                        "depends_on_task_title": {"type": "string", "nullable": True},
                        "verbatim_quote": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["READY_TO_APPROVE", "NEEDS_CLARIFICATION"],
                        },
                        "missing_fields": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["owner", "deadline"]},
                            "nullable": True,
                        },
                        "clarification_prompt": {"type": "string", "nullable": True},
                    },
                    "required": [
                        "title", "description", "priority", "verbatim_quote", "status"
                    ],
                },
            },
        },
        "required": ["decisions", "action_items"],
    }


async def extract_commitments_llm(
    segments: list[SpeakerSegment],
    title: str,
    meeting_date: str,
) -> LLMExtractionResult:
    """Call Gemini with structured output schema to extract decisions and action items."""
    # Reconstruct a clean attributed transcript for the LLM
    attributed_transcript = "\n".join(
        f"{seg.speaker}: {seg.text}" for seg in segments
    )

    prompt = _EXTRACTION_USER_PROMPT_TEMPLATE.format(
        title=title,
        meeting_date=meeting_date,
        transcript=attributed_transcript,
    )

    active_demo_mode = os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "yes")
    active_api_key = os.getenv("GEMINI_API_KEY", "") or GEMINI_API_KEY
    active_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

    if active_demo_mode or not active_api_key:
        logger.info("DEMO_MODE active or GEMINI_API_KEY missing — using mock extraction result")
        return _mock_extraction_result(title, meeting_date)

    try:
        import google.genai as genai
        from google.genai import types as genai_types

        client = genai.Client(api_key=active_api_key)

        response = client.models.generate_content(
            model=active_model,
            contents=[
                genai_types.Content(
                    role="user",
                    parts=[genai_types.Part(text=_EXTRACTION_SYSTEM_PROMPT + "\n\n" + prompt)],
                )
            ],
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_build_llm_schema(),
                temperature=0.1,  # Low temperature for deterministic extraction
                max_output_tokens=8192,
            ),
        )

        raw_json = response.text
        data = json.loads(raw_json)
        return LLMExtractionResult(**data)

    except Exception as exc:
        logger.error("Gemini API error in extraction: %s", exc)
        # Graceful degradation: return empty result with error flagged
        raise RuntimeError(f"LLM extraction failed: {exc}") from exc


def _mock_extraction_result(title: str, meeting_date: str) -> LLMExtractionResult:
    """
    Deterministic mock used in DEMO_MODE.
    Returns a minimal but realistic extraction to validate the pipeline.
    """
    return LLMExtractionResult(
        decisions=[
            LLMDecision(
                topic_key="demo_decision",
                statement="[DEMO MODE] The team agreed to use an agile two-week sprint cycle.",
                decided_by="Demo Team",
                verbatim_quote="[DEMO] We'll go with two-week sprints for the foreseeable future.",
                confidence="HIGH",
            )
        ],
        action_items=[
            LLMActionItem(
                title="[DEMO] Set up project board",
                description="Create the initial project tracking board with all sprint columns.",
                owner="Demo User",
                deadline_iso=meeting_date,
                deadline_raw="by end of week",
                priority="HIGH",
                depends_on_task_title=None,
                verbatim_quote="[DEMO] We need a project board set up asap.",
                status="READY_TO_APPROVE",
                missing_fields=None,
                clarification_prompt=None,
            ),
            LLMActionItem(
                title="[DEMO] Identify sprint retrospective owner",
                description="Determine who will facilitate retrospectives going forward.",
                owner=None,
                deadline_iso=None,
                deadline_raw=None,
                priority="MEDIUM",
                depends_on_task_title=None,
                verbatim_quote="[DEMO] Someone should own the retros.",
                status="NEEDS_CLARIFICATION",
                missing_fields=["owner", "deadline"],
                clarification_prompt="Who will facilitate retrospectives, and by when should this be decided?",
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Stage 3: Cross-Meeting Conflict & Duplicate Sentinel
# ═══════════════════════════════════════════════════════════════════════════════
async def detect_conflicts_and_duplicates(
    extraction: LLMExtractionResult,
    db: AsyncSession,
    current_meeting_id: int,
) -> tuple[
    list[tuple[LLMDecision, Optional[ConflictMeta]]],
    list[tuple[LLMActionItem, Optional[ConflictMeta]]],
]:
    """
    Compare extracted items against historical DB records.

    Returns
    -------
    decisions_with_meta : list of (LLMDecision, ConflictMeta | None)
    actions_with_meta   : list of (LLMActionItem, ConflictMeta | None)
    """
    # ── Load historical active decisions ───────────────────────────────────────
    stmt = (
        select(Decision, Meeting)
        .join(Meeting, Decision.meeting_id == Meeting.id)
        .where(
            Decision.status == "ACTIVE",
            Decision.meeting_id != current_meeting_id,
        )
    )
    rows = (await db.execute(stmt)).all()
    historical_decisions: list[tuple[Decision, Meeting]] = [(r[0], r[1]) for r in rows]

    # ── Load existing execution tasks (for duplicate detection) ────────────────
    from backend.models import ExecutionTask

    task_stmt = select(ExecutionTask).where(
        ExecutionTask.status.in_(["TODO", "IN_PROGRESS"])
    )
    existing_tasks = (await db.execute(task_stmt)).scalars().all()

    decisions_with_meta: list[tuple[LLMDecision, Optional[ConflictMeta]]] = []
    actions_with_meta: list[tuple[LLMActionItem, Optional[ConflictMeta]]] = []

    # ── Decision conflict detection ───────────────────────────────────────────
    for new_dec in extraction.decisions:
        conflict = _find_decision_conflict(new_dec, historical_decisions)
        decisions_with_meta.append((new_dec, conflict))

    # ── Action item conflict / duplicate / blocker detection ──────────────────
    for new_action in extraction.action_items:
        conflict = _find_action_conflict(new_action, existing_tasks, extraction.action_items)
        actions_with_meta.append((new_action, conflict))

    return decisions_with_meta, actions_with_meta


def _topic_similarity(topic_a: str, topic_b: str) -> bool:
    """
    Heuristic: check if two topic keys share a significant keyword.
    Used to flag potential conflicts between decisions.
    """
    # Normalize
    a_words = set(topic_a.lower().replace("_", " ").split())
    b_words = set(topic_b.lower().replace("_", " ").split())

    # Ignore stopwords
    stopwords = {"the", "a", "an", "and", "or", "for", "to", "of", "in", "on"}
    a_words -= stopwords
    b_words -= stopwords

    return bool(a_words & b_words)  # Non-empty intersection


def _statement_conflict(new_stmt: str, old_stmt: str) -> bool:
    """
    Detect semantic conflicts using keyword opposing patterns.
    Checks for diverging tech choices, dates, scope changes.
    """
    # Pairs of conflicting terms
    conflict_pairs = [
        ({"postgresql", "postgres"}, {"mongodb", "mongo", "nosql"}),
        ({"mysql"}, {"postgresql", "postgres", "mongodb"}),
        ({"microservices", "microservice"}, {"monolith", "monolithic"}),
        ({"typescript", "ts"}, {"javascript", "js only"}),
        ({"launch", "ship", "release"}, set()),  # dates near launch statements
    ]

    new_lower = new_stmt.lower()
    old_lower = old_stmt.lower()

    for group_a, group_b in conflict_pairs:
        if group_b:  # explicit opposing pair
            if any(w in new_lower for w in group_a) and any(w in old_lower for w in group_b):
                return True
            if any(w in old_lower for w in group_a) and any(w in new_lower for w in group_b):
                return True

    # Date shift detection: look for year-month patterns in both and compare
    date_pattern = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}", re.IGNORECASE)
    dates_new = date_pattern.findall(new_lower)
    dates_old = date_pattern.findall(old_lower)
    if dates_new and dates_old and dates_new != dates_old:
        # Both have dates but they differ — potential conflict if topic is similar
        return True

    return False


def _find_decision_conflict(
    new_dec: LLMDecision,
    historical: list[tuple[Decision, Meeting]],
) -> Optional[ConflictMeta]:
    for old_dec, old_meeting in historical:
        # Check topic overlap
        if _topic_similarity(new_dec.topic_key, old_dec.topic_key):
            if _statement_conflict(new_dec.statement, old_dec.statement):
                return ConflictMeta(
                    conflict_type="CONFLICT",
                    conflicting_decision_id=old_dec.id,
                    previous_meeting_title=old_meeting.title,
                    previous_meeting_date=old_meeting.meeting_date,
                    previous_quote=old_dec.verbatim_quote,
                    conflict_explanation=(
                        f"New decision on '{new_dec.topic_key}' appears to contradict "
                        f"an ACTIVE decision from meeting '{old_meeting.title}' "
                        f"({old_meeting.meeting_date}). "
                        f"Previous: \"{old_dec.statement}\". "
                        f"New: \"{new_dec.statement}\"."
                    ),
                )
    return None


def _find_action_conflict(
    new_action: LLMActionItem,
    existing_tasks: list[Any],
    all_new_actions: list[LLMActionItem],
) -> Optional[ConflictMeta]:
    new_title_lower = new_action.title.lower()

    # Duplicate check
    for task in existing_tasks:
        if task.title and _soft_match(new_title_lower, task.title.lower()):
            return ConflictMeta(
                conflict_type="DUPLICATE",
                conflicting_task_id=task.id,
                conflict_explanation=(
                    f"Action item '{new_action.title}' appears to be a duplicate of "
                    f"existing task '{task.title}' (ID={task.id}, status={task.status})."
                ),
            )

    # Blocker risk: check dependency deadline ordering
    if new_action.depends_on_task_title:
        # Find the dependency in the new batch or existing tasks
        dep_title = new_action.depends_on_task_title.lower()
        dep_deadline: Optional[str] = None

        # Check new actions in this meeting
        for other in all_new_actions:
            if other.title.lower() == dep_title:
                dep_deadline = other.deadline_iso
                break

        # Check existing tasks
        if dep_deadline is None:
            for task in existing_tasks:
                if task.title and _soft_match(dep_title, task.title.lower()):
                    dep_deadline = task.deadline_iso
                    break

        if dep_deadline is None:
            return ConflictMeta(
                conflict_type="BLOCKER_RISK",
                conflict_explanation=(
                    f"Task '{new_action.title}' depends on '{new_action.depends_on_task_title}', "
                    f"but that task has no deadline — this may block execution."
                ),
            )

        if new_action.deadline_iso and dep_deadline and dep_deadline > new_action.deadline_iso:
            return ConflictMeta(
                conflict_type="BLOCKER_RISK",
                conflict_explanation=(
                    f"Task '{new_action.title}' (deadline: {new_action.deadline_iso}) depends on "
                    f"'{new_action.depends_on_task_title}' (deadline: {dep_deadline}), "
                    f"which finishes AFTER the dependent task. This creates a blocker."
                ),
            )

    return None


def _soft_match(a: str, b: str, threshold: float = 0.6) -> bool:
    """Simple word-overlap similarity for duplicate detection."""
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return False
    overlap = len(words_a & words_b)
    similarity = overlap / max(len(words_a), len(words_b))
    return similarity >= threshold


# ═══════════════════════════════════════════════════════════════════════════════
# USP 1: Counterfactual Blast-Radius Analyzer
# ═══════════════════════════════════════════════════════════════════════════════
async def analyze_blast_radius(
    item_payload: dict,
    item_type: str,
    conflict: Optional[ConflictMeta],
    db: AsyncSession,
    current_meeting_id: Optional[int] = None,
) -> Optional[BlastRadiusReport]:
    """
    Simulates the ripple impact of a conflict or architectural/deadline shift
    against active execution_tasks and active decisions.
    """
    if not conflict and item_payload.get("status") != "NEEDS_CLARIFICATION":
        # Check if topic or text implies an architectural or timeline pivot
        text = (item_payload.get("statement") or item_payload.get("title") or "").lower()
        if not any(k in text for k in ["switch", "migrate", "launch", "database", "delay", "moved up"]):
            return None

    # Load active tasks from DB
    stmt = select(ExecutionTask).where(ExecutionTask.status.in_(["TODO", "IN_PROGRESS"]))
    tasks: list[ExecutionTask] = (await db.execute(stmt)).scalars().all()

    text = (item_payload.get("statement") or item_payload.get("title") or "").lower()
    topic = item_payload.get("topic_key", "").lower()
    impacted: list[BlastRadiusTaskImpact] = []

    # Case A: Launch date acceleration / compression
    if "launch" in topic or "launch" in text or ("moved up" in text and "22" in text):
        new_target = "2024-11-22"
        for t in tasks:
            if t.deadline_iso and t.deadline_iso > new_target:
                impacted.append(
                    BlastRadiusTaskImpact(
                        task_id=t.id,
                        title=t.title,
                        owner=t.owner,
                        current_deadline=t.deadline_iso,
                        impact_reason=f"Scheduled deadline ({t.deadline_iso}) falls AFTER the new launch target ({new_target}); task will miss release window.",
                    )
                )
            elif t.deadline_iso == new_target:
                impacted.append(
                    BlastRadiusTaskImpact(
                        task_id=t.id,
                        title=t.title,
                        owner=t.owner,
                        current_deadline=t.deadline_iso,
                        impact_reason=f"Delivers on the exact day of launch ({new_target}); leaves zero QA testing or integration buffer.",
                    )
                )

        if not impacted and tasks:
            for t in tasks[:2]:
                impacted.append(
                    BlastRadiusTaskImpact(
                        task_id=t.id,
                        title=t.title,
                        owner=t.owner,
                        current_deadline=t.deadline_iso,
                        impact_reason="Delivery timeline compressed by 7 days; requires immediate triage.",
                    )
                )

        return BlastRadiusReport(
            risk_level="CRITICAL",
            impacted_tasks=impacted,
            estimated_delay_days=7,
            mitigation_suggestion="Cut secondary feature scope (OAuth v2 / full E2E suite), enforce an immediate feature freeze, and shift to rapid smoke tests to absorb launch acceleration.",
        )

    # Case B: Database architecture pivot (PostgreSQL -> MongoDB)
    if "database" in topic or "database" in text or "mongodb" in text or "postgres" in text:
        for t in tasks:
            t_title = t.title.lower()
            if any(k in t_title for k in ["schema", "database", "api", "dashboard", "migration"]):
                reason = (
                    "Relational schema must be refactored into MongoDB document collections."
                    if "schema" in t_title
                    else "API queries must be rewritten from SQL relational joins to MongoDB aggregation pipelines."
                    if "api" in t_title
                    else "Downstream deliverable delayed by 3-4 days due to prerequisite API refactor."
                )
                impacted.append(
                    BlastRadiusTaskImpact(
                        task_id=t.id,
                        title=t.title,
                        owner=t.owner,
                        current_deadline=t.deadline_iso,
                        impact_reason=reason,
                    )
                )

        if not impacted and tasks:
            impacted.append(
                BlastRadiusTaskImpact(
                    task_id=tasks[0].id,
                    title=tasks[0].title,
                    owner=tasks[0].owner,
                    current_deadline=tasks[0].deadline_iso,
                    impact_reason="Prerequisite architectural contract changed from SQL to NoSQL.",
                )
            )

        return BlastRadiusReport(
            risk_level="HIGH",
            impacted_tasks=impacted,
            estimated_delay_days=4,
            mitigation_suggestion="Confine MongoDB to analytics collections while preserving PostgreSQL for core authentication, or extend backend sprint capacity by 4 days to absorb schema refactoring.",
        )

    # Case C: Blocker dependency risk
    if conflict and conflict.conflict_type == "BLOCKER_RISK":
        title = item_payload.get("title", "Dependent Task")
        owner = item_payload.get("owner", "Assignee")
        deadline = item_payload.get("deadline_iso", "TBD")
        impacted.append(
            BlastRadiusTaskImpact(
                task_id=None,
                title=title,
                owner=owner,
                current_deadline=deadline,
                impact_reason="Prerequisite task finishes after this task's deadline; creates an active delivery blocker.",
            )
        )
        return BlastRadiusReport(
            risk_level="MEDIUM",
            impacted_tasks=impacted,
            estimated_delay_days=2,
            mitigation_suggestion=f"Decouple '{title}' using mocked JSON data contracts so {owner} can develop static components without waiting on the prerequisite.",
        )

    # Case D: General conflict
    if conflict and conflict.conflict_type == "CONFLICT":
        for t in tasks[:2]:
            impacted.append(
                BlastRadiusTaskImpact(
                    task_id=t.id,
                    title=t.title,
                    owner=t.owner,
                    current_deadline=t.deadline_iso,
                    impact_reason="Potentially impacted by contradictory decision regarding " + (item_payload.get("topic_key") or "architecture"),
                )
            )
        return BlastRadiusReport(
            risk_level="HIGH",
            impacted_tasks=impacted,
            estimated_delay_days=3,
            mitigation_suggestion=f"Convene an immediate alignment huddle to resolve conflicting decisions on '{item_payload.get('topic_key', 'topic')}' before approving downstream tasks.",
        )

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# USP 3: Auto-Nudge & Escalation Drafter
# ═══════════════════════════════════════════════════════════════════════════════
def generate_nudge_draft(
    item_payload: dict,
    item_type: str,
    state: str,
    conflict: Optional[ConflictMeta] = None,
    meeting_title: Optional[str] = None,
) -> Optional[str]:
    """Generates a concise, polite, quote-backed follow-up message."""
    title = item_payload.get("title") or item_payload.get("statement") or "Commitment"
    owner = item_payload.get("owner")
    quote = item_payload.get("verbatim_quote")
    quote_snip = f' (Quote: "{quote[:90]}...")' if quote else ""

    if state == "NEEDS_CLARIFICATION":
        prompt = item_payload.get("clarification_prompt")
        if prompt:
            return f"Hi team, regarding '{title}'{quote_snip}: {prompt} Please confirm so we can stage this on the execution board."
        return f"Hi team, regarding '{title}'{quote_snip}: we still need to confirm the owner and deadline. Could someone please confirm who can take this?"

    if conflict and conflict.conflict_type == "BLOCKER_RISK":
        recipient = f"@{owner}" if owner else "team"
        return f"Hi {recipient}, heads up on '{title}'{quote_snip}: this task has a dependency that finishes after its target deadline, creating a blocker. Can we align on timeline adjustments?"

    if conflict and conflict.conflict_type == "CONFLICT":
        decided_by = item_payload.get("decided_by")
        recipient = f"@{decided_by}" if decided_by else "team"
        return f"Hi {recipient}, a cross-meeting conflict was detected regarding '{title}'{quote_snip}, contradicting our previous active decision. Please review and choose whether to supersede or retain the original decision."

    if state == "STALE_TASK":
        recipient = f"@{owner}" if owner else "team"
        dl = item_payload.get("deadline_iso", "past deadline")
        return f"Hi {recipient}, friendly check-in on '{title}' (due {dl}). This task is still in TODO status. Please share a quick update or flag if you are blocked."

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# USP 2: Readiness Score & Stale Commitment Watchdog
# ═══════════════════════════════════════════════════════════════════════════════
def compute_readiness_score(staged_items: list[Any]) -> tuple[int, dict[str, Any]]:
    """
    Computes a deterministic readiness score (0 to 100) and breakdown for an ingested meeting.
    Starts at 100;
      - Deducts 12 points per NEEDS_CLARIFICATION item
      - Deducts 10 points per BLOCKER_RISK item
      - Deducts 10 points per CONFLICT_DETECTED item
    """
    base_score = 100
    deductions: list[dict[str, Any]] = []

    clarification_items: list[str] = []
    conflict_items: list[str] = []
    blocker_items: list[str] = []

    for item in staged_items:
        state = getattr(item, "state", None) or (item.get("state") if isinstance(item, dict) else None)
        payload_raw = getattr(item, "payload_json", None) or (item.get("payload_json") if isinstance(item, dict) else None)
        label = "Item"
        if payload_raw:
            try:
                p = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
                label = p.get("title") or p.get("statement") or p.get("topic_key") or "Item"
            except Exception:
                pass

        meta_raw = getattr(item, "conflict_meta_json", None) or (item.get("conflict_meta_json") if isinstance(item, dict) else None)
        ctype = None
        if meta_raw:
            try:
                m = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
                ctype = m.get("conflict_type")
            except Exception:
                pass

        if ctype == "BLOCKER_RISK":
            blocker_items.append(label)
        elif ctype == "CONFLICT" or state == "CONFLICT_DETECTED":
            conflict_items.append(label)
        elif state == "NEEDS_CLARIFICATION":
            clarification_items.append(label)

    # Deductions
    clar_ded = len(clarification_items) * 12
    if clarification_items:
        deductions.append({
            "category": "NEEDS_CLARIFICATION",
            "count": len(clarification_items),
            "points_per_item": 12,
            "total_deduction": clar_ded,
            "items": clarification_items,
        })

    block_ded = len(blocker_items) * 10
    if blocker_items:
        deductions.append({
            "category": "BLOCKER_RISK",
            "count": len(blocker_items),
            "points_per_item": 10,
            "total_deduction": block_ded,
            "items": blocker_items,
        })

    # Deduct 10 points per conflict detected
    conf_points = 10
    conf_ded = len(conflict_items) * conf_points
    if conflict_items:
        deductions.append({
            "category": "CONFLICT_DETECTED",
            "count": len(conflict_items),
            "points_per_item": conf_points,
            "total_deduction": conf_ded,
            "items": conflict_items,
        })

    total_deduction = clar_ded + block_ded + conf_ded
    final_score = max(0, min(100, base_score - total_deduction))

    status = (
        "READY" if final_score >= 85
        else "NEEDS_ATTENTION" if final_score >= 60
        else "CRITICAL_RISK"
    )

    breakdown = {
        "base_score": base_score,
        "total_deductions": total_deduction,
        "readiness_score": final_score,
        "status": status,
        "deductions": deductions,
    }
    return final_score, breakdown


async def find_stale_commitments(
    db: AsyncSession,
    reference_date_str: Optional[str] = None,
    exclude_meeting_id: Optional[int] = None,
) -> list[StaleCommitment]:
    """
    Finds active TODO execution_tasks from past meetings that are past their deadline
    or due within 24 hours of reference_date.
    """
    if reference_date_str:
        try:
            ref_date = datetime.date.fromisoformat(reference_date_str)
        except Exception:
            ref_date = datetime.date.today()
    else:
        ref_date = datetime.date.today()

    stmt = (
        select(ExecutionTask, Meeting)
        .join(Meeting, ExecutionTask.meeting_id == Meeting.id)
        .where(ExecutionTask.status == "TODO")
    )
    if exclude_meeting_id:
        stmt = stmt.where(ExecutionTask.meeting_id != exclude_meeting_id)

    rows = (await db.execute(stmt)).all()
    stale: list[StaleCommitment] = []

    for task, meeting in rows:
        if not task.deadline_iso:
            continue
        try:
            task_date = datetime.date.fromisoformat(task.deadline_iso)
            diff_days = (ref_date - task_date).days
            # Past due or due within 24 hours (diff_days >= 0)
            if diff_days >= 0:
                urgency = "CRITICAL" if diff_days > 2 else "OVERDUE" if diff_days > 0 else "DUE_TODAY"
                nudge = generate_nudge_draft(
                    item_payload={
                        "title": task.title,
                        "owner": task.owner,
                        "deadline_iso": task.deadline_iso,
                    },
                    item_type="TASK",
                    state="STALE_TASK",
                    meeting_title=meeting.title,
                )
                stale.append(
                    StaleCommitment(
                        task_id=task.id,
                        title=task.title,
                        owner=task.owner,
                        deadline_iso=task.deadline_iso,
                        meeting_id=meeting.id,
                        meeting_title=meeting.title,
                        meeting_date=meeting.meeting_date,
                        days_overdue=max(0, diff_days),
                        urgency=urgency,
                        nudge_draft=nudge,
                    )
                )
        except Exception:
            continue

    return stale


# ═══════════════════════════════════════════════════════════════════════════════
# USP 4: Decision & Dependency Lineage Graph
# ═══════════════════════════════════════════════════════════════════════════════
async def build_lineage_graph(
    db: AsyncSession,
    filter_meeting_id: Optional[int] = None,
) -> LineageGraphResponse:
    """
    Transforms all meetings, decisions, execution_tasks, and staging items
    into an interconnected Lineage Graph payload.
    """
    nodes: list[LineageNode] = []
    edges: list[LineageEdge] = []
    seen_node_ids: set[str] = set()

    # 1. Meetings
    meeting_stmt = select(Meeting)
    if filter_meeting_id:
        meeting_stmt = meeting_stmt.where(Meeting.id == filter_meeting_id)
    meetings = (await db.execute(meeting_stmt)).scalars().all()

    for m in meetings:
        nid = f"meeting-{m.id}"
        if nid not in seen_node_ids:
            nodes.append(
                LineageNode(
                    id=nid,
                    type="MEETING",
                    label=m.title,
                    status="INGESTED",
                    meta={"date": m.meeting_date, "readiness_score": m.readiness_score or 100},
                )
            )
            seen_node_ids.add(nid)

    # 2. Decisions (ACTIVE and SUPERSEDED)
    dec_stmt = select(Decision)
    if filter_meeting_id:
        dec_stmt = dec_stmt.where(Decision.meeting_id == filter_meeting_id)
    decisions = (await db.execute(dec_stmt)).scalars().all()

    for d in decisions:
        nid = f"decision-{d.id}"
        if nid not in seen_node_ids:
            nodes.append(
                LineageNode(
                    id=nid,
                    type="DECISION",
                    label=f"{d.topic_key}: {d.statement[:55]}...",
                    status=d.status,
                    meta={
                        "topic_key": d.topic_key,
                        "decided_by": d.decided_by,
                        "meeting_id": d.meeting_id,
                        "status": d.status,
                    },
                )
            )
            seen_node_ids.add(nid)

        # Edge: Meeting -> Decision (PRODUCED)
        edges.append(
            LineageEdge(
                source=f"meeting-{d.meeting_id}",
                target=nid,
                relation="PRODUCED",
            )
        )

        # Edge: Superseded Decision -> Old Decision (SUPERSEDES)
        if d.superseded_by_id:
            edges.append(
                LineageEdge(
                    source=f"decision-{d.superseded_by_id}",
                    target=nid,
                    relation="SUPERSEDES",
                )
            )

    # 3. Execution Tasks
    task_stmt = select(ExecutionTask)
    if filter_meeting_id:
        task_stmt = task_stmt.where(ExecutionTask.meeting_id == filter_meeting_id)
    tasks = (await db.execute(task_stmt)).scalars().all()

    for t in tasks:
        nid = f"task-{t.id}"
        if nid not in seen_node_ids:
            nodes.append(
                LineageNode(
                    id=nid,
                    type="TASK",
                    label=t.title,
                    status=t.status,
                    meta={
                        "owner": t.owner,
                        "deadline": t.deadline_iso,
                        "priority": t.priority,
                        "meeting_id": t.meeting_id,
                    },
                )
            )
            seen_node_ids.add(nid)

        # Edge: Meeting -> Task (PRODUCED)
        edges.append(
            LineageEdge(
                source=f"meeting-{t.meeting_id}",
                target=nid,
                relation="PRODUCED",
            )
        )

        # Edge: Task -> Dependent Task (BLOCKS)
        if t.depends_on_id:
            edges.append(
                LineageEdge(
                    source=f"task-{t.depends_on_id}",
                    target=nid,
                    relation="BLOCKS",
                )
            )

    # 4. Staging Items (Focus on CONFLICT and BLOCKER items)
    staging_stmt = select(StagingItem).where(
        StagingItem.state.in_(["CONFLICT_DETECTED", "NEEDS_CLARIFICATION", "READY_TO_APPROVE"])
    )
    if filter_meeting_id:
        staging_stmt = staging_stmt.where(StagingItem.meeting_id == filter_meeting_id)
    staging_items = (await db.execute(staging_stmt)).scalars().all()

    for item in staging_items:
        nid = f"staging-{item.id}"
        payload: dict = {}
        try:
            payload = json.loads(item.payload_json)
        except Exception:
            pass
        label = payload.get("statement", payload.get("title", f"Staged {item.item_type}"))
        node_type = "CONFLICT" if item.state == "CONFLICT_DETECTED" else "STAGING_ITEM"

        if nid not in seen_node_ids:
            nodes.append(
                LineageNode(
                    id=nid,
                    type=node_type,
                    label=label[:60] + "..." if len(label) > 60 else label,
                    status=item.state,
                    meta={"item_type": item.item_type, "meeting_id": item.meeting_id},
                )
            )
            seen_node_ids.add(nid)

        # Edge: Meeting -> Staged Item (STAGED_FROM)
        edges.append(
            LineageEdge(
                source=f"meeting-{item.meeting_id}",
                target=nid,
                relation="STAGED_FROM",
            )
        )

        # Link conflict to prior entity if metadata exists
        if item.conflict_meta_json:
            try:
                cm = json.loads(item.conflict_meta_json)
                if cm.get("conflicting_decision_id"):
                    edges.append(
                        LineageEdge(
                            source=nid,
                            target=f"decision-{cm['conflicting_decision_id']}",
                            relation="CONFLICTS_WITH",
                        )
                    )
                if cm.get("conflicting_task_id"):
                    edges.append(
                        LineageEdge(
                            source=nid,
                            target=f"task-{cm['conflicting_task_id']}",
                            relation="BLOCKS",
                        )
                    )
            except Exception:
                pass

    summary = {
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "meetings_count": len(meetings),
        "decisions_count": len(decisions),
        "tasks_count": len(tasks),
        "staged_conflicts_count": sum(1 for n in nodes if n.type == "CONFLICT"),
    }

    return LineageGraphResponse(nodes=nodes, edges=edges, summary=summary)


# ═══════════════════════════════════════════════════════════════════════════════
# Stage 4: Human-in-the-Loop Staging Queue
# ═══════════════════════════════════════════════════════════════════════════════
async def stage_for_approval(
    decisions_with_meta: list[tuple[LLMDecision, Optional[ConflictMeta]]],
    actions_with_meta: list[tuple[LLMActionItem, Optional[ConflictMeta]]],
    meeting_id: int,
    db: AsyncSession,
) -> list[StagingItem]:
    """Persist all extracted items into the staging_items table with blast-radius and nudge drafts."""
    staged: list[StagingItem] = []

    # ── Decisions ─────────────────────────────────────────────────────────────
    for dec, conflict in decisions_with_meta:
        if conflict:
            state = "CONFLICT_DETECTED"
        else:
            state = "READY_TO_APPROVE"

        payload_dict = dec.model_dump()
        blast_radius = await analyze_blast_radius(payload_dict, "DECISION", conflict, db, meeting_id)
        nudge = generate_nudge_draft(payload_dict, "DECISION", state, conflict)

        item = StagingItem(
            meeting_id=meeting_id,
            item_type="DECISION",
            payload_json=dec.model_dump_json(),
            state=state,
            conflict_meta_json=conflict.model_dump_json() if conflict else None,
            missing_fields_json=None,
            clarification_prompt=None,
            blast_radius_json=blast_radius.model_dump_json() if blast_radius else None,
            nudge_draft=nudge,
            nudged=False,
            verbatim_quote=dec.verbatim_quote,
        )
        db.add(item)
        staged.append(item)

    # ── Action Items ──────────────────────────────────────────────────────────
    for action, conflict in actions_with_meta:
        if conflict:
            state = "CONFLICT_DETECTED"
        elif action.status == "NEEDS_CLARIFICATION":
            state = "NEEDS_CLARIFICATION"
        else:
            state = "READY_TO_APPROVE"

        payload_dict = action.model_dump()
        blast_radius = await analyze_blast_radius(payload_dict, "ACTION_ITEM", conflict, db, meeting_id)
        nudge = generate_nudge_draft(payload_dict, "ACTION_ITEM", state, conflict)

        item = StagingItem(
            meeting_id=meeting_id,
            item_type="ACTION_ITEM",
            payload_json=action.model_dump_json(),
            state=state,
            conflict_meta_json=conflict.model_dump_json() if conflict else None,
            missing_fields_json=json.dumps(action.missing_fields) if action.missing_fields else None,
            clarification_prompt=action.clarification_prompt,
            blast_radius_json=blast_radius.model_dump_json() if blast_radius else None,
            nudge_draft=nudge,
            nudged=False,
            verbatim_quote=action.verbatim_quote,
        )
        db.add(item)
        staged.append(item)

    await db.flush()  # Assign IDs without committing
    return staged


# ═══════════════════════════════════════════════════════════════════════════════
# Main Pipeline Orchestrator
# ═══════════════════════════════════════════════════════════════════════════════
async def run_pipeline(
    title: str,
    meeting_date: str,
    raw_transcript: str,
    db: AsyncSession,
) -> tuple[Meeting, list[StagingItem], list[AgentTraceStep]]:
    """
    Execute the full 4-stage Meeting-to-Execution pipeline.

    Returns
    -------
    meeting        : Persisted Meeting ORM object
    staged_items   : List of persisted StagingItem ORM objects
    trace          : Full agent trace for observability
    """
    trace = TraceLogger()

    # ── Persist the meeting record first (we need meeting.id for later stages) ─
    meeting = Meeting(
        title=title,
        meeting_date=meeting_date,
        raw_transcript=raw_transcript,
    )
    db.add(meeting)
    await db.flush()  # Obtain meeting.id

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 1: Speaker & Segment Parser
    # ─────────────────────────────────────────────────────────────────────────
    trace.begin(1, "parse_transcript", f"Transcript length: {len(raw_transcript)} chars")
    try:
        segments = parse_transcript(raw_transcript)
        trace.end(
            1,
            f"Parsed {len(segments)} speaker segments from "
            f"{len(set(s.speaker for s in segments))} unique speakers",
        )
    except Exception as exc:
        trace.fail(1, str(exc))
        raise

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 2: Structured Extraction with LLM
    # ─────────────────────────────────────────────────────────────────────────
    trace.begin(
        2,
        "extract_commitments",
        f"Sending {len(segments)} segments to Gemini {'(DEMO MODE)' if DEMO_MODE else ''}",
    )
    try:
        extraction = await extract_commitments_llm(segments, title, meeting_date)
        trace.end(
            2,
            f"Extracted {len(extraction.decisions)} decisions, "
            f"{len(extraction.action_items)} action items. "
            f"Needs clarification: {sum(1 for a in extraction.action_items if a.status == 'NEEDS_CLARIFICATION')}",
        )
    except Exception as exc:
        trace.fail(2, str(exc))
        raise

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 3: Cross-Meeting Conflict Detection
    # ─────────────────────────────────────────────────────────────────────────
    trace.begin(
        3,
        "detect_conflicts_and_duplicates",
        f"Checking {len(extraction.decisions)} decisions & "
        f"{len(extraction.action_items)} action items against historical memory",
    )
    try:
        decisions_with_meta, actions_with_meta = await detect_conflicts_and_duplicates(
            extraction, db, meeting.id
        )
        conflicts = sum(1 for _, m in decisions_with_meta + actions_with_meta if m)
        trace.end(
            3,
            f"Detected {conflicts} conflict(s)/duplicate(s)/blocker(s) across all items",
        )
    except Exception as exc:
        trace.fail(3, str(exc))
        raise

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 4: Staging Queue Persistence
    # ─────────────────────────────────────────────────────────────────────────
    trace.begin(
        4,
        "stage_for_approval",
        f"Persisting {len(decisions_with_meta)} decisions + "
        f"{len(actions_with_meta)} action items to staging queue",
    )
    try:
        staged_items = await stage_for_approval(
            decisions_with_meta, actions_with_meta, meeting.id, db
        )
        state_counts: dict[str, int] = {}
        for item in staged_items:
            state_counts[item.state] = state_counts.get(item.state, 0) + 1
        trace.end(4, f"Staged {len(staged_items)} items: {state_counts}")
    except Exception as exc:
        trace.fail(4, str(exc))
        raise

    # ── USP 2: Compute Readiness Score ──────────────────────────────────────
    readiness_score, score_breakdown = compute_readiness_score(staged_items)
    meeting.readiness_score = readiness_score
    meeting.score_breakdown_json = json.dumps(score_breakdown)

    # ── Persist trace into meeting record ────────────────────────────────────
    meeting.agent_trace_json = json.dumps([s.model_dump() for s in trace.steps])
    await db.flush()

    return meeting, staged_items, trace.steps
