"""add provider metadata used by personal dashboard

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("series") as batch_op:
        batch_op.add_column(sa.Column("genres", sa.JSON(), nullable=False, server_default="[]"))
        batch_op.add_column(sa.Column("average_rating", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("rating_source", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("episode_runtime_minutes", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "average_rating_range",
            "average_rating IS NULL OR (average_rating >= 0 AND average_rating <= 100)",
        )
        batch_op.create_check_constraint(
            "episode_runtime_positive",
            "episode_runtime_minutes IS NULL OR episode_runtime_minutes > 0",
        )

    with op.batch_alter_table("episodes") as batch_op:
        batch_op.add_column(sa.Column("duration_minutes", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "duration_positive",
            "duration_minutes IS NULL OR duration_minutes > 0",
        )
        batch_op.create_index(
            "ix_episodes_series_air_date", ["series_id", "air_date"], unique=False
        )

    with op.batch_alter_table("watched_episodes") as batch_op:
        batch_op.create_index(
            "ix_watched_episodes_user_watched_at",
            ["user_id", "watched_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("watched_episodes") as batch_op:
        batch_op.drop_index("ix_watched_episodes_user_watched_at")

    with op.batch_alter_table("episodes") as batch_op:
        batch_op.drop_index("ix_episodes_series_air_date")
        batch_op.drop_constraint("duration_positive", type_="check")
        batch_op.drop_column("duration_minutes")

    with op.batch_alter_table("series") as batch_op:
        batch_op.drop_constraint("episode_runtime_positive", type_="check")
        batch_op.drop_constraint("average_rating_range", type_="check")
        batch_op.drop_column("episode_runtime_minutes")
        batch_op.drop_column("rating_source")
        batch_op.drop_column("average_rating")
        batch_op.drop_column("genres")
