from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.timeutils import utc_now


def new_uuid() -> str:
    return str(uuid4())


class Router(Base):
    __tablename__ = "routers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_snapshot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_boot_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    credentials: Mapped[list[RouterCredential]] = relationship(
        back_populates="router", cascade="all, delete-orphan"
    )
    sources: Mapped[list[Source]] = relationship(
        back_populates="router", cascade="all, delete-orphan"
    )
    events: Mapped[list[VPNEvent]] = relationship(
        back_populates="router", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[VPNSession]] = relationship(
        back_populates="router", cascade="all, delete-orphan"
    )


class RouterCredential(Base):
    __tablename__ = "router_credentials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    router_id: Mapped[str] = mapped_column(
        ForeignKey("routers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utc_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    router: Mapped[Router] = relationship(back_populates="credentials")


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("router_id", "name", name="uq_sources_router_name"),
        Index("ix_sources_router_enabled", "router_id", "enabled"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    router_id: Mapped[str] = mapped_column(
        ForeignKey("routers.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    services: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    profiles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    interfaces: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    router: Mapped[Router] = relationship(back_populates="sources")
    events: Mapped[list[VPNEvent]] = relationship(back_populates="source")
    sessions: Mapped[list[VPNSession]] = relationship(back_populates="source")


class VPNEvent(Base):
    __tablename__ = "vpn_events"
    __table_args__ = (
        UniqueConstraint("router_id", "external_event_id", name="uq_vpn_events_router_external"),
        Index("ix_vpn_events_router_occurred", "router_id", "occurred_at"),
        Index("ix_vpn_events_source_occurred", "source_id", "occurred_at"),
        Index("ix_vpn_events_router_username", "router_id", "username"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    router_id: Mapped[str] = mapped_column(
        ForeignKey("routers.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    external_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    service: Mapped[str] = mapped_column(String(32), nullable=False)
    caller_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    local_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remote_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    interface_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utc_now)
    payload_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    router: Mapped[Router] = relationship(back_populates="events")
    source: Mapped[Source] = relationship(back_populates="events")


class VPNSession(Base):
    __tablename__ = "vpn_sessions"
    __table_args__ = (
        Index("ix_vpn_sessions_router_state", "router_id", "state"),
        Index("ix_vpn_sessions_source_state", "source_id", "state"),
        Index("ix_vpn_sessions_router_connected", "router_id", "connected_at"),
        Index("ix_vpn_sessions_router_username", "router_id", "username"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    router_id: Mapped[str] = mapped_column(
        ForeignKey("routers.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    router_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    service: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="EVENT")
    caller_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vpn_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    local_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    interface_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    router_boot_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    router: Mapped[Router] = relationship(back_populates="sessions")
    source: Mapped[Source] = relationship(back_populates="sessions")
