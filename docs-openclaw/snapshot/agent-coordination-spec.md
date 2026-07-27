# Multi-Agent Task Coordination Spec

A Moltbook-style shared space, but **task-focused**. Agents (OpenClaw or any LLM agent) collaborate through a shared folder ("blackboard"), coordinate through an explicit protocol, and emit an event stream that a visualizer renders live.

## Core principle

A shared folder alone does **not** produce collaboration — agents generate in parallel and talk past each other. Coordination must be designed explicitly: decomposition, information routing, and convergence. This spec encodes that as a phase state machine plus a novelty gate that suppresses redundant chatter.

---

## 1. Directory layout (the blackboard)

```
blackboard/
  task.md                  # the goal, shared by all agents (read-only to agents)
  config.yaml              # run config: agents, coordinator, convergence rule, timeouts
  agents/
    <agent-id>/SOUL.md     # persona + role + capabilities, one per agent
  messages/                # append-only log, 1 file = 1 message
    <ts>-<agent-id>-<type>.json
  state/                   # current shared state (overwritten, last-write-wins)
    phase.json
    decision.json
    assignments.json
    progress.json
    world.json             # shared world model: street map / canvas
  artifacts/               # outputs: photos, painted tiles, stitched map
  events.jsonl             # APPEND-ONLY feed for the visualizer (see §8)
```

Rule: agents **only** write to `messages/`, `artifacts/`, their own `state/progress.json` entry, and append to `events.jsonl`. The **coordinator** owns `state/phase.json`, `state/decision.json`, `state/assignments.json`. Single-writer per file avoids races.

---

## 2. SOUL.md — agent persona + role

One file per agent. YAML frontmatter (machine-read) + markdown body (fed to the agent as its system context).

```markdown
---
id: drone-2
name: Magpie
role: scout              # scout | painter | coordinator
capabilities:            # what actions this agent can take
  - move
  - photograph
  - detect_obstacle
vote_weight: 1.0         # used by weighted convergence rules
style:                   # only meaningful for creative tasks
  palette: [cobalt, bone, rust]
  technique: hatching
  influences: [Hokusai, Egon Schiele]
priorities:              # tie-breakers when proposing / voting
  - coverage_completeness
  - low_altitude_detail
---

You are Magpie, a scout drone. You favor thorough edge coverage over speed.
When proposing a plan, prefer schemes that guarantee no blind spots.
When voting, reward proposals that name explicit coverage checks.
Be terse. Only post a message if it adds information not already on the board.
```

Field notes:
- `role` selects which phase behaviors the agent runs.
- `capabilities` is the contract the coordinator uses to build assignments.
- `style` gives each painter a distinct fingerprint, which makes the convergence phase a real negotiation instead of a rubber stamp.
- The body's last line is the **novelty gate** instruction (see §6.4).

---

## 3. Message spec

One JSON file per message in `messages/`. Filename: `<iso-ts>-<agent-id>-<type>.json`. Append-only — never edit or delete.

```json
{
  "id": "msg-0007",
  "from": "drone-2",
  "to": "all",
  "phase": "PROPOSE",
  "type": "PROPOSAL",
  "ts": "2026-06-08T10:04:11Z",
  "ref": null,
  "novelty": 0.81,
  "body": "Split street into 4 length sectors; I take the north curb where parked cars create blind spots.",
  "payload": {
    "scheme": "length-4",
    "claim_sector": "A-north"
  }
}
```

Fields: `to` is an agent-id, `"all"`, or `"coordinator"`. `ref` links a reply/vote to the message it answers. `novelty` (0–1) is the agent's self-scored or coordinator-scored information gain; messages below threshold are dropped (§6.4). `payload` is the structured, machine-actionable part; `body` is human/agent-readable.

### Message types
| type | phase | meaning |
|---|---|---|
| `PROPOSAL` | PROPOSE | a candidate plan/style |
| `VOTE` | CONVERGE | endorse/score a proposal (`ref` = proposal id) |
| `ASSIGNMENT` | EXECUTE | coordinator hands a task to an agent |
| `STATUS` | EXECUTE | progress update |
| `REPORT` | REPORT | finished work + result location |
| `BLOCK` | any | "I'm stuck / need X" — pulls coordinator attention |

---

## 4. State spec

Small JSON files, overwritten in place (last-write-wins, single writer each).

```json
// state/phase.json   (writer: coordinator)
{ "phase": "CONVERGE", "round": 1, "updated_by": "coordinator", "ts": "...", "deadline": "2026-06-08T10:06:00Z" }

// state/decision.json   (writer: coordinator) — the converged choice
{ "scheme": "length-4", "style": null, "bounds": { "A": [0,25], "B": [25,50], "C": [50,75], "D": [75,100] } }

// state/assignments.json   (writer: coordinator)
{ "drone-1": "A", "drone-2": "B", "drone-3": "C", "drone-4": "D" }

// state/progress.json   (each agent writes ONLY its own key)
{ "drone-1": { "status": "done", "artifact": "artifacts/sector-A.jpg", "coverage": 0.97 } }

// state/world.json   (writer: coordinator) — merged shared model
{ "covered": ["A","B"], "gaps": ["C-east-edge"], "obstacles": [{ "sector":"A","type":"parked_car","xy":[12,3] }] }
```

---

## 5. Phase protocol (state machine)

```
INIT ──▶ PROPOSE ──▶ CONVERGE ──▶ EXECUTE ──▶ REPORT ──▶ DONE
                         ▲                        │
                         └──────── reopen ◀───────┘   (if coverage/quality fails)
```

| Phase | What happens | Exit condition (coordinator decides) |
|---|---|---|
| INIT | coordinator reads `task.md`, sets phase=PROPOSE | immediate |
| PROPOSE | every agent posts ≥1 `PROPOSAL` | all agents posted **or** deadline |
| CONVERGE | agents `VOTE` on proposals; coordinator tallies → writes `decision.json` | convergence rule satisfied (§6.3) |
| EXECUTE | coordinator writes `assignments.json`; agents act, write artifacts + `STATUS` | all assignments report done **or** deadline |
| REPORT | agents post `REPORT`; coordinator merges into `world.json`, checks completeness | pass → DONE; fail → reopen EXECUTE/CONVERGE |
| DONE | coordinator writes final verdict to `decision.json.result` | — |

### 6. Rules

**6.1 Phase transitions** — only the coordinator writes `phase.json`. It transitions when the exit condition is met or the `deadline` passes. (Deadlines stop a stalled agent from blocking the run.)

**6.2 Decentralized variant (no fixed coordinator)** — replace coordinator with quorum: a phase advances when ≥⌈N/2⌉+1 agents post a `VOTE` of type `advance`. Decision is the proposal with the highest tally. Slower, more robust, no single point of failure. Pick per `config.yaml: coordinator: none|<agent-id>`.

**6.3 Convergence rule** (configurable in `config.yaml`):
- `majority` — proposal with most votes wins; ties → re-vote among top 2.
- `weighted` — votes scaled by `vote_weight` from SOUL.md.
- `coordinator` — coordinator picks, using votes as advice.
- `score` — each agent scores every proposal 0–10 on the task's `priorities`; highest mean wins.

**6.4 Novelty gate** — before posting, an agent self-scores `novelty` against messages already on the board (semantic similarity to existing payloads). If `novelty < config.novelty_min` (default 0.3), the message is **not** posted. This is what prevents the "two-thirds of comments repeat prior content" failure mode of uncoordinated agent swarms.

**6.5 Conflict / blocking** — a `BLOCK` message forces the coordinator to respond before the next transition. Two agents claiming the same sector/quadrant in PROPOSE → coordinator resolves in `assignments.json` (capability + priority based).

### 7. Agent loop (pseudocode)

```python
cursor = 0
while True:
    phase = read("state/phase.json")["phase"]
    new_msgs = read_messages_since(cursor); cursor = now()
    if phase == "DONE": break

    action = decide(role=self.role, phase=phase, soul=self.soul,
                    board=read_state(), inbox=new_msgs)

    if action and novelty(action, board) >= NOVELTY_MIN:
        write_message(action)            # → messages/
        if action.type in ("STATUS","REPORT"):
            update_own_progress(action)  # → state/progress.json
            write_artifact(action)       # → artifacts/
        append_event(action)             # → events.jsonl

    wait_for_change("state/phase.json", "messages/")   # heartbeat
```

---

## 8. Event stream for the visualizer

Every message **and** every state transition is appended as one line to `events.jsonl`. The visualizer tails this file and renders. This decouples the agents from the UI entirely.

```jsonl
{"t":"...","kind":"message","from":"drone-2","to":"all","phase":"PROPOSE","type":"PROPOSAL","novelty":0.81}
{"t":"...","kind":"phase","phase":"CONVERGE","round":1}
{"t":"...","kind":"decision","decision":{"scheme":"length-4"}}
{"t":"...","kind":"assignment","map":{"drone-1":"A","drone-2":"B"}}
{"t":"...","kind":"artifact","from":"drone-1","path":"artifacts/sector-A.jpg"}
```

Suggested rendering:
- nodes = agents (color = current phase: thinking / posting / executing)
- edges = messages (a particle flies `from → to` on append; `BLOCK` glows red)
- center = the growing artifact / world model
- a scrubbable timeline keyed on `phase` events, so you can replay the exact moment the agents converged

---

## 9. Worked example A — street photo for safe car passage

- Agents: `coordinator` + `drone-1..4` (role `scout`).
- `task.md`: "Photograph the model street completely enough to certify a car can pass safely. No coverage gaps, all obstacles localized."
- **PROPOSE**: drones propose split schemes — by length sectors, by lane, by altitude bands. Each claims a sector matching its `priorities` (Magpie claims blind-spot curbs).
- **CONVERGE**: vote → `decision.json = {scheme:"length-4", bounds:{...}}`.
- **EXECUTE**: `assignments.json` maps drone→sector. Each flies, photographs, writes `artifacts/sector-X.jpg` + `progress.json` with a `coverage` ratio and detected `obstacles`.
- **REPORT**: coordinator merges into `world.json`. If `gaps` non-empty → reopen EXECUTE, reassign just the gap. When `gaps == [] and all obstacles localized` → `decision.json.result = "PASS: safe passage"`.

## 10. Worked example B — collaborative painting

- Agents: `painter-1..4` (role `painter`), `coordinator: none` (decentralized).
- `task.md`: "Together produce one coherent painting of a harbor at dawn."
- **PROPOSE**: each painter posts a `PROPOSAL` from its SOUL `style` (palette, technique, theme). Real disagreement here is the point.
- **CONVERGE**: `score` rule — painters score each style on coherence/feasibility → `decision.json = {style:{palette, technique}, canvas:"quadrants"}`. This is the "договорились" moment the visualizer should highlight.
- **EXECUTE**: each paints its quadrant in the agreed style, posts `STATUS`, writes `artifacts/quadrant-N.png`.
- **REPORT**: each painter reviews its neighbors' shared edges for continuity; mismatched seams → a `BLOCK`, triggering a short blend pass (reopen EXECUTE on the seam only) → DONE.

---

## Build order from here

1. `config.yaml` + folder scaffold + `events.jsonl` writer.
2. Coordinator (phase machine §5 + convergence §6.3).
3. One agent loop (§7) reused for all roles; behavior switches on `role`+`phase`.
4. SOUL.md files for the 4 agents.
5. Visualizer tailing `events.jsonl` (§8).
6. Swap in real drone/camera/paint tools behind the `capabilities` interface.
