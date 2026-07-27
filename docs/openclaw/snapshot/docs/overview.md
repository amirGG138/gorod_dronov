# Overview

*(refreshed 2026-07-07 — the previous rewrite of this page was lost to the NTFS
incident, see [audit-2026-07-07](audit-2026-07-07.md).)*

## The tasks

One coordination engine (blackboard + phase machine + open CHAT), four flows:

> **safe_passage** — 4 drones photograph a model street completely enough to
> certify safe passage; a rover then drives A → B on the resulting map.
>
> **survey (поиск груза)** — 4 drones split a 5×5 cell field in chat, sweep it
> with per-turn JSON action plans (fly → wait → photo+analyze), cross-verify
> every find one drone at a time, and send the rover to the confirmed cargo.
> See [survey](survey.md).
>
> **painting** — 4 painter personas free-chat, vote on a clustered ballot and
> paint one shared canvas. See [painters](painters.md).
>
> **debate** — a reusable moderated debate that ends in a vote.
> See [debate-system](debate-system.md).

Everything runs **end-to-end with no hardware**, using test images, so you can
watch the agents think and verify the full flow. Hardware (Pi-5 drones + ROS2)
is the later target; the seam between simulation and hardware is kept clean
(see [bridge](bridge.md) and [on-drone](on-drone.md)).

## Why this is non-trivial

A shared folder alone does **not** produce collaboration — agents generate in
parallel and talk past each other. Coordination has to be designed explicitly:
decomposition, information routing, and convergence. The protocol encodes that as
a **phase state machine** plus a **novelty gate** that suppresses redundant
chatter. See [protocol](protocol.md).

## The flow at a glance

Default (negotiation happens in an open CHAT; the silent PROPOSE→CONVERGE flow
remains available via `SCOUT_CHAT=0`):

```
INIT ─▶ CHAT ─▶ EXECUTE ─▶ REPORT ─▶ DONE
           ▲                   │
           └───── reopen ◀─────┘  (if coverage gaps remain)
```

1. **PROPOSE** — each scout drone proposes how to split the street and claims a
   sector matching its priorities.
2. **CONVERGE** — drones vote; the coordinator writes the agreed decision.
3. **EXECUTE** — the coordinator assigns sectors; each drone flies, photographs
   (`bridge.photograph`), and detects obstacles (`bridge.detect_obstacle`). The
   rover is assigned but **gated**: it waits for `world.ready`.
4. **REPORT** — the coordinator merges drone reports into `world.json`. When
   there are no coverage gaps and every obstacle is localized, it certifies
   `PASS: safe passage` and sets `world.ready = true`.
5. The rover unblocks, plans a path over the occupancy grid (`bridge.navigate`,
   A\*), drives A → B around the obstacle, and reports `arrived` → **DONE**.

## What ships

* A reusable **agent loop** (one binary, behavior switches on role + phase).
* A pluggable **brain**: a deterministic mock (no API key) or a real LLM
  (`sverk/qwen35`, Anthropic, OpenAI, Ollama) that narrates each step.
* A **mock bridge** serving fixture images + A\* navigation; a **ROS2 stub** for
  hardware.
* A live **dashboard** that streams each agent's chain-of-thought and animates
  the rover routing around the obstacle; click an agent for its full log.
* **Single-host** and **distributed (multi-drone)** deployment, plus a
  **PicoClaw-on-drone** skeleton.

## The sample scenario

`test_fixtures/scenario-1/` ships working: a 10×10 occupancy grid with a wall on
column `x=5` (`y=2..9`). The direct A→B diagonal is blocked, so the rover must
route through the gap at the top — the demo shows it routing around the obstacle.
Acceptance: `make demo` reaches `phase=DONE`, `result="PASS"`, rover `arrived`,
unattended.

See [architecture](architecture.md) next.
