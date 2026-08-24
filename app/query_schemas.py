from datetime import datetime

from pydantic import BaseModel


class QuerySummary(BaseModel):
    routers_enabled: int
    sources_enabled: int
    active_sessions: int
    active_users: int
    sessions_24h: int
    connect_events_24h: int
    last_event_at: datetime | None


class SessionQueryItem(BaseModel):
    session_id: str
    router_id: str
    router_name: str
    source_id: str
    source_display_name: str | None
    username: str
    service: str
    state: str
    origin: str
    caller_id: str | None
    vpn_address: str | None
    local_address: str | None
    interface_id: str | None
    connected_at: datetime
    disconnected_at: datetime | None
    last_observed_at: datetime | None
    duration_seconds: int | None
    end_reason: str | None


class RouterQueryItem(BaseModel):
    router_id: str
    router_name: str
    enabled: bool
    active_sessions: int
    active_users: int
    last_seen_at: datetime | None
    last_snapshot_at: datetime | None


class SourceQueryItem(BaseModel):
    source_id: str
    source_display_name: str | None
    router_id: str
    router_name: str
    enabled: bool
    active_sessions: int
    active_users: int
    last_snapshot_at: datetime | None


class UserQueryItem(BaseModel):
    username: str
    active_sessions: int
    total_sessions: int
    total_duration_seconds: int
    last_connected_at: datetime | None


class LogonAlertItem(BaseModel):
    alert_id: str
    router_id: str
    router_name: str
    source_id: str
    username: str
    caller_id: str | None
    vpn_address: str | None
    logon_at: datetime
    received_at: datetime
    alert_value: int = 1
