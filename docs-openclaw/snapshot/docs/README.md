# Documentation — Multi-Agent Rover + Drones Stack

Full docs for the coordination stack. One engine, four task flows:
**city of drones / smart rover** (scouts negotiate the sector split in an open
chat, photograph the street, a rover drives A → B on the certified map),
**cargo survey / поиск груза** (город дронов v2: drones split a 5×5 cell field
in chat, sweep it with per-turn JSON action plans, cross-verify each find one
drone at a time, and the rover drives to the confirmed cargo — see
[Survey](survey.md)), **painting studio** (drones free-chat about what to
paint, vote on a deduplicated ballot, each paints its own colour into one
canvas — see [Painters](painters.md)) and the **debate engine** (a reusable
turn-based debate with a first-class moderator role — see
[Debate](debate-system.md)).
Runs locally or in Docker with no hardware, streams each agent's live thinking
to a dashboard, and scales out to real drones (incl. Raspberry Pi).

Source of truth for the design: [`../BUILD_BRIEF.md`](../BUILD_BRIEF.md) and the
protocol [`../agent-coordination-spec.md`](../agent-coordination-spec.md). These
docs explain the implementation and how to run/extend it.

## Read in order

1. [Overview](overview.md) — what it is, the scenarios, the big picture.
2. [Architecture](architecture.md) — components, the blackboard, data flow.
3. [Coordination protocol](protocol.md) — phases, messages, state, novelty gate.
4. [Agents, roles & the brain](agents.md) — coordinator/moderator/scout/rover/
   painter/debater, SOULs, LLM providers (incl. sverk/qwen35), structured output.
5. [Bridge (robot actions)](bridge.md) — the HTTP contract, mock + ROS2 stub.
6. [Visualizer / dashboard](visualizer.md) — the React studio UI, SSE, legacy
   dashboards (`/rover`, `/debate`), transcript modal.
7. [Running it](running.md) — every run mode and `make` target.
8. [Distributed mode](distributed.md) — hub, HttpBoard, discovery, multi-host.
9. [On-drone & PicoClaw](on-drone.md) — the adaptable drone image, native
   PicoClaw, models, Pi-5.
10. [Painters / studio](painters.md) — personalities, studio chat, collab canvas.
11. [Debate engine](debate-system.md) — moderator, rounds, voting-only tally.
12. [Survey / поиск груза](survey.md) — 5×5 cell sweep, per-turn JSON action
    plans, sequential find verification (quorum), rover dispatch.
12a. [Pause / замена аккумуляторов](pause.md) — посадка всех дронов, заморозка
    фаз, взлёт с ресинком реальной позиции.
12b. [Fleet / хендлеры и привязка](fleet.md) — несколько команд в одной сети,
    LED-регистрация дронов, постоянная память привязки, единая bridge-нода
    sverk-ros2 (city|painter).
13. [Configuration reference](configuration.md) — every env var.
14. [Security & sandboxing](security.md) — the §11 hardening.
15. [Extending](extending.md) — new scenarios, roles, drones, open TODOs.
16. [Troubleshooting](troubleshooting.md) — common issues and fixes.

Changelogs / handoffs: [HANDOFF.md](HANDOFF.md) (start here),
[audit-2026-07/](audit-2026-07/README.md) (findings) +
[IMPLEMENTED.md](audit-2026-07/IMPLEMENTED.md) (fixes, verification),
[HANDOFF-vllm-upgrade.md](HANDOFF-vllm-upgrade.md) (next big task).
Historical: [audit-report.md](audit-report.md),
[debugging-painters.md](debugging-painters.md).

## TL;DR

```bash
cp .env.example .env          # optional; default brain is the no-key mock
make local-studio             # flagship: studio chat → vote → collab canvas (:8080/studio)
                              #   жюри (VLM-оценка 1..100 + финальный вердикт): :8080/critic
make local                    # city of drones: chat-negotiated sectors → rover PASS
make local-survey             # поиск груза: 5×5 sweep + verification (:8080/survey)
make local-debate             # debate test stand (:8080/debate)
make demo / demo-studio       # the docker variants
make demo-distributed         # drones talk to a central hub over HTTP
make reset                    # wipe the blackboard volume for a fresh run
```

Open <http://localhost:8080>, watch the agents think, and click any agent to
read its full chain-of-thought.
