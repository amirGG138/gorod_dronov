# Agents, roles & the brain

One binary (`agent/loop.py`) runs every agent; behavior switches on `ROLE` +
phase. Each role exposes `step(ctx)` returning a thought + candidate messages;
the loop handles novelty-gating, posting, and thought emission.

## Roles (`agent/roles/`)

### coordinator (`coordinator.py`)
Owns the phase machine and the world model. Never moves a robot.
* Transitions phases on exit conditions or deadlines.
* CONVERGE → writes `decision.json` (scheme `length-4`, bounds from the scenario).
* EXECUTE → writes `assignments.json` (scouts → sectors round-robin; rover →
  `{wait_for: world.ready}`) and posts `ASSIGNMENT` messages.
* REPORT → `_build_world()` merges drone progress into `world.json`
  (covered/gaps/obstacles + grid/start/goal), certifies `PASS` when complete,
  unblocks the rover, and on rover arrival → DONE. If gaps remain it reopens
  EXECUTE for just the gap sectors.
* **Discovery**: reads the hub registry each cycle so drones that join the
  network are included automatically; falls back to the `SCOUTS`/`ROVER` env.

### scout (`scout.py`)
* CHAT (default) → negotiates the sector split in an open channel
  (`scout_chat.py`): claims sectors, argues, trades, and signals done; the phase
  ends on done-consensus. The coordinator derives `assignments` from each
  scout's **last claim** — conflicts go to the earliest-settled claim, leftovers
  are handed out round-robin.
* `SCOUT_CHAT=0` restores the legacy path:
  * PROPOSE → posts a `PROPOSAL` claiming its preferred sector, body shaped by
    its SOUL `priorities`.
  * CONVERGE → scores proposals, posts a `VOTE` for the length-4 scheme.
* EXECUTE → reads its sector from `assignments`, calls `bridge.photograph` then
  `bridge.detect_obstacle`, writes an `artifact` event + its `progress` (status
  done, coverage, obstacles), posts `STATUS` then `REPORT`.
* `TASK=survey` dispatches the scout to `survey_scout.py` entirely: zone chat,
  then per-turn JSON action plans (`fly_to`/`wait`/`photo_analyze`, LLM plan
  validated against the grid + own zone, deterministic fallback), closed-loop
  pose from the bridge, `FOUND` broadcasts and sequential `VERIFY` duty. See
  [survey](survey.md).

### rover (`rover.py`)
* While `world.ready` is false → posts a single `BLOCK`, idles (safety: never
  drive on an uncertified map).
* When `world.ready` → reads grid/start/goal from `world.json`, calls
  `bridge.navigate` (streamed), emits a `pose` event per step (animates the path
  on the dashboard), writes `progress` (arrived + final pose), posts `REPORT`.

### painter (`painter.py`)
The painting-task drone. In the flagship studio flow (`STUDIO_CHAT=1`): free
CHAT (done-consensus) → CONVERGE (enum-locked ballot) → EXECUTE, where in
`PAINT_MODE=collab` each drone paints its **own colour** as z-layered filled
shapes (`z = facilitator_slot*1000 + local_z`). Other modes: `curated` (default
`PAINT_MODE` — the coordinator paints all) and `distributed` (spray). See
[painters](painters.md).

### moderator (`moderator.py`)
The debate chair — a **first-class role** in `roles._ROLES`
(`scripts/run_local.sh` launches it directly with `ROLE=moderator`). Frames the
motion, grants the floor, decides round continuation, tallies the vote.
`coordinator.py`'s `task==debate` dispatch is retained for compatibility. See
[debate-system](debate-system.md).

### debater (`debate.py`)
Opening statement → floor-gated arguments → one ballot. See
[debate-system](debate-system.md).

## SOULs (`souls/*.md`)

YAML frontmatter (machine-read) + markdown body (the agent's system context).
Parsed by `agent/souls.py` (a tiny stdlib YAML subset — no PyYAML dependency).

```markdown
---
id: drone-1
name: Magpie
role: scout
capabilities: [move, photograph, detect_obstacle]
vote_weight: 1.0
priorities:
  - blindspot_curbs
  - coverage_completeness
---
You are Magpie, a scout drone. You favor thorough edge coverage over speed...
```

The four drones have **distinct priorities** so PROPOSE/CONVERGE is a real
negotiation, not a rubber stamp:

| drone | name | priorities |
|---|---|---|
| drone-1 | Magpie | blind-spot curbs, coverage completeness |
| drone-2 | Swift | coverage/speed ratio, efficient sweeps |
| drone-3 | Kestrel | low-altitude detail, obstacle height |
| drone-4 | Harrier | intersection focus, conflict points |
| rover | Badger | safe passage, shortest certified path |
| coordinator | Keystone | safety first, no gaps, all obstacles localized |

The body is fed to the LLM as system context, so each agent reasons in character.

**Painter personas are seed-generated, not soul-fixed.** For the painting task,
`agent/roles/personas.py` derives each painter's name/colour/technique/
temperament/leaning per run from `agent_id + paint_seed` and publishes the
roster to `config.yaml.json` at INIT; `souls/painter-*.md` are optional
overrides. The scout/rover souls (Magpie etc.) remain the fixed source for
those roles.

## The brain (`agent/brain.py`)

The coordination **protocol is driven deterministically by the roles**, so the
demo runs unattended with no API key. When a real provider is configured, the
model **narrates its reasoning** for each step — that text becomes the `thought`
events the dashboard renders ("see what they think").

| `MODEL_PROVIDER` | default `MODEL` | notes |
|---|---|---|
| `mock` | — | deterministic templated reasoning; no key, reproducible |
| `sverk` | `qwen35` | custom OpenAI-compatible gateway `ai.sverk.tech/v1` |
| `anthropic` | `claude-opus-4-8` | Anthropic Messages API |
| `openai` | `gpt-4o-mini` | OpenAI-compatible (`OPENAI_API_BASE` to override) |
| `ollama` | `qwen2.5:3b` | local model on-device (4GB Pi fallback) |

All providers use raw HTTP via `urllib` (no SDK) so the agent image stays tiny
and the build needs no package index. Keys come from `.env`
(`SVERK_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`); never baked into
images. See [configuration](configuration.md).

### Live thought streaming

For OpenAI-compatible providers (`sverk`, `openai`) the brain **streams** tokens
(`think_stream` → `_stream_chat`, vLLM `stream:true`). The loop emits incremental
events: `thought_start` → many `thought_delta` → `thought_end`. The dashboard
fills each agent's bubble token-by-token with a typewriter effect. The mock brain
emits a single `thought` event.

> `qwen35` is a reasoning model: its content **is** a live chain-of-thought
> ("Here's a thinking process: 1. Analyze..."). That is exactly the
> see-what-they-think content; the dashboard reveals it smoothly and saves the
> full text per agent. Tune length with `MODEL_MAX_TOKENS`.

### Structured output

On the sverk gateway, `response_format: json_schema` is **grammar-enforced by
the sampler** and used on the small calls only — chat turns and votes (ballots
are enum-locked to the candidate list). Large compose calls stay plain text
(grammar decoding stalls on this deploy — see
[HANDOFF-vllm-upgrade](HANDOFF-vllm-upgrade.md)). Structured calls send
`enable_thinking: false`; vLLM-only params are **not** sent to
`api.openai.com`. Kill switch: `LLM_JSON_SCHEMA=0`.

### How a step is narrated

`emit_thought(...)` builds a prompt from the SOUL body (system) + the phase and
the planned deterministic action (user), then streams the model's reasoning. If
the LLM errors, it falls back to the role's templated thought — the protocol is
never blocked by a flaky model.
