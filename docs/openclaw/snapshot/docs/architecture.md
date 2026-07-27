# Architecture

## Components

| Component | Image | Role |
|---|---|---|
| coordinator | `picoclaw-agent` | Owns the phase machine + world model. No bridge. |
| drone-1..4 | `picoclaw-agent` | `scout` role; each has its own bridge. |
| rover | `picoclaw-agent` | `rover` role; gated on `world.ready`. |
| bridge-drone-1..4 | `ros2-bridge-mock` | `photograph`, `detect_obstacle`, `pose`. |
| bridge-rover | `ros2-bridge-mock` | `navigate` (A\*), `pose`. |
| viz / hub | `rover-viz` | Dashboard + SSE; in `HUB_MODE` also the network gateway. |
| blackboard | named volume | The shared spec folder (dev). |

One bridge per robot mirrors the real topology (each drone carries its own
bridge on-device).

## The two big abstractions

### 1. The blackboard (`agent/bb.py`)

A shared, file-based coordination space with strict single-writer rules. Two
interchangeable implementations behind the same method surface:

* **`FileBoard`** (class `Blackboard`) — reads/writes a directory (a Docker
  volume). Used by co-located agents (the coordinator, the dev demo).
* **`HttpBoard`** — same methods, but every read/write goes to the central
  **hub** over HTTP. Used by a drone on its own host. Reads tolerate a flaky
  link (return defaults); writes are best-effort.

`make_board(agent_id)` picks `HttpBoard` when `HUB_URL` is set, else `FileBoard`.
Roles never know which one they're using. See [distributed](distributed.md).

Directory layout:

```
blackboard/
  task.md                 # the goal (coordinator writes at INIT)
  config.yaml.json        # run config snapshot
  agents/<id>/meta.json   # registry: who is connected (powers discovery)
  .seq                    # board-global monotonic message counter (flock-guarded)
  messages/<seq>-<ts>-<id>-<type>.json   # append-only message log (seq-first names)
  state/
    phase.json            # writer: coordinator
    decision.json         # writer: coordinator
    assignments.json      # writer: coordinator
    world.json            # writer: coordinator (merged world model)
    progress/<id>.json    # writer: each agent writes ONLY its own file
  artifacts/              # photos copied by the bridge
  events.jsonl            # APPEND-ONLY feed for the dashboard
```

**Concurrency rules** (why it's race-free):
* State files are single-writer — the coordinator owns
  phase/decision/assignments/world; each agent owns its own
  `state/progress/<id>.json`. Per-agent progress files are a stricter form of
  the spec's "one writer per file" rule than a shared `progress.json`.
* Every message carries a board-global monotonic `seq`, taken from the
  flock-guarded counter file `blackboard/.seq` (wiped on reset; in hub mode the
  hub stamps it server-side). Filenames are seq-first
  (`{seq:06d}-{ts}-{from}-{type}.json`) → unique, no clobber — and consumers
  sort by `seq`, **not** `ts`, so ordering survives clock skew.
* `events.jsonl` lines are `< PIPE_BUF` (4096 B) and written with a single
  `O_APPEND` write → atomic concurrent appends on Linux.
* JSON state writes are atomic (temp file + `os.replace`).

### 2. The bridge (robot actions)

A per-robot HTTP sidecar. The **same contract** (`photograph`,
`detect_obstacle`, `navigate`, `pose`, `healthz`) for the dev mock and the real
`rclpy` node — only the implementation differs. The agent never imports ROS2; it
only calls the bridge over HTTP. This keeps the on-device install small and the
sim→hardware seam clean. See [bridge](bridge.md).

## Data flow (single host)

```
 coordinator ──writes──▶ state/*.json ◀──reads── drones
      ▲                       │                     │
      │ reads progress/msgs   │                     ├─HTTP─▶ bridge (photograph/detect/navigate)
      └───────────────────────┘                     │
 all agents ──append──▶ events.jsonl ──tail──▶ viz ──SSE──▶ browser dashboard
```

## Data flow (distributed / on-drone)

The shared volume is replaced by a central **hub**. The coordinator stays
co-located with the hub and uses `FileBoard` on the shared volume; remote drones
use `HttpBoard` → hub HTTP API → the same volume.

```
        orchestrator host                         each robot host
 ┌──────────────────────────────┐        ┌──────────────────────────────┐
 │ hub (FileBoard + HTTP + SSE)  │◀─HTTP─▶│ agent (HttpBoard) ─▶ bridge   │
 │ coordinator (FileBoard)       │        │                               │
 └──────────────────────────────┘        └──────────────────────────────┘
        ▲ browser dashboard + per-agent transcripts
```

See [distributed](distributed.md) for details.

## Code map

```
agent/
  loop.py          # the §7 agent loop: read -> decide -> novelty-gate -> emit
  bb.py            # FileBoard + HttpBoard + make_board + novelty()
  brain.py         # pluggable LLM: mock / sverk / anthropic / openai / ollama
  bridge_client.py # HTTP client for a robot's bridge
  souls.py         # SOUL.md frontmatter reader
  roles/
    coordinator.py # phase machine, convergence, world merge, rover gate; task dispatch
    moderator.py   # first-class debate chair: framing, floor grants, rounds, tally
    scout.py       # scout: CHAT negotiation (default) or legacy PROPOSE/CONVERGE, then EXECUTE
    rover.py       # gated navigate A->B (safe_passage: to goal; survey: to the cargo cell)
    survey.py      # survey coordinator: zone chat -> cell sweep -> sequential verification -> rover
    survey_scout.py    # survey drone: per-turn JSON action plans (fly_to/wait/photo_analyze),
                       # closed-loop pose, verify duty; LLM plans validated + deterministic fallback
    survey_common.py   # pure survey logic: serpentine zones, plan validation, quorum (unit-tested)
    painter.py     # painter drone: brick/build/vote phases + paint
    debate.py      # debater: opening -> floor-gated argument -> vote
    scout_chat.py  # open-channel sector negotiation (claim/argue/trade, done-consensus)
    studio_chat.py # free stigmergic studio chat; coordinator = thin facilitator
    collab_paint.py     # PAINT_MODE=collab: each drone paints its OWN colour, z-layered shapes
    coordinator_paint.py # PAINT_MODE=curated: coordinator composes + paints the whole canvas
    ballot.py      # ballot canonicalization: cluster near-duplicate free-text votes
    phase_util.py  # shared phase-machine helpers (deadlines, transitions, tie-breaks)
    personas.py    # seed-generated painter personas (roster -> config.yaml.json)
    painter_agent.py    # painter LLM calls: bricks -> shared build -> vote
    painter_palette.py  # shared palette + per-run roster/session context
    painter_compose.py  # abstract colour-field stroke composition per technique
    paint_shapes.py     # shape-plan DSL: JSON shapes -> rasterized spray polylines
    debate_common.py    # domain-agnostic debate primitives (positions, floors, votes)
    collaborative.py    # collaborative idea building: bricks -> draft -> candidates
bridge/
  mock.py          # dev bridge: fixture images + A* nav
  ros2/bridge_node.py  # hardware stub (rclpy)
viz/
  server.py        # dashboard + SSE + (HUB_MODE) the hub gateway
  index.html       # legacy rover dashboard (served at /rover)
  debate.html      # legacy debate test stand (served at /debate)
frontend/          # React/TS SPA — the default dashboard; `make web` builds
                   # frontend/dist, served at / and /studio
drone/             # on-drone / PicoClaw skeleton
```
