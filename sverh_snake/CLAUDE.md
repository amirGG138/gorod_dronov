# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workspace layout

This directory is a loose workspace, not a single repo (`git rev-parse` fails here). It contains:

- **`Archipelago2026/`** — the actual codebase: a single-file autonomous-flight program
  (`fly_snake.py`) for the drone competition «Взаимное позиционирование в рое: Змейка»
  (Moscow, 2026). This has its own git repo
  (`git -C Archipelago2026 ...`), remote `github.com/Bl1tz2200/Archipelago2026`. All commands below
  assume this directory as cwd.
- **`docs-sverk/`** — a local mirror of the `edu.sverk.tech` documentation (ROS 2/Obric platform,
  microdrone whoop platform). Reference material only, not code to build/lint/test.
- `reglament-zmeyka (1).md`, `butterfly.png` — competition rules and reference material, read-only.

## Platform

Target hardware is the **«Сверх.Исследования» (Обрик)** quadcopter running ROS 2 inside a
`sverk_ros2` container, controlled via the `sverk_interfaces` library (`drone.control`,
`drone.image`). `sverk_interfaces` and ROS 2 exist only on the drone — off-drone the program can
only be syntax-checked or exercised with a stubbed import.

Access to the physical drone: `ssh sverk@<drone-ip>` (port 22, password `sverk`) drops straight
into the `sverk_ros2` container. Browser VS Code is also available at the drone's IP.

## Commands

Run from `Archipelago2026/`. The whole program is one file, `fly_snake.py` — no launcher, no
package layout, no config files:

```bash
python3 fly_snake.py        # takeoff → read markers → fly ROUTE → land
python3 -m py_compile fly_snake.py    # syntax check off-drone
```

`sverk_interfaces` and ROS 2 are only importable on the drone. Off-drone the file can still be
exercised by stubbing the import (`sys.modules["sverk_interfaces"] = ...`) and feeding synthetic
ArUco frames to `markers()` / `apples()` / `goto()` with a fake drone object that records
`navigate` calls — that is the only test path, there is no test suite.

Dependencies: `pip3 install -r requirements.txt` (opencv-python, numpy).

If `sverk_interfaces` is not found on the drone, the shell lacks the ROS 2 environment:
`source /opt/ros/*/setup.bash && source ~/sverk_ws/install/setup.bash`.

## Architecture

One file, ~250 lines, five sections: settings → camera → vision → field map → flight.
Deliberately flat and dependency-free — this drone is experimental and everything must be
debuggable on-site. Do not reintroduce packages, YAML configs, CLI flags, or a test suite;
do not add functionality beyond the task.

**Flight commands are limited to the ones in the platform's basic flight example**:
`navigate(..., frame_id="body")`, `time.sleep`, `land`, `close`. No `set_position` /
offboard setpoints (the drone does not fly on them), no `get_telemetry` at all.

**Navigation is by markers only** — never by coordinates and never by dead reckoning. The
target of a hop is a marker; arrival means that marker sits at the centre of the frame.
Pixels convert to metres via the marker's own side length (`MARKER_M / side_px`), so neither
altitude nor camera calibration is needed. When the target marker is not in frame, direction
comes from the field map (`ID = row*7 + col`, `FLIP_X` for the mirrored column order) measured
from whichever marker *is* visible — the reference is always a real marker, not an accumulated
position estimate.

| Function | Responsibility |
|---|---|
| `patch_yuv(drone)` | camera publishes `yuv422_yuy2`; stock `to_cv2` crashes on it |
| `look(drone)` | one frame via `take_picture` |
| `markers(img)` | ArUco → `{id: (x, y, side_px)}`, with a shim for OpenCV 4.5/4.6 vs 4.7+ |
| `apples(img)` | HSV masks for three colours + area/roundness filter → list of colour names |
| `report(...)` | the required in-flight console line: markers around + apples seen |
| `node(mid)` | `ID → (col, row)` — the entire field map |
| `fly(drone, forward, left)` | one `navigate(frame_id="body")` + a sleep sized to the distance |
| `goto(drone, target)` | the whole navigation loop (see above); skips the node after `TRIES` |
| `scan(drone)` | post-takeoff marker read: which marker is underneath, what else is visible |

Settings live in one block at the top of the file (`ROUTE`, `ALT`, `SPEED`, `STEP_M`,
`MARKER_M`, `FLIP_X`, `TOL`, `TRIES`, HSV thresholds). On-site adjustments go there, never
into the code below it.

## Notes for this workspace

- `Archipelago2026` is its own git repo nested inside this workspace directory; run git commands
  with `-C Archipelago2026` or `cd` into it first — don't assume the workspace root is versioned.
- Competition rules referenced throughout the code/docs (e.g. "п. 2.1.2", "Приложение 3") are in
  `reglament-zmeyka (1).md` at the workspace root.
