# Router registration and event ingestion

This document describes the first authenticated RouterOS lifecycle-ingestion contract for MikroTik VPN Monitor.

All examples are intentionally fictitious. Production router identifiers, secrets, PPP identities, addresses and source configuration must remain outside this public repository.

## 1. Register a router

Apply database migrations before registering a router:

```bash
alembic upgrade head
```

Register one RouterOS device and its initial monitoring source:

```bash
python scripts/register_router.py \
  --name router-01 \
  --source-name primary-ovpn \
  --service ovpn \
  --profile example-ovpn-profile
```

The command prints three values:

```text
router_id=<generated-uuid>
source_id=primary-ovpn
router_secret=<one-time-secret>
```

The plaintext secret is shown only at provisioning time. The database stores only its SHA-256 hash. The secret is high entropy and must be transferred to RouterOS through a protected administrative process.

Multiple `--service`, `--profile` and `--interface` arguments may be supplied for the initial source.

## 2. Add another source

A registered router can own multiple monitoring sources without receiving another credential.

Example of staging another PPP profile while leaving it disabled:

```bash
python scripts/add_source.py \
  --router-id <router-id> \
  --name secondary-ovpn \
  --service ovpn \
  --profile example-restricted-profile \
  --disabled
```

The source stores its own service, profile and interface selectors. Creating it with `--disabled` allows configuration to be prepared without accepting events for that source yet.

This is the intended mechanism for introducing additional profiles/interfaces later without redesigning the API or data model.

## 3. Rotate a router secret

```bash
python scripts/rotate_router_token.py --router-id <router-id>
```

Rotation:

1. revokes all currently active ingestion credentials for that router;
2. creates one new high-entropy credential;
3. prints the new plaintext secret once.

The previous credential stops authenticating immediately, so update RouterOS promptly after rotation.

## 4. Authentication

Lifecycle ingestion requires both headers:

```http
X-Router-ID: <router-id>
Authorization: Bearer <router-secret>
```

Authentication succeeds only when:

- the router exists;
- the router is enabled;
- the supplied secret matches a non-revoked credential.

Successful authentication updates credential `last_used_at` and router `last_seen_at`.

Router credentials authorize ingestion only. They are deliberately separate from future local/query credentials.

## 5. Event endpoint

```http
POST /api/v1/router/events
Content-Type: application/json
X-Router-ID: <router-id>
Authorization: Bearer <router-secret>
```

### CONNECT example

```json
{
  "contract_version": 1,
  "event_id": "example-connect-0001",
  "event_type": "CONNECT",
  "source_id": "primary-ovpn",
  "service": "ovpn",
  "username": "vpn-user",
  "caller_id": "203.0.113.10",
  "local_address": "10.10.0.1",
  "remote_address": "10.10.0.20",
  "interface_id": "example-interface-id",
  "occurred_at": "2026-08-24T12:00:00Z"
}
```

### DISCONNECT example

```json
{
  "contract_version": 1,
  "event_id": "example-disconnect-0001",
  "event_type": "DISCONNECT",
  "source_id": "primary-ovpn",
  "service": "ovpn",
  "username": "vpn-user",
  "caller_id": "203.0.113.10",
  "local_address": "10.10.0.1",
  "remote_address": "10.10.0.20",
  "interface_id": "example-interface-id",
  "occurred_at": "2026-08-24T12:05:00Z"
}
```

`occurred_at` must contain an explicit timezone offset. The API normalizes it to UTC before persistence.

## 6. `source_id` semantics

The public event field is named `source_id`, but its value is the stable **source name** configured for that router, for example:

```text
primary-ovpn
```

The API resolves this name to the internal source UUID before persistence. RouterOS therefore never needs to know database UUIDs for sources.

An event is rejected when the source:

- does not exist for the authenticated router;
- is disabled;
- does not allow the submitted PPP service.

Profile/interface lists stored on the source are provisioning selectors used to decide where RouterOS hooks or future source-specific scripts are installed. The lifecycle event itself carries the stable source name explicitly.

## 7. Idempotency

`event_id` is unique per router.

First delivery:

```json
{
  "accepted": 1,
  "duplicates": 0,
  "event_id": "example-connect-0001",
  "session_action": "CREATED"
}
```

An exact replay of the same event is successful but does not create another immutable event or session:

```json
{
  "accepted": 0,
  "duplicates": 1,
  "event_id": "example-connect-0001",
  "session_action": "UNCHANGED"
}
```

Reusing the same `event_id` with different event content returns HTTP `409 Conflict`. This prevents accidental identifier reuse from silently replacing or masking telemetry.

## 8. Session projection

### CONNECT

A valid `CONNECT` creates an `ACTIVE` session with `origin=EVENT`.

When `interface_id` is present and an active session already exists with the same router, source, user, service and interface, the existing projection is refreshed instead of creating a second active row.

Possible `session_action` values include:

```text
CREATED
ALREADY_ACTIVE
```

### DISCONNECT

The API first looks for an active session matching:

```text
router + source + username + service + interface_id
```

If `interface_id` is not provided, it falls back to the most recent active session for:

```text
router + source + username + service
```

A match is closed with:

```text
state=CLOSED
end_reason=DISCONNECT
```

Duration is calculated in seconds from `connected_at` to the RouterOS-observed disconnect timestamp.

If no active session can be correlated, the immutable DISCONNECT event is still retained and the response uses:

```text
NO_ACTIVE_SESSION
```

Periodic snapshot reconciliation will address missed lifecycle state in the next implementation phase.

## 9. Error behavior

Typical responses:

| Status | Meaning |
| --- | --- |
| `200` | Event accepted or exact replay acknowledged |
| `401` | Missing, invalid, revoked or disabled-router credential |
| `409` | `event_id` reused with different content |
| `422` | Invalid contract, timestamp, source or source service scope |

## 10. Trust boundary

The intended deployment remains:

```text
RouterOS -> HTTPS reverse proxy -> loopback FastAPI
Grafana  -> local read API       -> loopback FastAPI
```

Only authenticated ingestion routes need to be reachable by RouterOS. Query routes are intended to remain local to the monitoring host.

## 11. Public repository safety

Do not commit:

- real router IDs or bearer secrets;
- hashes copied from the production database;
- production PPP usernames or supplier/customer identities;
- internal DNS names, production addresses or network ranges;
- RouterOS exports containing environment-specific configuration;
- captured event payloads from production.
