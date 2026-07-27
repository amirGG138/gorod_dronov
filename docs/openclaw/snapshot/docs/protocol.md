# Coordination protocol

This implements `agent-coordination-spec.md`. The coordinator drives a phase
state machine; agents react to the current phase. Only the coordinator writes
`phase/decision/assignments/world.json` (single-writer).

## Phases

Default (`SCOUT_CHAT=1`) — the scouts negotiate the split in an open chat:

```
INIT ─▶ CHAT ─▶ EXECUTE ─▶ REPORT ─▶ DONE
           ▲                   │
           └───── reopen ◀─────┘
```

Legacy (`SCOUT_CHAT=0`) — the silent proposal/vote flow:

```
INIT ─▶ PROPOSE ─▶ CONVERGE ─▶ EXECUTE ─▶ REPORT ─▶ DONE
```

| Phase | What happens | Exit condition |
|---|---|---|
| INIT | Coordinator writes `task.md` + config, opens CHAT (or PROPOSE). | immediate |
| CHAT *(default)* | Scouts negotiate the sector split in an open channel (`agent/roles/scout_chat.py`): claim, argue, trade, signal done. Coordinator derives `assignments` from each scout's last claim — conflicts → earliest-settled wins, leftovers round-robin. | done-consensus **or** deadline |
| PROPOSE *(legacy)* | Every scout posts a `PROPOSAL` claiming a sector. | all scouts posted **or** deadline |
| CONVERGE *(legacy)* | Scouts `VOTE`; coordinator tallies → `decision.json`. | all voted **or** deadline |
| EXECUTE | Coordinator writes `assignments.json`; drones photograph + detect, write `progress`. Rover posts `BLOCK` and idles. | all drones done **or** deadline |
| REPORT | Coordinator merges into `world.json`, checks completeness. PASS → certify + unblock rover; gaps → reopen EXECUTE. | rover arrived → DONE |
| DONE | Final verdict in `decision.json.result`. | — |

The painting **studio** flow reuses the same machine with different phase
content: CHAT (free stigmergic chat, done-consensus) → CONVERGE (clustered
ballot) → EXECUTE (collaborative canvas) → REPORT → DONE. See
[painters](painters.md); the debate flow is in
[debate-system](debate-system.md).

Deadlines (`agent/loop.py` `build_config`): propose 25 s, converge 25 s, execute
120 s, report 120 s. Deadlines stop a stalled agent from blocking the run.

## The rover gate (the key dependency)

The mapping team (coordinator + 4 drones) runs the phases. The rover is gated on
the result:

* In EXECUTE the rover's assignment is `{"wait_for": "world.ready"}`; it posts a
  `BLOCK` and idles.
* In REPORT the coordinator merges drone photos into `world.json` (covered cells,
  gaps, localized obstacles). When `gaps == [] and obstacles localized and all
  drones reported`, it sets `world.json.ready = true` and
  `decision.json.result = "PASS: safe passage"`.
* That unblocks the rover: it reads the grid/start/goal from `world.json`, calls
  `navigate(start, goal, grid)`, streams pose, and posts `REPORT` on arrival →
  `phase = DONE`.

`navigate` is one tool call from the rover's perspective — "go A → B on the map".
Path planning lives in the bridge (mock: A\* over the occupancy grid; hardware:
Nav2 `NavigateToPose`).

## Messages (`messages/<seq>-<ts>-<id>-<type>.json`)

Append-only, one JSON file per message. Filenames are **seq-first**
(`{seq:06d}-{ts}-{from}-{type}.json`), where `seq` is a board-global monotonic
counter (a flock-guarded `blackboard/.seq` file, wiped on reset; in hub mode
the hub stamps it server-side). Consumers sort messages by `seq`, **not** `ts`.
Fields:

```json
{
  "id": "msg-drone-2-0007",
  "seq": 7,
  "from": "drone-2", "to": "all", "phase": "PROPOSE", "type": "PROPOSAL",
  "ts": "2026-06-08T10:04:11Z", "ref": null, "novelty": 0.81,
  "body": "human/agent-readable text",
  "payload": { "scheme": "length-4", "claim_sector": "A" }
}
```

| type | phase | meaning |
|---|---|---|
| `PROPOSAL` | PROPOSE | a candidate split + claimed sector |
| `VOTE` | CONVERGE | endorse/score a proposal (`ref` = proposal id) |
| `ASSIGNMENT` | EXECUTE | coordinator hands a task to an agent |
| `STATUS` | EXECUTE | progress update |
| `REPORT` | REPORT | finished work + result location |
| `BLOCK` | any | "I'm stuck / waiting for X" — pulls coordinator attention |
| `CHAT` | CHAT | open-channel negotiation line (sector/zone/studio chats) |
| `PLAN` | EXECUTE | survey: the executed per-turn JSON action plan `{plan, results, pose}` |
| `FOUND` | EXECUTE | survey: cargo candidate `{cell, confidence, label}` |
| `VERIFY` | EXECUTE | survey: verifier verdict `{cell, cargo, confidence}` |

The survey task's phases, verification queue and world model are documented in
[survey](survey.md).

## State files

```jsonc
// state/phase.json        (writer: coordinator)
{ "phase": "CONVERGE", "round": 1, "updated_by": "coordinator", "ts": "...", "deadline": "..." }
// state/decision.json     (writer: coordinator)
{ "scheme": "length-4", "bounds": {...}, "rule": "score", "result": "PASS: safe passage" }
// state/assignments.json  (writer: coordinator)
{ "drone-1": "A", "drone-2": "B", ..., "rover": { "wait_for": "world.ready" } }
// state/progress/<id>.json (writer: that agent only)
{ "status": "done", "sector": "A", "artifact": "...", "coverage": 0.97, "obstacles": [...] }
// state/world.json        (writer: coordinator)
{ "covered": ["A","B","C","D"], "gaps": [], "obstacles": [...],
  "grid": [[...]], "start": [0,0], "goal": [9,9], "ready": true }
// state/pause.json        (writer: OPERATOR via hub/viz POST /pause; agents read-only)
{ "paused": true, "reason": "замена аккумуляторов", "by": "operator", "ts": "..." }
```

`pause.json` — глобальная пауза всех сценариев (посадка дронов, заморозка
фазовой машины, сдвиг дедлайнов на длительность паузы). См. [pause](pause.md).

## Convergence (`config.yaml: convergence`, default `score`)

Configurable; the demo uses `score` — each scout scores proposals and the
length-4 scheme (explicit per-sector coverage, no blind spots) wins. Other modes
defined in the spec: `majority`, `weighted`, `coordinator`.

## Novelty gate (spec §6.4)

Before posting, a message's information gain is scored against what's already on
the board (token Jaccard: `novelty = 1 − max_similarity`, in `agent/bb.py`).

* **Free-form chatter** (`PROPOSAL`) below `NOVELTY_MIN` (default 0.3) is
  **dropped** (logged as a `drop` event). This prevents the "two-thirds of
  comments repeat prior content" failure mode of uncoordinated swarms.
* **Protocol-critical** messages (VOTE, ASSIGNMENT, STATUS, REPORT, BLOCK)
  always post but still carry a novelty score for the dashboard.

This split lives in `agent/loop.py` (`gated_types = {"PROPOSAL"}`).

## Agent loop (spec §7)

```python
while True:
    phase = read("state/phase.json")["phase"]
    if phase == "DONE": break
    result = role.step(ctx)               # role behavior for (role, phase)
    if result.thought != last:            # "see what they think"
        emit_thought(...)                 # streamed (real LLM) or single (mock)
    for msg in result.messages:           # novelty-gate, then post + event
        if gated and novelty < min: drop; else write_message + message event
    sleep(POLL_INTERVAL)
```

Roles are **idempotent against the board** — `step()` checks what's already
posted/recorded before acting, so the polling loop never duplicates a message or
a robot action.
