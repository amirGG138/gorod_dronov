#!/usr/bin/env bash
# CLEAN full run of the city-drones scenario in ONE gz world (1 window). Restarts
# the SIM from scratch: 4 drones spawn in a LINE on the aruco field (cells
# [0,0]..[3,0]), sit on the ground, then the LLM survey lifts them off, they map
# the field (real gemma4-vlm fire detection), the rover drives to the fire, and
# every drone flies back to its start cell and lands.
#
#   scripts/full_scenario_single.sh
#
# Watch: gz GUI window + top-down frames at /tmp/fleet/overview/ .
set +e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; CT=sverk_sitl
source "$ROOT/.env" 2>/dev/null || true
KEY="${SVERK_API_KEY:-}"; BASE="${SVERK_API_BASE:-https://ai.sverk.tech/v1}"
W=obrik_aruco6x6
say(){ echo -e "\n=== $* ==="; }

say "1/8  tear down (agents + sim + bridges + camera)"
docker compose -f "$ROOT/docker-compose.yml" -f "$ROOT/docker-compose.real.yml" \
  stop coordinator drone-1 drone-2 drone-3 drone-4 rover >/dev/null 2>&1
docker exec "$CT" bash -lc '
  for pat in "sitl_default/bin/px""4" "real_""bridge.py" "rover_""bridge.py" "MicroXRCE""Agent" "g""z sim" "skycam_""capture.py"; do
    for p in $(pgrep -f "$pat"); do kill -9 $p 2>/dev/null; done; done; echo cleaned'
sleep 3

say "2/8  copy scripts"
for f in fleet_flight.py real_bridge.py mock.py rover_bridge.py aruco_cell.py skycam_capture.py; do
  docker cp "$ROOT/bridge/$f" "$CT:/tmp/$f" 2>/dev/null; done
docker cp "$ROOT/bridge/gazebo/sim_driver.py" "$CT:/tmp/sim_driver.py" 2>/dev/null
docker exec "$CT" mkdir -p /tmp/test_fixtures/survey-city
docker cp "$ROOT/test_fixtures/survey-city/map.json" "$CT:/tmp/test_fixtures/survey-city/map.json"

say "3/8  fresh single-world sim (4 px4 in a line on the field) — ~130s"
# spawn poses = field cells [0,0],[1,0],[2,0],[3,0]  (world x,y; cell=0.6, origin=-1.5)
docker exec "$CT" bash -lc 'cat > /tmp/sw_line.sh <<"SH"
PX4=/home/sverk/PX4-Autopilot; W=obrik_aruco6x6
export GZ_SIM_RESOURCE_PATH=$PX4/Tools/simulation/gz/models:$PX4/Tools/simulation/gz/worlds
R=$PX4/build/px4_sitl_default/rootfs; rm -f $R/parameters*.bson; for i in 0 1 2 3; do rm -f $R/$i/parameters*.bson; done
( cd $R; gz sim --verbose=1 -r -s $PX4/Tools/simulation/gz/worlds/$W.sdf > /tmp/fleet/sw_gz.log 2>&1 ) &
sleep 6
( export DISPLAY=:1; gz sim -g > /tmp/fleet/sw_gui.log 2>&1 ) &
MicroXRCEAgent udp4 -p 8888 > /tmp/fleet/sw_xrce.log 2>&1 &
sleep 3
SX="-1.5 1.5 -1.5 0.9"; SY="-1.5 -1.5 1.5 0.9"
i=0
for x in $SX; do
  y=$(echo $SY | cut -d" " -f$((i+1)))
  ( cd $PX4; PX4_GZ_STANDALONE=1 PX4_GZ_WORLD=$W PX4_SIM_MODEL=gz_x500_obrik_base PX4_SYS_AUTOSTART=4001 \
    PX4_GZ_MODEL_POSE="$x,$y,0,0,0,0" PX4_UXRCE_DDS_NS=px4_$i \
    ./build/px4_sitl_default/bin/px4 -i $i -d > /tmp/fleet/sw_px4_$i.log 2>&1 ) &
  i=$((i+1)); sleep 15
done
SH
bash /tmp/sw_line.sh > /tmp/fleet/sw_line.log 2>&1 &'
sleep 135

say "4/8  fire + top-down camera"
docker exec "$CT" bash -lc '
cat > /tmp/fire55.sdf <<SDF
<?xml version="1.0"?>
<sdf version="1.9"><model name="fire"><pose>1.5 1.5 0.05 0 0 0</pose><static>true</static>
 <link name="flame"><visual name="flame"><pose>0 0 0.2 0 0 0</pose>
  <geometry><box><size>0.5 0.5 0.4</size></box></geometry>
  <material><ambient>1 0.2 0 1</ambient><diffuse>1 0.3 0.02 1</diffuse><emissive>1 0.28 0 1</emissive></material></visual>
 <light name="fl" type="point"><pose>0 0 0.5 0 0 0</pose><diffuse>1 0.4 0.05 1</diffuse>
  <attenuation><range>1.4</range><linear>0.9</linear><quadratic>1.5</quadratic></attenuation><cast_shadows>false</cast_shadows></light></link></model></sdf>
SDF
cat > /tmp/skycam.sdf <<SDF
<?xml version="1.0"?>
<sdf version="1.9"><model name="skycam"><static>true</static><pose>0 0 14 0 0 0</pose>
 <link name="l"><sensor name="cam" type="camera"><pose>0 0 0 0 1.5707963 0</pose>
  <camera><horizontal_fov>0.75</horizontal_fov><image><width>1100</width><height>1100</height></image>
   <clip><near>0.1</near><far>200</far></clip></camera><always_on>1</always_on><update_rate>4</update_rate></sensor></link></model></sdf>
SDF
for m in fire skycam; do gz service -s /world/'"$W"'/create --reqtype gz.msgs.EntityFactory --reptype gz.msgs.Boolean --timeout 3000 --req "sdf_filename: \"/tmp/$m.sdf\", name: \"$m\"" >/dev/null 2>&1; done
GZ_SIM_RESOURCE_PATH=$PX4/Tools/simulation/gz/models nohup python3 /tmp/skycam_capture.py > /tmp/fleet/skycam.log 2>&1 &
echo "fire + skycam up"'

say "5/8  aruco-nav bridges (landed) + rover"
docker exec -d "$CT" bash -lc "
cd /tmp
export SVERK_API_KEY=$KEY SVERK_API_BASE=$BASE MODEL_VISION=gemma4-vlm VLM_FIRE=1
export TAKEOFF_Z=2.3 CAM_OFFX=0 CAM_OFFY=0 ANALYZE_SETTLE=2.0 ARUCO_NAV=1
export GZ_SIM_RESOURCE_PATH=/home/sverk/PX4-Autopilot/Tools/simulation/gz/models:/home/sverk/PX4-Autopilot/Tools/simulation/gz/worlds
export FIXTURES=/tmp/test_fixtures SCENARIO=survey-city WORLD=$W
SX='-1.5 1.5 -1.5 0.9'; SY='-1.5 -1.5 1.5 0.9'
i=0
for x in \$SX; do y=\$(echo \$SY|cut -d' ' -f\$((i+1))); n=\$((i+1))
  AGENT_ID=drone-\$n INSTANCE=\$i PORT=\$((9000+n)) SPAWN_X=\$x SPAWN_Y=\$y nohup python3 real_bridge.py > /tmp/fleet/rbridge_\$n.log 2>&1 &
  i=\$((i+1)); sleep 2; done
GZ_PARTITION=default GZ_WORLD=$W PORT=9005 CELL_SIZE=0.6 FIELD_ORIGIN=-1.5 FIRE_CELL=5,5 nohup python3 rover_bridge.py > /tmp/fleet/rover_bridge.log 2>&1 &"
sleep 20
for n in 1 2 3 4; do echo -n "  drone-$n: "; docker exec "$CT" curl -s "http://127.0.0.1:$((9000+n))/pose"; echo; done
echo "(drones should be LANDED on cells [0,0]..[3,0], alt ~0)"

say "6/8  reset blackboard"
docker run --rm -v openclaw-stack_blackboard:/bb alpine sh -c 'rm -rf /bb/* /bb/.seq 2>/dev/null'

say "7/8  launch survey (LLM chat -> takeoff -> map -> vlm -> rover), quorum=1"
VERIFY_QUORUM=1 TASK=survey SCENARIO=survey-city docker compose -f "$ROOT/docker-compose.yml" -f "$ROOT/docker-compose.real.yml" \
  up -d coordinator drone-1 drone-2 drone-3 drone-4 rover >/dev/null 2>&1
echo "RUNNING. Lifecycle: stand -> chat -> takeoff -> survey -> rover -> land home."
echo "Land each drone home at the end:  for n in 1 2 3 4; do docker exec $CT curl -s -XPOST http://127.0.0.1:\$((9000+n))/land -d '{\"home\":true}'; done"
