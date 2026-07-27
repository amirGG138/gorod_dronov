# Visualizer / dashboard

"See what they think." The dashboard (`viz/server.py` + `viz/index.html`) tails
`events.jsonl` and streams to the browser, rendering the agents thinking and the
rover routing around the obstacle. Open <http://localhost:8080>.

## How it streams

`events.jsonl` is the decoupling layer: agents (and state transitions) append
events; the server tails the file and pushes each line to the browser over
**Server-Sent Events (SSE)**. SSE is used instead of a raw WebSocket so the whole
thing is stdlib-only and gets browser auto-reconnect for free — same
"tail → stream → SPA" design as the brief's WebSocket suggestion. On connect the
server replays existing events (so the timeline and the current state rebuild),
then streams live.

## Event kinds (`events.jsonl`)

| kind | emitted when | fields |
|---|---|---|
| `thought` | mock brain, per step | `from, phase, text` |
| `thought_start` / `thought_delta` / `thought_end` | real LLM streaming | `from, phase, text` |
| `message` | a message is posted | `from, to, phase, type, novelty, id` |
| `drop` | a message fails the novelty gate | `from, type, novelty` |
| `phase` | a phase transition | `phase, round` |
| `decision` | scheme converged / verdict set | `decision` |
| `assignment` | sectors assigned | `map` |
| `artifact` | a sector is photographed | `from, path, sector` |
| `pose` | rover navigation step | `from, xy, progress` |

## What you see

* **Agent nodes** coloured by phase, each with a live thought-bubble. With a real
  reasoning model the bubble streams the chain-of-thought token-by-token (a
  client-side typewriter reveals it smoothly regardless of how the upstream
  chunked the stream — no extra network to the drones). A blinking cursor shows
  it's actively thinking.
* **Message feed** with novelty scores; sender/receiver nodes pulse on each
  message; `BLOCK` glows red.
* **World grid** (centre): cells tint as sectors are covered, obstacles drop in,
  then the rover's path animates A → B from `pose` events, routing around the
  wall.
* **Phase timeline** of every transition.
* **Click any agent node → a modal** with that agent's *full* untruncated
  chain-of-thought for every step, plus its chat (messages). This is the "click a
  drone, open everything it thought" view.

## Endpoints

Read-only (always available):

| endpoint | returns |
|---|---|
| `GET /` | the SPA |
| `GET /healthz` | `{ok, hub, scenario}` |
| `GET /scenario.json` | the occupancy grid / start / goal / sectors |
| `GET /events` | the SSE stream (replay + live) |
| `GET /agents` | list of agents with role + current phase + registered flag |
| `GET /agents/<id>/transcript` | `{role, thoughts:[{ts,phase,text}], messages}` |

Transcripts are **assembled from the persisted event stream**: `thought_delta`
events between a `thought_start`/`thought_end` are concatenated into the full,
untruncated reasoning for that step. So you can replay exactly what each drone
was thinking — even tokens that were only briefly on screen.

Hub-mode write endpoints (`HUB_MODE=1`, used by remote drones) are documented in
[distributed](distributed.md).

## Modes

* **Dashboard (read-only)** — default. The volume is mounted read-only; only the
  read endpoints above are served; POSTs return 403.
* **Hub** — `HUB_MODE=1`: also the network gateway drones post to. Same
  dashboard. See [distributed](distributed.md).
