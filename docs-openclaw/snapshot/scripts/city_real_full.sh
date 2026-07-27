#!/usr/bin/env bash
# FULL real city_missions run: fresh 4-drone MAVLink SITL (drones physically fly
# the survey) + real gz rover cube (drives fire+delivery). Not mock. Reuses the
# proven single-world MAVLink launch (flies 4 drones) + FLIGHT_BACKEND=mavlink
# bridges + rover_bridge, then the city_missions agents.
#
#   scripts/city_real_full.sh
set +e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; CT=sverk_sitl; W=domiki6x6
say(){ echo -e "\n=== $* ==="; }

say "1/6  tear down old sim + bridges"
docker compose -f "$ROOT/docker-compose.yml" -f "$ROOT/docker-compose.city.yml" \
  stop coordinator drone-1 drone-2 drone-3 drone-4 rover safety-1 >/dev/null 2>&1
docker exec "$CT" bash -lc '
  for pat in "sitl_default/bin/px""4" "real_""bridge.py" "rover_""bridge.py" "skycam_""capture.py" "MicroXRCE""Agent" "g""z sim"; do
    for p in $(pgrep -f "$pat"); do kill -9 $p 2>/dev/null; done; done; echo cleaned'
sleep 3

say "2/6  stage bridge code + the Domiki world/model"
for f in real_bridge.py fleet_flight.py rover_bridge.py mock.py aruco_cell.py skycam_capture.py; do
  docker cp "$ROOT/bridge/$f" "$CT:/tmp/$f" 2>/dev/null; done
docker cp "$ROOT/bridge/gazebo/sim_driver.py" "$CT:/tmp/sim_driver.py" 2>/dev/null
# the full Domiki city map (glb wrapped as a gz model) + the world that includes it
MDL=/home/sverk/PX4-Autopilot/Tools/simulation/gz/models
WLD=/home/sverk/PX4-Autopilot/Tools/simulation/gz/worlds
docker cp "$ROOT/bridge/gazebo/worlds/domiki6x6.sdf" "$CT:$WLD/domiki6x6.sdf" 2>/dev/null
# lightweight Domiki field (city-map plane + aruco pads) — renders in the drone
# camera sensor under load; the 32MB textured glb does not.
docker cp "$ROOT/bridge/gazebo/models/domiki_field" "$CT:$MDL/" 2>/dev/null
# the 4-marker aruco->cell map for the Domiki field (ids 51-54), in aruco_cell.py
# format — the default sverk_ws markers.txt is the old 36-marker obrik map.
docker cp "$ROOT/bridge/gazebo/models/domiki_field/markers_aruco.txt" "$CT:/tmp/domiki_markers.txt" 2>/dev/null

say "3/6  fresh single-world sim: 4 px4 on a line (MAVLink) — ~110s"
docker exec -d "$CT" bash -lc '
PX4=/home/sverk/PX4-Autopilot
export GZ_SIM_RESOURCE_PATH=$PX4/Tools/simulation/gz/models:$PX4/Tools/simulation/gz/worlds
R=$PX4/build/px4_sitl_default/rootfs; rm -f $R/parameters*.bson; for i in 0 1 2 3; do rm -f $R/$i/parameters*.bson; done
( cd $R; gz sim --verbose=0 -r -s $PX4/Tools/simulation/gz/worlds/'"$W"'.sdf > /tmp/fleet/city_gz.log 2>&1 ) &
sleep 6
( export DISPLAY=:1; gz sim -g > /tmp/fleet/city_gui.log 2>&1 ) &
MicroXRCEAgent udp4 -p 8888 > /tmp/fleet/city_xrce.log 2>&1 &
sleep 3
SX="-2.0 -1.2 -0.4 0.4"; i=0
for x in $SX; do
  ( cd $PX4; PX4_GZ_STANDALONE=1 PX4_GZ_WORLD='"$W"' PX4_SIM_MODEL=gz_x500_obrik_base PX4_SYS_AUTOSTART=4001 \
    PX4_GZ_MODEL_POSE="$x,-2.0,0,0,0,0" PX4_UXRCE_DDS_NS=px4_$i \
    ./build/px4_sitl_default/bin/px4 -i $i -d > /tmp/fleet/city_px4_$i.log 2>&1 ) &
  i=$((i+1)); sleep 15
done'
sleep 118

say "4/6  spawn fire[4,2] (house) + delivery/person markers + start bridges"
KEY=$(grep -E "^SVERK_API_KEY=" "$ROOT/.env" 2>/dev/null | cut -d= -f2-)
BASE=$(grep -E "^SVERK_API_BASE=" "$ROOT/.env" 2>/dev/null | cut -d= -f2- | awk '{print $1}')
# 4 drone bridges (MAVLink), single shared world (no partition)
docker exec -d "$CT" bash -lc "
export GZ_SIM_RESOURCE_PATH=/home/sverk/PX4-Autopilot/Tools/simulation/gz/models
export FIXTURES=/tmp/test_fixtures SCENARIO=survey-city WORLD='"$W"'
# per-drone spawn world position (matches PX4_GZ_MODEL_POSE above: x on a line at
# y=-2.0). The bridge maps cell<->NED relative to the drone spawn, so without this
# each drone photographs/flies its cells shifted by its spawn offset (up to ~3
# cells) — the cause of mislabeled + off-map (blank) frames on the shared world.
SXA=(-2.0 -1.2 -0.4 0.4)
for i in 0 1 2 3; do n=\$((i+1)); port=\$((9000+n))
  FLIGHT_BACKEND=mavlink CELL_SIZE=0.8 FIELD_ORIGIN=-2.0 AGENT_ID=drone-\$n INSTANCE=\$i PORT=\$port VLM_FIRE=1 \
    SVERK_API_KEY='$KEY' SVERK_API_BASE='$BASE' MODEL_VISION=gemma4-vlm TAKEOFF_Z=4.0 \
    SPAWN_X=\${SXA[\$i]} SPAWN_Y=-2.0 \
    CAM_OFFX=0 CAM_OFFY=0 ARUCO_OFFX=0 ARUCO_OFFY=0 ARUCO_MARKERS=/tmp/domiki_markers.txt PHOTO_CROP=0.5 \
    nohup python3 /tmp/real_bridge.py > /tmp/fleet/city_dbridge_\$n.log 2>&1 &
  sleep 2
done"
# rover bridge (city config) — GZ_PARTITION=default: the fresh sim runs in the
# DEFAULT partition, so the rover cube must live there too (else it drives an
# empty d0 world and /pose is stuck at [0,0]).
docker exec -d "$CT" bash -lc '
export GZ_SIM_RESOURCE_PATH=/home/sverk/PX4-Autopilot/Tools/simulation/gz/models:/home/sverk/PX4-Autopilot/Tools/simulation/gz/worlds
GZ_PARTITION=default GZ_WORLD='"$W"' PORT=9005 CELL_SIZE=0.8 FIELD_ORIGIN=-2.0 FIRE_CELL=4,2 ROVER_START=3,3 \
  NAV_STEP_SEC=0.4 OVERVIEW_DIR=/tmp/fleet/overview OVERVIEW_STEPS=1 python3 /tmp/rover_bridge.py > /tmp/fleet/city_rover.log 2>&1'
# overview camera capture: top-down of the WHOLE field every ~4s -> /tmp/fleet/overview/
docker exec -d "$CT" bash -lc '
export GZ_SIM_RESOURCE_PATH=/home/sverk/PX4-Autopilot/Tools/simulation/gz/models
SKYCAM_WORLD='"$W"' OVERVIEW_DIR=/tmp/fleet/overview python3 /tmp/skycam_capture.py > /tmp/fleet/skycam.log 2>&1'
sleep 12
docker exec "$CT" bash -lc 'for p in 9001 9002 9003 9004 9005; do echo -n ":$p "; curl -s --max-time 3 http://localhost:$p/healthz >/dev/null 2>&1 && echo ok || echo down; done'

say "5/6  reset board + launch city agents (scouts fly fleet:9001-9004, rover fleet:9005)"
# make the agent brain visible: real drones flying on a silent mock brain is the
# worst kind of demo — say it out loud (compose auto-loads .env for the agents)
BRAIN=$(grep -E "^MODEL_PROVIDER=" "$ROOT/.env" 2>/dev/null | cut -d= -f2)
echo "  agent brain: ${BRAIN:-mock (!! no MODEL_PROVIDER in .env — chats will be canned)}"
docker run --rm -v openclaw-stack_blackboard:/bb alpine sh -lc 'rm -rf /bb/state /bb/messages /bb/events.jsonl /bb/.seq' >/dev/null 2>&1
CITY_DRONE_BRIDGES=1 docker compose -f "$ROOT/docker-compose.yml" -f "$ROOT/docker-compose.city.yml" \
  -f "$ROOT/docker-compose.city-fly.yml" up -d --force-recreate \
  coordinator drone-1 drone-2 drone-3 drone-4 rover safety-1 viz 2>&1 | tail -3

say "6/6  watch (~4 min: survey flight -> plan -> rover missions)"
for t in $(seq 1 48); do
  ph=$(docker run --rm -v openclaw-stack_blackboard:/bb alpine sh -lc 'grep -oE "\"phase\":\"[A-Z]+\"" /bb/events.jsonl 2>/dev/null | tail -1')
  echo "  t=$((t*5))s $ph"
  echo "$ph" | grep -q DONE && break
  sleep 5
done
echo "dashboard http://localhost:8095/ | drones fly in gz + rover cube drives"
