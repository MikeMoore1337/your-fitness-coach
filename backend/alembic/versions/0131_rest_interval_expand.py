"""Expand measured rest lineage; indexes are built before the single-slot constraint swap."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0131_rest_interval_expand"
down_revision: str | None = "0130_workout_rest_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Three nullable metadata-only columns plus four PostgreSQL CONCURRENTLY unique indexes. "
    "Existing rows remain predecessor=NULL and start_mutation_id=NULL. "
    "An existing multi-running workout fails the new unique index, without changing its facts. "
    "Concurrent indexes can wait for long transactions; use isolated PG16 timing and a "
    "bounded maintenance window before enabling the replacement API."
)


def upgrade() -> None:
    op.add_column("workout_rest_sessions", sa.Column("predecessor_id", sa.Integer(), nullable=True))
    op.add_column("workout_rest_sessions", sa.Column("start_mutation_id", sa.String(64), nullable=True))
    op.add_column("workout_rest_sessions", sa.Column("start_fingerprint", sa.String(64), nullable=True))
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.create_index(
                "uq_workout_rest_initial_source", "workout_rest_sessions", ["source_set_id"],
                unique=True, postgresql_where=sa.text("predecessor_id IS NULL"),
                sqlite_where=sa.text("predecessor_id IS NULL"),
                postgresql_concurrently=True, if_not_exists=True,
            )
            op.create_index(
                "uq_workout_rest_predecessor", "workout_rest_sessions", ["predecessor_id"],
                unique=True, postgresql_concurrently=True, if_not_exists=True,
            )
            op.create_index(
                "uq_workout_rest_start_mutation", "workout_rest_sessions",
                ["workout_id", "start_mutation_id"], unique=True,
                postgresql_concurrently=True, if_not_exists=True,
            )
            op.create_index(
                "uq_workout_rest_running_workout", "workout_rest_sessions", ["workout_id"],
                unique=True, postgresql_where=sa.text("status = 'running'"),
                sqlite_where=sa.text("status = 'running'"),
                postgresql_concurrently=True, if_not_exists=True,
            )
    else:
        op.create_index(
            "uq_workout_rest_initial_source", "workout_rest_sessions", ["source_set_id"],
            unique=True, postgresql_where=sa.text("predecessor_id IS NULL"),
            sqlite_where=sa.text("predecessor_id IS NULL"),
            postgresql_concurrently=True, if_not_exists=True,
        )
        op.create_index(
            "uq_workout_rest_predecessor", "workout_rest_sessions", ["predecessor_id"],
            unique=True, postgresql_concurrently=True, if_not_exists=True,
        )
        op.create_index(
            "uq_workout_rest_start_mutation", "workout_rest_sessions",
            ["workout_id", "start_mutation_id"], unique=True,
            postgresql_concurrently=True, if_not_exists=True,
        )
        op.create_index(
            "uq_workout_rest_running_workout", "workout_rest_sessions", ["workout_id"],
            unique=True, postgresql_where=sa.text("status = 'running'"),
            sqlite_where=sa.text("status = 'running'"),
            postgresql_concurrently=True, if_not_exists=True,
        )


def downgrade() -> None:
    op.drop_index("uq_workout_rest_running_workout", table_name="workout_rest_sessions")
    op.drop_index("uq_workout_rest_start_mutation", table_name="workout_rest_sessions")
    op.drop_index("uq_workout_rest_predecessor", table_name="workout_rest_sessions")
    op.drop_index("uq_workout_rest_initial_source", table_name="workout_rest_sessions")
    op.drop_column("workout_rest_sessions", "start_fingerprint")
    op.drop_column("workout_rest_sessions", "start_mutation_id")
    op.drop_column("workout_rest_sessions", "predecessor_id")
