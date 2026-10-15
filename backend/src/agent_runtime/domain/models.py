from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agent_runtime.db.base import Base, IdentityMixin, TimestampMixin


class PolicyAction(StrEnum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    PAUSE = "PAUSE"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class ReplayStatus(StrEnum):
    PENDING = "pending"
    PLANNED = "planned"
    BLOCKED = "blocked"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReplayMode(StrEnum):
    REEXECUTE_SAFE_TOOLS = "reexecute_safe_tools"
    REUSE_PRIOR_OUTPUTS = "reuse_prior_outputs"
    DRY_RUN_SIDE_EFFECTS = "dry_run_side_effects"


class ReplayCapability(StrEnum):
    COMPARE_ONLY = "compare_only"
    FULL_RERUN = "full_rerun"
    CHECKPOINT_REPLAY = "checkpoint_replay"


class ApprovalState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Project(IdentityMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    workflows: Mapped[list["WorkflowConfiguration"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class WorkflowConfiguration(IdentityMixin, TimestampMixin, Base):
    __tablename__ = "workflow_configurations"
    __table_args__ = (
        Index("ix_workflow_project_name_environment", "project_id", "name", "environment"),
    )

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str | None] = mapped_column(String(100))
    environment: Mapped[str] = mapped_column(String(50), nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    project: Mapped[Project] = relationship(back_populates="workflows")


class Policy(IdentityMixin, TimestampMixin, Base):
    __tablename__ = "policies"

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    action: Mapped[PolicyAction] = mapped_column(
        Enum(PolicyAction, native_enum=False, length=32), nullable=False
    )
    conditions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    fail_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ReplayRequest(IdentityMixin, TimestampMixin, Base):
    __tablename__ = "replay_requests"

    project_id: Mapped[UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    source_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mode: Mapped[ReplayMode] = mapped_column(
        Enum(ReplayMode, native_enum=False, length=32), nullable=False
    )
    status: Mapped[ReplayStatus] = mapped_column(
        Enum(ReplayStatus, native_enum=False, length=16), default=ReplayStatus.PENDING
    )
    requested_changes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    requested_capability: Mapped[ReplayCapability] = mapped_column(
        Enum(ReplayCapability, native_enum=False, length=32),
        default=ReplayCapability.FULL_RERUN,
        nullable=False,
    )
    resolved_capability: Mapped[ReplayCapability] = mapped_column(
        Enum(ReplayCapability, native_enum=False, length=32),
        default=ReplayCapability.COMPARE_ONLY,
        nullable=False,
    )
    checkpoint_id: Mapped[str | None] = mapped_column(String(200))
    adapter_id: Mapped[str] = mapped_column(String(100), default="generic", nullable=False)
    plan: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    output_run_id: Mapped[str | None] = mapped_column(String(64), index=True)
    external_reference: Mapped[str | None] = mapped_column(String(200))
    status_reason: Mapped[str | None] = mapped_column(Text)


class Approval(IdentityMixin, TimestampMixin, Base):
    __tablename__ = "approvals"

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    policy_id: Mapped[UUID | None] = mapped_column(ForeignKey("policies.id"))
    state: Mapped[ApprovalState] = mapped_column(
        Enum(ApprovalState, native_enum=False, length=16), default=ApprovalState.PENDING
    )
    action_summary: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    reviewer_reference: Mapped[str | None] = mapped_column(String(200))
    workflow_name: Mapped[str | None] = mapped_column(String(200))
    agent_name: Mapped[str | None] = mapped_column(String(200))
    tool_name: Mapped[str | None] = mapped_column(String(200))
    operation: Mapped[str | None] = mapped_column(String(200))
    confidence: Mapped[float | None] = mapped_column(Float)
    proposed_inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    match_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    integration_reference: Mapped[str | None] = mapped_column(String(200))


class PolicyDecision(IdentityMixin, TimestampMixin, Base):
    __tablename__ = "policy_decisions"

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[PolicyAction] = mapped_column(
        Enum(PolicyAction, native_enum=False, length=32), nullable=False
    )
    matched_policy_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evaluation_failed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    decision_made: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failure_behavior: Mapped[str | None] = mapped_column(String(32))


class ApprovalAuditEvent(IdentityMixin, Base):
    __tablename__ = "approval_audit_events"

    approval_id: Mapped[UUID] = mapped_column(
        ForeignKey("approvals.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_reference: Mapped[str | None] = mapped_column(String(200))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
