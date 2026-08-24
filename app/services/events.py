from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Router, Source, VPNEvent, VPNSession
from app.schemas import EventType, RouterEvent
from app.timeutils import to_utc_naive, utc_now


class EventValidationError(ValueError):
    """Raised when an authenticated event does not match configured monitoring scope."""


class EventConflictError(ValueError):
    """Raised when one external event identifier is reused for different event content."""


@dataclass(frozen=True)
class EventProcessingResult:
    accepted: int
    duplicates: int
    event_id: str
    session_action: str


def _resolve_source(db: Session, router: Router, event: RouterEvent) -> Source:
    source = db.scalar(
        select(Source).where(
            Source.router_id == router.id,
            Source.name == event.source_id,
        )
    )
    if source is None or not source.enabled:
        raise EventValidationError("unknown or disabled source")
    if source.services and event.service not in source.services:
        raise EventValidationError("event service is not allowed by source")
    return source


def _same_event(stored: VPNEvent, source: Source, event: RouterEvent) -> bool:
    return (
        stored.source_id == source.id
        and stored.event_type == event.event_type.value
        and stored.username == event.username
        and stored.service == event.service
        and stored.caller_id == event.caller_id
        and stored.local_address == event.local_address
        and stored.remote_address == event.remote_address
        and stored.interface_id == event.interface_id
        and stored.occurred_at == to_utc_naive(event.occurred_at)
        and stored.payload_version == event.contract_version
    )


def _find_active_session(
    db: Session,
    *,
    router_id: str,
    source_id: str,
    username: str,
    service: str,
    interface_id: str | None,
) -> VPNSession | None:
    statement = select(VPNSession).where(
        VPNSession.router_id == router_id,
        VPNSession.source_id == source_id,
        VPNSession.username == username,
        VPNSession.service == service,
        VPNSession.state == "ACTIVE",
    )
    if interface_id:
        statement = statement.where(VPNSession.interface_id == interface_id)
    return db.scalar(
        statement.order_by(VPNSession.connected_at.desc(), VPNSession.id.desc()).limit(1)
    )


def _apply_connect(
    db: Session,
    *,
    router: Router,
    source: Source,
    event: RouterEvent,
) -> str:
    occurred_at = to_utc_naive(event.occurred_at)

    if event.interface_id:
        existing = _find_active_session(
            db,
            router_id=router.id,
            source_id=source.id,
            username=event.username,
            service=event.service,
            interface_id=event.interface_id,
        )
        if existing is not None:
            existing.caller_id = event.caller_id
            existing.local_address = event.local_address
            existing.vpn_address = event.remote_address
            existing.last_observed_at = occurred_at
            return "ALREADY_ACTIVE"

    db.add(
        VPNSession(
            router_id=router.id,
            source_id=source.id,
            username=event.username,
            service=event.service,
            state="ACTIVE",
            origin="EVENT",
            caller_id=event.caller_id,
            vpn_address=event.remote_address,
            local_address=event.local_address,
            interface_id=event.interface_id,
            connected_at=occurred_at,
            last_observed_at=occurred_at,
        )
    )
    return "CREATED"


def _apply_disconnect(
    db: Session,
    *,
    router: Router,
    source: Source,
    event: RouterEvent,
) -> str:
    session = _find_active_session(
        db,
        router_id=router.id,
        source_id=source.id,
        username=event.username,
        service=event.service,
        interface_id=event.interface_id,
    )
    if session is None:
        return "NO_ACTIVE_SESSION"

    occurred_at = to_utc_naive(event.occurred_at)
    session.state = "CLOSED"
    session.disconnected_at = occurred_at
    session.last_observed_at = occurred_at
    session.duration_seconds = max(
        0,
        int((occurred_at - session.connected_at).total_seconds()),
    )
    session.end_reason = "DISCONNECT"
    return "CLOSED"


def process_event(
    db: Session,
    *,
    router: Router,
    event: RouterEvent,
) -> EventProcessingResult:
    source = _resolve_source(db, router, event)

    duplicate = db.scalar(
        select(VPNEvent).where(
            VPNEvent.router_id == router.id,
            VPNEvent.external_event_id == event.event_id,
        )
    )
    if duplicate is not None:
        if not _same_event(duplicate, source, event):
            raise EventConflictError("event_id is already associated with different content")
        return EventProcessingResult(
            accepted=0,
            duplicates=1,
            event_id=event.event_id,
            session_action="UNCHANGED",
        )

    stored_event = VPNEvent(
        router_id=router.id,
        source_id=source.id,
        external_event_id=event.event_id,
        event_type=event.event_type.value,
        username=event.username,
        service=event.service,
        caller_id=event.caller_id,
        local_address=event.local_address,
        remote_address=event.remote_address,
        interface_id=event.interface_id,
        occurred_at=to_utc_naive(event.occurred_at),
        received_at=utc_now(),
        payload_version=event.contract_version,
    )
    db.add(stored_event)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return EventProcessingResult(
            accepted=0,
            duplicates=1,
            event_id=event.event_id,
            session_action="UNCHANGED",
        )

    if event.event_type == EventType.CONNECT:
        session_action = _apply_connect(db, router=router, source=source, event=event)
    else:
        session_action = _apply_disconnect(db, router=router, source=source, event=event)

    db.commit()
    return EventProcessingResult(
        accepted=1,
        duplicates=0,
        event_id=event.event_id,
        session_action=session_action,
    )
