"""Extend replay requests with capability and safety planning state."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261015_0002"
down_revision: str | None = "20261015_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

replay_capability = sa.Enum(
    "COMPARE_ONLY",
    "FULL_RERUN",
    "CHECKPOINT_REPLAY",
    name="replaycapability",
    native_enum=False,
    length=32,
)


def upgrade() -> None:
    op.alter_column("replay_requests", "project_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column(
        "replay_requests",
        sa.Column(
            "requested_capability",
            replay_capability,
            nullable=False,
            server_default="FULL_RERUN",
        ),
    )
    op.add_column(
        "replay_requests",
        sa.Column(
            "resolved_capability",
            replay_capability,
            nullable=False,
            server_default="COMPARE_ONLY",
        ),
    )
    op.add_column("replay_requests", sa.Column("checkpoint_id", sa.String(200)))
    op.add_column(
        "replay_requests",
        sa.Column("adapter_id", sa.String(100), nullable=False, server_default="generic"),
    )
    op.add_column(
        "replay_requests",
        sa.Column("plan", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column("replay_requests", sa.Column("output_run_id", sa.String(64)))
    op.add_column("replay_requests", sa.Column("external_reference", sa.String(200)))
    op.add_column("replay_requests", sa.Column("status_reason", sa.Text()))
    op.create_index(op.f("ix_replay_requests_output_run_id"), "replay_requests", ["output_run_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_replay_requests_output_run_id"), table_name="replay_requests")
    for column in (
        "status_reason",
        "external_reference",
        "output_run_id",
        "plan",
        "adapter_id",
        "checkpoint_id",
        "resolved_capability",
        "requested_capability",
    ):
        op.drop_column("replay_requests", column)
    op.alter_column("replay_requests", "project_id", existing_type=sa.Uuid(), nullable=False)
