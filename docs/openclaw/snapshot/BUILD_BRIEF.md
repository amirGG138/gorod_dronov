# BUILD BRIEF — Multi-Agent Rover + Drones Coordination (for Claude Code)

Read this whole file, then read `agent-coordination-spec.md` (same folder — the protocol). Build the **rover/street scenario** first; painters come later. Ask before any destructive action.

---

## 0. Read first (do not skip)

1. Fetch and read the real PicoClaw repo: `https://github.com/sipeed/picoclaw` — confirm the **config format**, **model-provider setup**, and the **tool / external-command mechanism**. The official source is `github.com/sipeed/picoclaw` / `picoclaw.io` only. Ignore any crypto-token / "$PICOCLAW" pages — those are scams, not the project. Pin a specific commit/tag.
2. Read `agent-coordination-spec.md` for the blackboard layout, message/state schemas, phase machine, novelty gate, and the `events.jsonl` event stream. This brief only adds the **rover delta** and the **runtime** (Docker, bridge, viz, tests).

If PicoClaw's tool mechanism turns out to require recompiling Go per tool, do **not** put robot logic inside PicoClaw. Use the bridge pattern below: PicoClaw calls one generic external tool (`call_bridge`) that proxies to an HTTP sidecar. That way tools change without rebuilding the agent.

---

## 1. Goal

Stand up, in Docker, a working multi-agent run for this task:

> 4 drones photograph a model street completely enough to certify safe passage; a rover then drives point A → B on the resulting map.

It must run **end-to-end with no hardware**, using test images, so we can watch the agents think and verify the full flow. Hardware (Pi 5 drones + ROS2) is the later target; keep the seam clean.

---

## 2. Stack decision

- **Brain:** PicoClaw, one container per agent. Tiny footprint, matches the Pi 5 2–4GB target. Model provider = remote API by default (Anthropic/OpenAI) via `.env`; allow Ollama as an option.
- **Robot actions:** a **bridge sidecar** per robot agent. In dev it's a mock (serves test images, simulates motion). On hardware it's a `rclpy` ROS2 node. PicoClaw never imports ROS2 — it only calls the bridge over HTTP. This is what keeps the on-device install small.
- **Blackboard:** a shared Docker volume mounted into every container (matches the spec's folder layout). Single-writer rules from the spec still apply. (Distributed/real-hardware swap: replace the volume with the coordinator exposing an HTTP+WebSocket API that drones POST messages to and GET state from. Note this as a TODO; don't build it yet.)
- **Visualizer:** one web container tailing `events.jsonl`, streaming to the browser over WebSocket.

If single-language extension is strongly preferred over Go, NanoBot or FreeClaw (Python OpenClaw-variants) are acceptable substitutes for the brain — but default to PicoClaw per the hardware target.

---

## 3. Container topology

```
docker-compose
├─ blackboard            # named volume, the shared spec folder
├─ coordinator           # picoclaw, ROLE=coordinator        (no bridge — pure software)
├─ drone-1 … drone-4     # picoclaw, ROLE=scout              each → its own bridge
├─ rover                 # picoclaw, ROLE=rover              → its own bridge
├─ bridge-drone-1 … 4    # mock ROS2 bridge (photograph, detect_obstacle, get_pose)
├─ bridge-rover          # mock ROS2 bridge (navigate, get_pose)
└─ viz                   # tails events.jsonl, serves dashboard on :8080
```

One bridge per robot mirrors the real topology (each drone carries its own bridge on-device). All containers mount the blackboard volume; `viz` mounts it read-only.

---

## 4. Roles for this scenario

| agent | role | SOUL capabilities | bridge tools used |
|---|---|---|---|
| coordinator | coordinator | — | — |
| drone-1..4 | scout | move, photograph, detect_obstacle | photograph, detect_obstacle, get_pose |
| rover | rover | navigate | navigate, get_pose |

Write a `SOUL.md` per agent (frontmatter format from the spec §2). Give the 4 drones distinct `priorities` so the PROPOSE/CONVERGE phases are a real negotiation (e.g. one prioritizes blind-spot curbs, one prioritizes speed/coverage ratio, one altitude detail, one intersection focus).

---

## 5. Delta from the spec — the rover and the map→nav dependency

The spec's phases (PROPOSE → CONVERGE → EXECUTE → REPORT → DONE) run for the **mapping team** (coordinator + 4 drones). The rover is gated on the result:

- The rover is assigned in EXECUTE but its assignment is `{ "wait_for": "world.ready" }`. It posts a `BLOCK` and idles until the coordinator certifies the map.
- During REPORT the coordinator merges drone photos into `state/world.json` (covered cells, gaps, localized obstacles). When `gaps == [] and obstacles localized`, it sets `world.json.ready = true` and writes `decision.json.result = "PASS: safe passage"`.
- That unblocks the rover: it requests a path A→B over `world.json`, calls `navigate(A, B)`, streams pose, and posts `REPORT` on arrival. Then `phase = DONE`.

`navigate` is a single tool call from the rover's perspective — exactly "go A → B on the map." Path planning lives in the bridge (mock: A* over the occupancy grid in `world.json`; real: Nav2 `NavigateToPose`).

Add to `state/world.json`: `ready: bool`, `grid: <occupancy grid>`, `start: [x,y]`, `goal: [x,y]`.

---

## 6. Bridge interface (tools)

HTTP service. Same contract for mock and real; only the implementation differs. Each robot's bridge is reachable by its agent at `BRIDGE_URL`.

```
POST /photograph        { sector }            -> { image_path, ts }
POST /detect_obstacle   { image_path }        -> { obstacles: [{type, xy, conf}], coverage }
POST /navigate          { from, to, grid }    -> streams { pose, progress } then { status:"arrived" }
GET  /pose                                    -> { xy, heading }
GET  /healthz                                 -> ok
```

**Mock implementation (dev):**
- `photograph(sector)` → returns the path of a test image mapped to that sector (see §7). Copies it into `artifacts/`.
- `detect_obstacle(image_path)` → reads a sidecar `<image>.labels.json` if present (hand-annotated), else runs a trivial CV pass (e.g. contour/colour blob) to fabricate plausible obstacles. Returns a `coverage` number derived from the fixture metadata.
- `navigate(from,to,grid)` → A* over the grid, emits simulated pose updates on a timer, ends `arrived` (or `blocked` if no path).
- `get_pose` → current simulated pose.

**Real implementation (hardware, later):** wrap each endpoint in a `rclpy` node — `photograph` = capture from the camera topic; `detect_obstacle` = your perception node / depth+lidar; `navigate` = Nav2 action client; `get_pose` = `/odom` or AMCL pose. Keep the HTTP contract identical so nothing upstream changes.

---

## 7. Test-image harness (full-flow verification)

Goal: drop images in a folder, run the stack, watch the whole flow complete.

```
test_fixtures/
  scenario-1/
    map.json                # occupancy grid + start A + goal B
    sector-A.jpg            # one (or several) image per sector
    sector-A.labels.json    # optional: ground-truth obstacles + coverage
    sector-B.jpg ...
```

- A `--scenario` flag (env `SCENARIO=scenario-1`) tells the mock bridges which fixture set to serve.
- `photograph(sector)` returns the matching fixture image.
- The coordinator stitches reported sectors into `world.json` using `map.json`.
- Provide one shipped sample scenario with placeholder images + a grid that has exactly one obstacle the rover must route around, so a fresh checkout demos the full flow immediately.

Acceptance: `docker compose up` on the sample scenario reaches `phase=DONE` with `result="PASS"` and the rover's `arrived` report, unattended.

---

## 8. Thinking visualizer

"See what they think." Two event kinds drive it (extend the spec's `events.jsonl`):

- `thought` — emitted every agent cycle **before** it acts: `{kind:"thought", from, phase, text}` where `text` is the LLM's reasoning for this step. Wrap the PicoClaw loop so each decision logs its rationale here even when no message is posted.
- everything else (`message`, `phase`, `decision`, `assignment`, `artifact`, `pose`) as in spec §8. Add `pose` events from `navigate` so the rover's path animates.

Dashboard (`viz` container, `:8080`):
- nodes = agents; node colour = current phase; a live thought-bubble shows the latest `thought`.
- edges = messages; a particle flies `from → to` on each `message`; `BLOCK` glows red.
- centre panel = the occupancy grid: cells fill as sectors are covered, obstacles drop in, then the rover's path animates A→B from `pose` events.
- a scrubbable timeline keyed on `phase` events — replay the exact moment the drones converged and the moment the rover was unblocked.

Implement as: tail `events.jsonl` → WebSocket → a single-page dashboard. No build step beyond a static page + a tiny server is fine.

---

## 9. Docker / config

- `docker-compose.yml` with the services in §3. Shared volume `blackboard`. `viz` exposes `:8080`.
- One image `picoclaw-agent` (PicoClaw binary + a thin wrapper implementing the spec's agent loop §7: read phase/messages → decide → novelty-gate → write message/progress → append `thought`+events). Parameterize by `AGENT_ID`, `ROLE`, `BRIDGE_URL`, `SCENARIO`.
- One image `ros2-bridge-mock` for the bridges.
- `.env` for `MODEL_PROVIDER`, `MODEL`, `*_API_KEY`. **Never bake keys into images or compose.** Provide `.env.example`; gitignore `.env`.
- `make up` / `make down` / `make logs` / `make demo` (demo = up on the sample scenario, then print the dashboard URL).

---

## 10. Pi 5 / ROS2 deployment notes (later, but design for it now)

- Per drone on a Pi 5 (2–4GB): PicoClaw binary + the `rclpy` bridge node + camera. PicoClaw's footprint is trivial; the heavy part is the bridge/ROS2 and the camera pipeline.
- Model: a 2–4GB Pi cannot run a useful local LLM. Default each drone to a **remote model API** (needs network). Only consider a tiny quantized local model (Ollama, 1–3B Q4) on the 4GB units for offline runs, and expect quality/latency hits.
- ROS2: target a current LTS distro; the bridge is the only ROS2-aware component. Breakout-board GPIO/sensors are exposed through additional bridge endpoints — keep the same HTTP-tool contract.
- The blackboard becomes the coordinator's HTTP+WebSocket API (the §2 swap) once agents are on separate machines; the shared volume is dev-only.

---

## 11. Safety and sandboxing

This system spins up several autonomous agents with tool access, so treat it as untrusted-by-default and contain it deliberately. Run every PicoClaw container with no host shell access and a read-only root filesystem except the blackboard mount, and put the agents on an internal Docker network with no outbound internet beyond the model-provider endpoint and their own bridge. The bridge must expose only the whitelisted endpoints in §6 — never a generic "run command" or filesystem tool — so a confused or prompt-injected agent cannot escalate beyond moving a simulated robot or returning an image. Because these agents can ingest external content (test images, messages from peers), assume prompt injection is possible: validate every tool argument against a strict schema at the bridge boundary, and have the coordinator reject malformed messages rather than acting on them. Pin the PicoClaw version to a verified commit from the official Sipeed repo and check it into the project; do not pull "latest" at build time. Finally, the rover's `navigate` endpoint is the one action with real-world consequences on hardware — gate it behind the coordinator's explicit `world.ready` certification (per §5) and add a hard stop / e-stop path in the real bridge before any of this touches a physical rover.

---

## 12. File tree to create

```
project/
  README.md
  Makefile
  docker-compose.yml
  .env.example
  agent-coordination-spec.md        # already provided — keep it here
  agent/                            # picoclaw-agent image
    Dockerfile
    loop.(go|py)                    # spec §7 loop + thought/event emit + novelty gate
    roles/                          # role-specific decide() per phase
  bridge/                           # ros2-bridge-mock image
    Dockerfile
    mock.py                         # §6 mock impl (A* nav, fixture images)
    ros2/                           # real rclpy node stubs (later)
  souls/                            # SOUL.md per agent (§4)
    coordinator.md drone-1.md … rover.md
  viz/                              # §8 dashboard + ws server
  test_fixtures/scenario-1/         # §7 sample scenario, ships working
  blackboard/                       # gitignored runtime dir / volume target
```

---

## 13. Build order + acceptance

1. Read PicoClaw repo + spec (§0). Write a one-paragraph note in the README on the tool mechanism you found and the bridge approach you chose.
2. Blackboard scaffold + event/`thought` writer + novelty gate.
3. Coordinator: phase machine, convergence (`score` rule), `world.json` merge + safety verdict, rover gating (§5).
4. One agent loop reused for all roles; behavior switches on `ROLE`+`phase`. SOUL.md files.
5. Mock bridge (§6) + sample fixture scenario (§7).
6. docker-compose: bring up coordinator + 4 drones + rover + bridges. Verify a full PROPOSE→…→DONE run reaching `result="PASS"` and rover `arrived`.
7. Viz dashboard (§8) — confirm thoughts, message particles, grid fill, and the animated rover path all render live.
8. Stub the real `rclpy` bridge endpoints (no hardware calls yet) so the hardware seam is visible.

**Done = `make demo` runs the sample scenario unattended to a PASS verdict with the rover arriving, and the dashboard shows the agents thinking and the rover routing around the obstacle.**
```
