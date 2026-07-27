#!/usr/bin/env bash
# Launch N real PX4 bridges INSIDE the sverk_sitl container, one per drone.
# Each bridge drives PX4 instance i (MAVLink 14540+i) in gz partition d$i and
# serves the mock-compatible HTTP contract on port 900(i+1).
#
#   docker exec sverk_sitl bash /tmp/real_bridges.sh 4
#
# The openclaw drone-(i+1) agent points BRIDGE_URL at fleet:900(i+1)
# (sverk_sitl's alias on openclaw-stack_mesh). See docker-compose.real.yml.
N="${1:-4}"
cd /tmp
export GZ_SIM_RESOURCE_PATH=/home/sverk/PX4-Autopilot/Tools/simulation/gz/models:/home/sverk/PX4-Autopilot/Tools/simulation/gz/worlds
export FIXTURES=/tmp/test_fixtures SCENARIO=survey-city WORLD=obrik_aruco6x6
# real VLM fire detection (gemma4-vlm on the sverk gateway) — passed in by caller
export MODEL_VISION="${MODEL_VISION:-gemma4-vlm}"
export SVERK_API_BASE="${SVERK_API_BASE:-https://ai.sverk.tech/v1}"
export SVERK_API_KEY="${SVERK_API_KEY:-}"
export VLM_FIRE="${VLM_FIRE:-1}"
# survey altitude ~1.5 m real (NED cmd 2.3 accounts for the ~0.8 m EKF alt offset);
# nadir camera + frame-centre detection localises the fire to its cell.
export TAKEOFF_Z="${TAKEOFF_Z:-2.3}"
export ANALYZE_SETTLE="${ANALYZE_SETTLE:-2.5}"
export CAM_OFFX="${CAM_OFFX:-0}"; export CAM_OFFY="${CAM_OFFY:-0}"

kill_split() { local a="$1" b="$2"; for p in $(pgrep -f "${a}${b}"); do kill -9 "$p" 2>/dev/null; done; }
kill_split "real_" "bridge.py"
sleep 1

# spawn the fire object (cell [5,5] = world 1.5,1.5) into every drone's partition
cat > /tmp/fire55.sdf <<'SDF'
<?xml version="1.0"?>
<sdf version="1.9"><model name="fire"><pose>1.5 1.5 0.05 0 0 0</pose><static>true</static>
  <link name="flame"><visual name="flame"><pose>0 0 0.2 0 0 0</pose>
    <geometry><box><size>0.5 0.5 0.4</size></box></geometry>
    <material><ambient>1.0 0.2 0.0 1</ambient><diffuse>1.0 0.3 0.02 1</diffuse><emissive>1.0 0.28 0.0 1</emissive></material></visual>
  <light name="fl" type="point"><pose>0 0 0.5 0 0 0</pose><diffuse>1.0 0.4 0.05 1</diffuse>
    <attenuation><range>1.4</range><linear>0.9</linear><quadratic>1.5</quadratic></attenuation><cast_shadows>false</cast_shadows></light>
  </link></model></sdf>
SDF
for i in $(seq 0 $((N-1))); do
  GZ_PARTITION="d$i" gz service -s /world/${WORLD}/create --reqtype gz.msgs.EntityFactory \
    --reptype gz.msgs.Boolean --timeout 3000 --req "sdf_filename: \"/tmp/fire55.sdf\", name: \"fire\"" >/dev/null 2>&1
done
echo "[real_bridges] fire spawned in d0..d$((N-1))"

for i in $(seq 0 $((N-1))); do
  n=$((i+1)); port=$((9000+n))
  GZ_PARTITION="d$i" AGENT_ID="drone-$n" INSTANCE="$i" PORT="$port" \
    nohup python3 real_bridge.py > "/tmp/fleet/rbridge_$n.log" 2>&1 &
  echo "[real_bridges] drone-$n -> inst $i, partition d$i, :$port"
  sleep 2
done

# real rover cube: shares drone-1's world (partition d0), drives cell-by-cell
kill_split "rover_" "bridge.py"
GZ_PARTITION=d0 GZ_WORLD=obrik_aruco6x6 PORT=9005 CELL_SIZE=0.6 FIELD_ORIGIN=-1.5 \
  FIRE_CELL=5,5 ROVER_START=0,0 \
  nohup python3 rover_bridge.py > /tmp/fleet/rover_bridge.log 2>&1 &
echo "[real_bridges] rover -> partition d0, :9005"
sleep 3
echo "=== listeners ==="; ss -tlnp 2>/dev/null | grep -E ":900[0-9]" || netstat -tlnp 2>/dev/null | grep -E ":900[0-9]"
