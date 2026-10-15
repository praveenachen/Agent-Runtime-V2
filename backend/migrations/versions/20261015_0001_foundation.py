"""Create Milestone 1 application-state tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261015_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

policy_action = sa.Enum(
    "ALLOW",
    "BLOCK",
    "PAUSE",
    "REQUIRE_APPROVAL",
    name="policyaction",
    native_enum=False,
    length=32,
)
replay_mode = sa.Enum(
    "REEXECUTE_SAFE_TOOLS",
    "REUSE_PRIOR_OUTPUTS",
    "DRY_RUN_SIDE_EFFECTS",
    name="replaymode",
    native_enum=False,
    length=32,
)
replay_status = sa.Enum(
    "PENDING",
    "RUNNING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    name="replaystatus",
    native_enum=False,
    length=16,
)
approval_state = sa.Enum(
    "PENDING",
    "APPROVED",
    "REJECTED",
    "EXPIRED",
    name="approvalstate",
    native_enum=False,
    length=16,
)


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
        sa.UniqueConstraint("slug", name=op.f("uq_projects_slug")),
    )
    op.create_table(
        "workflow_configurations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.String(length=100)),
        sa.Column("environment", sa.String(length=50), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_workflow_configurations_project_id_projects"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_configurations")),
    )
    op.create_index(
        "ix_workflow_project_name_environment",
        "workflow_configurations",
        ["project_id", "name", "environment"],
    )
    op.create_table(
        "policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("action", policy_action, nullable=False),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("fail_closed", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_policies_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policies")),
    )
    op.create_table(
        "replay_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_run_id", sa.String(length=64), nullable=False),
        sa.Column("mode", replay_mode, nullable=False),
        sa.Column("status", replay_status, nullable=False),
        sa.Column("requested_changes", sa.JSON(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_replay_requests_project_id_projects"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_replay_requests")),
    )
    op.create_index(op.f("ix_replay_requests_source_run_id"), "replay_requests", ["source_run_id"])
    op.create_table(
        "approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("policy_id", sa.Uuid()),
        sa.Column("state", approval_state, nullable=False),
        sa.Column("action_summary", sa.Text(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("reviewer_reference", sa.String(length=200)),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["policy_id"], ["policies.id"], name=op.f("fk_approvals_policy_id_policies")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_approvals_project_id_projects"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approvals")),
    )
    op.create_index(op.f("ix_approvals_run_id"), "approvals", ["run_id"])


def downgrade() -> None:
    op.drop_table("approvals")
    op.drop_table("replay_requests")
    op.drop_table("policies")
    op.drop_table("workflow_configurations")
    op.drop_table("projects")

