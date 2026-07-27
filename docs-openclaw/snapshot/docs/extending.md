# Extending

## Add a scenario

```
test_fixtures/scenario-2/
  map.json                 # grid + start + goal + sector boxes
  sector-A.png ...         # one image per sector
  sector-A.labels.json ... # ground-truth obstacles + coverage (optional)
```

`map.json`:

```jsonc
{
  "name": "scenario-2",
  "grid": [[0,0,1,...], ...],   // grid[y][x], 1 = blocked
  "start": [0,0], "goal": [9,9],
  "sectors": {
    "A": { "image": "sector-A.png", "bounds": [x0,x1,y0,y1], "expected_coverage": 0.95 },
    ...
  }
}
```

`sector-X.labels.json`: `{ "sector": "X", "coverage": 0.96, "obstacles": [{"type":"...","xy":[x,y],"conf":0.9}] }`.

Run with `SCENARIO=scenario-2 make demo`. Generate placeholder PNGs with stdlib
(`zlib`) if you don't have real images — see how `scenario-1` ships.

For a clean PASS, make sure each sector's `coverage ≥ COVERAGE_MIN` (0.9) and
every obstacle has an `xy`. To exercise the **reopen** path, drop one sector's
coverage below the threshold — the coordinator reopens EXECUTE for the gap.

## Add a role

1. Create `agent/roles/<role>.py` with `def step(ctx): -> {thought, messages, idle}`.
2. Register it in `agent/roles/__init__.py` (`_ROLES`).
3. Give it a SOUL in `souls/` and a `ROLE=<role>` service.

`ctx` exposes: `bb` (board), `brain`, `soul`, `agent_id`, `role`, `phase`,
`messages`, `assignments`, `progress`, `world`, `bridge`, `emit`, `config`,
`scenario_map`. Use the helpers in `roles/__init__.py` (`has_posted`,
`messages_of`, `make_msg`) and keep `step()` **idempotent against the board**.

## Add a bridge action

1. Add the endpoint to `bridge/mock.py` (and the real `bridge/ros2/bridge_node.py`).
2. Add a method to `agent/bridge_client.py`.
3. Add the tool to `drone/picoclaw_bridge_mcp.py` (and the role that calls it).

Keep the contract identical between mock and hardware, and validate arguments at
the boundary ([security](security.md)).

## Add a drone (distributed)

Bring up a node — it registers and the coordinator picks it up:

```bash
make drone AGENT_ID=drone-5 ROLE=scout HUB_URL=http://<orch>:8080 HUB_TOKEN=<same>
```

Give it a SOUL (baked into the agent image, or mount one) so it reasons in
character. See [distributed](distributed.md) and [on-drone](on-drone.md).

## Swap the brain / model

Set `MODEL_PROVIDER` + `MODEL` in `.env` ([configuration](configuration.md)). To
add a provider, add a branch in `agent/brain.py` (`think` / `think_stream`) —
reuse `_chat_completions` / `_stream_chat` if it's OpenAI-compatible.

## Open TODOs

* **Dynamic N-way map decomposition.** Today the scenario has 4 sectors; extra
  scouts beyond that get redundant assignments (round-robin over the sectors).
  Generalize the coordinator's EXECUTE assignment + the scenario sector model to
  split the grid into `N = number of registered scouts` sectors.
* **Coordinator over HTTP.** The coordinator runs co-located with the hub
  (FileBoard). For a fully remote coordinator, use the hub's `POST /state/<name>`
  (already implemented) from an `HttpBoard`-style writer.
* **Native PicoClaw integration.** The MCP shim is a skeleton; wire it to a
  pinned PicoClaw build and pipe its streaming reasoning to the hub `/events`.
* **WebSocket transport** for the dashboard (currently SSE) if you need
  bidirectional control from the browser.
* **Painting scenario (worked example B).** The protocol supports a decentralized
  (`coordinator: none`) quorum variant and a `score` convergence for creative
  tasks; not wired into a runnable scenario yet.
