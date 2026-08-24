from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTEROS = ROOT / "routeros"


def _read(name: str) -> str:
    return (ROUTEROS / name).read_text(encoding="utf-8")


def test_routeros_templates_are_present():
    expected = {
        "config.example.rsc",
        "event-sender.rsc",
        "snapshot-sender.rsc",
        "profile-hooks.example.rsc",
        "snapshot-source.example.rsc",
        "README.md",
    }
    assert expected <= {path.name for path in ROUTEROS.iterdir() if path.is_file()}


def test_config_template_contains_only_public_placeholders():
    content = _read("config.example.rsc")

    assert '"apiBase"="https://vpn-api.example.com/api/v1"' in content
    assert '"routerId"="00000000-0000-0000-0000-000000000000"' in content
    assert '"routerSecret"="REPLACE_WITH_ROUTER_SECRET"' in content


def test_event_sender_uses_authenticated_json_https_delivery():
    content = _read("event-sender.rsc")

    assert '"event_id"=$eventId' in content
    assert '"interface_id"=[:tostr $vpnInterfaceId]' in content
    assert "/router/events" in content
    assert "Content-Type:application/json" in content
    assert "X-Router-ID:" in content
    assert "Authorization:Bearer " in content
    assert "check-certificate=yes" in content
    assert ":serialize" in content
    assert ":retry" in content
    assert ":rndstr" in content


def test_snapshot_sender_uses_ppp_active_and_local_profile_filtering():
    content = _read("snapshot-sender.rsc")

    assert "/ppp active print as-value" in content
    assert '($activeRow->"session-id")' in content
    assert '($activeRow->"uptime")' in content
    assert "/ppp secret find where name=$vpnName" in content
    assert '"uptime_seconds"=$uptimeSeconds' in content
    assert "/router/snapshot" in content
    assert "check-certificate=yes" in content
    assert ":retry" in content


def test_profile_hook_example_maps_connect_and_disconnect_to_one_source():
    content = _read("profile-hooks.example.rsc")

    assert 'name="example-ovpn-profile"' in content
    assert 'eventType="CONNECT"' in content
    assert 'eventType="DISCONNECT"' in content
    assert 'sourceName="primary-ovpn"' in content
    assert 'vpnInterfaceId=$interface' in content


def test_snapshot_source_example_runs_every_minute_with_profile_filter():
    content = _read("snapshot-source.example.rsc")

    assert 'name="vpn-monitor-snapshot-primary"' in content
    assert 'sourceName="primary-ovpn"' in content
    assert 'profileNames={"example-ovpn-profile"}' in content
    assert "interval=1m" in content
    assert "policy=read,test" in content
