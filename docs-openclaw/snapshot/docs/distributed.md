# Distributed mode (each robot its own host)

The dev demo uses one shared blackboard volume. For real drones — each its own
Docker host — that volume becomes a central **hub** the drones reach over HTTP
(the brief §2 swap). The agent code is unchanged; a pluggable board picks the
transport by env.

```
        orchestrator host                         each robot host
 ┌──────────────────────────────┐        ┌──────────────────────────────┐
 │ hub = dashboard + HTTP + SSE  │◀─HTTP─▶│ agent (HttpBoard) ─▶ bridge   │
 │ coordinator (FileBoard)       │        │  (camera / Nav2 stay local)   │
 └──────────────────────────────┘        └──────────────────────────────┘
       ▲ every drone streams its thinking here; click a node for the full log
```

## The board transport (`agent/bb.py`)

* **`FileBoard`** — for co-located agents: the coordinator on the orchestrator
  (shares the volume with the hub), and the single-host dev demo.
* **`HttpBoard`** — for a drone/rover on its own host: every read/write goes to
  the hub over HTTP. Reads tolerate transient hub errors (return defaults; the
  loop retries next cycle); writes/events are best-effort, so a flaky link never
  crashes a drone.
* `make_board(agent_id)` returns `HttpBoard` when `HUB_URL` is set, else
  `FileBoard`. Roles are identical either way.

## The hub (`viz/server.py` with `HUB_MODE=1`)

The same dashboard server, plus a write gateway. The coordinator stays
co-located and uses `FileBoard` directly on the shared volume; the hub writes
remote drones' data to that same volume, so the coordinator sees everything.

Endpoints (in addition to the read-only dashboard ones in
[visualizer](visualizer.md)):

| method | endpoint | purpose |
|---|---|---|
| `GET` | `/state/<phase\|decision\|assignments\|world>` | read shared state |
| `GET` | `/messages`, `/progress` | read the board |
| `POST` | `/messages` | post a message (hub assigns id, returns it) |
| `POST` | `/progress/<id>` | a drone writes its own progress |
| `POST` | `/events` | append a (streamed thought / pose / …) event |
| `POST` | `/register` | a drone registers on boot |
| `POST` | `/state/<name>` | (optional) remote coordinator writes state |

**Auth**: when `HUB_TOKEN` is set, all POSTs require
`Authorization: Bearer <HUB_TOKEN>`. Set the same token on every drone. GET
(dashboard/SSE) is open.

## Discovery (plug-and-play)

Each drone POSTs `/register` on boot (`agent/bb.py: HttpBoard.register`), writing
`agents/<id>/meta.json`. The coordinator reads the registry each cycle
(`read_registry`) and includes registered scouts/rover automatically — bring a
node up and it joins; the `SCOUTS`/`ROVER` env are just a fallback.

> Open TODO: dynamic N-way map decomposition. The scenario has 4 sectors; extra
> scouts beyond that currently get redundant assignments (round-robin over the
> sectors). See [extending](extending.md).

## Streaming brains to the central dashboard

Whether a drone calls the shared `sverk/qwen35` server model or an on-board local
model, it streams its reasoning to the hub the same way — `thought_start` /
`thought_delta` / `thought_end` events POSTed to `/events`. The dashboard renders
them live and the hub persists them, so clicking a drone shows its full thinking.
A client-side typewriter keeps the reveal smooth even if the upstream stream
arrives in coarse chunks (which can happen through NAT/VPN).

## Single-host demo of the distributed wiring

Proves the on-drone path end to end on one box (drones use `HttpBoard`, the
coordinator uses `FileBoard`, both via the hub's shared volume):

```bash
make demo-distributed                         # mock brain, unattended -> PASS
MODEL_PROVIDER=sverk make demo-distributed    # real qwen35 over the hub
# dashboard: http://localhost:8080
make down-distributed
```

(`docker-compose.distributed.yml`.) Verified: drones register, the coordinator
discovers them, the run reaches PASS / rover-arrived, and full qwen35 thinking
streams to the hub with 0 errors — clickable per drone.

## Real multi-host deploy

On the **orchestrator** box:

```bash
HUB_TOKEN=$(openssl rand -hex 16) make hub
# dashboard: http://<orchestrator>:8080 ; share that HUB_TOKEN with the drones
```

On **each robot** (has Docker; copy the repo or pull the images):

```bash
make drone AGENT_ID=drone-5 ROLE=scout \
  HUB_URL=http://<orchestrator>:8080 HUB_TOKEN=<same>
# rover: ROLE=rover AGENT_ID=rover
```

`docker-compose.drone.yml` runs one `agent` + one local `bridge` per robot
(`docker compose -p <AGENT_ID>` so multiple nodes don't collide). The bridge
stays local to the robot (artifacts on an ephemeral local store; camera/Nav2 on
hardware). Put all robots + the orchestrator on one private LAN/VPN so they reach
`HUB_URL`. See [security](security.md) and [on-drone](on-drone.md).
