from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_systemd_template_runs_migrations_and_hardens_service():
    unit = read_text("deploy/mikrotik-vpn-monitor.service.in")

    assert "User=@APP_USER@" in unit
    assert "Group=@APP_GROUP@" in unit
    assert "EnvironmentFile=@ENV_FILE@" in unit
    assert "StateDirectory=mikrotik-vpn-monitor" in unit
    assert "ExecStartPre=@APP_ROOT@/.venv/bin/alembic -c @APP_ROOT@/alembic.ini upgrade head" in unit
    assert "ExecStart=@APP_ROOT@/.venv/bin/mikrotik-vpn-monitor" in unit
    assert "ProtectSystem=strict" in unit
    assert "NoNewPrivileges=true" in unit
    assert "CapabilityBoundingSet=" in unit


def test_nginx_template_exposes_only_exact_ingestion_routes():
    nginx = read_text("deploy/nginx.conf.example")

    assert "location = /api/v1/router/events" in nginx
    assert "location = /api/v1/router/snapshot" in nginx
    assert "proxy_pass http://127.0.0.1:8092;" in nginx
    assert "allow 192.0.2.10;" in nginx
    assert "limit_except POST" in nginx
    assert "location / {\n        return 404;\n    }" in nginx
    assert "/api/v1/health" not in nginx
    assert "/api/v1/query/" not in nginx
    assert "/api/v1/alerts/" not in nginx


def test_production_environment_keeps_api_on_loopback_and_database_in_state_dir():
    environment = read_text("deploy/mikrotik-vpn-monitor.env.example")

    assert "VPN_MONITOR_DATABASE_URL=sqlite:////var/lib/mikrotik-vpn-monitor/vpn-monitor.db" in environment
    assert "VPN_MONITOR_BIND_HOST=127.0.0.1" in environment
    assert "VPN_MONITOR_BIND_PORT=8092" in environment
    assert "replace-with-a-long-random-query-key" in environment


def test_linux_installer_has_valid_shell_syntax_and_preserves_existing_environment():
    installer_path = ROOT / "scripts/install_linux.sh"
    subprocess.run(["bash", "-n", str(installer_path)], check=True)

    installer = installer_path.read_text(encoding="utf-8")
    assert "Preserving existing $ENV_FILE" in installer
    assert "systemctl daemon-reload" in installer
    assert "The service was NOT enabled or started automatically." in installer
