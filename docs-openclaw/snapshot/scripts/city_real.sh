#!/usr/bin/env bash
# One-command REAL city_missions run: the coordinator plans fire + delivery and the
# ROVER agent drives the compiled plan on the real gz rover cube (cell-by-cell, LED
# beacon, 3s/5s dwells, energy). Monitor drones post observations; ВУП does the
# person search. Not mock — real robot movement in Gazebo + the dashboard.
#
#   scripts/city_real.sh
#
# Needs the sverk_sitl container up with a live gz world (partition d0), joined to
# openclaw-stack_mesh as `fleet` (docker network connect --alias fleet openclaw-stack_mesh sverk_sitl).
set +e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; CT=sverk_sitl
say(){ echo -e "\n=== $* ==="; }

say "1/5  stage rover bridge + deps into $CT"
for f in rover_bridge.py mock.py; do docker cp "$ROOT/bridge/$f" "$CT:/tmp/$f"; done
docker cp "$ROOT/bridge/gazebo/sim_driver.py" "$CT:/tmp/sim_driver.py"

say "2/5  (re)launch the real gz rover bridge on fleet:9005 (partition d0)"
docker exec "$CT" bash -lc 'for p in $(pgrep -f "rover_""bridge.py"); do kill -9 $p 2>/dev/null; done'
docker exec -d "$CT" bash -lc '
  mkdir -p /tmp/fleet
  export GZ_SIM_RESOURCE_PATH=/home/sverk/PX4-Autopilot/Tools/simulation/gz/models:/home/sverk/PX4-Autopilot/Tools/simulation/gz/worlds
  GZ_PARTITION=d0 GZ_WORLD=domiki6x6 PORT=9005 CELL_SIZE=0.6 FIELD_ORIGIN=-1.5 \
    FIRE_CELL=5,5 ROVER_START=3,3 ROVER_Z=0.12 NAV_STEP_SEC=0.15 \
    python3 /tmp/rover_bridge.py > /tmp/fleet/city_rover.log 2>&1'
sleep 5
docker exec "$CT" bash -lc 'curl -s --max-time 5 http://localhost:9005/healthz && echo " <- rover bridge up"'

say "3/5  build agent image + reset blackboard"
docker compose -f "$ROOT/docker-compose.yml" build coordinator >/dev/null 2>&1
docker run --rm -v openclaw-stack_blackboard:/bb alpine sh -lc 'rm -rf /bb/state /bb/messages /bb/events.jsonl /bb/.seq 2>/dev/null' >/dev/null 2>&1

say "4/5  launch city_missions agents + dashboard"
docker compose -f "$ROOT/docker-compose.yml" -f "$ROOT/docker-compose.city.yml" up -d --force-recreate \
  coordinator drone-1 drone-2 drone-3 drone-4 rover safety-1 viz 2>&1 | tail -4

say "5/5  watch the run (up to ~2 min)"
for t in $(seq 1 24); do
  ph=$(docker run --rm -v openclaw-stack_blackboard:/bb alpine sh -lc 'grep -oE "\"phase\":\"[A-Z]+\"" /bb/events.jsonl 2>/dev/null | tail -1')
  echo "  t=$((t*5))s $ph"
  echo "$ph" | grep -q DONE && break
  sleep 5
done
echo ""
echo "dashboard: http://localhost:8095/  |  rover cube in gz partition d0"
echo "evidence:  docker run --rm -v openclaw-stack_blackboard:/bb python:3.12-slim python3 -c \"import json;[print(json.loads(l).get('action_id'),json.loads(l).get('evidence')) for l in open('/bb/events.jsonl') if '\\\"ACTION_COMPLETED\\\"' in l]\""
