#!/usr/bin/env bash
# Full "city drones" scenario, from a clean restart to the finished survey, with
# the REAL stack: 4 PX4 SITL drones (each in its own gz partition), real cameras,
# real gemma4-vlm fire detection, chat-negotiated zones, and a real rover cube.
#
#   scripts/full_scenario.sh
#
# Watch it two ways while it runs:
#   * gz GUI window on partition d0 (drone-1 + fire, brought up here)
#   * web dashboard  http://localhost:8080  (all 4 drones on the survey grid)
#
# Needs: the sverk_sitl container running + built openclaw images + .env with
# SVERK_API_KEY/BASE + sverk_sitl joined to openclaw-stack_mesh as `fleet`.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CT=sverk_sitl
source "$ROOT/.env" 2>/dev/null || true
KEY="${SVERK_API_KEY:-}"; BASE="${SVERK_API_BASE:-https://ai.sverk.tech/v1}"

say(){ echo -e "\n=== $* ==="; }

say "1/7  tearing down old run"
docker compose -f "$ROOT/docker-compose.yml" -f "$ROOT/docker-compose.real.yml" \
  stop coordinator drone-1 drone-2 drone-3 drone-4 rover >/dev/null 2>&1 || true
docker exec "$CT" bash -lc '
  for pat in "sitl_default/bin/px""4" "real_""bridge.py" "rover_""bridge.py" "offboard_""control" "MicroXRCE""Agent" "g""z sim"; do
    for p in $(pgrep -f "$pat"); do kill -9 $p 2>/dev/null; done
  done; echo cleaned'
docker run --rm -v openclaw-stack_blackboard:/bb alpine sh -c 'rm -rf /bb/* /bb/.seq 2>/dev/null' || true
sleep 3

say "2/7  copying scripts into the container"
for f in fleet_flight.py real_bridge.py mock.py rover_bridge.py; do docker cp "$ROOT/bridge/$f" "$CT:/tmp/$f"; done
docker cp "$ROOT/bridge/gazebo/sim_driver.py" "$CT:/tmp/sim_driver.py"
docker cp "$ROOT/scripts/sitl_fleet.sh" "$CT:/tmp/sitl_fleet.sh"
docker cp "$ROOT/scripts/real_bridges.sh" "$CT:/tmp/real_bridges.sh"
docker exec "$CT" mkdir -p /tmp/test_fixtures/survey-city
docker cp "$ROOT/test_fixtures/survey-city/map.json" "$CT:/tmp/test_fixtures/survey-city/map.json"

say "3/7  launching 4-vehicle SITL fleet (partitioned) — ~130s to converge"
docker exec -d "$CT" bash /tmp/sitl_fleet.sh 4
sleep 135

say "4/7  real bridges (4 drones + rover) with gemma4-vlm fire detection"
docker exec -d "$CT" bash -lc "SVERK_API_KEY=$KEY SVERK_API_BASE=$BASE MODEL_VISION=gemma4-vlm VLM_FIRE=1 bash /tmp/real_bridges.sh 4"
sleep 45
for n in 1 2 3 4; do echo -n "  drone-$n: "; docker exec "$CT" curl -s "http://127.0.0.1:$((9000+n))/healthz"; echo; done
echo -n "  rover: "; docker exec "$CT" curl -s http://127.0.0.1:9005/healthz; echo

say "5/7  gz GUI on partition d0 (drone-1 + fire)"
docker exec -d "$CT" bash -lc 'export DISPLAY=:1 GZ_PARTITION=d0 GZ_SIM_RESOURCE_PATH=/home/sverk/PX4-Autopilot/Tools/simulation/gz/models:/home/sverk/PX4-Autopilot/Tools/simulation/gz/worlds; gz sim -g > /tmp/fleet/gui_d0.log 2>&1'

say "6/7  web dashboard on :8080"
docker compose -f "$ROOT/docker-compose.yml" -f "$ROOT/docker-compose.real.yml" up -d viz >/dev/null 2>&1 || true

say "7/7  launching survey agents (chat -> fly -> vlm -> map -> rover)"
TASK=survey SCENARIO=survey-city docker compose -f "$ROOT/docker-compose.yml" -f "$ROOT/docker-compose.real.yml" \
  up -d coordinator drone-1 drone-2 drone-3 drone-4 rover >/dev/null 2>&1

echo
echo "RUNNING. Watch: gz window (d0) + http://localhost:8080"
echo "Poll:  docker run --rm -v openclaw-stack_blackboard:/bb alpine sh -c 'grep covered_count /bb/state/world.json'"
