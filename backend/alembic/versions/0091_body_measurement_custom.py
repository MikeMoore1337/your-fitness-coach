"""Add owner-scoped custom body measurements and handoff comments."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0091_body_measurement_custom"
down_revision: str | None = "0090_nutrition_power_features"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds empty owner-scoped custom measurement tables and one nullable report-handoff comment. "
    "Existing body measurements remain valid and the new child values are bounded to centimetres."
)


def upgrade() -> None:
    op.add_column(
        "report_handoffs",
        sa.Column("client_comment", sa.Text(), nullable=True),
    )

    op.create_table(
        "body_measurement_definitions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey(
                "users.id",
                name="body_measurement_definitions_user_id_fkey",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("normalized_label", sa.String(length=64), nullable=False),
        sa.Column("unit", sa.String(length=8), server_default="cm", nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(label)) BETWEEN 1 AND 64",
            name="ck_body_measurement_definitions_label_length",
        ),
        sa.CheckConstraint(
            "length(trim(normalized_label)) BETWEEN 1 AND 64",
            name="ck_body_measurement_definitions_normalized_label_length",
        ),
        sa.CheckConstraint("unit = 'cm'", name="ck_body_measurement_definitions_unit"),
        sa.UniqueConstraint(
            "user_id",
            "normalized_label",
            name="uq_body_measurement_definition_user_label",
        ),
        sa.PrimaryKeyConstraint("id", name="body_measurement_definitions_pkey"),
    )
    op.create_index(
        "ix_body_measurement_definitions_user_archived",
        "body_measurement_definitions",
        ["user_id", "archived_at", "id"],
    )

    op.create_table(
        "body_measurement_custom_values",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "measurement_id",
            sa.Integer(),
            sa.ForeignKey(
                "body_measurements.id",
                name="body_measurement_custom_values_measurement_id_fkey",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "definition_id",
            sa.Integer(),
            sa.ForeignKey(
                "body_measurement_definitions.id",
                name="body_measurement_custom_values_definition_id_fkey",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "value > 0 AND value <= 300",
            name="ck_body_measurement_custom_values_range",
        ),
        sa.UniqueConstraint(
            "measurement_id",
            "definition_id",
            name="uq_body_measurement_custom_value_measurement_definition",
        ),
        sa.PrimaryKeyConstraint("id", name="body_measurement_custom_values_pkey"),
    )
    op.create_index(
        "ix_body_measurement_custom_values_definition_measurement",
        "body_measurement_custom_values",
        ["definition_id", "measurement_id"],
    )
    op.create_index(
        "ix_body_measurement_custom_values_measurement",
        "body_measurement_custom_values",
        ["measurement_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_body_measurement_custom_values_measurement",
        table_name="body_measurement_custom_values",
    )
    op.drop_index(
        "ix_body_measurement_custom_values_definition_measurement",
        table_name="body_measurement_custom_values",
    )
    op.drop_table("body_measurement_custom_values")
    op.drop_index(
        "ix_body_measurement_definitions_user_archived",
        table_name="body_measurement_definitions",
    )
    op.drop_table("body_measurement_definitions")
    op.drop_column("report_handoffs", "client_comment")
