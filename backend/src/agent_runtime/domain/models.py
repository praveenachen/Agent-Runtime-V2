from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agent_runtime.db.base import Base, IdentityMixin, TimestampMixin


class PolicyAction(StrEnum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    PAUSE = "PAUSE"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class ReplayStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReplayMode(StrEnum):
    REEXECUTE_SAFE_TOOLS = "reexecute_safe_tools"
    REUSE_PRIOR_OUTPUTS = "reuse_prior_outputs"
    DRY_RUN_SIDE_EFFECTS = "dry_run_side_effects"


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
    active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    action: Mapped[PolicyAction] = mapped_column(
        Enum(PolicyAction, native_enum=False, length=32), nullable=False
    )
    conditions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    fail_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ReplayRequest(IdentityMixin, TimestampMixin, Base):
    __tablename__ = "replay_requests"

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    source_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mode: Mapped[ReplayMode] = mapped_column(
        Enum(ReplayMode, native_enum=False, length=32), nullable=False
    )
    status: Mapped[ReplayStatus] = mapped_column(
        Enum(ReplayStatus, native_enum=False, length=16), default=ReplayStatus.PENDING
    )
    requested_changes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


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

