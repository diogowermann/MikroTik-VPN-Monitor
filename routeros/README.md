# RouterOS integration templates

This directory contains sanitized RouterOS templates for delivering PPP lifecycle events and periodic `/ppp active` snapshots to MikroTik VPN Monitor.

The templates intentionally contain no production identifiers or credentials. Create a private working copy before replacing placeholders.

## Initial target

The first supported/test target is RouterOS 7.21+.

The templates rely on:

- PPP profile `on-up` / `on-down` variables;
- `/tool fetch` with HTTPS POST and custom headers;
- `:parse`, `:serialize`, `:retry`, `:rndstr`, `:tonsec` and `print as-value`;
- `/system scheduler` for snapshot delivery.

Before deployment, verify that RouterOS device-mode permits `fetch` and `scheduler` where device-mode restrictions are enabled.

## Files

- `config.example.rsc` - persistent API URL, router UUID and bearer secret. This is the only template that contains the ingestion secret after local customization.
- `event-sender.rsc` - shared CONNECT/DISCONNECT sender parsed by PPP hooks.
- `snapshot-sender.rsc` - shared `/ppp active` collector and snapshot sender.
- `profile-hooks.example.rsc` - example `on-up` / `on-down` binding for one PPP profile/source.
- `snapshot-source.example.rsc` - example one-minute snapshot wrapper/scheduler for one source.

## Recommended installation order

1. Register the router and initial source in the central API.
2. Copy `config.example.rsc` outside the repository and replace all placeholders locally.
3. Upload each prepared `.rsc` to RouterOS and use `/import file-name=<file> verbose=yes dry-run` before applying it.
4. Import the private configuration copy.
5. Import `event-sender.rsc` and `snapshot-sender.rsc` unchanged.
6. Back up the existing target PPP profile hooks.
7. Create a private copy of `profile-hooks.example.rsc`, set the intended profile/source names and merge unrelated existing hook logic if necessary.
8. Dry-run and apply the lifecycle hooks.
9. Create a private copy of `snapshot-source.example.rsc`, configure the source/profile selector, dry-run it and import it.
10. Run the snapshot wrapper manually once, then validate scheduler execution and RouterOS logs.

A successful dry-run checks RouterOS parsing only; it does not prove API reachability, authentication, certificate trust or event semantics. Those are validated during the controlled rollout.

## TLS and time requirements

`/tool fetch` uses `check-certificate=yes`. The API certificate chain must therefore be trusted by RouterOS before ingestion is enabled.

RouterOS event/snapshot timestamps are constructed from the system date, time and active GMT offset. Configure network time synchronization before relying on session duration/history.

## Multi-source behavior

A single router credential can serve multiple configured sources.

For each additional profile/source:

1. create the source centrally (it may be staged disabled first);
2. copy the profile hook template and change `sourceName` plus the PPP profile selector;
3. optionally create a separate snapshot wrapper/scheduler for that source.

The shared event/snapshot senders and `vpn-monitor-config` do not need to be duplicated.

### Snapshot profile filtering

`/ppp active` exposes the active username, service, assigned address, caller ID, session ID and uptime, but not the PPP profile itself. When `profileNames` is supplied, the snapshot sender resolves the local `/ppp secret` for each active username and uses its configured profile as the source selector.

This works for locally defined PPP users. A RADIUS-only user without a local `/ppp secret` cannot be assigned to a profile-filtered source by this generic template and is skipped with a RouterOS warning.

If `profileNames` is omitted/empty, every active session matching `serviceName` is included.

### Interface-specific sources

PPP lifecycle hooks receive the RouterOS `interface` internal ID and send it as `interface_id` on CONNECT/DISCONNECT events.

The generic `/ppp active` view does not expose the same interface ID reliably, so the snapshot template does not fabricate one. Interface-specific event sources are supported, but interface-only snapshot partitioning requires an environment-specific collector or a future validated RouterOS mapping.

## Failure behavior

Lifecycle and snapshot POSTs are retried up to three times with a one-second delay. The event identifier and request payload are created before retry begins, so retransmission remains idempotent at the API.

If all lifecycle retries fail, the event sender logs an error. The next successful snapshot can repair current session state, but a short session that starts and ends entirely during API unavailability may remain absent from history.

## Secret handling

The customized `vpn-monitor-config` contains the real bearer secret in RouterOS script source. Treat RouterOS read/admin access and configuration exports as sensitive.

Never commit:

- a customized configuration template;
- a router UUID copied from production;
- the bearer secret or its hash;
- real PPP profile names/users;
- internal API hostnames or addresses;
- exported RouterOS configuration or captured telemetry.
