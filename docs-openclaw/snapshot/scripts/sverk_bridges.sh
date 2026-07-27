#!/usr/bin/env bash
# Launch N openclaw bridges that fly the drones through the REAL sverk offboard
# stack (FLIGHT_BACKEND=sverk -> sverk_interfaces -> /px4_i/navigate). Companion
# to sitl_fleet.sh: run that FIRST (it brings up the partitioned px4 fleet + one
# offboard_control per drone with auto_release:=false), then this.
#
#   docker exec sverk_sitl bash /tmp/sitl_fleet.sh    4     # px4 + offboard nodes
#   docker exec sverk_sitl bash /tmp/sverk_bridges.sh 4     # sverk-backed bridges
#
# Each drone i lives in gz partition d$i (its own single-vehicle world => stable
# EKF => the sverk offboard_control node can arm + hold OFFBOARD; a shared world
# gives multi-vehicle "Yaw estimate error" and will NOT fly the offboard path).
# Bridge i serves the mock-compatible HTTP contract on port 900(i+1); the
# openclaw drone-(i+1) agent points BRIDGE_URL at fleet:900(i+1).
N="${1:-4}"
cd /tmp
source /opt/ros/humble/setup.bash 2>/dev/null
source /home/sverk/sverk_ws/install/setup.bash 2>/dev/null
export GZ_SIM_RESOURCE_PATH=/home/sverk/PX4-Autopilot/Tools/simulation/gz/models:/home/sverk/PX4-Autopilot/Tools/simulation/gz/worlds
export FIXTURES=/tmp/test_fixtures SCENARIO=survey-city WORLD=obrik_aruco6x6
export FLIGHT_BACKEND=sverk                       # <-- real sverk_interfaces flight
export MODEL_VISION="${MODEL_VISION:-gemma4-vlm}"
export SVERK_API_BASE="${SVERK_API_BASE:-https://ai.sverk.tech/v1}"
export SVERK_API_KEY="${SVERK_API_KEY:-}"
export VLM_FIRE="${VLM_FIRE:-1}"
export TAKEOFF_Z="${TAKEOFF_Z:-1.5}"              # metres up (map/ENU); sverk holds it
export ANALYZE_SETTLE="${ANALYZE_SETTLE:-2.5}"
export CAM_OFFX="${CAM_OFFX:-0}"; export CAM_OFFY="${CAM_OFFY:-0}"
mkdir -p /tmp/fleet

kill_split() { local a="$1" b="$2"; for p in $(pgrep -f "${a}${b}"); do kill -9 "$p" 2>/dev/null; done; }
kill_split "real_" "bridge.py"
sleep 1

# fire object (cell [5,5] = world 1.5,1.5) into every drone's partition
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
echo "[sverk_bridges] fire spawned in d0..d$((N-1))"

# Each drone lives in its OWN DDS domain (ROS_DOMAIN_ID=i, see sitl_fleet.sh) so
# the bridge for drone i must join domain i to reach /px4_i's services.
for i in $(seq 0 $((N-1))); do
  n=$((i+1)); port=$((9000+n))
  ROS_DOMAIN_ID="$i" GZ_PARTITION="d$i" AGENT_ID="drone-$n" INSTANCE="$i" PORT="$port" \
    OFFBOARD_NS="/px4_$i" \
    nohup python3 real_bridge.py > "/tmp/fleet/sverk_rbridge_$n.log" 2>&1 &
  echo "[sverk_bridges] drone-$n -> /px4_$i (sverk offboard, domain $i), partition d$i, :$port"
  sleep 2
done

# real rover cube: shares drone-1's world (partition d0), drives cell-by-cell
kill_split "rover_" "bridge.py"
GZ_PARTITION=d0 GZ_WORLD=obrik_aruco6x6 PORT=9005 CELL_SIZE=0.6 FIELD_ORIGIN=-1.5 \
  FIRE_CELL=5,5 ROVER_START=0,0 \
  nohup python3 rover_bridge.py > /tmp/fleet/rover_bridge.log 2>&1 &
echo "[sverk_bridges] rover -> partition d0, :9005"
sleep 3
echo "[sverk_bridges] up. bridges: fleet:9001..900$N  rover: fleet:9005"
