#!/usr/bin/env bash
# Runs INSIDE the sverk ROS2 environment on a real drone: (re)start the openclaw
# scan bridge for the test-3x3 scenario. Called by scripts/deploy_drone.sh (via
# `docker exec` or bare ssh). Expects the node files already staged in /tmp:
#   real_bridge.py sverk_flight.py fleet_flight.py mock.py aruco_cell.py markers.txt
#
# Env (with test-3x3 defaults):
#   FLIGHT_BACKEND sverk|mavlink  INSTANCE  PORT  CELL_SIZE  FIELD_ORIGIN
#   TAKEOFF_Z  ARUCO_MARKERS  NODE_DIR
set +e
NODE_DIR="${NODE_DIR:-/tmp}"
PORT="${PORT:-9001}"
INSTANCE="${INSTANCE:-0}"

source /opt/ros/humble/setup.bash 2>/dev/null
source /home/sverk/sverk_ws/install/setup.bash 2>/dev/null

# kill a previous bridge (awk/ps split avoids the pgrep self-match)
for p in $(pgrep -f "real_""bridge.py"); do kill -9 "$p" 2>/dev/null; done
sleep 1

cd "$NODE_DIR" || exit 1
# лётный рецепт реального борта: взлёт по body (маркеры с земли не видны),
# полёт в aruco_map (общий кадр поля по маркерам)
FLIGHT_BACKEND="${FLIGHT_BACKEND:-sverk}" \
  AGENT_ID="${AGENT_ID:-drone-1}" INSTANCE="$INSTANCE" PORT="$PORT" \
  OFFBOARD_NS="${OFFBOARD_NS:-}" \
  SVERK_FRAME="${SVERK_FRAME:-aruco_map}" TAKEOFF_FRAME="${TAKEOFF_FRAME:-body}" \
  CELL_SIZE="${CELL_SIZE:-0.6}" FIELD_ORIGIN="${FIELD_ORIGIN:--0.6}" \
  TAKEOFF_Z="${TAKEOFF_Z:-1.0}" TAKEOFF_Z_M="${TAKEOFF_Z:-1.0}" \
  CAM_OFFX="${CAM_OFFX:-0}" CAM_OFFY="${CAM_OFFY:-0}" \
  ARUCO_MARKERS="${ARUCO_MARKERS:-$NODE_DIR/markers.txt}" \
  nohup python3 "$NODE_DIR/real_bridge.py" > /tmp/openclaw_bridge.log 2>&1 &

# sverk-фасад коннектится до 25с — не кричать DOWN раньше времени
up=0
for i in 1 2 3 4 5 6 7 8; do
  sleep 4
  curl -s --max-time 5 "http://localhost:$PORT/healthz" >/dev/null 2>&1 && { up=1; break; }
done
if [ "$up" = 1 ]; then
  echo "bridge UP on :$PORT ($(curl -s http://localhost:$PORT/healthz))"
else
  echo "bridge DOWN — tail /tmp/openclaw_bridge.log:"; tail -n 20 /tmp/openclaw_bridge.log 2>/dev/null
  exit 1
fi
