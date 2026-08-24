# Grafana query API and alerting

MikroTik VPN Monitor exposes a read-only API intended for Grafana running on the same monitoring host.

The supported deployment keeps this API on loopback:

```text
http://127.0.0.1:8092/api/v1
```

The public Nginx virtual host must **not** proxy these routes. RouterOS only needs the ingestion endpoints documented separately.

All examples below use fictitious identities and placeholder credentials.

## 1. Authentication

Every query and alert endpoint requires:

```http
X-API-Key: <query-api-key>
```

The key comes from:

```dotenv
VPN_MONITOR_QUERY_API_KEY=<high-entropy-secret>
```

If the setting is absent, query endpoints fail closed with HTTP `503`. Missing or invalid request credentials return HTTP `401`.

The query key is independent from RouterOS ingestion credentials.

## 2. Available endpoints

### Overall summary

```http
GET /api/v1/query/summary
```

Returns:

- enabled routers;
- enabled sources;
- active sessions;
- distinct active users;
- sessions started in the last 24 hours;
- CONNECT events in the last 24 hours;
- most recent lifecycle event timestamp.

### Active sessions

```http
GET /api/v1/query/sessions/active
```

Optional filters:

```text
router_id
source_id
username
limit
```

`source_id` is the stable source identifier used by RouterOS, for example `primary-ovpn`. Internal source UUIDs are not exposed by the query contract.

### Session history

```http
GET /api/v1/query/sessions/history
```

Optional filters:

```text
state=ACTIVE|CLOSED
router_id=<router UUID>
source_id=<stable source identifier>
username=<PPP username>
since=<ISO-8601 timestamp>
until=<ISO-8601 timestamp>
limit=200
offset=0
```

The maximum page size is `1000` rows.

### Router summary

```http
GET /api/v1/query/routers
```

Returns one row per registered router with active-session/user counts and last-seen/snapshot timestamps.

### Source summary

```http
GET /api/v1/query/sources
```

Returns one row per configured source with router identity, source state, active-session/user counts and last snapshot timestamp.

### User summary

```http
GET /api/v1/query/users
```

Returns one row per observed PPP username with:

- active sessions;
- total sessions;
- accumulated duration of completed sessions;
- last connection timestamp.

The optional `limit` parameter is bounded to `2000` rows.

## 3. Example local requests

Summary:

```bash
curl -sS \
  -H 'X-API-Key: replace-with-local-query-key' \
  http://127.0.0.1:8092/api/v1/query/summary
```

Active sessions:

```bash
curl -sS \
  -H 'X-API-Key: replace-with-local-query-key' \
  'http://127.0.0.1:8092/api/v1/query/sessions/active?source_id=primary-ovpn'
```

Recent history:

```bash
curl -sS \
  -H 'X-API-Key: replace-with-local-query-key' \
  'http://127.0.0.1:8092/api/v1/query/sessions/history?limit=100'
```

Do not put a production query key in shell history, dashboards exported to Git, screenshots, issue reports or public documentation.

## 4. Infinity data source

The intended Grafana integration uses the Infinity data source against the loopback API.

Recommended data-source settings:

```text
Base URL: http://127.0.0.1:8092/api/v1
Header:   X-API-Key = <query-api-key>
```

Store the header as a secure data-source setting rather than embedding it in individual panel queries.

For ordinary dashboard panels, query the JSON endpoints directly and select only the columns required by each visualization.

Useful first panels include:

- active sessions table;
- active users stat;
- sessions by router;
- sessions by source;
- recent session history;
- top users by session count or accumulated duration.

## 5. Event-based logon alert feed

The alert endpoint is:

```http
GET /api/v1/alerts/logons?lookback_minutes=5
```

`lookback_minutes` defaults to `5` and is constrained to `1..60`.

The feed is based on immutable `CONNECT` events, not on the current `ACTIVE` state. This is important because two different users can log in while another VPN session remains active; a state-only alert would not reliably represent each new login.

Each row contains:

```text
alert_id
router_id
router_name
source_id
username
caller_id
vpn_address
logon_at
received_at
alert_value
```

`alert_id` is the central immutable event UUID and remains stable while the event stays inside the lookback window. `alert_value` is always numeric `1`.

The lookback uses API `received_at`, so an event delivered after a temporary network/API delay can still produce an alert when it finally arrives.

A DISCONNECT does not create a logon alert and does not remove the CONNECT row early; the row naturally leaves the feed when the lookback expires.

## 6. Grafana alert rule shape

Grafana Infinity alerting requires a backend-capable parser such as **JSONata** or **JQ**. The alert query should use JSON/table output and explicitly map only one numeric column.

Recommended columns for the logon alert rule:

| Column | Type | Purpose |
| --- | --- | --- |
| `alert_id` | String | unique alert-instance label |
| `router_name` | String | router/hostname label |
| `source_id` | String | monitored source label |
| `username` | String | PPP identity label |
| `alert_value` | Number | threshold value |

Then apply a threshold equivalent to:

```text
alert_value > 0
```

No reduce expression is required when Grafana is evaluating properly shaped tabular rows with one numeric value per row.

Keeping `alert_id` in the string-label set prevents two successive logins by the same user/router/source from collapsing into one alert instance.

Suggested annotations:

```text
Summary: New VPN logon on {{ $labels.router_name }}
Description: User {{ $labels.username }} connected through source {{ $labels.source_id }}.
```

When no recent CONNECT exists, the endpoint returns an empty JSON array. The alert rule should therefore treat **No Data** as normal rather than as an infrastructure failure.

Notification grouping is a separate Grafana concern. If every login must generate an independent notification, group notifications by a label set that includes `alert_id`.

## 7. Exposure boundary

Do not add these paths to the public ingestion Nginx virtual host:

```text
/api/v1/query/*
/api/v1/alerts/*
```

The supported architecture is:

```text
RouterOS --HTTPS--> Nginx --POST only--> API
Grafana ----------------loopback--------> API query/alerts
```

If Grafana is moved to another host or into a network-isolated container, redesign the read boundary explicitly rather than exposing the entire API by convenience.

## References

- Grafana Infinity data source: https://grafana.com/docs/plugins/yesoreyeram-infinity-datasource/latest/
- Infinity JSONata/backend parser: https://grafana.com/docs/plugins/yesoreyeram-infinity-datasource/latest/query/backend/
- Grafana tabular alerting: https://grafana.com/docs/grafana/latest/alerting/examples/table-data/
- Grafana multi-dimensional alerting: https://grafana.com/docs/grafana/latest/alerting/examples/multi-dimensional-alerts/
