"""
models.py — SQLAlchemy ORM models for Meeting-to-Execution Agent.

Tables
------
meetings          : Ingested meeting records + raw transcript + agent trace
decisions         : Extracted decisions with active/superseded lifecycle
staging_items     : Human-in-the-Loop approval queue
execution_tasks   : Approved, actionable tasks on the execution board
"""
from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


# ── Helpers ──────────────────────────────────────────────────────────────────
def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# ── Meeting ──────────────────────────────────────────────────────────────────
class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    meeting_date: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="ISO 8601 date string, e.g. 2024-11-14"
    )
    raw_transcript: Mapped[str] = mapped_column(Text, nullable=False)
    agent_trace_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="JSON array of AgentTraceStep objects"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )

    # Relationships
    decisions: Mapped[list["Decision"]] = relationship(
        "Decision", back_populates="meeting", cascade="all, delete-orphan"
    )
    staging_items: Mapped[list["StagingItem"]] = relationship(
        "StagingItem", back_populates="meeting", cascade="all, delete-orphan"
    )
    execution_tasks: Mapped[list["ExecutionTask"]] = relationship(
        "ExecutionTask", back_populates="meeting", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Meeting id={self.id} title={self.title!r}>"


# ── Decision ─────────────────────────────────────────────────────────────────
class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    meeting_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    topic_key: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="Short machine-readable topic slug"
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    verbatim_quote: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True, comment="HIGH | MEDIUM | LOW"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="ACTIVE",
        comment="ACTIVE | SUPERSEDED",
    )
    superseded_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("decisions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )

    # Relationships
    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="decisions")
    superseded_by: Mapped[Optional["Decision"]] = relationship(
        "Decision", remote_side="Decision.id", foreign_keys=[superseded_by_id]
    )

    def __repr__(self) -> str:
        return f"<Decision id={self.id} topic={self.topic_key!r} status={self.status}>"


# ── StagingItem ───────────────────────────────────────────────────────────────
class StagingItem(Base):
    __tablename__ = "staging_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    meeting_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="DECISION | ACTION_ITEM"
    )
    payload_json: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Serialised extracted decision or action_item"
    )
    state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="READY_TO_APPROVE",
        comment="READY_TO_APPROVE | CONFLICT_DETECTED | NEEDS_CLARIFICATION | APPROVED | REJECTED",
    )
    conflict_meta_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="ConflictMeta JSON if state=CONFLICT_DETECTED"
    )
    missing_fields_json: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment='JSON array of missing field names, e.g. ["owner","deadline"]',
    )
    clarification_prompt: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Human-readable prompt for missing info"
    )
    verbatim_quote: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )

    # Relationships
    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="staging_items")
    execution_task: Mapped[Optional["ExecutionTask"]] = relationship(
        "ExecutionTask", back_populates="staging_item", uselist=False
    )

    def __repr__(self) -> str:
        return f"<StagingItem id={self.id} type={self.item_type} state={self.state}>"


# ── ExecutionTask ─────────────────────────────────────────────────────────────
class ExecutionTask(Base):
    __tablename__ = "execution_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    staging_item_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("staging_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    meeting_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    deadline_iso: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, default="MEDIUM", comment="HIGH | MEDIUM | LOW"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="TODO",
        comment="TODO | IN_PROGRESS | DONE",
    )
    depends_on_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("execution_tasks.id", ondelete="SET NULL"), nullable=True
    )
    external_execution_receipt_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="JSON receipt from GitHub / Webhook dispatcher"
    )
    approved_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="execution_tasks")
    staging_item: Mapped[Optional["StagingItem"]] = relationship(
        "StagingItem", back_populates="execution_task"
    )
    depends_on: Mapped[Optional["ExecutionTask"]] = relationship(
        "ExecutionTask", remote_side="ExecutionTask.id", foreign_keys=[depends_on_id]
    )

    def __repr__(self) -> str:
        return f"<ExecutionTask id={self.id} title={self.title!r} status={self.status}>"
