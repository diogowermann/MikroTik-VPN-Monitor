"""Create initial VPN monitoring domain tables.

Revision ID: 20260824_0001
Revises:
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260824_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "routers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("last_snapshot_at", sa.DateTime(), nullable=True),
        sa.Column("last_boot_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "router_credentials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("router_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["router_id"], ["routers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_router_credentials_router_id", "router_credentials", ["router_id"])

    op.create_table(
        "sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("router_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("services", sa.JSON(), nullable=False),
        sa.Column("profiles", sa.JSON(), nullable=False),
        sa.Column("interfaces", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["router_id"], ["routers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("router_id", "name", name="uq_sources_router_name"),
    )
    op.create_index("ix_sources_router_enabled", "sources", ["router_id", "enabled"])

    op.create_table(
        "vpn_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("router_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("external_event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("service", sa.String(length=32), nullable=False),
        sa.Column("caller_id", sa.String(length=255), nullable=True),
        sa.Column("local_address", sa.String(length=64), nullable=True),
        sa.Column("remote_address", sa.String(length=64), nullable=True),
        sa.Column("interface_id", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("payload_version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["router_id"], ["routers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("router_id", "external_event_id", name="uq_vpn_events_router_external"),
    )
    op.create_index("ix_vpn_events_router_occurred", "vpn_events", ["router_id", "occurred_at"])
    op.create_index("ix_vpn_events_source_occurred", "vpn_events", ["source_id", "occurred_at"])
    op.create_index("ix_vpn_events_router_username", "vpn_events", ["router_id", "username"])

    op.create_table(
        "vpn_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("router_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("router_session_id", sa.String(length=128), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("service", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False, server_default="EVENT"),
        sa.Column("caller_id", sa.String(length=255), nullable=True),
        sa.Column("vpn_address", sa.String(length=64), nullable=True),
        sa.Column("local_address", sa.String(length=64), nullable=True),
        sa.Column("interface_id", sa.String(length=255), nullable=True),
        sa.Column("router_boot_id", sa.String(length=128), nullable=True),
        sa.Column("connected_at", sa.DateTime(), nullable=False),
        sa.Column("disconnected_at", sa.DateTime(), nullable=True),
        sa.Column("last_observed_at", sa.DateTime(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("end_reason", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["router_id"], ["routers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vpn_sessions_router_state", "vpn_sessions", ["router_id", "state"])
    op.create_index("ix_vpn_sessions_source_state", "vpn_sessions", ["source_id", "state"])
    op.create_index("ix_vpn_sessions_router_connected", "vpn_sessions", ["router_id", "connected_at"])
    op.create_index("ix_vpn_sessions_router_username", "vpn_sessions", ["router_id", "username"])


def downgrade() -> None:
    op.drop_index("ix_vpn_sessions_router_username", table_name="vpn_sessions")
    op.drop_index("ix_vpn_sessions_router_connected", table_name="vpn_sessions")
    op.drop_index("ix_vpn_sessions_source_state", table_name="vpn_sessions")
    op.drop_index("ix_vpn_sessions_router_state", table_name="vpn_sessions")
    op.drop_table("vpn_sessions")

    op.drop_index("ix_vpn_events_router_username", table_name="vpn_events")
    op.drop_index("ix_vpn_events_source_occurred", table_name="vpn_events")
    op.drop_index("ix_vpn_events_router_occurred", table_name="vpn_events")
    op.drop_table("vpn_events")

    op.drop_index("ix_sources_router_enabled", table_name="sources")
    op.drop_table("sources")

    op.drop_index("ix_router_credentials_router_id", table_name="router_credentials")
    op.drop_table("router_credentials")
    op.drop_table("routers")
