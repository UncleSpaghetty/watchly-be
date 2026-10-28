"""store only episode dates supplied by catalog providers

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("episode_availability")
    op.drop_table("services")

    with op.batch_alter_table("data_sources") as batch_op:
        batch_op.drop_constraint(
            batch_op.f("ck_data_sources_validated_has_date"), type_="check"
        )
        batch_op.drop_column("italy_episode_availability_validated")
        batch_op.drop_column("validated_at")

    with op.batch_alter_table("episodes") as batch_op:
        batch_op.drop_index("ix_episodes_original_air_date")
    with op.batch_alter_table("episodes") as batch_op:
        batch_op.alter_column("original_air_at", new_column_name="air_at")
        batch_op.alter_column("original_air_date", new_column_name="air_date")
    with op.batch_alter_table("episodes") as batch_op:
        batch_op.create_index("ix_episodes_air_date", ["air_date"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("episodes") as batch_op:
        batch_op.drop_index("ix_episodes_air_date")
    with op.batch_alter_table("episodes") as batch_op:
        batch_op.alter_column("air_at", new_column_name="original_air_at")
        batch_op.alter_column("air_date", new_column_name="original_air_date")
    with op.batch_alter_table("episodes") as batch_op:
        batch_op.create_index(
            "ix_episodes_original_air_date", ["original_air_date"], unique=False
        )

    with op.batch_alter_table("data_sources") as batch_op:
        batch_op.add_column(
            sa.Column(
                "italy_episode_availability_validated",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_check_constraint(
            batch_op.f("ck_data_sources_validated_has_date"),
            "NOT italy_episode_availability_validated OR validated_at IS NOT NULL",
        )

    op.create_table(
        "services",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("country_scope", sa.String(length=2), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_services"),
    )
    op.create_table(
        "episode_availability",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("episode_id", sa.Uuid(), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("service_id", sa.String(length=50), nullable=False),
        sa.Column("available_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_local_date", sa.Date(), nullable=True),
        sa.Column("precision", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("source_id", sa.String(length=50), nullable=False),
        sa.Column("source_record_id", sa.String(length=200), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("evidence_type", sa.String(length=50), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["data_sources.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_episode_availability"),
    )
