# RouterOS integration

This document describes how RouterOS delivers lifecycle events and current-state snapshots to the central MikroTik VPN Monitor API.

All examples are intentionally fictitious. Production router IDs, secrets, PPP profile names, identities, API hostnames and network information must remain outside this public repository.

## 1. Collection model

RouterOS uses two complementary paths:

```text
PPP on-up / on-down
        |
        | CONNECT / DISCONNECT
        v
POST /api/v1/router/events

/ppp active + scheduler
        |
        | current-state snapshot
        v
POST /api/v1/router/snapshot
```

Lifecycle events retain history. Snapshots repair current state when an event cannot be delivered.

## 2. Shared configuration

The RouterOS templates store three deployment values in one `vpn-monitor-config` system script:

```text
apiBase
routerId
routerSecret
```

Only a locally customized copy should contain real values.

The event and snapshot senders parse the configuration script when invoked. This keeps the bearer secret out of individual PPP profile hooks and out of source-specific scheduler wrappers.

## 3. Lifecycle hooks

RouterOS PPP profiles expose the following variables to `on-up` and `on-down` scripts:

```text
user
local-address
remote-address
caller-id
called-id
interface
```

The `interface` value is an internal interface ID rather than an interface name.

The generic hook maps these values to the API event contract:

| RouterOS hook value | API field |
| --- | --- |
| configured hook action | `event_type` |
| configured source name | `source_id` |
| configured PPP service | `service` |
| `user` | `username` |
| `caller-id` | `caller_id` |
| `local-address` | `local_address` |
| `remote-address` | `remote_address` |
| `interface` | `interface_id` |
| RouterOS date/time/GMT offset | `occurred_at` |

A random `event_id` is generated once before delivery begins. The same payload is reused for all retry attempts, preserving API idempotency.

## 4. HTTP delivery

Both senders use HTTPS POST with:

```http
Content-Type: application/json
X-Router-ID: <router UUID>
Authorization: Bearer <router secret>
```

The templates use `check-certificate=yes`. Production deployment must therefore install/trust the appropriate CA chain on RouterOS before enabling hooks.

Each POST is retried up to three times with a one-second delay. A terminal delivery failure is written to the RouterOS log.

## 5. Snapshot collection

The snapshot sender reads:

```routeros
/ppp active print as-value where service=<configured-service>
```

For each included active session it sends:

```text
router_session_id <- session-id
username          <- name
service           <- service
caller_id         <- caller-id
address           <- address
uptime_seconds    <- uptime converted to seconds
```

The generic collector intentionally does not populate `interface_id` or `local_address` from `/ppp active` because those values are not reliably exposed by the active-session view in the same form used by lifecycle hooks.

## 6. Source/profile selection

A source is still identified by its stable configured source name, for example `primary-ovpn`.

When one RouterOS router has multiple monitored PPP profiles, each profile hook can point at a different `sourceName` while using the same shared sender and router credential.

For snapshots, `profileNames` is optional:

- empty filter: include every active PPP session matching `serviceName`;
- populated filter: resolve each active username in local `/ppp secret` and include it only when its configured profile is in `profileNames`.

This prevents two local PPP profiles using the same `ovpn` service from being merged into one source snapshot.

### RADIUS limitation

A RADIUS-only identity with no local `/ppp secret` has no locally queryable profile assignment for this generic collector. When a profile filter is active, such a session is skipped rather than guessed.

A deployment that requires RADIUS profile reconciliation should provide an explicit environment-specific mapping instead of weakening source isolation.

## 7. Interface-specific sources

Lifecycle events support interface-aware data because PPP hook variable `interface` is available at connection/disconnection time.

The generic snapshot template does not attempt interface-only partitioning. `/ppp active` provides `session-id` for durable reconciliation but does not expose the same hook interface ID as a documented active-user field.

Consequently:

- profile-based source partitioning is supported by the generic snapshot template;
- interface metadata is retained on lifecycle events;
- interface-only snapshot partitioning remains an extension point.

## 8. Clock requirements

The API requires an explicit timezone on lifecycle and snapshot timestamps.

The templates construct ISO-like values from:

```routeros
/system clock get date
/system clock get time
/system clock get gmt-offset
```

Network time synchronization should be operational before rollout. An incorrect RouterOS clock produces valid but inaccurate historical timestamps and duration calculations.

## 9. Permissions and device-mode

PPP hooks execute with a restricted RouterOS policy set that includes `read`, `write`, `test` and `reboot`. The integration only needs read access plus Fetch/network test capability.

The scheduled snapshot wrapper is created with `read,test` policy.

On RouterOS installations with device-mode restrictions, verify that both `fetch` and `scheduler` are permitted before rollout.

## 10. Rollout sequence

Recommended first deployment:

1. register the router/source centrally and obtain the one-time secret;
2. prepare/import the private `vpn-monitor-config`;
3. import both shared senders;
4. verify HTTPS connectivity and certificate validation;
5. run one snapshot wrapper manually with no user connected;
6. back up existing PPP hooks;
7. apply hooks to one monitored profile;
8. establish one VPN session and verify CONNECT ingestion;
9. wait for at least one snapshot and verify the active session is refreshed;
10. disconnect and verify DISCONNECT closure;
11. simulate a missed lifecycle event and verify snapshot reconciliation;
12. only then enable the recurring scheduler for production monitoring.

## 11. Existing hook preservation

`profile-hooks.example.rsc` demonstrates complete replacement of `on-up` and `on-down` on an example profile. This is intentionally explicit.

If a profile already performs other work in either hook, do not import the example unchanged. Merge the VPN Monitor call into the existing script so unrelated automation is preserved.

## 12. Public repository boundary

The committed RouterOS files must remain templates only. Never add:

- production `vpn-monitor-config` source;
- real router IDs or secrets;
- internal CA/certificate material;
- real PPP profile names or identities;
- internal DNS/IP information;
- production exports or logs.
