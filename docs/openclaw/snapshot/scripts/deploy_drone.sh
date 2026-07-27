#!/usr/bin/env bash
# Upload + configure the openclaw scan node onto a REAL drone over SSH.
#
# The drone already runs the sverk ROS2 image (our base image). This adds OUR part
# — the bridge (real_bridge.py + deps) + the 3×3 ArUco map — starts it against the
# real flight stack (FLIGHT_BACKEND=sverk -> sverk_interfaces -> PX4 FMU) at ~1 m in
# the map frame, and tells the drone which cell it is over. The pilots/coordinator
# AGENTS run on the operator host (docker-compose.test.yml) — see docs/test-3x3.md.
#
#   DRONE=sverk@192.168.1.50 bash scripts/deploy_drone.sh
#   DRONE=... SVERK_CT=sverk_sitl INSTANCE=0 START_CELL=1,1 FLIGHT_BACKEND=sverk \
#     bash scripts/deploy_drone.sh
#   DRONE=... SVERK_CT="" bash scripts/deploy_drone.sh    # sverk stack runs bare (no docker)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
: "${DRONE:?set DRONE=user@host (ssh target of the drone companion computer)}"
SVERK_CT="${SVERK_CT-sverk_sitl}"           # sverk ROS2 container name; "" => run bare on host
INSTANCE="${INSTANCE:-0}"                    # PX4 instance / /px4_<i> offboard namespace
PORT="${PORT:-9001}"
START_CELL="${START_CELL:-1,1}"             # cell the drone starts over (id4 centre = [1,1])
BACKEND="${FLIGHT_BACKEND:-sverk}"          # sverk (real FMU) | mavlink (SITL)
ALT="${TAKEOFF_Z:-1.0}"                      # metres up (map/ENU)
REMOTE_TMP="${REMOTE_TMP:-/tmp/openclaw}"
NODE_FILES=(real_bridge.py sverk_flight.py fleet_flight.py mock.py aruco_cell.py)
say(){ echo -e "\n=== $* ==="; }

say "1/5  upload node files -> $DRONE:$REMOTE_TMP"
ssh "$DRONE" "mkdir -p '$REMOTE_TMP'"
for f in "${NODE_FILES[@]}"; do scp -q "$ROOT/bridge/$f" "$DRONE:$REMOTE_TMP/"; done
scp -q "$ROOT/test_fixtures/test-3x3/markers.txt" "$DRONE:$REMOTE_TMP/"
scp -q "$ROOT/scripts/_drone_bridge_launch.sh" "$DRONE:$REMOTE_TMP/"

if [ -n "$SVERK_CT" ]; then
  say "2/5  copy node into the sverk container ($SVERK_CT)"
  for f in "${NODE_FILES[@]}" markers.txt _drone_bridge_launch.sh; do
    ssh "$DRONE" "docker cp '$REMOTE_TMP/$f' '$SVERK_CT:/tmp/$f'"
  done
  NODE_DIR=/tmp
else
  say "2/5  sverk runs bare on host — node staged at $REMOTE_TMP"
  NODE_DIR="$REMOTE_TMP"
fi

say "3/5  (re)start bridge (backend=$BACKEND, 3×3, ${ALT}m, port $PORT)"
ENVS="-e FLIGHT_BACKEND=$BACKEND -e INSTANCE=$INSTANCE -e PORT=$PORT -e TAKEOFF_Z=$ALT -e NODE_DIR=$NODE_DIR -e CELL_SIZE=0.6 -e FIELD_ORIGIN=-0.6 -e ARUCO_MARKERS=$NODE_DIR/markers.txt"
if [ -n "$SVERK_CT" ]; then
  ssh "$DRONE" "docker exec -d $ENVS $SVERK_CT bash $NODE_DIR/_drone_bridge_launch.sh"
  sleep 6
  ssh "$DRONE" "docker exec $SVERK_CT bash -lc 'curl -s --max-time 5 http://localhost:$PORT/healthz || tail -n 20 /tmp/openclaw_bridge.log'"
else
  ssh "$DRONE" "env FLIGHT_BACKEND=$BACKEND INSTANCE=$INSTANCE PORT=$PORT TAKEOFF_Z=$ALT NODE_DIR=$NODE_DIR CELL_SIZE=0.6 FIELD_ORIGIN=-0.6 ARUCO_MARKERS=$NODE_DIR/markers.txt bash $NODE_DIR/_drone_bridge_launch.sh"
fi

say "4/5  tell the drone which cell it is over ($START_CELL)"
CELL_JSON="{\"cell\":[${START_CELL}]}"
if [ -n "$SVERK_CT" ]; then
  ssh "$DRONE" "docker exec $SVERK_CT curl -s http://localhost:$PORT/set_cell -d '$CELL_JSON'; echo"
else
  ssh "$DRONE" "curl -s http://localhost:$PORT/set_cell -d '$CELL_JSON'; echo"
fi

say "5/5  done"
echo "Bridge up on $DRONE (port $PORT). Now run the AGENTS on the operator host:"
echo "  1) point the flyer at the drone — in docker-compose.test.yml, service 'flyer':"
echo "       environment: { BRIDGE_URL: http://<DRONE-IP>:$PORT, BRIDGE_TIMEOUT: \"180\" }"
echo "     (or join the drone sverk container to the openclaw 'mesh' as alias 'fleet'"
echo "      and use BRIDGE_URL=http://fleet:$PORT — same as the local stack)"
echo "  2) MODEL_PROVIDER=sverk bash scripts/test_3x3.sh"
echo "  Front: http://localhost:${VIZ_HOST_PORT:-8095}/test"
echo
echo "Camera note: real_bridge captures the downward frame from a gz topic (SITL)."
echo "On a real camera (no gz) flight+scan run, but /photograph returns captured:false"
echo "until the camera source is pointed at the drone ROS2 image topic — see docs."
