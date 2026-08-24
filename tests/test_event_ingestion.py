from sqlalchemy import func, select

from app.models import Router, RouterCredential, VPNEvent, VPNSession
from app.services.routers import register_router


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


def _event(
    *,
    event_id: str,
    event_type: str,
    occurred_at: str,
    source_id: str = "primary-ovpn",
    service: str = "ovpn",
    interface_id: str | None = "example-interface-id",
) -> dict[str, object]:
    return {
        "contract_version": 1,
        "event_id": event_id,
        "event_type": event_type,
        "source_id": source_id,
        "service": service,
        "username": "vpn-user",
        "caller_id": "203.0.113.10",
        "local_address": "10.10.0.1",
        "remote_address": "10.10.0.20",
        "interface_id": interface_id,
        "occurred_at": occurred_at,
    }


def test_connect_event_creates_immutable_event_and_active_session(client, session_factory):
    registered = _register(session_factory)

    response = client.post(
        "/api/v1/router/events",
        headers=_headers(registered),
        json=_event(
            event_id="connect-0001",
            event_type="CONNECT",
            occurred_at="2026-08-24T12:00:00Z",
        ),
    )

    assert response.status_code == 200
    assert response.json() == {
        "accepted": 1,
        "duplicates": 0,
        "event_id": "connect-0001",
        "session_action": "CREATED",
    }

    with session_factory() as db:
        stored_event = db.scalar(
            select(VPNEvent).where(VPNEvent.external_event_id == "connect-0001")
        )
        session = db.scalar(select(VPNSession).where(VPNSession.state == "ACTIVE"))
        router = db.get(Router, registered.router_id)
        credential = db.scalar(
            select(RouterCredential).where(
                RouterCredential.router_id == registered.router_id,
                RouterCredential.revoked_at.is_(None),
            )
        )

        assert stored_event is not None
        assert stored_event.username == "vpn-user"
        assert session is not None
        assert session.username == "vpn-user"
        assert session.origin == "EVENT"
        assert session.interface_id == "example-interface-id"
        assert session.vpn_address == "10.10.0.20"
        assert router is not None and router.last_seen_at is not None
        assert credential is not None and credential.last_used_at is not None


def test_replayed_event_is_idempotent(client, session_factory):
    registered = _register(session_factory)
    payload = _event(
        event_id="connect-0001",
        event_type="CONNECT",
        occurred_at="2026-08-24T12:00:00Z",
    )

    first = client.post("/api/v1/router/events", headers=_headers(registered), json=payload)
    second = client.post("/api/v1/router/events", headers=_headers(registered), json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["accepted"] == 0
    assert second.json()["duplicates"] == 1
    assert second.json()["session_action"] == "UNCHANGED"

    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(VPNEvent)) == 1
        assert db.scalar(select(func.count()).select_from(VPNSession)) == 1


def test_reused_event_id_with_different_content_is_conflict(client, session_factory):
    registered = _register(session_factory)
    first_payload = _event(
        event_id="connect-0001",
        event_type="CONNECT",
        occurred_at="2026-08-24T12:00:00Z",
    )
    conflicting_payload = _event(
        event_id="connect-0001",
        event_type="DISCONNECT",
        occurred_at="2026-08-24T12:01:00Z",
    )

    first = client.post(
        "/api/v1/router/events",
        headers=_headers(registered),
        json=first_payload,
    )
    conflict = client.post(
        "/api/v1/router/events",
        headers=_headers(registered),
        json=conflicting_payload,
    )

    assert first.status_code == 200
    assert conflict.status_code == 409

    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(VPNEvent)) == 1
        assert db.scalar(select(func.count()).select_from(VPNSession)) == 1


def test_disconnect_closes_matching_active_session(client, session_factory):
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
    disconnect = client.post(
        "/api/v1/router/events",
        headers=_headers(registered),
        json=_event(
            event_id="disconnect-0001",
            event_type="DISCONNECT",
            occurred_at="2026-08-24T12:05:00Z",
        ),
    )

    assert connect.status_code == 200
    assert disconnect.status_code == 200
    assert disconnect.json()["session_action"] == "CLOSED"

    with session_factory() as db:
        session = db.scalar(select(VPNSession))
        assert session is not None
        assert session.state == "CLOSED"
        assert session.end_reason == "DISCONNECT"
        assert session.duration_seconds == 300
        assert db.scalar(select(func.count()).select_from(VPNEvent)) == 2


def test_disconnect_without_interface_falls_back_to_latest_user_session(client, session_factory):
    registered = _register(session_factory)
    client.post(
        "/api/v1/router/events",
        headers=_headers(registered),
        json=_event(
            event_id="connect-0001",
            event_type="CONNECT",
            occurred_at="2026-08-24T12:00:00Z",
            interface_id=None,
        ),
    )

    response = client.post(
        "/api/v1/router/events",
        headers=_headers(registered),
        json=_event(
            event_id="disconnect-0001",
            event_type="DISCONNECT",
            occurred_at="2026-08-24T12:01:00Z",
            interface_id=None,
        ),
    )

    assert response.status_code == 200
    assert response.json()["session_action"] == "CLOSED"


def test_unknown_or_disallowed_source_scope_is_rejected(client, session_factory):
    registered = _register(session_factory)

    unknown_source = client.post(
        "/api/v1/router/events",
        headers=_headers(registered),
        json=_event(
            event_id="connect-unknown-source",
            event_type="CONNECT",
            occurred_at="2026-08-24T12:00:00Z",
            source_id="secondary-ovpn",
        ),
    )
    wrong_service = client.post(
        "/api/v1/router/events",
        headers=_headers(registered),
        json=_event(
            event_id="connect-wrong-service",
            event_type="CONNECT",
            occurred_at="2026-08-24T12:00:00Z",
            service="l2tp",
        ),
    )

    assert unknown_source.status_code == 422
    assert wrong_service.status_code == 422

    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(VPNEvent)) == 0
        assert db.scalar(select(func.count()).select_from(VPNSession)) == 0


def test_event_contract_requires_supported_version_and_timezone(client, session_factory):
    registered = _register(session_factory)

    unsupported = _event(
        event_id="unsupported-version",
        event_type="CONNECT",
        occurred_at="2026-08-24T12:00:00Z",
    )
    unsupported["contract_version"] = 2
    no_timezone = _event(
        event_id="missing-timezone",
        event_type="CONNECT",
        occurred_at="2026-08-24T12:00:00",
    )

    unsupported_response = client.post(
        "/api/v1/router/events",
        headers=_headers(registered),
        json=unsupported,
    )
    timezone_response = client.post(
        "/api/v1/router/events",
        headers=_headers(registered),
        json=no_timezone,
    )

    assert unsupported_response.status_code == 422
    assert timezone_response.status_code == 422
