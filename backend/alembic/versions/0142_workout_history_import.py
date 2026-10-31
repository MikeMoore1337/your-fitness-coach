"""Add short-lived import drafts and provenance for existing workout rows."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0142_workout_history_import"
down_revision: str | None = "0141_workout_history_nullable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = "Create empty import tables and indexes without changing existing rows."


def upgrade() -> None:
    op.create_table(
        "workout_history_import_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("parser_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("draft_json", sa.JSON(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'cancelled', 'expired')",
            name="ck_workout_history_import_draft_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_workout_history_import_draft_version"),
    )
    op.create_index(
        "ix_workout_history_import_drafts_expiry", "workout_history_import_drafts", ["expires_at"]
    )
    op.create_index(
        "ix_workout_history_import_drafts_owner",
        "workout_history_import_drafts",
        ["owner_user_id", "created_at"],
    )
    op.create_table(
        "imported_workouts",
        sa.Column(
            "workout_id",
            sa.Integer(),
            sa.ForeignKey("user_workouts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "owner_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("source_ref_hash", sa.String(64), nullable=False),
        sa.Column("fact_hash", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(32), nullable=False),
        sa.Column("source_timezone", sa.String(128), nullable=False),
        sa.UniqueConstraint(
            "owner_user_id", "provider", "source_ref_hash", name="uq_imported_workouts_source"
        ),
        sa.UniqueConstraint("owner_user_id", "fact_hash", name="uq_imported_workouts_facts"),
    )
    op.create_index("ix_imported_workouts_owner", "imported_workouts", ["owner_user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "LOCK TABLE workout_history_import_drafts, imported_workouts IN ACCESS EXCLUSIVE MODE"
        )
    if (
        bind.execute(sa.text("SELECT 1 FROM imported_workouts LIMIT 1")).first()
        or bind.execute(sa.text("SELECT 1 FROM workout_history_import_drafts LIMIT 1")).first()
    ):
        raise RuntimeError("Unsafe downgrade: imported workout history or drafts exist")
    op.drop_table("imported_workouts")
    op.drop_table("workout_history_import_drafts")
