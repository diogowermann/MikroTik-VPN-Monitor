# MikroTik VPN Monitor documentation

This directory contains the public technical documentation for MikroTik VPN Monitor.

## Documents

- [System architecture](system-architecture.md) — components, trust boundaries, sources, event flow, snapshot reconciliation and overall data model.
- [Persistence model](persistence-model.md) — routers, credential storage, configurable sources, immutable events, consolidated sessions, indexes and Alembic migrations.
- [Router registration and event ingestion](router-ingestion.md) — provisioning, secret rotation, request authentication, contract v1, idempotency and CONNECT/DISCONNECT session projection.
- [Snapshot ingestion and reconciliation](snapshot-reconciliation.md) — `/ppp active` contract, per-source ordering, missing-event recovery, reboot handling and reconciliation semantics.
- [RouterOS integration](routeros-integration.md) — lifecycle hooks, shared credential/senders, profile-aware snapshots, TLS, retries and rollout sequence.
- [Linux installation and deployment](installation.md) — system user, virtualenv, SQLite state, systemd, Nginx ingestion boundary, updates and rollout order.
- [Grafana query API and alerting](grafana.md) — local read API, `X-API-Key`, dashboard projections, event-based logon feed and Infinity alert rule shape.

Additional implementation guides will be added as the project progresses:

- operational troubleshooting and upgrades;
- validated dashboard examples after the first end-to-end deployment.

## Public documentation policy

Examples in this repository must remain infrastructure-agnostic. Use fictitious hostnames, users and documentation network ranges only. Never add real credentials, internal DNS names, private/public production addresses, certificate material, RouterOS exports or captured VPN telemetry.
