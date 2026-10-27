"""Backfill legacy program provenance from stable ownership and catalog identity."""

from collections.abc import Sequence

from alembic import op

revision: str = "0095_program_provenance_backfill"
down_revision: str | None = "0094_program_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "backfill"
online_rollout_notes = (
    "Updates at most 1000 legacy templates per batch in id order, prioritizing system-owned public "
    "catalog rows. The update is idempotent and touches only NULL provenance_type values. The "
    "eight source-adaptation slugs follow the approved Stage 3C catalog; other system-owned public "
    "templates are YFC_GENERIC and user-owned or private templates are CUSTOM. Serializers keep "
    "NULL values readable during expand/backfill coexistence."
)
online_rollout_batch_size = 1000
online_rollout_idempotent = True


def upgrade() -> None:
    op.execute(
        """UPDATE program_templates
        SET provenance_type = CASE
            WHEN owner_user_id IS NOT NULL OR created_by_user_id IS NOT NULL THEN 'CUSTOM'
            WHEN slug IN (
                'stronglifts-5x5',
                'gzclp',
                '531-for-beginners',
                'phul',
                'nsuns-4d',
                'metallicdpa-linear-progression-ppl',
                'bwf-recommended-routine',
                'dumbbell-ppl-gregarioushermit'
            ) THEN 'SOURCE_ADAPTATION'
            WHEN is_public = TRUE THEN 'YFC_GENERIC'
            ELSE 'CUSTOM'
        END
        WHERE id IN (
            SELECT id
            FROM program_templates
            WHERE provenance_type IS NULL
            ORDER BY CASE
                WHEN owner_user_id IS NULL
                    AND created_by_user_id IS NULL
                    AND is_public = TRUE THEN 0
                ELSE 1
            END, id
            LIMIT 1000
        )"""
    )


def downgrade() -> None:
    pass
