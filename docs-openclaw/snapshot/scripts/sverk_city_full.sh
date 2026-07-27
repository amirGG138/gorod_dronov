#!/usr/bin/env bash
# FULL city run over the REAL sverk stack in ONE shared world: 4 PX4 SITL drones
# fly through sverk_interfaces -> offboard_control -> uXRCE-DDS (no MAVLink), the
# rover cube drives fire+delivery, agents think with the live LLM.
#
# Verified 2026-07-22: all 4 drones arm, hold OFFBOARD and fly cells concurrently
# in one domiki6x6 world. The historical "only instance 0 flies" blocker needs
# three things, all handled here:
#   1) a CLEAN start — orphaned offboard nodes / agents from old runs must die
#      (a stale node survives a PX4 restart and spams stale_local_position);
#   2) offboard_control nodes launched with auto_release:=false (default true
#      releases setpoints on arrival -> drones sink and it LOOKS like OFFBOARD
#      is lost);
#   3) the sverk-ros2 image with the dds shm cleanup fix (3334980+).
#
#   scripts/sverk_city_full.sh
set +e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; CT=sverk_sitl; W=domiki6x6
say(){ echo -e "\n=== $* ==="; }

say "1/6  tear down old sim + bridges + offboard nodes"
docker compose -f "$ROOT/docker-compose.yml" -f "$ROOT/docker-compose.city.yml" \
  stop coordinator drone-1 drone-2 drone-3 drone-4 rover safety-1 >/dev/null 2>&1
docker exec "$CT" bash -lc '
  for pat in "sitl_default/bin/px""4" "offboard_""control" "real_""bridge.py" "rover_""bridge.py" \
             "skycam_""capture.py" "MicroXRCE""Agent" "g""z sim"; do
    for p in $(pgrep -f "$pat"); do kill -9 $p 2>/dev/null; done; done; echo cleaned'
sleep 3

say "2/6  stage bridge code + the Domiki world/model"
for f in real_bridge.py sverk_flight.py fleet_flight.py mock.py aruco_cell.py skycam_capture.py rover_bridge.py; do
  docker cp "$ROOT/bridge/$f" "$CT:/tmp/$f" 2>/dev/null; done
MDL=/home/sverk/PX4-Autopilot/Tools/simulation/gz/models
WLD=/home/sverk/PX4-Autopilot/Tools/simulation/gz/worlds
docker cp "$ROOT/bridge/gazebo/worlds/domiki6x6.sdf" "$CT:$WLD/domiki6x6.sdf" 2>/dev/null
docker cp "$ROOT/bridge/gazebo/models/domiki_field" "$CT:$MDL/" 2>/dev/null
docker cp "$ROOT/bridge/gazebo/models/domiki_field/markers_aruco.txt" "$CT:/tmp/domiki_markers.txt" 2>/dev/null

say "3/6  ONE shared world + ONE agent :8888 + 4 px4 (ns px4_i) — ~110s"
docker exec -d "$CT" bash -lc '
PX4=/home/sverk/PX4-Autopilot
export GZ_SIM_RESOURCE_PATH=$PX4/Tools/simulation/gz/models:$PX4/Tools/simulation/gz/worlds
R=$PX4/build/px4_sitl_default/rootfs; rm -f $R/parameters*.bson; for i in 0 1 2 3; do rm -f $R/$i/parameters*.bson; done
( cd $R; gz sim --verbose=0 -r -s $PX4/Tools/simulation/gz/worlds/'"$W"'.sdf > /tmp/fleet/city_gz.log 2>&1 ) &
sleep 6
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

say "4/6  4 offboard_control nodes (auto_release:=false) + sverk bridges + rover + skycam"
docker exec "$CT" bash -lc '
source /opt/ros/humble/setup.bash 2>/dev/null; source /home/sverk/sverk_ws/install/setup.bash 2>/dev/null
for i in 0 1 2 3; do
  ns="/px4_$i"
  ros2 run offboard_control offboard_control --ros-args \
    -r __ns:="$ns" -p offboard_timeout:=30.0 -p arming_timeout:=30.0 -p auto_release:=false \
    -r "/fmu/vehicle_command:=${ns}/fmu/vehicle_command" \
    -r "/fmu/in/offboard_control_mode:=${ns}/fmu/in/offboard_control_mode" \
    -r "/fmu/in/trajectory_setpoint:=${ns}/fmu/in/trajectory_setpoint" \
    -r "/fmu/in/vehicle_attitude_setpoint:=${ns}/fmu/in/vehicle_attitude_setpoint" \
    -r "/fmu/in/vehicle_rates_setpoint:=${ns}/fmu/in/vehicle_rates_setpoint" \
    -r "/fmu/out/vehicle_status:=${ns}/fmu/out/vehicle_status" \
    -r "/fmu/out/vehicle_global_position:=${ns}/fmu/out/vehicle_global_position" \
    -r "/fmu/out/vehicle_odometry:=${ns}/fmu/out/vehicle_odometry" \
    -r "/fmu/out/battery_status:=${ns}/fmu/out/battery_status" \
    -r "/fmu/out/manual_control_setpoint:=${ns}/fmu/out/manual_control_setpoint" \
    -r "/fmu/out/vehicle_angular_velocity:=${ns}/fmu/out/vehicle_angular_velocity" \
    -r "/fmu/out/hover_thrust_estimate:=${ns}/fmu/out/hover_thrust_estimate" \
    -r "/fmu/out/vehicle_land_detected:=${ns}/fmu/out/vehicle_land_detected" \
    > /tmp/fleet/city_ofb_$i.log 2>&1 &
  sleep 2
done; sleep 4; echo "offboard nodes up"'
KEY=$(grep -E "^SVERK_API_KEY=" "$ROOT/.env" 2>/dev/null | cut -d= -f2-)
BASE=$(grep -E "^SVERK_API_BASE=" "$ROOT/.env" 2>/dev/null | cut -d= -f2- | awk '{print $1}')
docker exec -d "$CT" bash -lc "
source /opt/ros/humble/setup.bash 2>/dev/null; source /home/sverk/sverk_ws/install/setup.bash 2>/dev/null
export GZ_SIM_RESOURCE_PATH=/home/sverk/PX4-Autopilot/Tools/simulation/gz/models
export FIXTURES=/tmp/test_fixtures SCENARIO=survey-city WORLD='"$W"'
SXA=(-2.0 -1.2 -0.4 0.4)
for i in 0 1 2 3; do n=\$((i+1)); port=\$((9000+n))
  FLIGHT_BACKEND=sverk OFFBOARD_NS=/px4_\$i CELL_SIZE=0.8 FIELD_ORIGIN=-2.0 \
    AGENT_ID=drone-\$n INSTANCE=\$i PORT=\$port VLM_FIRE=1 \
    SVERK_API_KEY='$KEY' SVERK_API_BASE='$BASE' MODEL_VISION=gemma4-vlm \
    TAKEOFF_Z=4.0 TAKEOFF_Z_M=4.0 SPAWN_X=\${SXA[\$i]} SPAWN_Y=-2.0 \
    CAM_OFFX=0 CAM_OFFY=0 ARUCO_OFFX=0 ARUCO_OFFY=0 \
    ARUCO_MARKERS=/tmp/domiki_markers.txt PHOTO_CROP=0.5 \
    nohup python3 /tmp/real_bridge.py > /tmp/fleet/city_dbridge_\$n.log 2>&1 &
  sleep 2
done"
docker exec -d "$CT" bash -lc '
export GZ_SIM_RESOURCE_PATH=/home/sverk/PX4-Autopilot/Tools/simulation/gz/models:/home/sverk/PX4-Autopilot/Tools/simulation/gz/worlds
GZ_PARTITION=default GZ_WORLD='"$W"' PORT=9005 CELL_SIZE=0.8 FIELD_ORIGIN=-2.0 FIRE_CELL=4,2 ROVER_START=3,3 \
  NAV_STEP_SEC=0.4 OVERVIEW_DIR=/tmp/fleet/overview OVERVIEW_STEPS=1 python3 /tmp/rover_bridge.py > /tmp/fleet/city_rover.log 2>&1'
docker exec -d "$CT" bash -lc '
export GZ_SIM_RESOURCE_PATH=/home/sverk/PX4-Autopilot/Tools/simulation/gz/models
SKYCAM_WORLD='"$W"' OVERVIEW_DIR=/tmp/fleet/overview python3 /tmp/skycam_capture.py > /tmp/fleet/skycam.log 2>&1'
sleep 14
docker exec "$CT" bash -lc 'for p in 9001 9002 9003 9004 9005; do echo -n ":$p "; curl -s --max-time 3 http://localhost:$p/healthz >/dev/null 2>&1 && echo ok || echo down; done'

say "5/6  reset board + launch city agents"
BRAIN=$(grep -E "^MODEL_PROVIDER=" "$ROOT/.env" 2>/dev/null | cut -d= -f2)
echo "  agent brain: ${BRAIN:-mock (!! no MODEL_PROVIDER in .env — chats will be canned)}"
docker run --rm -v openclaw-stack_blackboard:/bb alpine sh -lc 'rm -rf /bb/state /bb/messages /bb/events.jsonl /bb/.seq' >/dev/null 2>&1
CITY_DRONE_BRIDGES=1 docker compose -f "$ROOT/docker-compose.yml" -f "$ROOT/docker-compose.city.yml" \
  -f "$ROOT/docker-compose.city-fly.yml" up -d --force-recreate \
  coordinator drone-1 drone-2 drone-3 drone-4 rover safety-1 viz 2>&1 | tail -3

say "6/6  watch (~6 min: survey flight -> rover missions)"
for t in $(seq 1 90); do
  ph=$(docker run --rm -v openclaw-stack_blackboard:/bb alpine sh -lc 'grep -oE "\"phase\":\"[A-Z]+\"" /bb/events.jsonl 2>/dev/null | tail -1')
  echo "  t=$((t*5))s $ph"
  echo "$ph" | grep -q DONE && break
  sleep 5
done
echo "dashboard http://localhost:8095/ | 4 drones fly the SVERK path in one world"
