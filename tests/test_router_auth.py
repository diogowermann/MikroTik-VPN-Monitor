from app.models import Router
from app.services.routers import register_router, rotate_router_secret


def _event_payload() -> dict[str, object]:
    return {
        "contract_version": 1,
        "event_id": "event-auth-test",
        "event_type": "CONNECT",
        "source_id": "primary-ovpn",
        "service": "ovpn",
        "username": "vpn-user",
        "caller_id": "203.0.113.10",
        "local_address": "10.10.0.1",
        "remote_address": "10.10.0.20",
        "interface_id": "example-interface-id",
        "occurred_at": "2026-08-24T12:00:00Z",
    }


def test_router_ingestion_requires_authentication(client):
    response = client.post("/api/v1/router/events", json=_event_payload())
    assert response.status_code == 401


def test_router_ingestion_rejects_invalid_secret(client, session_factory):
    with session_factory() as db:
        registered = register_router(db, name="router-01")

    response = client.post(
        "/api/v1/router/events",
        headers={
            "X-Router-ID": registered.router_id,
            "Authorization": "Bearer invalid-secret",
        },
        json=_event_payload(),
    )
    assert response.status_code == 401


def test_router_ingestion_rejects_revoked_secret(client, session_factory):
    with session_factory() as db:
        registered = register_router(db, name="router-01")
        rotate_router_secret(db, router_id=registered.router_id)

    response = client.post(
        "/api/v1/router/events",
        headers={
            "X-Router-ID": registered.router_id,
            "Authorization": f"Bearer {registered.secret}",
        },
        json=_event_payload(),
    )
    assert response.status_code == 401


def test_router_ingestion_rejects_disabled_router(client, session_factory):
    with session_factory() as db:
        registered = register_router(db, name="router-01")
        router = db.get(Router, registered.router_id)
        assert router is not None
        router.enabled = False
        db.commit()

    response = client.post(
        "/api/v1/router/events",
        headers={
            "X-Router-ID": registered.router_id,
            "Authorization": f"Bearer {registered.secret}",
        },
        json=_event_payload(),
    )
    assert response.status_code == 401
