from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class EventType(str, Enum):
    CONNECT = "CONNECT"
    DISCONNECT = "DISCONNECT"


def require_timezone(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include an explicit UTC offset")
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

    @field_validator("contract_version")
    @classmethod
    def only_contract_v1(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported contract version")
        return value


class EventIngestResult(BaseModel):
    accepted: int
    duplicates: int
    event_id: str
    session_action: str
