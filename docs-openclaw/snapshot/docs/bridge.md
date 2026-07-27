# Bridge (robot actions)

The bridge is a per-robot HTTP sidecar — the single seam between the agents and
the physical world. **Same contract for the dev mock and the real hardware
node**; only the implementation differs. The agent calls it via
`agent/bridge_client.py` (`BridgeClient`). The agent never imports ROS2.

## HTTP contract (§6)

```
POST /photograph      { sector }            -> { image_path, ts, sector }
POST /photograph      { cell:[x,y] }        -> { image_path, ts, cell }        (survey)
POST /detect_obstacle { image_path }        -> { obstacles:[{type,xy,conf}], coverage }
POST /analyze         { cell, close_look }  -> { cargo, confidence, label }    (survey)
POST /navigate        { from, to, grid }    -> streams {pose,progress}\n ... {status:"arrived"|"blocked"}
POST /move            { to:[x,y] }          -> { pose, ok }                    (painters/survey fly_to)
POST /land            {}                    -> { ok, landed:true, pose }       (пауза / замена АКБ)
POST /takeoff         {}                    -> { ok, landed:false, pose }      (поза после взлёта = реальная)
GET  /pose                                  -> { xy, heading }
GET  /healthz                               -> { ok: true }
```

While landed, the mock answers **409** to `/photograph`, `/move` and `/spray`
(§11 strict boundary — an agent that missed the pause sees an explicit error).
See [pause](pause.md) for the full pause/battery-swap flow.

`/navigate` returns **newline-delimited JSON** (one frame per line): a
`{pose,progress}` per grid step, then a final `{status}`. The rover client
(`BridgeClient.navigate`) iterates the stream and emits a `pose` event per frame
so the dashboard animates the path live.

## Mock implementation (`bridge/mock.py`)

Pure stdlib (`http.server`), one process per robot. Configured by env
(`AGENT_ID`, `SCENARIO`, `FIXTURES`, `BLACKBOARD`, `PORT`, `NAV_STEP_SEC`).

* **`photograph(sector)`** — copies the scenario fixture image
  (`test_fixtures/<scenario>/sector-<X>.png`) into `artifacts/` and returns its
  path. Validates `sector` against a strict regex (§11 boundary).
* **`detect_obstacle(image_path)`** — reads the hand-annotated
  `sector-<X>.labels.json` if present (ground-truth obstacles + coverage),
  otherwise returns a plausible fabricated result. Infers the sector from the
  image path.
* **`navigate(from, to, grid)`** — runs **A\*** over the occupancy grid
  (`grid[y][x]`, `1 = blocked`, 4-neighbour), then streams one pose frame per
  cell (sleeping `NAV_STEP_SEC` between) and a final `arrived` (or `blocked` if
  no path).
* **`pose`** — the current simulated pose (updated during navigate).
* **survey**: `photograph {cell}` synthesizes a top-down cell photo (stdlib PNG
  writer — green field / brown crate / grey debris); `analyze {cell,
  close_look}` answers from the fixture ground truth (`cargo`, `decoys` in
  `map.json`): the cargo cell always reads as cargo, a decoy reads as cargo
  from survey altitude but resolves to debris on a `close_look` (the
  verification pass). On hardware this endpoint is the seam for a real
  detector/VLM.

The A\* and the grid come from `map.json`, so the rover's path is consistent with
the obstacles the drones reported.

## Real implementation — hardware stub (`bridge/ros2/bridge_node.py`)

Wraps each endpoint in an `rclpy` node, keeping the **exact same HTTP contract**:

| endpoint | hardware mapping |
|---|---|
| `/photograph` | capture from the camera topic (`sensor_msgs/Image`) |
| `/detect_obstacle` | perception node (depth + lidar) → obstacle list |
| `/analyze` | cargo detector / VLM over the cell frame (survey) |
| `/navigate` | Nav2 `NavigateToPose` action client; feedback → pose stream |
| `/land`, `/takeoff` | takeoff/land services of the project's custom ROS2 build; after takeoff `/pose` MUST return the re-localized position |
| `/pose` | `/odom` or AMCL pose |

Today these raise `NotImplementedError` so the seam is visible and a hardware
bring-up has a concrete checklist. The rover's `navigate` is the one action with
real-world consequences — gate it behind the coordinator's `world.ready`
certification and add a hard **e-stop** before it touches a physical rover
([security](security.md)).

## Why a bridge (vs. tools inside the agent)

PicoClaw adds tools declaratively via MCP — no Go recompile (verified against
sipeed/picoclaw v0.2.9). The bridge pattern lets robot logic change without
rebuilding the agent, keeps the on-device install small (the heavy ROS2/camera
pipeline lives only in the bridge), and exposes **only** a short whitelist of
actions (`photograph`/`detect_obstacle`/`navigate`/`pose`, plus `move`/`spray`/
`canvas` for painters) — no generic shell/file tool — so a confused or
prompt-injected agent cannot escalate beyond moving a simulated robot or
returning an image. See
[on-drone](on-drone.md) for the PicoClaw MCP shim that proxies to this contract.
