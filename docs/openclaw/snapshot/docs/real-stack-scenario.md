# City-drones on the REAL stack (PX4 SITL + gemma4-VLM)

The city-drones survey run against **real PX4 SITL drones** (not the mock bridge):
4 drones sit on the aruco field, the LLMs negotiate zones, the drones take off
and map every cell, a real **gemma4-vlm** checks each camera frame for fire, the
rover drives to the confirmed fire cell-by-cell, and the drones land back on
their start cells. An independent **cv2-aruco reality-check** validates where each
drone really is (the ROS2 aruco→EKF flight path is unstable, so we use aruco only
as extra positioning info, not for control).

```
stand on cells → LLM chat (zones) → takeoff → sweep+VLM → fire found+verified
              → rover drives to fire → drones land home
```

## What you need

| | |
|---|---|
| **sverk-ros2 repo** (`~/dev/soslo/sverh/sverk-ros2`) | provides the `sverk_sitl` Docker image = PX4-Autopilot (fork) + Gazebo Harmonic + the obrik x500 model + the aruco packages (`aruco_det_loc`, `aruco_map`) + `markers.txt`. **Required** — the drones, world, camera model and marker map all come from here. |
| **`sverk_sitl` container running** | `docker ps` shows it. Holds the gz worlds (`obrik_aruco6x6.sdf`), the x500_obrik_base model, MicroXRCEAgent, and (host-mounted) `/home/sverk`. |
| **openclaw-stack** (this repo) | the agents (`picoclaw-agent` image), the bridges, the survey logic, the compose files. |
| **`.env`** | `MODEL_PROVIDER=sverk`, `MODEL=gemma4-vlm`, `SVERK_API_KEY=…`, `SVERK_API_BASE=https://ai.sverk.tech/v1` (gemma4-vlm = gemma3-27B, both LLM and VLM). |
| **network** | `sverk_sitl` joined to `openclaw-stack_mesh` with alias **`fleet`** (`docker network connect --alias fleet openclaw-stack_mesh sverk_sitl`) so the agents reach the bridges at `fleet:9001..9005`. |
| **opencv (reality-check)** | isolated `numpy<2 + opencv-python-headless` in `/tmp/cvlib` inside the container: `pip install --target=/tmp/cvlib "numpy<2" opencv-python-headless`. |

## Run it (one command)

```bash
scripts/full_scenario_single.sh
```

Does the whole thing from a **clean restart**: tears down the old run, launches a
fresh single gz world with 4 PX4 drones spawned on field corners
(`[0,0],[5,0],[0,5],[4,4]`; `[4,4]` sits next to the fire so verification is a
short hop — do NOT spawn on the rover cell `[0,0]`), spawns the fire + a top-down
camera, starts the aruco-nav bridges (drones **landed**, waiting), resets the
blackboard, and launches the survey agents. ~4 min to set up, then the run.

Land the drones home at the end:
```bash
for n in 1 2 3 4; do docker exec sverk_sitl curl -s -XPOST http://127.0.0.1:$((9000+n))/land -d '{"home":true}'; done
```

## Run it on the REAL sverk offboard path (`sverk_interfaces`)

Flies every drone through the sverk `offboard_control` node instead of MAVLink.
Uses the **partitioned** topology (one gz world per drone → stable EKF), which is
also the "4 isolated full stacks" layout.

```bash
# inside sverk_sitl: partitioned px4 fleet + one offboard_control per drone
docker exec sverk_sitl bash /tmp/sitl_fleet.sh 4        # (auto_release:=false hold)
# sverk-backed bridges (FLIGHT_BACKEND=sverk) + rover, on fleet:9001..9005
docker exec sverk_sitl bash /tmp/sverk_bridges.sh 4
# then the agents (mesh/alias `fleet` as usual)
docker compose -f docker-compose.yml -f docker-compose.real.yml up \
    coordinator drone-1 drone-2 drone-3 drone-4 rover viz
```

**Bridge-per-container** ("4 full ROS2 images"): `docker-compose.sverk.yml` runs
each drone's bridge in its own container off the `sverk/ros2:sitl` image, sharing
`sverk_sitl`'s network + IPC. It needs `sverk_sitl` started with `ipc: shareable`
(one line in docker-sitl's compose) so FastDDS/gz transport is visible across
containers; see the header of `docker-compose.sverk.yml`.

## Reality gate (survey trusts only what the camera confirms)

The survey logic (`agent/roles/survey_scout.py`) gates every **positive** claim on
the cv2-aruco reality-check: a drone raises a `FOUND` (or votes cargo/fire = yes on
verify) **only** when `GET /pose` confirms it is really over the claimed cell
(`on_field`, `aruco_cell` matches, `reality_ok` not false). If the camera
contradicts it (blown off-field, aruco mismatch), the find is withheld (a
`reality_reject` event + a note to the coordinator) and the drone re-flies to
re-shoot. Fail-open: the mock bridge returns no reality fields, so mock runs are
unaffected.

## Watch it

* **gz window** — the single world with all 4 drones + fire + rover (needs the
  container's `DISPLAY=:1`; software-rendered, no GPU).
* **Top-down camera** — frames every 4 s in the container at `/tmp/fleet/overview/latest.png`
  (`docker cp sverk_sitl:/tmp/fleet/overview/latest.png .`).
* **Dashboard** — `http://localhost:8080/survey` (coverage grid, chat, fire, rover).

## Architecture (why it looks the way it does)

* **One drone per gz partition… or one shared world.** PX4's gz lockstep only
  cleanly supports one vehicle per world, so the *reliable* topology is 4
  partitions (`scripts/sitl_fleet.sh`, 4 gz windows). The single-world run
  (`full_scenario_single.sh`, 1 window) works too but needs the aruco
  reality-check to catch the extra drift.
* **Bridge = the seam.** `bridge/real_bridge.py` implements the same HTTP contract
  as `bridge/mock.py` (`/move /photograph /analyze /navigate /pose /land …`), so
  the unchanged survey agents drive real drones. The flight primitive is pluggable
  via `FLIGHT_BACKEND` (same `Drone` interface either way):
  * `sverk` — the **real sverk offboard stack via `sverk_interfaces`**
    (`bridge/sverk_flight.py`): every hop is a `/px4_i/navigate` (+ `/px4_i/land`,
    `/px4_i/get_telemetry`) service call → `offboard_control` → uXRCE-DDS → PX4,
    exactly as on hardware. **Requires the partitioned topology** (one gz world per
    drone): a shared multi-vehicle world gives PX4 "Yaw estimate error"
    (`heading_good_for_control=false`) and OFFBOARD position control will not hold.
    Launch offboard with `auto_release:=false` (done by `sitl_fleet.sh`) so the
    setpoint stream holds position between hops.
  * `mavlink` (default) — direct PX4 OFFBOARD over MAVLink (`bridge/fleet_flight.py`);
    the fallback that flies in a shared world too (yaw-independent setpoints).
* **Real VLM fire detection.** `analyze` snaps the drone camera and asks
  gemma4-vlm `FIRE=yes/no` + position in frame; the map is only a fallback if the
  VLM is unreachable. (A confirmed cell ≠ the map's fire cell is proof the VLM,
  not the map, decided.)
* **cv2-aruco reality-check.** `bridge/aruco_cell.py` (persistent service) reports
  the marker under the camera → the drone's REAL cell. `GET /pose` returns
  `aruco_cell`, `on_field`, `reality_ok` (true only when the camera confirms the
  reported cell). Catches EKF drift, off-field, and kill-switch/`set_cell` misplacement.

## Controls (pause / battery-swap / arbitrary start)

* **Pause / resume** the whole mission (built-in, see [pause.md](pause.md)):
  dashboard `⏸/▶`, `make pause`/`make resume`, or `POST /pause` with header
  `x-pause: 1`, body `{"paused": true|false}`. On resume every drone re-syncs its
  real pose (`GET /pose`) and the phase deadline shifts — so it survives a
  kill-switch (drone landed anywhere).
* **Battery swap per drone:** bridge `POST /pause` (land+freeze) then `/takeoff`
  (resume).
* **Arbitrary start / kill-switch recovery:** put the drone on any cell, then
  `POST /set_cell {"cell":[x,y]}` — the bridge recalibrates so the scenario
  continues from there (the aruco reality-check confirms it really is there).
* **Land home:** `POST /land {"home":true}` flies the drone back to its start cell
  and lands.

## Fallback (mock, no PX4)

Remove the overlay and the original mock bridges drive everything (blackboard
stack intact): `docker compose -f docker-compose.yml up` (see [running.md](running.md)).
