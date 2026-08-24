# MikroTik VPN Monitor documentation

This directory contains the public technical documentation for MikroTik VPN Monitor.

## Documents

- [System architecture](system-architecture.md) — components, trust boundaries, sources, event flow, snapshot reconciliation and overall data model.
- [Persistence model](persistence-model.md) — routers, credential storage, configurable sources, immutable events, consolidated sessions, indexes and Alembic migrations.
- [Router registration and event ingestion](router-ingestion.md) — provisioning, secret rotation, request authentication, contract v1, idempotency and CONNECT/DISCONNECT session projection.

Additional implementation guides will be added as the project progresses:

- installation and Linux service management;
- RouterOS event hooks and snapshot scheduler;
- snapshot reconciliation;
- Grafana dashboards and alerting;
- operational troubleshooting and upgrades.

## Public documentation policy

Examples in this repository must remain infrastructure-agnostic. Use fictitious hostnames, users and documentation network ranges only. Never add real credentials, internal DNS names, private/public production addresses, certificate material, RouterOS exports or captured VPN telemetry.
