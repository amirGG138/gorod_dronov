#!/usr/bin/env python3
"""Gazebo drone mirror — reflects the openclaw mapping swarm into Gazebo.

The 4 scout drones are planned/negotiated by the openclaw stack (LLM plans,
zone chat, coverage) and their cell positions land in the shared blackboard
(`state/world.json` -> positions). This host loop reads those positions and
teleports the matching mock quad models in the live Gazebo world (via
`docker exec sim_driver setmany`), so you watch the 4 drones sweep the aruco
field while the real logic runs unchanged. The rover is driven separately by
the rover agent through gazebo_rover_bridge.py; the scene itself is spawned by
that bridge on boot, so this mirror only MOVES drones.

Env: CONTAINER(sverk_sitl) BLACKBOARD(./blackboard) POLL_SEC(0.7)
     DRONES("drone-1,..,drone-4") + the coord env forwarded to sim_driver.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

CONTAINER = os.environ.get("CONTAINER", "sverk_sitl")
BLACKBOARD = Path(os.environ.get("BLACKBOARD", "./blackboard")).resolve()
POLL = float(os.environ.get("POLL_SEC", "0.7"))
DRONES = [d.strip() for d in os.environ.get(
    "DRONES", "drone-1,drone-2,drone-3,drone-4").split(",") if d.strip()]
DRIVER_DST = "/tmp/sim_driver.py"
_FWD = ("GZ_WORLD", "CELL_SIZE_X", "CELL_SIZE_Y", "FIELD_ORIGIN_X", "FIELD_ORIGIN_Y",
        "DRONE_Z", "ROVER_Z", "FIRE_Z", "ROVER_START", "FIRE_CELL", "DRONES")


def _exec_env() -> list[str]:
    out = []
    for k in _FWD:
        if os.environ.get(k) is not None:
            out += ["-e", f"{k}={os.environ[k]}"]
    return out


def _setmany(payload: dict) -> None:
    subprocess.run(
        ["docker", "exec", *_exec_env(), CONTAINER, "python3", DRIVER_DST,
         "setmany", json.dumps(payload)],
        capture_output=True, text=True, timeout=12)


def _read_positions() -> dict:
    wf = BLACKBOARD / "state" / "world.json"
    try:
        w = json.loads(wf.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    pos = w.get("positions") or {}
    return {d: pos[d] for d in DRONES
            if isinstance(pos.get(d), list) and len(pos[d]) == 2}


def main():
    print(f"[gazebo-mirror] mirroring {DRONES} from {BLACKBOARD} -> {CONTAINER} "
          f"every {POLL}s", flush=True)
    last: dict = {}
    while True:
        cur = _read_positions()
        moved = {d: c for d, c in cur.items() if last.get(d) != c}
        if moved:
            try:
                _setmany(moved)
                last.update(moved)
                print(f"[gazebo-mirror] {moved}", flush=True)
            except subprocess.SubprocessError as exc:
                print(f"[gazebo-mirror] setmany failed: {exc}", flush=True)
        time.sleep(POLL)


if __name__ == "__main__":
    main()
