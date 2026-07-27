# Turn-based debate / chat / decision engine

A reusable, project-agnostic engine for making a set of agents **chat, debate a
topic, and reach a decision** — turn-based, moderated, with a voting conclusion.
It is built on the existing OpenClaw primitives (blackboard, phase machine,
brain, souls, event feed), so it inherits their robustness: single-writer state,
atomic append-only messages/events, novelty gating, per-run logging, and the
local ↔ distributed (`FileBoard`/`HttpBoard`) swap.

> Design rationale and the research it's based on (multi-agent debate, AutoGen
> speaker selection, adaptive stopping, voting-vs-judge) are summarized in the
> chat thread that introduced this engine. TL;DR of the literature: personas
> drive quality, majority voting is a strong cheap baseline, and an adaptive
> stopping rule beats a fixed round count.

## Flow

```
INIT/FRAME ──▶ OPENING ──▶ DEBATE (rounds) ──▶ VOTE ──▶ CONCLUDE ──▶ DONE
   moderator     all         turn-based           all      moderator
   states the    open in     floor-gated turns    cast     tallies
   motion        parallel    (+ dynamic length)   ballots  (voting only)
```

- **FRAME** — the moderator posts the motion/question (+ options) from the topic
  fixture. Everyone argues the same question.
- **OPENING** — each debater states an initial position *in parallel* (avoids
  anchoring on whoever speaks first).
- **DEBATE** — turn-based rounds. The moderator grants the **floor** to one
  speaker at a time (or the whole room, in `parallel` mode); a debater only
  speaks while holding an unanswered floor grant. Rounds continue while the
  debate is productive and stop early on consensus (see *Dynamic length*).
- **VOTE** — each debater casts one ballot over the candidate positions (the
  explicit options, or the distinct stances that emerged).
- **CONCLUDE** — the moderator tallies (majority or soul-weighted) and writes the
  decision. **Voting only — no judge.**

## Turn order (`DEBATE_TURNS`)

| Mode | Behavior | When to use |
|---|---|---|
| `moderated` *(default)* | Moderator picks the next speaker each turn (LLM-assisted: calls on whoever was challenged / dissents / hasn't answered; deterministic round-robin fallback). One live speaker at a time. | Best arguments, most "interesting" flow. |
| `round_robin` | Fixed rotation through the debaters. | Deterministic, easiest to reason about. |
| `parallel` | The whole room responds each round (opening-statement style). | Fastest; many voices at once. |

## Dynamic length

Rounds are **not** a fixed count. After each round the moderator decides to
continue or call the vote:

- always continue below `DEBATE_MIN_ROUNDS`;
- hard-stop at `DEBATE_MAX_ROUNDS`;
- **stop early** when positions converge (`DEBATE_CONSENSUS` share of debaters
  hold the same stance) or when all speakers *yield*;
- otherwise **keep going while it's productive** — i.e. the last round produced a
  *novel* argument (via the built-in novelty gate) or a debater *requested the
  floor*.

Debaters signal this themselves: each `ARGUMENT` payload carries `yield` (nothing
to add) and `request_floor` (wants another turn).

## Configuration

All via env (see `agent/loop.py::build_config`):

| Env | Default | Meaning |
|---|---|---|
| `TASK` | — | set to `debate` |
| `SCENARIO` | `debate-1` | topic fixture dir under `FIXTURES` |
| `DEBATERS` | `debater-1,debater-2,debater-3` | participant ids (auto-discovered from the hub registry in distributed mode) |
| `DEBATE_TURNS` | `moderated` | `moderated` \| `round_robin` \| `parallel` |
| `DEBATE_MIN_ROUNDS` | `1` | floor on debate rounds |
| `DEBATE_MAX_ROUNDS` | `3` | ceiling on debate rounds |
| `DEBATE_CONSENSUS` | `1.0` | stance share that ends the debate early (1.0 = unanimity) |
| `DEBATE_RULE` / `CONVERGENCE` | `majority` | `majority` or `weighted` (by soul `vote_weight`) |
| `DEADLINE_OPENING/DEBATE/FLOOR/VOTE` | 90/120/60/90 s | phase + per-turn safety timeouts |

The **topic** lives in `test_fixtures/<SCENARIO>/map.json`:

```json
{ "topic": "...", "question": "...?", "options": ["A", "B", "C"] }
```

Leave `options` empty to let stances emerge freely — the ballot is then built
from the distinct positions debaters actually took.

## Run it

The moderator is a **first-class role** (`moderator` in `roles._ROLES`):
`scripts/run_local.sh`'s debate branch launches it directly with
`AGENT_ID=moderator ROLE=moderator`. The `coordinator.py` `task==debate`
dispatch is retained for compatibility.

```bash
make local-debate                      # moderator + 3 debaters + test stand
# real arguments (needs a provider in .env or inline):
MODEL_PROVIDER=sverk make local-debate
# knobs:
DEBATE_TURNS=parallel DEBATE_MAX_ROUNDS=4 make local-debate
```

Test stand (live current-speaker window + every debater's argument in parallel +
final tally): **http://localhost:8080/debate**

## Reusing in another project

Nothing in the engine is tied to this repo's domain. To reuse:

1. **Topic** — drop a `map.json` with `topic/question/options` (or point
   `SCENARIO` at your own fixtures dir).
2. **Personas** — write `souls/<id>.md` per debater (frontmatter `name`,
   `vote_weight`, `priorities`; markdown body = the voice/values). See
   `souls/debater-1..3.md` and `souls/moderator.md`. Personas are the #1 quality
   lever — make them genuinely divergent.
3. **Provider** — set `MODEL_PROVIDER` (`sverk`/`anthropic`/`openai`/`ollama`);
   `mock` exercises the protocol without a key.
4. Consume the **event feed** (`events.jsonl` / the `/events` SSE) for your own
   UI. Debate-specific events: `debate` (motion), `floor` (`{speaker, round}`),
   plus the standard `phase`, `message` (`OPENING`/`ARGUMENT`/`VOTE`/…),
   `thought_start|delta|end` (live reasoning), and `decision` (the tally).

## Files

| File | Responsibility |
|---|---|
| `agent/roles/debate_common.py` | Shared protocol: message/phase constants, topic/frame, board-state parsing (positions, floors, candidates). |
| `agent/roles/debate.py` | The `debater` role: opening → floor-gated argument → vote. One LLM call per turn. Idempotent against the board. |
| `agent/roles/moderator.py` | The moderator — a first-class role: framing, speaker selection, dynamic rounds, and the voting tally. |
| `agent/roles/coordinator.py` | Compat dispatch: `TASK=debate` → `moderator.debate_step` (run_local launches the moderator directly). |
| `agent/roles/ballot.py` | Vote resolution/dedup: clusters near-duplicate free-text votes onto candidates; an unmatched write-in becomes an explicit abstain, recorded with its raw text. |
| `agent/roles/phase_util.py` | Shared phase-machine helpers (deadlines, transitions, stable tie-breaks) used by moderator + coordinator. |
| `souls/moderator.md`, `souls/debater-*.md` | Example personas. |
| `test_fixtures/debate-1/map.json` | Example topic. |
| `viz/debate.html` | Test stand (served at `/debate`). |
```
