"""Bind approvals to immutable evaluated action context."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0004"
down_revision: str | None = "20261015_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "approvals", "run_id", existing_type=sa.String(length=64), type_=sa.String(length=200)
    )
    op.alter_column(
        "policy_decisions",
        "run_id",
        existing_type=sa.String(length=64),
        type_=sa.String(length=200),
    )
    op.add_column("approvals", sa.Column("policy_revision", sa.String(length=64)))
    op.add_column("approvals", sa.Column("control_reference", sa.String(length=200)))
    op.add_column("approvals", sa.Column("context_hash", sa.String(length=64)))
    op.add_column("approvals", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.create_index(op.f("ix_approvals_policy_revision"), "approvals", ["policy_revision"])
    op.create_index(op.f("ix_approvals_control_reference"), "approvals", ["control_reference"])
    op.create_index(op.f("ix_approvals_context_hash"), "approvals", ["context_hash"])
    op.add_column(
        "policy_decisions",
        sa.Column(
            "authorization_source",
            sa.String(length=32),
            nullable=False,
            server_default="direct_policy",
        ),
    )
    op.add_column(
        "policy_decisions", sa.Column("authorizing_approval_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_policy_decisions_authorizing_approval_id_approvals"),
        "policy_decisions",
        "approvals",
        ["authorizing_approval_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_policy_decisions_authorizing_approval_id_approvals"),
        "policy_decisions",
        type_="foreignkey",
    )
    op.drop_column("policy_decisions", "authorizing_approval_id")
    op.drop_column("policy_decisions", "authorization_source")
    op.drop_index(op.f("ix_approvals_context_hash"), table_name="approvals")
    op.drop_index(op.f("ix_approvals_control_reference"), table_name="approvals")
    op.drop_index(op.f("ix_approvals_policy_revision"), table_name="approvals")
    op.drop_column("approvals", "expires_at")
    op.drop_column("approvals", "context_hash")
    op.drop_column("approvals", "control_reference")
    op.drop_column("approvals", "policy_revision")
    op.alter_column(
        "policy_decisions",
        "run_id",
        existing_type=sa.String(length=200),
        type_=sa.String(length=64),
    )
    op.alter_column(
        "approvals", "run_id", existing_type=sa.String(length=200), type_=sa.String(length=64)
    )
