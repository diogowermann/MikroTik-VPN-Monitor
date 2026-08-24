from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class EventType(str, Enum):
    CONNECT = "CONNECT"
    DISCONNECT = "DISCONNECT"


def require_timezone(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include an explicit UTC offset")
    return value


def require_contract_v1(value: int) -> int:
    if value != 1:
        raise ValueError("unsupported contract version")
    return value


class RouterEvent(BaseModel):
    contract_version: int = 1
    event_id: str = Field(min_length=1, max_length=128)
    event_type: EventType
    source_id: str = Field(min_length=1, max_length=64)
    service: str = Field(min_length=1, max_length=32)
    username: str = Field(min_length=1, max_length=255)
    caller_id: str | None = Field(default=None, max_length=255)
    local_address: str | None = Field(default=None, max_length=64)
    remote_address: str | None = Field(default=None, max_length=64)
    interface_id: str | None = Field(default=None, max_length=255)
    occurred_at: datetime

    _occurred_has_timezone = field_validator("occurred_at")(require_timezone)
    _contract_is_v1 = field_validator("contract_version")(require_contract_v1)


class EventIngestResult(BaseModel):
    accepted: int
    duplicates: int
    event_id: str
    session_action: str


class SnapshotSession(BaseModel):
    router_session_id: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=1, max_length=255)
    service: str = Field(min_length=1, max_length=32)
    caller_id: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=64)
    local_address: str | None = Field(default=None, max_length=64)
    interface_id: str | None = Field(default=None, max_length=255)
    uptime_seconds: int | None = Field(default=None, ge=0)


class RouterSnapshot(BaseModel):
    contract_version: int = 1
    source_id: str = Field(min_length=1, max_length=64)
    observed_at: datetime
    boot_id: str | None = Field(default=None, min_length=1, max_length=128)
    sessions: list[SnapshotSession] = Field(default_factory=list, max_length=10000)

    _observed_has_timezone = field_validator("observed_at")(require_timezone)
    _contract_is_v1 = field_validator("contract_version")(require_contract_v1)

    @model_validator(mode="after")
    def unique_router_session_ids(self) -> "RouterSnapshot":
        session_ids = [item.router_session_id for item in self.sessions]
        if len(session_ids) != len(set(session_ids)):
            raise ValueError("snapshot contains duplicate router_session_id values")
        return self


class SnapshotIngestResult(BaseModel):
    accepted: int
    stale: bool
    source_id: str
    observed_sessions: int
    created: int
    refreshed: int
    closed: int
    reboot_closed: int
