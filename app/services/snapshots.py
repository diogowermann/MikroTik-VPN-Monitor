from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Router, Source, VPNSession
from app.schemas import RouterSnapshot, SnapshotSession
from app.timeutils import to_utc_naive


class SnapshotValidationError(ValueError):
    """Raised when an authenticated snapshot does not match configured monitoring scope."""


@dataclass(frozen=True)
class SnapshotProcessingResult:
    accepted: int
    stale: bool
    source_id: str
    observed_sessions: int
    created: int
    refreshed: int
    closed: int
    reboot_closed: int


def _resolve_source(db: Session, router: Router, snapshot: RouterSnapshot) -> Source:
    source = db.scalar(
        select(Source).where(
            Source.router_id == router.id,
            Source.name == snapshot.source_id,
        )
    )
    if source is None or not source.enabled:
        raise SnapshotValidationError("unknown or disabled source")

    disallowed_services = sorted(
        {
            item.service
            for item in snapshot.sessions
            if source.services and item.service not in source.services
        }
    )
    if disallowed_services:
        raise SnapshotValidationError("snapshot contains a service not allowed by source")
    return source


def _close_session(session: VPNSession, *, observed_at, reason: str) -> None:
    session.state = "CLOSED"
    session.disconnected_at = observed_at
    session.last_observed_at = observed_at
    session.duration_seconds = max(0, int((observed_at - session.connected_at).total_seconds()))
    session.end_reason = reason


def _close_sessions_for_reboot(db: Session, *, router: Router, observed_at) -> int:
    sessions = db.scalars(
        select(VPNSession).where(
            VPNSession.router_id == router.id,
            VPNSession.state == "ACTIVE",
            VPNSession.connected_at <= observed_at,
        )
    ).all()
    for session in sessions:
        _close_session(session, observed_at=observed_at, reason="ROUTER_REBOOT")
    return len(sessions)


def _find_by_router_session_id(
    db: Session,
    *,
    router: Router,
    source: Source,
    item: SnapshotSession,
    observed_at,
) -> VPNSession | None:
    return db.scalar(
        select(VPNSession)
        .where(
            VPNSession.router_id == router.id,
            VPNSession.source_id == source.id,
            VPNSession.router_session_id == item.router_session_id,
            VPNSession.state == "ACTIVE",
            VPNSession.connected_at <= observed_at,
        )
        .order_by(VPNSession.connected_at.desc(), VPNSession.id.desc())
        .limit(1)
    )


def _find_unique_event_fallback(
    db: Session,
    *,
    router: Router,
    source: Source,
    item: SnapshotSession,
    observed_at,
) -> VPNSession | None:
    candidates = db.scalars(
        select(VPNSession).where(
            VPNSession.router_id == router.id,
            VPNSession.source_id == source.id,
            VPNSession.username == item.username,
            VPNSession.service == item.service,
            VPNSession.state == "ACTIVE",
            VPNSession.router_session_id.is_(None),
            VPNSession.connected_at <= observed_at,
        )
    ).all()

    compatible: list[VPNSession] = []
    for candidate in candidates:
        if item.address and candidate.vpn_address and item.address != candidate.vpn_address:
            continue
        if item.caller_id and candidate.caller_id and item.caller_id != candidate.caller_id:
            continue
        if item.interface_id and candidate.interface_id and item.interface_id != candidate.interface_id:
            continue
        compatible.append(candidate)

    if len(compatible) == 1:
        return compatible[0]
    return None


def _refresh_session(
    session: VPNSession,
    *,
    item: SnapshotSession,
    observed_at,
    boot_id: str | None,
) -> None:
    session.router_session_id = item.router_session_id
    if item.caller_id is not None:
        session.caller_id = item.caller_id
    if item.address is not None:
        session.vpn_address = item.address
    if item.local_address is not None:
        session.local_address = item.local_address
    if item.interface_id is not None:
        session.interface_id = item.interface_id
    if boot_id is not None:
        session.router_boot_id = boot_id
    session.last_observed_at = observed_at


def _create_reconciled_session(
    db: Session,
    *,
    router: Router,
    source: Source,
    item: SnapshotSession,
    observed_at,
    boot_id: str | None,
) -> VPNSession:
    connected_at = observed_at
    if item.uptime_seconds is not None:
        connected_at = observed_at - timedelta(seconds=item.uptime_seconds)

    session = VPNSession(
        router_id=router.id,
        source_id=source.id,
        router_session_id=item.router_session_id,
        username=item.username,
        service=item.service,
        state="ACTIVE",
        origin="RECONCILIATION",
        caller_id=item.caller_id,
        vpn_address=item.address,
        local_address=item.local_address,
        interface_id=item.interface_id,
        router_boot_id=boot_id,
        connected_at=connected_at,
        last_observed_at=observed_at,
    )
    db.add(session)
    db.flush()
    return session


def process_snapshot(
    db: Session,
    *,
    router: Router,
    snapshot: RouterSnapshot,
) -> SnapshotProcessingResult:
    source = _resolve_source(db, router, snapshot)
    observed_at = to_utc_naive(snapshot.observed_at)

    if source.last_snapshot_at is not None and observed_at <= source.last_snapshot_at:
        return SnapshotProcessingResult(
            accepted=0,
            stale=True,
            source_id=source.name,
            observed_sessions=len(snapshot.sessions),
            created=0,
            refreshed=0,
            closed=0,
            reboot_closed=0,
        )

    if (
        snapshot.boot_id is not None
        and router.last_boot_id is not None
        and snapshot.boot_id != router.last_boot_id
        and router.last_snapshot_at is not None
        and observed_at <= router.last_snapshot_at
    ):
        return SnapshotProcessingResult(
            accepted=0,
            stale=True,
            source_id=source.name,
            observed_sessions=len(snapshot.sessions),
            created=0,
            refreshed=0,
            closed=0,
            reboot_closed=0,
        )

    reboot_closed = 0
    if snapshot.boot_id is not None:
        if router.last_boot_id is not None and snapshot.boot_id != router.last_boot_id:
            reboot_closed = _close_sessions_for_reboot(
                db,
                router=router,
                observed_at=observed_at,
            )
            if reboot_closed:
                db.flush()
        router.last_boot_id = snapshot.boot_id

    matched_session_ids: set[str] = set()
    created = 0
    refreshed = 0

    for item in snapshot.sessions:
        session = _find_by_router_session_id(
            db,
            router=router,
            source=source,
            item=item,
            observed_at=observed_at,
        )
        if session is None:
            session = _find_unique_event_fallback(
                db,
                router=router,
                source=source,
                item=item,
                observed_at=observed_at,
            )

        if session is None:
            session = _create_reconciled_session(
                db,
                router=router,
                source=source,
                item=item,
                observed_at=observed_at,
                boot_id=snapshot.boot_id,
            )
            created += 1
        else:
            _refresh_session(
                session,
                item=item,
                observed_at=observed_at,
                boot_id=snapshot.boot_id,
            )
            refreshed += 1
        matched_session_ids.add(session.id)

    active_sessions = db.scalars(
        select(VPNSession).where(
            VPNSession.router_id == router.id,
            VPNSession.source_id == source.id,
            VPNSession.state == "ACTIVE",
            VPNSession.connected_at <= observed_at,
        )
    ).all()

    closed = 0
    for session in active_sessions:
        if session.id in matched_session_ids:
            continue
        _close_session(session, observed_at=observed_at, reason="RECONCILIATION")
        closed += 1

    source.last_snapshot_at = observed_at
    if router.last_snapshot_at is None or observed_at > router.last_snapshot_at:
        router.last_snapshot_at = observed_at

    db.commit()
    return SnapshotProcessingResult(
        accepted=1,
        stale=False,
        source_id=source.name,
        observed_sessions=len(snapshot.sessions),
        created=created,
        refreshed=refreshed,
        closed=closed,
        reboot_closed=reboot_closed,
    )
