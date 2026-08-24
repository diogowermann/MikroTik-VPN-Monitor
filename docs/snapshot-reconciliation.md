# Snapshot ingestion and reconciliation

This document describes the contract and state-reconciliation behavior used to compare MikroTik RouterOS `/ppp active` state with the session projection stored by MikroTik VPN Monitor.

All examples are intentionally fictitious. Production router identifiers, secrets, PPP identities, addresses and source configuration must remain outside this public repository.

## 1. Why snapshots exist

PPP `on-up` and `on-down` lifecycle hooks remain the preferred history source because they capture short sessions and preserve the real connection/disconnection sequence.

A lifecycle event can still be missed during a network, reverse-proxy or API outage. The snapshot path provides eventual consistency by periodically submitting the current RouterOS active-session set.

The two inputs have different roles:

```text
PPP on-up / on-down  -> immutable lifecycle history
/ppp active snapshot -> current-state reconciliation
```

Snapshots do not create synthetic immutable `vpn_events`. They only reconcile the `vpn_sessions` projection.

## 2. Endpoint and authentication

```http
POST /api/v1/router/snapshot
Content-Type: application/json
X-Router-ID: <router-id>
Authorization: Bearer <router-secret>
```

The endpoint uses the same per-router authentication boundary as lifecycle ingestion. Missing, invalid, revoked or disabled-router credentials are rejected before reconciliation.

## 3. Contract v1

Example:

```json
{
  "contract_version": 1,
  "source_id": "primary-ovpn",
  "observed_at": "2026-08-24T12:05:00Z",
  "boot_id": "example-boot-id",
  "sessions": [
    {
      "router_session_id": "example-session-id",
      "username": "vpn-user",
      "service": "ovpn",
      "caller_id": "203.0.113.10",
      "address": "10.10.0.20",
      "local_address": "10.10.0.1",
      "interface_id": null,
      "uptime_seconds": 300
    }
  ]
}
```

### Top-level fields

| Field | Required | Purpose |
| --- | --- | --- |
| `contract_version` | yes | Must be `1` for the current contract. |
| `source_id` | yes | Stable source name configured for the authenticated router. |
| `observed_at` | yes | Router-observed timestamp with an explicit timezone offset. |
| `boot_id` | no | Stable identifier for the current router boot/generation when available. |
| `sessions` | yes | Current active sessions belonging to this source. An empty list is valid. |

`source_id` is the public source name, not the internal database UUID.

### Session fields

| Field | Required | Purpose |
| --- | --- | --- |
| `router_session_id` | yes | Router-observed PPP session identity used as the primary reconciliation key. |
| `username` | yes | Authenticated PPP identity. |
| `service` | yes | PPP service such as `ovpn`. |
| `caller_id` | no | Remote peer/caller identity when RouterOS exposes it. |
| `address` | no | VPN address assigned to the remote session. |
| `local_address` | no | Local PPP address when available. |
| `interface_id` | no | Interface identity when available to the collection script. |
| `uptime_seconds` | no | Session uptime used to approximate `connected_at` when the CONNECT event was missed. |

One snapshot cannot contain the same `router_session_id` twice.

## 4. Source validation

The source must:

- belong to the authenticated router;
- be enabled;
- allow every PPP service represented in the submitted sessions.

A source may represent a single profile or a wider selector composed of services, profiles and interfaces. The central reconciliation algorithm remains unchanged when additional sources are enabled later.

## 5. Per-source ordering

Each source persists its own `last_snapshot_at` timestamp.

This is required because one router may have several monitored sources. A snapshot from source A must not make a valid snapshot from source B appear stale simply because the two scheduler executions occur at slightly different times.

When:

```text
observed_at <= source.last_snapshot_at
```

the snapshot is acknowledged as stale and no session state is changed.

Example response:

```json
{
  "accepted": 0,
  "stale": true,
  "source_id": "primary-ovpn",
  "observed_sessions": 0,
  "created": 0,
  "refreshed": 0,
  "closed": 0,
  "reboot_closed": 0
}
```

This prevents delayed or repeated snapshots from reversing newer state.

## 6. Matching an observed session

For each submitted session the service first searches for an active session with:

```text
router + source + router_session_id
```

If found, the existing projection is refreshed and `last_observed_at` is advanced.

### Event-to-snapshot correlation

A CONNECT event may create an active session before the periodic snapshot has exposed the RouterOS `router_session_id` to the API.

When no `router_session_id` match exists, the service searches for an active event-origin session with no router session ID using:

```text
router + source + username + service
```

Address, caller ID and interface are also used as compatibility checks when both sides provide them.

The fallback is applied only when exactly one compatible candidate exists. Ambiguous candidates are not guessed.

When the unique fallback succeeds, the snapshot attaches `router_session_id` to the existing event-origin session instead of creating a duplicate row.

## 7. Missing CONNECT recovery

If an observed RouterOS session has no matching active projection, the API creates:

```text
state=ACTIVE
origin=RECONCILIATION
```

If `uptime_seconds` is available:

```text
connected_at = observed_at - uptime_seconds
```

Otherwise `connected_at` defaults to `observed_at` because the exact start time cannot be reconstructed safely.

This recovered session does not fabricate a `vpn_events` CONNECT record. Event history and reconciled state remain distinguishable.

## 8. Missing DISCONNECT recovery

After all observed sessions are matched or created, the API compares them with active stored sessions for the same router/source.

An active stored session that is absent from the current snapshot is closed as:

```text
state=CLOSED
end_reason=RECONCILIATION
```

The disconnect timestamp becomes the snapshot `observed_at` value and duration is calculated from the stored `connected_at` timestamp.

### Empty snapshot

An empty `sessions` list is meaningful. It states that the source currently has no active sessions.

Therefore an accepted empty snapshot closes all eligible active sessions for that source with `end_reason=RECONCILIATION`.

## 9. Temporal protection

A snapshot cannot safely describe state that began after the snapshot itself was observed.

For that reason, only sessions satisfying:

```text
connected_at <= observed_at
```

are eligible for snapshot matching or closure.

This protects a newer CONNECT event from being incorrectly closed by a delayed older snapshot.

## 10. Router reboot detection

When `boot_id` is supplied, the router stores the most recently accepted boot identifier.

On the first boot-aware snapshot, the identifier is recorded without assuming a reboot.

When a later, non-stale snapshot supplies a different boot identifier, every eligible active session for that router is closed with:

```text
end_reason=ROUTER_REBOOT
```

This closure is router-wide rather than source-specific because a RouterOS reboot invalidates PPP sessions across all monitored sources.

The current source snapshot is then reconciled normally, so any sessions active after the reboot are recreated/refreshed under the new boot generation.

A snapshot carrying an older boot identifier cannot roll the router back when its `observed_at` is not newer than the router-wide latest snapshot timestamp.

## 11. Response counters

Successful reconciliation returns operational counters:

```json
{
  "accepted": 1,
  "stale": false,
  "source_id": "primary-ovpn",
  "observed_sessions": 1,
  "created": 0,
  "refreshed": 1,
  "closed": 0,
  "reboot_closed": 0
}
```

- `created`: sessions created because current RouterOS state had no projection;
- `refreshed`: existing active sessions matched and updated;
- `closed`: sessions missing from this source snapshot and closed by reconciliation;
- `reboot_closed`: router-wide active sessions closed after a boot-generation change.

## 12. Failure behavior

| Status | Meaning |
| --- | --- |
| `200` | Snapshot reconciled or safely ignored as stale. |
| `401` | Missing, invalid, revoked or disabled-router credential. |
| `422` | Invalid contract, timestamp, source, duplicate router session IDs or disallowed service. |

Contract validation and source-scope validation happen before session state is changed.

## 13. What snapshots cannot recover

A session that both connects and disconnects entirely while lifecycle event delivery and snapshot delivery are unavailable may never appear in central state.

That limitation is intentional in the first version. The RouterOS lifecycle hooks remain the mechanism for durable history, while snapshots provide state repair rather than a replacement event log.

## 14. Public repository safety

Do not commit:

- real `router_id`, `boot_id` or production session IDs;
- bearer secrets or credential hashes;
- production PPP usernames, supplier/customer identities or captured snapshots;
- internal DNS names, production IP ranges or RouterOS exports;
- database files containing actual session history.
