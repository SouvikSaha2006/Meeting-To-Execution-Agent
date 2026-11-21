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

from backend.models import Decision, Meeting, StagingItem
from backend.schemas import (
    AgentTraceStep,
    ConflictMeta,
    LLMActionItem,
    LLMDecision,
    LLMExtractionResult,
    SpeakerSegment,
)

logger = logging.getLogger(__name__)

DEMO_MODE: bool = os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "yes")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = "gemini-2.5-flash"


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

    if DEMO_MODE or not GEMINI_API_KEY:
        logger.info("DEMO_MODE active — using mock extraction result")
        return _mock_extraction_result(title, meeting_date)

    try:
        import google.genai as genai
        from google.genai import types as genai_types

        client = genai.Client(api_key=GEMINI_API_KEY)

        response = client.models.generate_content(
            model=GEMINI_MODEL,
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
# Stage 4: Human-in-the-Loop Staging Queue
# ═══════════════════════════════════════════════════════════════════════════════
async def stage_for_approval(
    decisions_with_meta: list[tuple[LLMDecision, Optional[ConflictMeta]]],
    actions_with_meta: list[tuple[LLMActionItem, Optional[ConflictMeta]]],
    meeting_id: int,
    db: AsyncSession,
) -> list[StagingItem]:
    """Persist all extracted items into the staging_items table."""
    staged: list[StagingItem] = []

    # ── Decisions ─────────────────────────────────────────────────────────────
    for dec, conflict in decisions_with_meta:
        if conflict:
            state = "CONFLICT_DETECTED"
        else:
            state = "READY_TO_APPROVE"

        item = StagingItem(
            meeting_id=meeting_id,
            item_type="DECISION",
            payload_json=dec.model_dump_json(),
            state=state,
            conflict_meta_json=conflict.model_dump_json() if conflict else None,
            missing_fields_json=None,
            clarification_prompt=None,
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

        item = StagingItem(
            meeting_id=meeting_id,
            item_type="ACTION_ITEM",
            payload_json=action.model_dump_json(),
            state=state,
            conflict_meta_json=conflict.model_dump_json() if conflict else None,
            missing_fields_json=json.dumps(action.missing_fields) if action.missing_fields else None,
            clarification_prompt=action.clarification_prompt,
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

    # ── Persist trace into meeting record ────────────────────────────────────
    meeting.agent_trace_json = json.dumps([s.model_dump() for s in trace.steps])

    return meeting, staged_items, trace.steps
