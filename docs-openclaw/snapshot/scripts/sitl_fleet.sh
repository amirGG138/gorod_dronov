#!/usr/bin/env bash
# Launch an N-drone PX4 SITL fleet with FULL per-drone isolation: each vehicle
# gets its OWN gz transport partition (isolated world -> stable EKF) AND its OWN
# DDS domain + its OWN MicroXRCEAgent (isolated ROS graph -> no offboard/arming
# contention). Each drone i: ROS_DOMAIN_ID=i, agent on udp port 8888+i, px4 -i i
# in gz partition d$i, one offboard_control (/px4_i/navigate, /land, ...) in domain i.
#
# Run INSIDE the sverk_sitl container:
#   docker exec sverk_sitl bash /tmp/sitl_fleet.sh 4
#   docker exec sverk_sitl bash /tmp/sitl_fleet.sh 4 gui   # attach a GUI to d0
#
# WHY PER-DRONE gz PARTITION: PX4's gz SITL lockstep only cleanly supports ONE
# vehicle per gz world (later models get jittery sensor timing -> "Yaw estimate
# error" / drift -> cannot hold OFFBOARD). Own GZ_PARTITION => own single-vehicle
# world => rock-stable EKF.
# WHY PER-DRONE DDS DOMAIN: one shared MicroXRCEAgent + one ROS domain for 4 drones
# starves the 2nd-4th vehicles' offboard/arming handshake — only drone 0 keeps
# OFFBOARD, the rest fall to AUTO.LOITER and disarm. Own ROS_DOMAIN_ID + own agent
# => no cross-drone DDS contention => all 4 arm and hold. This is the "4 isolated
# full stacks" topology; the openclaw bridge for drone i runs with ROS_DOMAIN_ID=i.
N="${1:-4}"
WANT_GUI="${2:-nogui}"
PX4_DIR=/home/sverk/PX4-Autopilot
WORLD=obrik_aruco6x6
WORLDS="$PX4_DIR/Tools/simulation/gz/worlds"
MODELS="$PX4_DIR/Tools/simulation/gz/models"
MODEL=gz_x500_obrik_base
AUTOSTART=4001
LOG=/tmp/fleet
mkdir -p "$LOG"

source /opt/ros/humble/setup.bash 2>/dev/null
source /home/sverk/sverk_ws/install/setup.bash 2>/dev/null
export GZ_SIM_RESOURCE_PATH="$MODELS:$WORLDS"

kill_split() { local a="$1" b="$2"; for p in $(pgrep -f "${a}${b}"); do kill -9 "$p" 2>/dev/null; done; }

echo "=== [fleet] cleaning old procs ==="
kill_split "sitl_default/bin/" "px4"
kill_split "offboard_" "control"
kill_split "g" "z sim"
kill_split "MicroXRCE" "Agent"
sleep 3

echo "=== [fleet] wiping per-instance param storage (clean stock EKF) ==="
ROOTFS="$PX4_DIR/build/px4_sitl_default/rootfs"
rm -f "$ROOTFS"/parameters*.bson
for i in $(seq 0 $((N-1))); do rm -f "$ROOTFS/$i"/parameters*.bson; done

for i in $(seq 0 $((N-1))); do
  part="d$i"; port=$((8888+i))
  echo "=== [fleet] drone $i: DDS domain $i, agent :$port, gz partition $part ==="
  ROS_DOMAIN_ID=$i MicroXRCEAgent udp4 -p $port > "$LOG/xrce_$i.log" 2>&1 &
  sleep 1
  ( export GZ_PARTITION="$part"
    export GZ_SIM_RESOURCE_PATH="$MODELS:$WORLDS"
    cd "$ROOTFS"
    gz sim --verbose=1 -r -s "$WORLDS/${WORLD}.sdf" > "$LOG/gz_$i.log" 2>&1 ) &
  sleep 6
  if [ "$WANT_GUI" = "gui" ] && [ "$i" = "0" ]; then
    ( export GZ_PARTITION="$part"; gz sim -g > "$LOG/gui_$i.log" 2>&1 ) &
  fi

  echo "=== [fleet] drone $i: px4 -i $i ns=px4_$i domain $i port $port ==="
  ( export GZ_PARTITION="$part"
    cd "$PX4_DIR"
    ROS_DOMAIN_ID=$i \
    PX4_GZ_STANDALONE=1 \
    PX4_GZ_WORLD="$WORLD" \
    PX4_SIM_MODEL="$MODEL" \
    PX4_SYS_AUTOSTART="$AUTOSTART" \
    PX4_GZ_MODEL_POSE="0,0,0,0,0,0" \
    PX4_UXRCE_DDS_NS="px4_$i" \
    PX4_UXRCE_DDS_PORT="$port" \
    GZ_SIM_RESOURCE_PATH="$MODELS:$WORLDS" \
    ./build/px4_sitl_default/bin/px4 -i "$i" -d > "$LOG/px4_$i.log" 2>&1 ) &
  sleep 8
done

echo "=== [fleet] waiting for DDS topics + EKF convergence ==="
sleep 20

for i in $(seq 0 $((N-1))); do
  ns="/px4_$i"
  echo "=== [fleet] offboard_control for $ns (domain $i) ==="
  # auto_release:=false: держать последний сетпоинт между перелётами — иначе
  # нода отпускает поток на arrival и дрон тонет (см. sverk_bridges.sh)
  ROS_DOMAIN_ID=$i ros2 run offboard_control offboard_control --ros-args \
    -r __ns:="$ns" \
    -p offboard_timeout:=30.0 -p arming_timeout:=30.0 -p auto_release:=false \
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
    > "$LOG/ofb_$i.log" 2>&1 &
  sleep 3
done

echo "=== [fleet] launched N=$N (per-drone gz partition + DDS domain). logs in $LOG ==="
sleep 5
echo "=== px4 instances ==="; pgrep -af "sitl_default/bin/px""4" | grep -oE "\-i [0-9]" | sort -u
for i in $(seq 0 $((N-1))); do
  echo -n "domain $i offboard: "; ROS_DOMAIN_ID=$i ros2 node list 2>/dev/null | grep offboard_control | tr '\n' ' '; echo
done
