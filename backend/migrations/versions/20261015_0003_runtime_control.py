"""Add deterministic policy and approval control records."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261015_0003"
down_revision: str | None = "20261015_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

policy_action = sa.Enum(
    "ALLOW", "BLOCK", "PAUSE", "REQUIRE_APPROVAL",
    name="policyaction", native_enum=False, length=32,
)


def upgrade() -> None:
    op.add_column("policies", sa.Column("description", sa.Text()))
    op.add_column(
        "policies", sa.Column("priority", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("approvals", sa.Column("workflow_name", sa.String(200)))
    op.add_column("approvals", sa.Column("agent_name", sa.String(200)))
    op.add_column("approvals", sa.Column("tool_name", sa.String(200)))
    op.add_column("approvals", sa.Column("operation", sa.String(200)))
    op.add_column("approvals", sa.Column("confidence", sa.Float()))
    op.add_column(
        "approvals",
        sa.Column("proposed_inputs", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "approvals", sa.Column("match_reason", sa.Text(), nullable=False, server_default="")
    )
    op.add_column("approvals", sa.Column("resolved_at", sa.DateTime(timezone=True)))
    op.add_column("approvals", sa.Column("integration_reference", sa.String(200)))
    op.create_table(
        "policy_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("action", policy_action, nullable=False),
        sa.Column("matched_policy_ids", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("evaluation_failed", sa.Boolean(), nullable=False),
        sa.Column("decision_made", sa.Boolean(), nullable=False),
        sa.Column("failure_behavior", sa.String(32)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name=op.f("fk_policy_decisions_project_id_projects"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_decisions")),
    )
    op.create_index(op.f("ix_policy_decisions_run_id"), "policy_decisions", ["run_id"])
    op.create_table(
        "approval_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("actor_reference", sa.String(200)),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["approval_id"], ["approvals.id"],
            name=op.f("fk_approval_audit_events_approval_id_approvals"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_audit_events")),
    )
    op.create_index(
        op.f("ix_approval_audit_events_approval_id"),
        "approval_audit_events",
        ["approval_id"],
    )


def downgrade() -> None:
    op.drop_table("approval_audit_events")
    op.drop_table("policy_decisions")
    for column in (
        "integration_reference", "resolved_at", "match_reason", "proposed_inputs",
        "confidence", "operation", "tool_name", "agent_name", "workflow_name",
    ):
        op.drop_column("approvals", column)
    op.drop_column("policies", "priority")
    op.drop_column("policies", "description")
