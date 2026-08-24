#!/usr/bin/env bash
set -euo pipefail

APP_NAME="mikrotik-vpn-monitor"
APP_USER="${APP_USER:-mikrotik-vpn-monitor}"
APP_GROUP="${APP_GROUP:-mikrotik-vpn-monitor}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="${APP_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
CONFIG_DIR="/etc/$APP_NAME"
STATE_DIR="/var/lib/$APP_NAME"
ENV_FILE="$CONFIG_DIR/$APP_NAME.env"
SERVICE_FILE="/etc/systemd/system/$APP_NAME.service"
SERVICE_TEMPLATE="$APP_ROOT/deploy/$APP_NAME.service.in"
ENV_TEMPLATE="$APP_ROOT/deploy/$APP_NAME.env.example"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

if [[ "${EUID}" -ne 0 ]]; then
    fail "run this installer as root"
fi

if [[ "$APP_ROOT" =~ [[:space:]] ]] || [[ "$APP_ROOT" == *"|"* ]] || [[ "$APP_ROOT" == *"&"* ]]; then
    fail "APP_ROOT must not contain whitespace, | or &"
fi

[[ -f "$APP_ROOT/pyproject.toml" ]] || fail "pyproject.toml not found under APP_ROOT=$APP_ROOT"
[[ -f "$SERVICE_TEMPLATE" ]] || fail "systemd template not found: $SERVICE_TEMPLATE"
[[ -f "$ENV_TEMPLATE" ]] || fail "environment template not found: $ENV_TEMPLATE"

require_command python3
require_command getent
require_command groupadd
require_command useradd
require_command systemctl
require_command sed
require_command install

python3 -m venv --help >/dev/null 2>&1 || fail "python3 venv support is required"

if ! getent group "$APP_GROUP" >/dev/null 2>&1; then
    groupadd --system "$APP_GROUP"
fi

if ! id -u "$APP_USER" >/dev/null 2>&1; then
    NOLOGIN_SHELL="$(command -v nologin || true)"
    if [[ -z "$NOLOGIN_SHELL" ]]; then
        NOLOGIN_SHELL="/usr/sbin/nologin"
    fi
    useradd \
        --system \
        --gid "$APP_GROUP" \
        --home-dir "$STATE_DIR" \
        --no-create-home \
        --shell "$NOLOGIN_SHELL" \
        "$APP_USER"
fi

install -d -o root -g "$APP_GROUP" -m 0750 "$CONFIG_DIR"
install -d -o "$APP_USER" -g "$APP_GROUP" -m 0750 "$STATE_DIR"

if [[ ! -e "$ENV_FILE" ]]; then
    install -o root -g "$APP_GROUP" -m 0640 "$ENV_TEMPLATE" "$ENV_FILE"
    echo "Created $ENV_FILE from the public template."
else
    echo "Preserving existing $ENV_FILE."
fi

python3 -m venv "$APP_ROOT/.venv"
"$APP_ROOT/.venv/bin/python" -m pip install --upgrade "$APP_ROOT"

TEMP_SERVICE="$(mktemp)"
trap 'rm -f "$TEMP_SERVICE"' EXIT

sed \
    -e "s|@APP_USER@|$APP_USER|g" \
    -e "s|@APP_GROUP@|$APP_GROUP|g" \
    -e "s|@APP_ROOT@|$APP_ROOT|g" \
    -e "s|@ENV_FILE@|$ENV_FILE|g" \
    "$SERVICE_TEMPLATE" > "$TEMP_SERVICE"

install -o root -g root -m 0644 "$TEMP_SERVICE" "$SERVICE_FILE"
systemctl daemon-reload

if command -v systemd-analyze >/dev/null 2>&1; then
    systemd-analyze verify "$SERVICE_FILE"
fi

cat <<EOF

Linux deployment files are installed.

The service was NOT enabled or started automatically.

Next steps:
  1. Review and customize: $ENV_FILE
  2. Keep VPN_MONITOR_BIND_HOST=127.0.0.1 for the supported deployment model.
  3. Enable/start: systemctl enable --now $APP_NAME
  4. Check: systemctl status $APP_NAME --no-pager
  5. Validate locally: curl -fsS http://127.0.0.1:8092/api/v1/health
  6. Customize deploy/nginx.conf.example and validate it with nginx -t before reload.
EOF
