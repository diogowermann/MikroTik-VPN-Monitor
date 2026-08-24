from datetime import datetime

from sqlalchemy import func, select

from app.models import Router, Source, VPNSession
from app.services.routers import add_source, register_router


def _register(session_factory):
    with session_factory() as db:
        return register_router(
            db,
            name="router-01",
            source_name="primary-ovpn",
            services=["ovpn"],
            profiles=["example-ovpn-profile"],
        )


def _headers(registered) -> dict[str, str]:
    return {
        "X-Router-ID": registered.router_id,
        "Authorization": f"Bearer {registered.secret}",
    }


def _snapshot(
    *,
    observed_at: str,
    sessions: list[dict[str, object]],
    source_id: str = "primary-ovpn",
    boot_id: str | None = "boot-a",
) -> dict[str, object]:
    return {
        "contract_version": 1,
        "source_id": source_id,
        "observed_at": observed_at,
        "boot_id": boot_id,
        "sessions": sessions,
    }


def _session(
    *,
    router_session_id: str = "session-0001",
    username: str = "vpn-user",
    service: str = "ovpn",
    uptime_seconds: int | None = 300,
) -> dict[str, object]:
    return {
        "router_session_id": router_session_id,
        "username": username,
        "service": service,
        "caller_id": "203.0.113.10",
        "address": "10.10.0.20",
        "local_address": "10.10.0.1",
        "uptime_seconds": uptime_seconds,
    }


def _event(
    *,
    event_id: str,
    event_type: str,
    occurred_at: str,
    source_id: str = "primary-ovpn",
    username: str = "vpn-user",
) -> dict[str, object]:
    return {
        "contract_version": 1,
        "event_id": event_id,
        "event_type": event_type,
        "source_id": source_id,
        "service": "ovpn",
        "username": username,
        "caller_id": "203.0.113.10",
        "local_address": "10.10.0.1",
        "remote_address": "10.10.0.20",
        "occurred_at": occurred_at,
    }


def test_snapshot_creates_missing_reconciled_session(client, session_factory):
    registered = _register(session_factory)

    response = client.post(
        "/api/v1/router/snapshot",
        headers=_headers(registered),
        json=_snapshot(
            observed_at="2026-08-24T12:05:00Z",
            sessions=[_session()],
        ),
    )

    assert response.status_code == 200
    assert response.json() == {
        "accepted": 1,
        "stale": False,
        "source_id": "primary-ovpn",
        "observed_sessions": 1,
        "created": 1,
        "refreshed": 0,
        "closed": 0,
        "reboot_closed": 0,
    }

    with session_factory() as db:
        session = db.scalar(select(VPNSession))
        source = db.scalar(select(Source).where(Source.name == "primary-ovpn"))
        router = db.get(Router, registered.router_id)

        assert session is not None
        assert session.state == "ACTIVE"
        assert session.origin == "RECONCILIATION"
        assert session.router_session_id == "session-0001"
        assert session.connected_at == datetime(2026, 8, 24, 12, 0, 0)
        assert session.last_observed_at == datetime(2026, 8, 24, 12, 5, 0)
        assert source is not None and source.last_snapshot_at == datetime(2026, 8, 24, 12, 5, 0)
        assert router is not None
        assert router.last_snapshot_at == datetime(2026, 8, 24, 12, 5, 0)
        assert router.last_boot_id == "boot-a"


def test_snapshot_attaches_router_session_id_to_unique_event_session(client, session_factory):
    registered = _register(session_factory)
    connect = client.post(
        "/api/v1/router/events",
        headers=_headers(registered),
        json=_event(
            event_id="connect-0001",
            event_type="CONNECT",
            occurred_at="2026-08-24T12:00:00Z",
        ),
    )
    assert connect.status_code == 200

    response = client.post(
        "/api/v1/router/snapshot",
        headers=_headers(registered),
        json=_snapshot(
            observed_at="2026-08-24T12:01:00Z",
            sessions=[_session(uptime_seconds=60)],
        ),
    )

    assert response.status_code == 200
    assert response.json()["created"] == 0
    assert response.json()["refreshed"] == 1

    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(VPNSession)) == 1
        session = db.scalar(select(VPNSession))
        assert session is not None
        assert session.origin == "EVENT"
        assert session.router_session_id == "session-0001"
        assert session.last_observed_at == datetime(2026, 8, 24, 12, 1, 0)


def test_empty_snapshot_closes_missing_active_session(client, session_factory):
    registered = _register(session_factory)
    client.post(
        "/api/v1/router/events",
        headers=_headers(registered),
        json=_event(
            event_id="connect-0001",
            event_type="CONNECT",
            occurred_at="2026-08-24T12:00:00Z",
        ),
    )

    response = client.post(
        "/api/v1/router/snapshot",
        headers=_headers(registered),
        json=_snapshot(observed_at="2026-08-24T12:05:00Z", sessions=[]),
    )

    assert response.status_code == 200
    assert response.json()["closed"] == 1

    with session_factory() as db:
        session = db.scalar(select(VPNSession))
        assert session is not None
        assert session.state == "CLOSED"
        assert session.end_reason == "RECONCILIATION"
        assert session.duration_seconds == 300


def test_stale_snapshot_is_noop(client, session_factory):
    registered = _register(session_factory)
    first = client.post(
        "/api/v1/router/snapshot",
        headers=_headers(registered),
        json=_snapshot(
            observed_at="2026-08-24T12:05:00Z",
            sessions=[_session()],
        ),
    )
    assert first.status_code == 200

    stale = client.post(
        "/api/v1/router/snapshot",
        headers=_headers(registered),
        json=_snapshot(observed_at="2026-08-24T12:04:00Z", sessions=[]),
    )

    assert stale.status_code == 200
    assert stale.json()["accepted"] == 0
    assert stale.json()["stale"] is True
    assert stale.json()["closed"] == 0

    with session_factory() as db:
        session = db.scalar(select(VPNSession))
        assert session is not None and session.state == "ACTIVE"


def test_snapshot_does_not_close_session_that_started_after_observation(client, session_factory):
    registered = _register(session_factory)
    client.post(
        "/api/v1/router/events",
        headers=_headers(registered),
        json=_event(
            event_id="connect-future",
            event_type="CONNECT",
            occurred_at="2026-08-24T12:10:00Z",
        ),
    )

    response = client.post(
        "/api/v1/router/snapshot",
        headers=_headers(registered),
        json=_snapshot(observed_at="2026-08-24T12:05:00Z", sessions=[]),
    )

    assert response.status_code == 200
    assert response.json()["closed"] == 0
    with session_factory() as db:
        session = db.scalar(select(VPNSession))
        assert session is not None and session.state == "ACTIVE"


def test_boot_change_closes_active_sessions_across_sources(client, session_factory):
    registered = _register(session_factory)
    with session_factory() as db:
        add_source(
            db,
            router_id=registered.router_id,
            name="secondary-ovpn",
            services=["ovpn"],
            profiles=["example-secondary-profile"],
            enabled=True,
        )
        router = db.get(Router, registered.router_id)
        assert router is not None
        router.last_boot_id = "boot-a"
        router.last_snapshot_at = datetime(2026, 8, 24, 11, 59, 0)
        db.commit()

    for source_id, username in (
        ("primary-ovpn", "vpn-user-primary"),
        ("secondary-ovpn", "vpn-user-secondary"),
    ):
        response = client.post(
            "/api/v1/router/events",
            headers=_headers(registered),
            json=_event(
                event_id=f"connect-{source_id}",
                event_type="CONNECT",
                occurred_at="2026-08-24T12:00:00Z",
                source_id=source_id,
                username=username,
            ),
        )
        assert response.status_code == 200

    reboot = client.post(
        "/api/v1/router/snapshot",
        headers=_headers(registered),
        json=_snapshot(
            observed_at="2026-08-24T12:05:00Z",
            boot_id="boot-b",
            sessions=[_session(username="vpn-user-primary", uptime_seconds=30)],
        ),
    )

    assert reboot.status_code == 200
    assert reboot.json()["reboot_closed"] == 2
    assert reboot.json()["created"] == 1

    with session_factory() as db:
        closed = db.scalars(
            select(VPNSession).where(VPNSession.state == "CLOSED")
        ).all()
        active = db.scalars(
            select(VPNSession).where(VPNSession.state == "ACTIVE")
        ).all()
        assert len(closed) == 2
        assert all(item.end_reason == "ROUTER_REBOOT" for item in closed)
        assert len(active) == 1
        assert active[0].origin == "RECONCILIATION"
        router = db.get(Router, registered.router_id)
        assert router is not None and router.last_boot_id == "boot-b"


def test_snapshot_rejects_invalid_scope_and_duplicate_session_ids(client, session_factory):
    registered = _register(session_factory)

    wrong_service = client.post(
        "/api/v1/router/snapshot",
        headers=_headers(registered),
        json=_snapshot(
            observed_at="2026-08-24T12:05:00Z",
            sessions=[_session(service="l2tp")],
        ),
    )
    duplicate_ids = client.post(
        "/api/v1/router/snapshot",
        headers=_headers(registered),
        json=_snapshot(
            observed_at="2026-08-24T12:05:00Z",
            sessions=[_session(), _session(username="another-user")],
        ),
    )

    assert wrong_service.status_code == 422
    assert duplicate_ids.status_code == 422
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(VPNSession)) == 0
