"""Add additive provenance and product metadata to program templates."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0094_program_provenance"
down_revision: str | None = "0093_advanced_prescriptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_PROVENANCE_CHECK = (
    "provenance_type IN ('YFC_GENERIC', 'SOURCE_ADAPTATION', 'CUSTOM')"
)


def upgrade() -> None:
    with op.batch_alter_table("program_templates") as batch_op:
        batch_op.add_column(
            sa.Column(
                "provenance_type",
                sa.String(length=24),
                nullable=False,
                server_default="CUSTOM",
            )
        )
        batch_op.add_column(sa.Column("provenance", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("program_metadata", sa.JSON(), nullable=True))
        batch_op.create_check_constraint(
            "ck_program_templates_provenance_type",
            _PROVENANCE_CHECK,
        )
        batch_op.create_index(
            "ix_program_templates_provenance_type",
            ["provenance_type"],
        )


def downgrade() -> None:
    with op.batch_alter_table("program_templates") as batch_op:
        batch_op.drop_index("ix_program_templates_provenance_type")
        batch_op.drop_constraint("ck_program_templates_provenance_type", type_="check")
        batch_op.drop_column("program_metadata")
        batch_op.drop_column("provenance")
        batch_op.drop_column("provenance_type")
