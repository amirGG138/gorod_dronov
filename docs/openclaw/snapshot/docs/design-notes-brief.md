# Design notes (бывший корневой README)

> Архив. Это README проекта до 2026-07-27 — он писался как ответ на
> `BUILD_BRIEF.md` и содержит обоснования решений (PicoClaw, контракт
> бриджа, сценарии). Актуальные точки входа: [../README.md](../README.md)
> для людей и [../AGENTS.md](../AGENTS.md) для агентов.

---

The same coordination engine, four scenarios:

* **Smart rover** — four scout drones photograph a model street completely
  enough to **certify safe passage**; a rover then drives point A → B on the
  resulting map.
* **Cargo survey (поиск груза)** — город дронов v2: four drones **negotiate a
  split of a 5×5 cell field in an open chat**, sweep it with per-turn JSON
  action plans (`fly_to → wait → photo_analyze`), cross-verify every find
  **one drone at a time** (quorum confirms, decoys get rejected), and the rover
  drives to the confirmed cargo cell. See [docs/survey.md](docs/survey.md).
* **Painters** — four painter drones, each with its own personality, palette and
  spray-can colour, **negotiate what to draw** and then collaboratively paint one
  shared canvas, each spraying its own colour into its quadrant.
* **Debate** — a reusable turn-based debate/decision engine with a first-class
  moderator. See [docs/debate-system.md](docs/debate-system.md).

Everything runs in Docker with **no hardware**, so you can watch the agents
think and verify the full flow end to end. The same nodes also run on a
Raspberry Pi and join over the network (see *On-drone / Pi-5* below).

Built to `BUILD_BRIEF.md` against the protocol in `agent-coordination-spec.md`.

```bash
cp .env.example .env        # optional — defaults to the no-key mock brain

make demo                   # smart-rover: run unattended, wait for PASS
make demo-survey            # поиск груза: 5×5 sweep + verification + rover (:8080/survey)
make demo-painters          # painters: negotiate a subject + paint the canvas
# open http://localhost:8080   <- live dashboard

make down                   # stop
make reset                  # wipe the blackboard volume (fresh run next time)
```

`make demo` reaches `phase=DONE` with `result="PASS: safe passage"` and the
rover's `arrived` report; `make demo-painters` reaches `phase=DONE` with
`result="Painting complete: …"`. Both run unattended, no API key required.

> **Fresh start every run.** Each `make demo*` first drops the blackboard volume
> (`make reset`), and the coordinator also wipes stale state at boot. This is
> what stops a *previous* run's messages/phase from being replayed — the
> "drones already talked to each other before I started the demo" symptom of a
> persisted volume. Use `RESET_ON_START=0` to opt out of the boot reset.

📖 **Full documentation: [`docs/`](docs/README.md)** — overview, architecture,
protocol, agents/brain, bridge, dashboard, running, distributed/on-drone,
PicoClaw, configuration, security, extending, troubleshooting.

---

## Note on the PicoClaw tool mechanism + why the bridge (brief §0/§13.1)

I read the official Sipeed PicoClaw repo (`github.com/sipeed/picoclaw`, latest
release **v0.2.9**, written in Go; config is JSON `~/.picoclaw/config.json` with
keys in `.security.yml`; model providers via a `model_list` of `protocol/model`
entries — Anthropic / OpenAI / Ollama / vLLM, etc.). **Its tool mechanism is
declarative — built-in tools, `SKILL.md` skills, and MCP servers spawned as
child processes — so adding a tool needs no Go recompile.** That validates the
brief's bridge pattern: on hardware PicoClaw reaches the robot through one
generic external tool (an MCP/`call_bridge` shim) that proxies to the HTTP
**bridge sidecar**; tools change without rebuilding the agent.

**What runs in this repo.** Two constraints shaped the dev build: (1) `make demo`
must run *unattended with no API key* (brief §13), and (2) the bridge HTTP
contract is what must stay stable across sim → hardware (brief §6). So the agent
is a thin **Python wrapper of the spec §7 loop** with a **pluggable brain**:

* `MODEL_PROVIDER=mock` (default) — the coordination protocol is driven
  deterministically by the role modules, so the demo is reproducible and
  key-free.
* `MODEL_PROVIDER=sverk|anthropic|openai|ollama` — a real LLM narrates the
  reasoning behind each step (the `thought` events the dashboard renders), via
  raw HTTP (no SDK), keys from `.env`. `sverk` is the custom OpenAI-compatible
  gateway at `ai.sverk.tech/v1` (default model `qwen35`, a reasoning model whose
  live chain-of-thought *is* the "see what they think" content).

  ```bash
  # .env already set to MODEL_PROVIDER=sverk, MODEL=qwen35, SVERK_API_KEY=...
  make demo-sverk     # full run with the real qwen35 brain (needs egress)
  ```

  Verified end-to-end on both the local and Docker paths: all six agents
  (coordinator + 4 drones + rover) narrate via qwen35 through every phase and
  the protocol reaches `PASS` with the rover arriving (0 LLM errors). Real
  providers need outbound access, so `make demo-sverk` adds
  `docker-compose.egress.yml` (attaches agents to the host-reachable `edge`
  network — the default `mesh` is internal/no-egress, §11).

This is exactly the "PicoClaw binary + thin §7-loop wrapper" the brief
describes, and §0 explicitly permits a Python OpenClaw-variant as the brain.
**The bridge HTTP contract (§6) is identical for mock and real**, so swapping
the brain to PicoClaw-on-Pi-5 — or the mock bridge to the `rclpy` node in
`bridge/ros2/` — changes nothing upstream. Pin PicoClaw to the verified v0.2.9
commit when you wire it in (brief §11).

---

## How it works

```
docker compose
├─ coordinator           agent loop, ROLE=coordinator   (owns the phase machine)
├─ drone-1 … drone-4     agent loop, ROLE=scout          each → its own bridge
├─ rover                 agent loop, ROLE=rover          → its own bridge
├─ bridge-drone-1 … 4    mock bridge (photograph, detect_obstacle, pose)
├─ bridge-rover          mock bridge (navigate A*, pose)
├─ viz                   tails events.jsonl → SSE → dashboard on :8080
└─ blackboard            named volume = the shared spec folder
```

**Phase machine (spec §5).** `INIT → PROPOSE → CONVERGE → EXECUTE → REPORT →
DONE`, with `reopen` back to EXECUTE if coverage gaps remain. Only the
coordinator writes `phase/decision/assignments/world.json` (single-writer, §1).

**The rover gate (brief §5).** The rover is assigned in EXECUTE with
`{wait_for: "world.ready"}`; it posts a `BLOCK` and idles. During REPORT the
coordinator merges drone reports into `world.json` (covered cells, gaps,
localized obstacles); when `gaps == [] and obstacles localized` it sets
`world.ready = true` and `decision.result = "PASS: safe passage"`. That unblocks
the rover, which calls `navigate(A, B)` (A* in the bridge), streams pose, and
reports `arrived` → `phase = DONE`.

**Novelty gate (spec §6.4).** Before posting, free-form messages (proposals) are
scored for information gain vs. what's already on the board; below
`NOVELTY_MIN` (0.3) they're dropped (logged as a `drop` event). Protocol-
critical messages (votes, assignments, reports, blocks) always post but still
carry a novelty score for the dashboard.

**Bridge contract (brief §6)** — same for mock and real (`bridge/ros2/` stub):

```
POST /photograph      {sector}            -> {image_path, ts}
POST /detect_obstacle {image_path}        -> {obstacles:[{type,xy,conf}], coverage}
POST /navigate        {from,to,grid}      -> streams {pose,progress} … {status:"arrived"}
GET  /pose                                -> {xy, heading}
GET  /healthz                             -> {ok:true}
```

---

## Painters scenario (spec §10 — collaborative painting)

The same phase machine, novelty gate, souls and dashboard drive a creative task:

```bash
make demo-painters                         # mock brain, unattended -> canvas painted
make demo-painters-sverk                   # real qwen35 narrates each painter's reasoning
TASK=painting SCENARIO=painters-1 bash scripts/run_local.sh   # no Docker
```

* **Four painters, four personalities** (`souls/painter-1..4.md`): Aurora
  (warm impressionist, amber, soft bands), Cobalt (cool minimalist, blue, long
  strokes), Ember (fiery expressionist, crimson, diagonal hatching), Sage
  (patient naturalist, green, stippling). Each carries its own spray-can
  **colour** and **technique**.
* **PROPOSE** — each painter pitches the subject it loves (real disagreement).
  **CONVERGE** — they score the proposals and converge on one shared subject
  (the "договорились" moment). **EXECUTE** — they paint **one whole picture
  together**: the coordinator gives each painter a *layer* of that single scene
  (sky / water / light / foreground), and each sends `move`/`spray` commands to
  its drone to paint that layer **across the whole canvas in its own colour** —
  amber dawn sky, blue water, a red sun + reflection, green shoreline blend into
  one image. **REPORT** — the coordinator certifies the finished canvas
  (`result="Painting complete: …"`).
* **Each drone has a spray can.** The painter agent decides the strokes and
  drives its robot through the bridge — `POST /move {to}` flies it, `POST /spray
  {points,color}` lays a coloured polyline (the can on). On hardware the same
  endpoints drive Nav2 to each waypoint and toggle the spray actuator; the HTTP
  contract is identical (mock vs. real), exactly like the rover's `navigate`.
* The dashboard renders the shared canvas live: every `stroke` event paints a
  coloured polyline, so you watch four colours blend into one scene while each
  painter's thinking streams in its bubble. Verdict turns green on completion.

The composition (which strokes, where) is generated deterministically from each
painter's layer + the shared canvas, so the demo is reproducible and key-free;
with a real brain the LLM narrates *why*. Add `test_fixtures/painters-2/…` (a
`map.json` with `mode: "painting"`, a `canvas`, `horizon`, `layers` and
`subjects`) and run `PAINTERS_SCENARIO=painters-2 make demo-painters`.

---

## The dashboard (brief §8)

`http://localhost:8080` — tail `events.jsonl` → SSE → single-page app:

* **agent nodes** coloured by phase, each with a live thought-bubble. With a
  real reasoning model (sverk/`qwen35`) the bubble **streams the model's
  chain-of-thought token-by-token** with a blinking cursor — you watch each
  agent think before it acts (`thought_start` → `thought_delta*` →
  `thought_end`; the mock brain emits a single `thought`);
* **message feed** with novelty scores; sender/receiver pulse on each message;
  `BLOCK` glows red;
* **world grid**: cells tint as sectors are covered, obstacles drop in, then the
  rover's path animates A→B from `pose` events, routing around the wall;
* **phase timeline** of every transition;
* **click any agent node** → a modal with that agent's *full* untruncated
  chain-of-thought for every step plus its chat (messages). Served from
  `GET /agents/<id>/transcript`, assembled from the persisted event stream — so
  you can replay exactly what each drone was thinking.

> SSE is used instead of a raw WebSocket so the viz is stdlib-only and gets
> browser auto-reconnect for free; same "tail → stream → SPA" design. Swapping
> in a WebSocket means replacing the `/events` handler and the `EventSource`
> call.

---

## Test-image harness (brief §7)

```
test_fixtures/scenario-1/
  map.json              # 10x10 occupancy grid + start A + goal B + sector boxes
  sector-{A,B,C,D}.png  # one placeholder image per sector
  sector-{…}.labels.json# ground-truth obstacles + coverage per sector
```

The sample scenario ships working: a wall on column `x=5` (`y=2..9`) blocks the
direct diagonal, so the rover must route through the gap at the top — the demo
shows it routing around the obstacle. Add `test_fixtures/scenario-2/…` and run
with `SCENARIO=scenario-2 make demo`.

---

## Run without Docker (fast iteration)

```bash
make local        # starts bridges + agents as local processes (mock brain)
cat blackboard/state/decision.json
make stop-local
```

---

## Distributed / on-drone mode (each robot its own host)

The dev demo uses one shared blackboard volume. For real drones — each its own
Docker host — that volume becomes a central **hub** the drones reach over HTTP
(the brief §2 swap). The agent code is unchanged: a pluggable board picks the
transport by env.

```
                 orchestrator host                     each robot host
  ┌───────────────────────────────────┐      ┌──────────────────────────────┐
  │  hub  = dashboard + HTTP API + SSE │◀────▶│  agent ──HTTP──▶ bridge       │
  │  coordinator (owns world model)    │ HTTP │  (HttpBoard→hub)  (cam/Nav2)  │
  └───────────────────────────────────┘      └──────────────────────────────┘
        ▲ every drone streams its thinking here; click a node for the full log
```

* **Board transport** (`agent/bb.py`): `FileBoard` (co-located: coordinator on
  the orchestrator, or the dev demo) or `HttpBoard` (a drone → hub). `make_board`
  picks `HttpBoard` automatically when `HUB_URL` is set. Reads tolerate a flaky
  link; writes are best-effort, so a drone never crashes on a dropped packet.
* **Hub** = the same `viz/server.py` with `HUB_MODE=1`: drones POST messages /
  progress / streamed thoughts and GET shared state; writes are gated by a shared
  `HUB_TOKEN` (§11). It also serves the dashboard, the SSE feed, and the
  per-agent transcripts.
* **Discovery**: each drone registers on boot; the coordinator picks up
  registered drones automatically — bring a node up and it joins. (Dynamic N-way
  map decomposition is the open TODO; today extra scouts beyond the 4 sectors get
  redundant assignments.)
* **Brains stream regardless of where they run**: whether a drone calls the
  shared `sverk/qwen35` server model or an on-board local model, it streams its
  reasoning to the hub the same way.

```bash
# single-host demo of the whole distributed wiring (mock or sverk):
make demo-distributed                         # -> http://localhost:8080, PASS
MODEL_PROVIDER=sverk make demo-distributed    # real qwen35 over the hub

# real multi-host:
#   on the orchestrator:
HUB_TOKEN=$(openssl rand -hex 16) make hub                    # smart-rover
TASK=painting SCENARIO=painters-1 HUB_TOKEN=$(openssl rand -hex 16) make hub   # painters
#   on each robot (a Raspberry Pi, etc.):
make drone AGENT_ID=drone-5  ROLE=scout   HUB_URL=http://<orchestrator>:8080 HUB_TOKEN=<same>
make drone AGENT_ID=painter-5 ROLE=painter TASK=painting HUB_URL=http://<orchestrator>:8080 HUB_TOKEN=<same>
```

Verified end-to-end (single host): drones run `HttpBoard`, register, are
discovered by the coordinator, reach `PASS`/rover-arrived, and stream their full
qwen35 thinking to the hub (0 errors) — clickable per drone. See `drone/` for the
per-node compose and the **PicoClaw-on-drone** skeleton (config + the generic
`call_bridge` MCP shim) so native PicoClaw drops in without changing the bridge
contract or the hub API.

## Pi-5 / ROS2 deployment (brief §10)

**Plug a Raspberry Pi in and watch it on the dashboard.** One image —
`openclaw-drone` (`drone/Dockerfile`, multi-arch incl. `linux/arm64`) — adapts
to whatever node it is by env and joins the hub:

```bash
# on the Pi (has Docker), pointed at the orchestrator hub:
AGENT_ID=painter-7 ROLE=painter HUB_URL=http://<hub>:8080 HUB_TOKEN=<same> \
  docker compose -p painter-7 -f docker-compose.drone.yml up -d   # joins the painters swarm
# scout / rover are identical with ROLE=scout|rover (TASK defaults from the role)
```

* **The image adapts per drone.** `AGENT_ID`/`ROLE`/`TASK` pick the behaviour;
  an unknown name (e.g. `painter-7`) gets a **generated persona** (colour +
  technique, overridable with `DRONE_COLOR`/`DRONE_TECHNIQUE`/`DRONE_NAME`/
  `DRONE_SUBJECT`), so you can scale the swarm without editing files. The node
  registers on boot, the coordinator discovers it, and its thinking + (painters)
  its coloured strokes stream to the dashboard — click the node for its full log.
* **PicoClaw-ready.** The default brain is the proven Python §7-loop wrapper.
  To run native PicoClaw instead, build with `--build-arg WITH_PICOCLAW=1`
  (drop the pinned `drone/bin/picoclaw-<arch>` binary in first — brief §11) and
  set `BRAIN=picoclaw`; the entrypoint renders `~/.picoclaw/config.json`, wires
  the `call_bridge` MCP shim (`drone/picoclaw_bridge_mcp.py`), and falls back to
  the wrapper if the binary is absent. See `drone/README.md`.
* Per drone on a Pi-5: the brain + the `rclpy` bridge node (`bridge/ros2/
  bridge_node.py`, a stub today) + camera/spray-can. Keep the §6 HTTP contract.
* Default each drone to a **remote model API** (a 2–4 GB Pi can't run a useful
  local LLM); a tiny quantized Ollama model is an offline-only fallback.

## Safety / sandboxing (brief §11)

Containers run **read-only root fs** (except the blackboard mount), `cap_drop:
ALL`, `no-new-privileges`, and on an **internal Docker network with no outbound
internet** (`mesh`, `internal: true`). The bridge exposes **only** the four
whitelisted endpoints — no generic shell/file tool — and **validates every tool
argument against a strict schema**, rejecting malformed input (brief §11). The
rover's `navigate` is gated behind the coordinator's explicit `world.ready`
certification; the real bridge must add a hard e-stop before any physical drive.

## File tree

```
README.md  Makefile  .env.example
docker-compose.yml            # single-host shared-volume demo (smart rover)
docker-compose.egress.yml     # overlay: real model provider (egress)
docker-compose.painters.yml   # single-host painters demo
docker-compose.painters.egress.yml  # painters overlay: real model provider
docker-compose.distributed.yml# single-host demo of the distributed wiring
docker-compose.hub.yml        # multi-host: orchestrator (hub + coordinator)
docker-compose.drone.yml      # multi-host: one robot node (openclaw-drone + bridge)
agent-coordination-spec.md  BUILD_BRIEF.md
agent/    loop.py  brain.py  bb.py (FileBoard+HttpBoard)  souls.py  bridge_client.py  roles/  Dockerfile
          roles/   coordinator.py  scout.py  rover.py  painter.py
bridge/   mock.py (photograph/detect/navigate + move/spray)  ros2/bridge_node.py  Dockerfile
drone/    Dockerfile (openclaw-drone, multi-arch)  entrypoint.sh  README.md
          picoclaw.config.json  picoclaw_bridge_mcp.py            # native PicoClaw seam
souls/    coordinator.md  drone-1..4.md  rover.md  painter-1..4.md
viz/      server.py (dashboard + hub)  index.html (grid + painting canvas)  Dockerfile
test_fixtures/scenario-1/   map.json  sector-*.png  sector-*.labels.json
test_fixtures/painters-1/   map.json (mode: painting, canvas, quadrants, subjects)
scripts/  run_local.sh  stop_local.sh  wait_done.sh
blackboard/   # runtime volume (gitignored)
```
