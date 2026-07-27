# Security & sandboxing

This system spins up several autonomous agents with tool access, so it's treated
as untrusted-by-default and contained deliberately (brief §11). Because agents
ingest external content (test images, peer messages), assume prompt injection is
possible.

## Container hardening

Every agent / bridge / hub container runs with:

* **read-only root filesystem** except the blackboard mount (`read_only: true`,
  `tmpfs: [/tmp]`; drone bridges use `tmpfs: [/blackboard]` for ephemeral
  artifacts);
* **`cap_drop: ALL`** and **`no-new-privileges`**;
* no host shell access.

Set in every compose file.

## Network isolation

* The base `docker-compose.yml` puts agents + bridges on an **internal** network
  (`mesh`, `internal: true`) with **no outbound internet**; only the dashboard's
  published port is exposed (via a separate `edge` network).
* A real model provider needs egress — `docker-compose.egress.yml` (used by
  `make demo-sverk`) adds the agents to the host-reachable `edge` network so they
  can reach the API endpoint, and nothing more.
* In production, keep all robots + the orchestrator on one private LAN/VPN; the
  ideal is an egress allowlist limited to the model-provider endpoint and each
  drone's own bridge.

## The bridge boundary

The bridge exposes **only** a whitelisted set of endpoints (`photograph`,
`detect_obstacle`, `navigate`, `pose`, `healthz`; painter bridges add `move`,
`spray`, `canvas`) — never a generic "run command" or filesystem tool. So a confused or prompt-injected agent cannot escalate beyond
moving a simulated robot or returning an image. Every tool argument is
**validated against a strict schema at the bridge boundary** (e.g. `sector` must
match a strict regex; `from/to/grid` must be the right types), and malformed
input is rejected rather than acted on. The same applies at the hub: malformed
JSON POSTs are rejected.

## The rover gate (real-world consequences)

`navigate` is the one action with real-world consequences on hardware. It is
gated behind the coordinator's explicit `world.ready` certification (the rover
posts a `BLOCK` and refuses to move until the map is certified safe). On hardware
the real bridge must add a hard **e-stop** path before any of this touches a
physical rover.

## Hub authentication

When `HUB_TOKEN` is set, every write to the hub (`POST /messages|events|progress|
register|state`) requires `Authorization: Bearer <HUB_TOKEN>`. Set the same token
on the hub and every drone so only your robots can post. Generate one with
`openssl rand -hex 16`. GET (dashboard/SSE/read state) is open — front it with
your own auth/reverse-proxy if the dashboard must be private.

Hub-mode POSTs (`/messages`, `/register`, `/progress/<id>`) **validate agent
ids** against `^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$` before they touch the
filesystem (path-traversal fix). `POST /rerun` — the one write that works in
any mode (it wipes the runtime for a fresh keep-alive run) — requires the
header `x-rerun: 1`; `GET /rerun` returns 405.

## Supply chain

Pin PicoClaw to a verified commit/tag (v0.2.9) from the official Sipeed repo and
check it into your image; do **not** pull "latest" at build time. The official
source is `github.com/sipeed/picoclaw` / `picoclaw.io` only — ignore any
crypto-token / "$PICOCLAW" pages (scams, not the project).

## Secrets

API keys live only in `.env` (gitignored) and are passed as env vars; never baked
into images or compose. PicoClaw keys go in `.security.yml`, never in
`config.json`. `.env` and `blackboard/` are gitignored.
