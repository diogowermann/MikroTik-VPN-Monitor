from datetime import datetime, timedelta

from sqlalchemy import and_, case, distinct, func, select
from sqlalchemy.orm import Session

from app.models import Router, Source, VPNEvent, VPNSession
from app.query_schemas import (
    LogonAlertItem,
    QuerySummary,
    RouterQueryItem,
    SessionQueryItem,
    SourceQueryItem,
    UserQueryItem,
)
from app.timeutils import as_utc, to_utc_naive, utc_now


def _session_item(session: VPNSession, router: Router, source: Source) -> SessionQueryItem:
    duration_seconds = session.duration_seconds
    if session.state == "ACTIVE" and duration_seconds is None:
        duration_seconds = max(0, int((utc_now() - session.connected_at).total_seconds()))

    return SessionQueryItem(
        session_id=session.id,
        router_id=router.id,
        router_name=router.name,
        source_id=source.name,
        source_display_name=source.display_name,
        username=session.username,
        service=session.service,
        state=session.state,
        origin=session.origin,
        caller_id=session.caller_id,
        vpn_address=session.vpn_address,
        local_address=session.local_address,
        interface_id=session.interface_id,
        connected_at=as_utc(session.connected_at),
        disconnected_at=as_utc(session.disconnected_at),
        last_observed_at=as_utc(session.last_observed_at),
        duration_seconds=duration_seconds,
        end_reason=session.end_reason,
    )


def get_summary(db: Session) -> QuerySummary:
    since = utc_now() - timedelta(hours=24)

    routers_enabled = db.scalar(
        select(func.count()).select_from(Router).where(Router.enabled.is_(True))
    ) or 0
    sources_enabled = db.scalar(
        select(func.count()).select_from(Source).where(Source.enabled.is_(True))
    ) or 0
    active_sessions = db.scalar(
        select(func.count()).select_from(VPNSession).where(VPNSession.state == "ACTIVE")
    ) or 0
    active_users = db.scalar(
        select(func.count(distinct(VPNSession.username))).where(VPNSession.state == "ACTIVE")
    ) or 0
    sessions_24h = db.scalar(
        select(func.count()).select_from(VPNSession).where(VPNSession.connected_at >= since)
    ) or 0
    connect_events_24h = db.scalar(
        select(func.count())
        .select_from(VPNEvent)
        .where(VPNEvent.event_type == "CONNECT", VPNEvent.occurred_at >= since)
    ) or 0
    last_event_at = db.scalar(select(func.max(VPNEvent.occurred_at)))

    return QuerySummary(
        routers_enabled=int(routers_enabled),
        sources_enabled=int(sources_enabled),
        active_sessions=int(active_sessions),
        active_users=int(active_users),
        sessions_24h=int(sessions_24h),
        connect_events_24h=int(connect_events_24h),
        last_event_at=as_utc(last_event_at),
    )


def list_sessions(
    db: Session,
    *,
    state: str | None = None,
    router_id: str | None = None,
    source_id: str | None = None,
    username: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[SessionQueryItem]:
    statement = (
        select(VPNSession, Router, Source)
        .join(Router, Router.id == VPNSession.router_id)
        .join(Source, Source.id == VPNSession.source_id)
    )

    if state:
        statement = statement.where(VPNSession.state == state)
    if router_id:
        statement = statement.where(VPNSession.router_id == router_id)
    if source_id:
        statement = statement.where(Source.name == source_id)
    if username:
        statement = statement.where(VPNSession.username == username)
    if since:
        statement = statement.where(VPNSession.connected_at >= to_utc_naive(since))
    if until:
        statement = statement.where(VPNSession.connected_at <= to_utc_naive(until))

    statement = statement.order_by(VPNSession.connected_at.desc(), VPNSession.id.desc())
    statement = statement.limit(limit).offset(offset)

    return [_session_item(session, router, source) for session, router, source in db.execute(statement)]


def list_routers(db: Session) -> list[RouterQueryItem]:
    active_join = and_(
        VPNSession.router_id == Router.id,
        VPNSession.state == "ACTIVE",
    )
    statement = (
        select(
            Router.id,
            Router.name,
            Router.enabled,
            Router.last_seen_at,
            Router.last_snapshot_at,
            func.count(VPNSession.id),
            func.count(distinct(VPNSession.username)),
        )
        .outerjoin(VPNSession, active_join)
        .group_by(
            Router.id,
            Router.name,
            Router.enabled,
            Router.last_seen_at,
            Router.last_snapshot_at,
        )
        .order_by(Router.name.asc())
    )

    return [
        RouterQueryItem(
            router_id=router_id,
            router_name=router_name,
            enabled=enabled,
            active_sessions=int(active_sessions),
            active_users=int(active_users),
            last_seen_at=as_utc(last_seen_at),
            last_snapshot_at=as_utc(last_snapshot_at),
        )
        for (
            router_id,
            router_name,
            enabled,
            last_seen_at,
            last_snapshot_at,
            active_sessions,
            active_users,
        ) in db.execute(statement)
    ]


def list_sources(db: Session) -> list[SourceQueryItem]:
    active_join = and_(
        VPNSession.source_id == Source.id,
        VPNSession.state == "ACTIVE",
    )
    statement = (
        select(
            Source.name,
            Source.display_name,
            Source.enabled,
            Source.last_snapshot_at,
            Router.id,
            Router.name,
            func.count(VPNSession.id),
            func.count(distinct(VPNSession.username)),
        )
        .join(Router, Router.id == Source.router_id)
        .outerjoin(VPNSession, active_join)
        .group_by(
            Source.id,
            Source.name,
            Source.display_name,
            Source.enabled,
            Source.last_snapshot_at,
            Router.id,
            Router.name,
        )
        .order_by(Router.name.asc(), Source.name.asc())
    )

    return [
        SourceQueryItem(
            source_id=source_id,
            source_display_name=source_display_name,
            router_id=router_id,
            router_name=router_name,
            enabled=enabled,
            active_sessions=int(active_sessions),
            active_users=int(active_users),
            last_snapshot_at=as_utc(last_snapshot_at),
        )
        for (
            source_id,
            source_display_name,
            enabled,
            last_snapshot_at,
            router_id,
            router_name,
            active_sessions,
            active_users,
        ) in db.execute(statement)
    ]


def list_users(db: Session, *, limit: int = 500) -> list[UserQueryItem]:
    statement = (
        select(
            VPNSession.username,
            func.sum(case((VPNSession.state == "ACTIVE", 1), else_=0)),
            func.count(VPNSession.id),
            func.coalesce(func.sum(VPNSession.duration_seconds), 0),
            func.max(VPNSession.connected_at),
        )
        .group_by(VPNSession.username)
        .order_by(func.max(VPNSession.connected_at).desc(), VPNSession.username.asc())
        .limit(limit)
    )

    return [
        UserQueryItem(
            username=username,
            active_sessions=int(active_sessions or 0),
            total_sessions=int(total_sessions),
            total_duration_seconds=int(total_duration_seconds or 0),
            last_connected_at=as_utc(last_connected_at),
        )
        for (
            username,
            active_sessions,
            total_sessions,
            total_duration_seconds,
            last_connected_at,
        ) in db.execute(statement)
    ]


def list_logon_alerts(db: Session, *, lookback_minutes: int) -> list[LogonAlertItem]:
    cutoff = utc_now() - timedelta(minutes=lookback_minutes)
    statement = (
        select(VPNEvent, Router, Source)
        .join(Router, Router.id == VPNEvent.router_id)
        .join(Source, Source.id == VPNEvent.source_id)
        .where(
            VPNEvent.event_type == "CONNECT",
            VPNEvent.received_at >= cutoff,
            Router.enabled.is_(True),
            Source.enabled.is_(True),
        )
        .order_by(VPNEvent.received_at.asc(), VPNEvent.id.asc())
    )

    return [
        LogonAlertItem(
            alert_id=event.id,
            router_id=router.id,
            router_name=router.name,
            source_id=source.name,
            username=event.username,
            caller_id=event.caller_id,
            vpn_address=event.remote_address,
            logon_at=as_utc(event.occurred_at),
            received_at=as_utc(event.received_at),
            alert_value=1,
        )
        for event, router, source in db.execute(statement)
    ]
