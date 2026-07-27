# Running it

## Prerequisites

* Docker + Docker Compose (the only requirement for the demos).
* Optional: an API key for a real brain (otherwise the no-key `mock` runs).
* Python 3.12 only if you want the no-Docker local mode.

## Quick start

```bash
cp .env.example .env      # optional; without it the brain defaults to mock
make demo                 # build, run the sample scenario unattended, wait for PASS
# open http://localhost:8080
make down                 # stop  (make clean = stop + wipe the blackboard volume)
```

`make demo` reaches `phase=DONE`, `result="PASS: safe passage"`, rover `arrived`,
unattended. No API key required.

## Run modes (`make` targets)

| target | what it does |
|---|---|
| `make demo` | Single-host, shared-volume demo. Build + up + wait for PASS. |
| `make demo-sverk` | Same, with the real `sverk/qwen35` brain (needs `.env` + egress). |
| `make demo-painters` | Painting demo (curated mode) in Docker. |
| `make demo-painters-sverk` | Painting demo with the real `sverk` brain. |
| `make demo-studio` | The flagship **studio** painting demo (`STUDIO_CHAT=1`, collab canvas). |
| `make demo-survey` | **Поиск груза**: 5×5 sweep, JSON-планы ходов, верификация по очереди, ровер (`:8080/survey`). |
| `make up-painters` / `make down-painters` | Bring the painters stack up (detached) / stop it. |
| `make demo-distributed` | Single-host demo of the **distributed** wiring (drones → hub over HTTP). |
| `make up` / `make down` | Bring the base stack up (detached) / stop it. |
| `make down-distributed` | Stop the distributed stack. |
| `make logs` | Follow logs. |
| `make verdict` | Print the current phase + verdict from the running stack. |
| `make build` | Build images only. |
| `make web` | Build the React dashboard (`frontend/` → `frontend/dist`). |
| `make reset` | Wipe the blackboard for a fresh run. |
| `make clean` | Stop + delete the blackboard volume (fresh next run). |
| `make hub` | **Multi-host**: bring up the orchestrator (hub + coordinator). |
| `make drone AGENT_ID=.. ROLE=.. HUB_URL=..` | **Multi-host**: one robot node. |
| `make local` / `make stop-local` | Run without Docker (host processes, fast iteration). |
| `make local-painters` | No-Docker painting run (curated mode). |
| `make local-collab` | No-Docker painting run in `PAINT_MODE=collab`. |
| `make local-studio` | No-Docker **studio** run (`STUDIO_CHAT=1` + collab canvas). |
| `make local-debate` | No-Docker debate run (moderator + debaters). |
| `make local-survey` | No-Docker **поиск груза** run (см. [survey](survey.md)). |
| `make pause` / `make resume` | ⏸ Пауза всех сценариев (замена АКБ): дроны садятся / взлетают + ресинк позиции. См. [pause](pause.md). |
| `make pause-docker` / `make resume-docker` | То же для docker-демо (viz там read-only — пишем через координатор). |

See [distributed](distributed.md) for `hub` / `drone` / `demo-distributed`.

## Using a real brain

Edit `.env`:

```dotenv
MODEL_PROVIDER=sverk      # mock | sverk | anthropic | openai | ollama
MODEL=qwen35              # provider-specific id; blank = provider default
SVERK_API_KEY=sk-...      # the key for the chosen provider
SVERK_API_BASE=https://ai.sverk.tech/v1
MODEL_MAX_TOKENS=200      # how much reasoning to stream per step
```

Then `make demo-sverk`. The protocol still runs deterministically; the model
narrates each step, streamed live to the dashboard. A real provider needs
outbound network, so `make demo-sverk` adds `docker-compose.egress.yml` (attaches
agents to a host-reachable `edge` network; the base `mesh` is internal/no-egress
for safety — see [security](security.md)).

Full env reference: [configuration](configuration.md).

## Compose files

| file | purpose |
|---|---|
| `docker-compose.yml` | single-host shared-volume demo |
| `docker-compose.egress.yml` | overlay: give agents egress for a real model |
| `docker-compose.distributed.yml` | single-host demo of the distributed wiring |
| `docker-compose.hub.yml` | multi-host: the orchestrator |
| `docker-compose.drone.yml` | multi-host: one robot node |

## Run without Docker (fast iteration)

```bash
make local                # bridges + agents as host processes (reads .env)
cat blackboard/state/decision.json
make stop-local
```

`scripts/run_local.sh` starts 5 bridges + coordinator + 4 drones + rover as local
processes pointing at `./blackboard`, sourcing `.env` for the brain config. Logs
land in `.local-logs/`. It also has **painting** and **debate** branches
(driven by `TASK`, used by `make local-painters`/`local-collab`/`local-studio`
and `make local-debate` — the debate branch launches the moderator as its own
agent). A **double-start guard** refuses to launch while a previous stack's
pids are still alive; `scripts/stop_local.sh` kills only this checkout's
processes and also stops `viz/server.py`.

## A new scenario

```bash
# add test_fixtures/scenario-2/ (map.json + sector-*.png + sector-*.labels.json)
SCENARIO=scenario-2 make demo
```

See [extending](extending.md).
