import pytest

from app.config import get_settings
from app.services.routers import register_router


QUERY_KEY = "query-test-key-with-sufficient-entropy"


@pytest.fixture
def query_headers(monkeypatch):
    monkeypatch.setenv("VPN_MONITOR_QUERY_API_KEY", QUERY_KEY)
    get_settings.cache_clear()
    try:
        yield {"X-API-Key": QUERY_KEY}
    finally:
        get_settings.cache_clear()


def _register(session_factory):
    with session_factory() as db:
        return register_router(
            db,
            name="router-01",
            source_name="primary-ovpn",
            services=["ovpn"],
            profiles=["example-ovpn-profile"],
        )


def _router_headers(registered) -> dict[str, str]:
    return {
        "X-Router-ID": registered.router_id,
        "Authorization": f"Bearer {registered.secret}",
    }


def _event(*, event_id: str, event_type: str, username: str, occurred_at: str) -> dict[str, object]:
    return {
        "contract_version": 1,
        "event_id": event_id,
        "event_type": event_type,
        "source_id": "primary-ovpn",
        "service": "ovpn",
        "username": username,
        "caller_id": "203.0.113.10",
        "local_address": "10.10.0.1",
        "remote_address": "10.10.0.20",
        "interface_id": "example-interface-id",
        "occurred_at": occurred_at,
    }


def _post_event(client, registered, payload):
    response = client.post(
        "/api/v1/router/events",
        headers=_router_headers(registered),
        json=payload,
    )
    assert response.status_code == 200
    return response


def test_query_api_requires_configured_key(client, monkeypatch):
    monkeypatch.delenv("VPN_MONITOR_QUERY_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        response = client.get("/api/v1/query/summary")
        assert response.status_code == 503
        assert response.json()["detail"] == "query API is not configured"
    finally:
        get_settings.cache_clear()


def test_query_api_rejects_missing_or_wrong_key(client, query_headers):
    missing = client.get("/api/v1/query/summary")
    wrong = client.get("/api/v1/query/summary", headers={"X-API-Key": "wrong-key"})

    assert missing.status_code == 401
    assert wrong.status_code == 401


def test_active_history_and_dimension_queries(client, session_factory, query_headers):
    registered = _register(session_factory)
    _post_event(
        client,
        registered,
        _event(
            event_id="connect-user-a",
            event_type="CONNECT",
            username="vpn-user-a",
            occurred_at="2026-08-24T17:00:00Z",
        ),
    )
    _post_event(
        client,
        registered,
        _event(
            event_id="connect-user-b",
            event_type="CONNECT",
            username="vpn-user-b",
            occurred_at="2026-08-24T17:01:00Z",
        ),
    )

    active = client.get("/api/v1/query/sessions/active", headers=query_headers)
    assert active.status_code == 200
    assert {item["username"] for item in active.json()} == {"vpn-user-a", "vpn-user-b"}
    assert all(item["state"] == "ACTIVE" for item in active.json())
    assert all(item["router_name"] == "router-01" for item in active.json())
    assert all(item["source_id"] == "primary-ovpn" for item in active.json())
    assert all(item["duration_seconds"] >= 0 for item in active.json())

    routers = client.get("/api/v1/query/routers", headers=query_headers)
    assert routers.status_code == 200
    assert routers.json()[0]["active_sessions"] == 2
    assert routers.json()[0]["active_users"] == 2

    sources = client.get("/api/v1/query/sources", headers=query_headers)
    assert sources.status_code == 200
    assert sources.json()[0]["source_id"] == "primary-ovpn"
    assert sources.json()[0]["active_sessions"] == 2
    assert sources.json()[0]["active_users"] == 2

    users = client.get("/api/v1/query/users", headers=query_headers)
    assert users.status_code == 200
    assert {item["username"] for item in users.json()} == {"vpn-user-a", "vpn-user-b"}
    assert all(item["active_sessions"] == 1 for item in users.json())

    filtered = client.get(
        "/api/v1/query/sessions/history",
        headers=query_headers,
        params={"username": "vpn-user-a", "source_id": "primary-ovpn"},
    )
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["username"] == "vpn-user-a"

    _post_event(
        client,
        registered,
        _event(
            event_id="disconnect-user-a",
            event_type="DISCONNECT",
            username="vpn-user-a",
            occurred_at="2026-08-24T17:05:00Z",
        ),
    )

    closed = client.get(
        "/api/v1/query/sessions/history",
        headers=query_headers,
        params={"state": "CLOSED", "username": "vpn-user-a"},
    )
    assert closed.status_code == 200
    assert len(closed.json()) == 1
    assert closed.json()[0]["duration_seconds"] == 300
    assert closed.json()[0]["end_reason"] == "DISCONNECT"


def test_summary_reports_current_counts(client, session_factory, query_headers):
    registered = _register(session_factory)
    _post_event(
        client,
        registered,
        _event(
            event_id="connect-summary",
            event_type="CONNECT",
            username="vpn-user",
            occurred_at="2026-08-24T17:00:00Z",
        ),
    )

    response = client.get("/api/v1/query/summary", headers=query_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["routers_enabled"] == 1
    assert payload["sources_enabled"] == 1
    assert payload["active_sessions"] == 1
    assert payload["active_users"] == 1
    assert payload["last_event_at"] is not None


def test_logon_alert_feed_is_stable_and_event_based(client, session_factory, query_headers):
    registered = _register(session_factory)
    _post_event(
        client,
        registered,
        _event(
            event_id="connect-alert",
            event_type="CONNECT",
            username="vpn-alert-user",
            occurred_at="2026-08-24T17:00:00Z",
        ),
    )

    first = client.get(
        "/api/v1/alerts/logons",
        headers=query_headers,
        params={"lookback_minutes": 5},
    )
    second = client.get(
        "/api/v1/alerts/logons",
        headers=query_headers,
        params={"lookback_minutes": 5},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(first.json()) == 1
    assert first.json()[0]["alert_id"] == second.json()[0]["alert_id"]
    assert first.json()[0]["router_name"] == "router-01"
    assert first.json()[0]["source_id"] == "primary-ovpn"
    assert first.json()[0]["username"] == "vpn-alert-user"
    assert first.json()[0]["alert_value"] == 1

    _post_event(
        client,
        registered,
        _event(
            event_id="disconnect-alert",
            event_type="DISCONNECT",
            username="vpn-alert-user",
            occurred_at="2026-08-24T17:03:00Z",
        ),
    )

    after_disconnect = client.get("/api/v1/alerts/logons", headers=query_headers)
    assert after_disconnect.status_code == 200
    assert len(after_disconnect.json()) == 1
    assert after_disconnect.json()[0]["alert_id"] == first.json()[0]["alert_id"]


def test_alert_lookback_is_bounded(client, query_headers):
    too_small = client.get(
        "/api/v1/alerts/logons",
        headers=query_headers,
        params={"lookback_minutes": 0},
    )
    too_large = client.get(
        "/api/v1/alerts/logons",
        headers=query_headers,
        params={"lookback_minutes": 61},
    )

    assert too_small.status_code == 422
    assert too_large.status_code == 422
