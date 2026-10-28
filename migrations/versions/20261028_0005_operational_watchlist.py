"""operational watchlist, notification preferences and news state

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("following", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("watch_status", sa.String(length=20), nullable=False, server_default="in_list")
        )
        batch_op.add_column(
            sa.Column("favorite", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column(
                "status_updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            )
        )
        batch_op.create_check_constraint(
            "ck_following_watch_status",
            "watch_status IN ('in_list', 'planned', 'watching', 'paused', 'completed', 'dropped')",
        )

    with op.batch_alter_table("series", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("watch_providers", sa.JSON(), nullable=False, server_default="[]")
        )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("notification_quiet_start", sa.String(5), nullable=True))
        batch_op.add_column(sa.Column("notification_quiet_end", sa.String(5), nullable=True))
        batch_op.add_column(
            sa.Column("notification_lead_days", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("notify_releases", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.add_column(
            sa.Column(
                "notify_schedule_changes", sa.Boolean(), nullable=False, server_default=sa.true()
            )
        )
        batch_op.add_column(
            sa.Column("notify_new_seasons", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.add_column(
            sa.Column("notify_news", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("weekly_digest", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("preferred_services", sa.JSON(), nullable=False, server_default="[]")
        )

    op.create_table(
        "user_news_states",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("news_id", sa.Uuid(), nullable=False),
        sa.Column("saved", sa.Boolean(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["news_id"], ["news_articles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "news_id"),
    )


def downgrade() -> None:
    op.drop_table("user_news_states")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("preferred_services")
        batch_op.drop_column("weekly_digest")
        batch_op.drop_column("notify_news")
        batch_op.drop_column("notify_new_seasons")
        batch_op.drop_column("notify_schedule_changes")
        batch_op.drop_column("notify_releases")
        batch_op.drop_column("notification_lead_days")
        batch_op.drop_column("notification_quiet_end")
        batch_op.drop_column("notification_quiet_start")
    with op.batch_alter_table("series", schema=None) as batch_op:
        batch_op.drop_column("watch_providers")
    with op.batch_alter_table("following", schema=None) as batch_op:
        batch_op.drop_constraint("ck_following_watch_status", type_="check")
        batch_op.drop_column("status_updated_at")
        batch_op.drop_column("favorite")
        batch_op.drop_column("watch_status")
