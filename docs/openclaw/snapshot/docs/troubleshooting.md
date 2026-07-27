# Troubleshooting

## The run hangs and never reaches DONE

* **Stuck in PROPOSE/CONVERGE** — the coordinator is waiting for proposals/votes.
  Check each drone reached its bridge (`bridge healthz`) and is online. Deadlines
  (25 s) should force-advance; if not, check the coordinator log.
* **Stuck in REPORT** — drones never reported `done`, so `world.ready` is never
  set. Usually the drones can't write progress. In distributed mode this means
  the drones can't reach the hub (see below). Inspect `state/world.json`:
  `gaps` non-empty + `covered: []` ⇒ no progress landed.
* **Stuck because a verdict isn't PASS** — a sector's `coverage` is below
  `COVERAGE_MIN` (0.9) or an obstacle has no `xy`. Check the scenario
  `labels.json`.

## Distributed: drones don't appear / board stays empty

Symptom: drones log "registered with hub" but `/agents` is empty and progress
never lands.

* **Confirm the drone can reach the hub:**
  ```bash
  docker compose -f docker-compose.distributed.yml exec -T drone-1 \
    python -c "import urllib.request;print(urllib.request.urlopen('http://hub:8080/healthz',timeout=5).read())"
  ```
* **Check the hub is in `HUB_MODE`** — `GET /healthz` should return `"hub": true`.
  In read-only dashboard mode POSTs return 403.
* **Auth** — if `HUB_TOKEN` is set on the hub, every drone must send the same
  token. A mismatch → 401 (silently swallowed by the best-effort writes).
* **Reads default silently** — `HttpBoard` reads return defaults on error so a
  drone never crashes; that can mask an unreachable hub. If a drone seems idle,
  test the endpoint directly as above.

> Lesson learned: an unimported `urllib` in `bb.py` once made every `HttpBoard`
> call raise `NameError`, swallowed by the best-effort wrappers — drones silently
> did nothing and the run hung in REPORT. If HTTP-board behavior looks "dead",
> instrument one call without the try/except to see the real exception.

## Real model (sverk/qwen35) errors

* **400 `Invalid model name passed in model=qwen-35`** — the gateway id is
  `qwen35` (no dash). Set `MODEL=qwen35` in `.env`.
* **500 `InternalServerError ... Connection error` / `Model Group=qwen35`** — the
  upstream model is down/cold. Retry; if persistent, the model host needs a
  restart.
* **403 `Country, region, or territory not supported`** (e.g. `gpt-4o-mini` via a
  proxy) — that backend isn't available from your egress; use `qwen35`.
* **`gemma4` 500 `requires more system memory`** — the model host is out of RAM
  for that model; pick a smaller one.
* **Endpoint unreachable (connect timeout)** — `ai.sverk.tech` is firewalled /
  IP-allowlisted / behind a VPN; the host running the agents must be able to
  reach it. Containers egress via the host's network, so the host's VPN route
  must cover it. Verify from the host first.
* **`(llm error: ...)` appears in a thought** — the brain call failed and fell
  back to the templated reasoning; the protocol still proceeds. Check the key,
  base URL, model id, and egress.

## Thoughts show but don't "type out" smoothly

The dashboard has a client-side typewriter, so any chunking animates. If a thought
appears all at once, the upstream stream arrived in one chunk (common through
NAT/VPN). The full text is still captured and saved. Increase `MODEL_MAX_TOKENS`
for longer visible reasoning.

## `make demo` viz crashes on a read-only volume

The dashboard only calls `ensure_layout()` (which `mkdir`s) in `HUB_MODE`; in
read-only mode it just reads. If you customized the viz, keep writes behind the
`HUB_MODE` guard.

## Port 8080 already in use

Another service holds the port. Stop it, or change the published port in the
compose file (`ports: ["8081:8080"]`) and open `:8081`.

## Inspect a stuck run

```bash
make verdict                                   # phase + verdict
docker compose logs coordinator                # phase-machine decisions
docker compose logs drone-1                    # one drone
docker compose exec -T viz python -c \
  "import json;print(json.load(open('/blackboard/state/world.json')))"
curl -s localhost:8080/agents                  # who's connected + phase
curl -s localhost:8080/agents/drone-1/transcript  # full thinking of one drone
```

## Clean slate

```bash
make clean                # base: stop + wipe the blackboard volume
make down-distributed     # distributed stack
docker compose -f docker-compose.distributed.yml down -v
```

## No-Docker local mode issues

`make local` needs `PYTHONPATH=agent` (the script sets it). Logs are in
`.local-logs/`. `make stop-local` kills the processes; a stray `pgrep` match is
usually the subshell, not a real process.
