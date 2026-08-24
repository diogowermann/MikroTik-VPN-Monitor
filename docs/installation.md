# Linux installation and service deployment

This guide deploys MikroTik VPN Monitor as a single-host Linux service with:

- application checkout under `/opt`;
- a dedicated unprivileged system user;
- a Python virtual environment;
- SQLite state under `/var/lib`;
- runtime configuration under `/etc`;
- Alembic migrations before every service start;
- journald logging;
- FastAPI bound only to loopback;
- Nginx exposing only the RouterOS ingestion endpoints over HTTPS.

All hostnames, addresses and identities in this document are fictitious. Production values must stay outside the public repository.

## 1. Supported deployment model

The intended topology is:

```text
RouterOS
   |
   | HTTPS POST
   v
Nginx :443
   |
   | only /api/v1/router/events
   | and  /api/v1/router/snapshot
   v
127.0.0.1:8092
MikroTik VPN Monitor
   |
   v
/var/lib/mikrotik-vpn-monitor/vpn-monitor.db

Grafana / local administration
   |
   +----> 127.0.0.1:8092
```

Port `8092` is not intended to listen on a LAN/WAN address. Keep `VPN_MONITOR_BIND_HOST=127.0.0.1` in the supported production deployment.

## 2. Prerequisites

The first supported Linux deployment expects:

- Python 3.11 or newer;
- Python `venv` support;
- Git;
- systemd;
- Nginx or an equivalent TLS reverse proxy;
- an HTTPS certificate whose CA chain can be trusted by RouterOS.

Package names vary by distribution. On Debian/Ubuntu-like hosts they commonly include `python3`, `python3-venv`, `git` and `nginx`.

## 3. Clone the application

Recommended location:

```bash
git clone https://github.com/diogowermann/MikroTik-VPN-Monitor.git /opt/mikrotik-vpn-monitor
cd /opt/mikrotik-vpn-monitor
```

For controlled production changes, deploy a reviewed commit or release rather than an arbitrary development branch.

## 4. Run the installer

From the repository root:

```bash
sudo bash scripts/install_linux.sh
```

The installer is intentionally conservative. It:

1. creates the `mikrotik-vpn-monitor` system group if necessary;
2. creates the `mikrotik-vpn-monitor` system user if necessary;
3. prepares `/etc/mikrotik-vpn-monitor`;
4. prepares `/var/lib/mikrotik-vpn-monitor`;
5. creates the production environment file only when it does not already exist;
6. creates/refreshes `.venv` under the application checkout;
7. installs the current project into the virtual environment;
8. materializes the systemd unit from the public template;
9. reloads the systemd manager configuration;
10. verifies the rendered unit when `systemd-analyze` is available.

The installer **does not enable or start the service automatically**. This prevents a public placeholder configuration from becoming active by accident.

Running the installer again is the supported way to refresh the virtual environment and systemd unit after a code update. Existing runtime configuration is preserved.

## 5. Configure the runtime environment

Edit:

```text
/etc/mikrotik-vpn-monitor/mikrotik-vpn-monitor.env
```

The default production template is:

```dotenv
VPN_MONITOR_DATABASE_URL=sqlite:////var/lib/mikrotik-vpn-monitor/vpn-monitor.db
VPN_MONITOR_QUERY_API_KEY=replace-with-a-long-random-query-key
VPN_MONITOR_LOG_LEVEL=INFO
VPN_MONITOR_BIND_HOST=127.0.0.1
VPN_MONITOR_BIND_PORT=8092
```

Generate a high-entropy query key before query endpoints are enabled, for example with the operating system's preferred secret generator. Do not commit the resulting value.

The database URL should continue to point at the systemd state directory unless an intentional database migration is being performed.

## 6. SQLite production behavior

The application configures file-backed SQLite connections with:

```text
foreign_keys = ON
journal_mode = WAL
busy_timeout = 5000 ms
synchronous = NORMAL
```

This keeps the deployment lightweight while allowing the API and local read workloads to coexist more safely than the default rollback-journal behavior.

SQLite remains the intended database for the current single-host workload. SQLAlchemy/Alembic preserve a future migration path if scale or concurrency requirements change.

## 7. Start the systemd service

After reviewing the environment file:

```bash
sudo systemctl enable --now mikrotik-vpn-monitor
```

Check status:

```bash
sudo systemctl status mikrotik-vpn-monitor --no-pager
```

The unit runs Alembic automatically before starting the API:

```text
alembic upgrade head
```

If a migration fails, the API does not start. This is deliberate: serving against an unknown schema is considered less safe than failing closed.

### Local health check

```bash
curl -fsS http://127.0.0.1:8092/api/v1/health
```

Expected response:

```json
{"status":"ok"}
```

### Logs

Recent service logs:

```bash
sudo journalctl -u mikrotik-vpn-monitor -n 100 --no-pager
```

Follow logs:

```bash
sudo journalctl -u mikrotik-vpn-monitor -f
```

## 8. systemd hardening

The supplied unit runs without root privileges and includes conservative hardening such as:

- `NoNewPrivileges=true`;
- `ProtectSystem=strict`;
- `ProtectHome=true`;
- private temporary/device namespaces;
- kernel/control-group protection;
- empty Linux capability sets;
- restricted address families;
- a dedicated writable `StateDirectory`.

Application logs remain in journald. The service does not need a writable log directory.

## 9. Configure the HTTPS reverse proxy

The public template is:

```text
deploy/nginx.conf.example
```

Copy it to the appropriate Nginx configuration location for the distribution and replace:

- `vpn-api.example.com` with the production ingestion FQDN;
- the fictitious certificate paths;
- `192.0.2.10` with the RouterOS source address allowed to submit telemetry.

For multiple routers, add one explicit `allow` line per trusted source before `deny all`.

The example exposes only:

```text
POST /api/v1/router/events
POST /api/v1/router/snapshot
```

All other paths return `404` through that virtual host. The application health endpoint and future query endpoints are intentionally not proxied.

Validate Nginx before reloading:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Do not expose port `8092` through the host firewall.

## 10. TLS trust

The RouterOS templates use:

```text
check-certificate=yes
```

Therefore the certificate presented by Nginx must chain to a CA trusted by the MikroTik device.

Validate the certificate chain and RouterOS trust before applying PPP lifecycle hooks. Disabling certificate verification is not part of the supported deployment model.

## 11. Register the router after the API is running

Router registration writes to the production database, so run the administrative helper with the production environment loaded and under the service identity.

Example:

```bash
sudo -u mikrotik-vpn-monitor bash -c '
  set -a
  source /etc/mikrotik-vpn-monitor/mikrotik-vpn-monitor.env
  set +a
  /opt/mikrotik-vpn-monitor/.venv/bin/python \
    /opt/mikrotik-vpn-monitor/scripts/register_router.py \
    --name router-01 \
    --source-name primary-ovpn \
    --service ovpn \
    --profile example-ovpn-profile
'
```

The command prints a one-time router secret. Store it securely and place it only in the private RouterOS `vpn-monitor-config`. The plaintext secret cannot be recovered from the API database later.

## 12. Controlled RouterOS rollout

Once the Linux/API side is healthy:

1. confirm the RouterOS clock/NTP state;
2. confirm the API certificate chain is trusted by RouterOS;
3. prepare private copies of the `.rsc` templates;
4. run RouterOS `/import ... verbose=yes dry-run` for each prepared file;
5. import the shared configuration and senders;
6. run one snapshot manually before enabling the scheduler;
7. apply lifecycle hooks to one intended profile;
8. verify one CONNECT, one snapshot refresh and one DISCONNECT;
9. verify reconciliation behavior;
10. only then enable recurring collection broadly.

See [RouterOS integration](routeros-integration.md) for the collection contract and failure semantics.

## 13. Updating the application

A typical update is:

```bash
cd /opt/mikrotik-vpn-monitor
git pull --ff-only
sudo bash scripts/install_linux.sh
sudo systemctl restart mikrotik-vpn-monitor
```

The installer preserves the existing `/etc/mikrotik-vpn-monitor/mikrotik-vpn-monitor.env` file.

The restart runs `alembic upgrade head` before launching the new application process.

For schema-changing releases, take a database backup before updating. A straightforward maintenance-window approach is to stop the service, copy the SQLite database and its WAL/SHM companions when present, then perform the update and restart.

## 14. Rollback boundary

Application rollback and database rollback are separate operations.

Reverting the Git checkout alone does not automatically downgrade Alembic. If a future release introduces a schema change that is not backward-compatible, follow that release's documented database downgrade/restore procedure rather than blindly checking out an older commit.

## 15. Public repository boundary

Never commit deployment-specific copies containing:

- production FQDNs or IP allowlists;
- real TLS certificates/private keys;
- the production environment file;
- query keys or router ingestion secrets;
- production SQLite files or WAL/SHM files;
- Nginx configuration copied back from the live host;
- production logs or captured telemetry.

Keep those values under `/etc`, `/var/lib`, the system certificate store and private infrastructure management only.
