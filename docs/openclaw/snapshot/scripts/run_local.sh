#!/usr/bin/env bash
# Run the whole stack as local processes (no Docker) for fast iteration.
# Brain defaults to mock so it runs unattended with no API key.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

# Remember what the CALLER asked for before .env (which pins the street demo's
# SCENARIO) can clobber it -- otherwise `make local-painters` would load the
# street map.
CALLER_TASK="${TASK:-}"; CALLER_SCENARIO="${SCENARIO:-}"
CALLER_MODEL="${MODEL_PROVIDER:-}"

# pick up real-brain config (MODEL_PROVIDER, keys, model) like compose does
if [ -f "$ROOT/.env" ]; then set -a; . "$ROOT/.env"; set +a; fi

export TASK="${CALLER_TASK:-${TASK:-safe_passage}}"
if [ "$TASK" = "painting" ]; then export SCENARIO="${CALLER_SCENARIO:-painters-1}";
elif [ "$TASK" = "debate" ]; then export SCENARIO="${CALLER_SCENARIO:-debate-1}";
elif [ "$TASK" = "survey" ]; then
  export SCENARIO="${CALLER_SCENARIO:-survey-1}"
  # симуляция: сжимаем «подождать 20 сек» до ~1с; на железе WAIT_SCALE=1
  export WAIT_SCALE="${WAIT_SCALE:-0.05}"
else export SCENARIO="${CALLER_SCENARIO:-${SCENARIO:-scenario-1}}"; fi
export FIXTURES="$ROOT/test_fixtures"
export BLACKBOARD="$ROOT/blackboard"
export MODEL_PROVIDER="${CALLER_MODEL:-${MODEL_PROVIDER:-mock}}"
export PYTHONPATH="$ROOT/agent"
export NAV_STEP_SEC="${NAV_STEP_SEC:-0.12}"
export PAINT_STEP_SEC="${PAINT_STEP_SEC:-0.08}"

LOG="$ROOT/.local-logs"; mkdir -p "$LOG"
# double-start guard: a second launch used to rm -rf the board out from under
# live KEEP_ALIVE agents and spawn a second coordinator on the same blackboard
if [ -f "$LOG/pids" ]; then
  ALIVE=""
  for pid in $(cat "$LOG/pids"); do
    kill -0 "$pid" 2>/dev/null && ALIVE="$ALIVE $pid"
  done
  if [ -n "$ALIVE" ]; then
    echo "A local stack is already running (pids:$ALIVE). Run 'make stop-local' first." >&2
    exit 1
  fi
fi

mkdir -p "$BLACKBOARD"
# fresh run (belt-and-suspenders; the coordinator also resets on boot)
rm -rf "$BLACKBOARD"/messages "$BLACKBOARD"/state "$BLACKBOARD"/artifacts "$BLACKBOARD"/events.jsonl "$BLACKBOARD"/agents 2>/dev/null || true

PIDS=()

start() { "$@" & PIDS+=($!); }

if [ "$TASK" = "debate" ]; then
  # ---- debate: moderator (first-class role) + debater-1..N, no bridges ----
  export DEBATERS="${DEBATERS:-debater-1,debater-2,debater-3}"
  AGENT_ID=moderator ROLE=moderator SOUL="$ROOT/souls/moderator.md" \
    start python3 "$ROOT/agent/loop.py" >"$LOG/moderator.log" 2>&1
  IFS=',' read -ra DEBS <<< "$DEBATERS"
  for r in "${DEBS[@]}"; do
    AGENT_ID="$r" ROLE=debater SOUL="$ROOT/souls/$r.md" \
      start python3 "$ROOT/agent/loop.py" >"$LOG/$r.log" 2>&1
  done
  # live test stand: current speaker + all arguments in parallel + final tally
  if [ "${HEADLESS:-0}" != "1" ]; then
    VIZ_PORT="${VIZ_PORT:-8080}"
    PORT="$VIZ_PORT" start python3 "$ROOT/viz/server.py" >"$LOG/viz.log" 2>&1
    echo "debate test stand: http://localhost:$VIZ_PORT/debate"
  fi
elif [ "$TASK" = "painting" ]; then
  # ---- painters: coordinator + painter-1..4, one spray bridge each ----
  declare -A PORT=( [painter-1]=9011 [painter-2]=9012 [painter-3]=9013 [painter-4]=9014 )
  for r in painter-1 painter-2 painter-3 painter-4; do
    AGENT_ID="$r" PORT="${PORT[$r]}" start python3 "$ROOT/bridge/mock.py" >"$LOG/bridge-$r.log" 2>&1
  done
  sleep 1
  AGENT_ID=coordinator ROLE=coordinator \
    start python3 "$ROOT/agent/loop.py" >"$LOG/coordinator.log" 2>&1
  for r in painter-1 painter-2 painter-3 painter-4; do
    AGENT_ID="$r" ROLE=painter BRIDGE_URL="http://localhost:${PORT[$r]}" SOUL="$ROOT/souls/$r.md" \
      start python3 "$ROOT/agent/loop.py" >"$LOG/$r.log" 2>&1
  done
  # VLM-критик (жюри): оценивает холст 1..100 каждые пару секунд + финальный
  # вердикт; экран — /critic. Отключается CRITIC=0.
  if [ "${CRITIC:-1}" != "0" ]; then
    AGENT_ID=critic ROLE=critic SOUL="$ROOT/souls/critic.md" \
      start python3 "$ROOT/agent/loop.py" >"$LOG/critic.log" 2>&1
  fi
  # investor dashboard: live canvas + drones + chat (PORT is an assoc array here,
  # so pass the viz port via env to avoid clobbering it)
  if [ "${HEADLESS:-0}" != "1" ]; then
    VIZ_PORT="${VIZ_PORT:-8080}"
    env PORT="$VIZ_PORT" python3 "$ROOT/viz/server.py" >"$LOG/viz.log" 2>&1 & PIDS+=($!)
    echo "studio dashboard: http://localhost:$VIZ_PORT/studio"
    [ "${CRITIC:-1}" != "0" ] && echo "жюри (VLM-оценка картины): http://localhost:$VIZ_PORT/critic"
  fi
else
  # ---- safe-passage / survey: coordinator + drone-1..4 + rover ----
  # (survey — поиск груза на поле клеток — использует ту же топологию:
  #  по бриджу на робота, ровер ждёт world.ready)
  declare -A PORT=( [drone-1]=9001 [drone-2]=9002 [drone-3]=9003 [drone-4]=9004 [rover]=9005 )
  # GAZEBO_SIM=1: ровер — реальный куб в Gazebo (bridge/gazebo_rover_bridge.py на
  # :9105), плюс зеркало 4 дронов в Gazebo. Дроны всё так же планируют/мапят
  # логикой стека через свои mock-бриджи; в Gazebo их модели двигает mirror.
  GZ="${GAZEBO_SIM:-0}"
  if [ "$GZ" != "0" ] && [ "$TASK" = "survey" ]; then
    # точка А (старт ровера) и точка Б (пожар) из карты сценария
    read -r ROVER_START FIRE_CELL <<EOF
$(python3 - "$FIXTURES/$SCENARIO/map.json" <<'PY'
import json,sys
m=json.load(open(sys.argv[1]))
s=m.get("start") or [0,0]; f=m.get("fire") or [4,4]
print(f"{s[0]},{s[1]} {f[0]},{f[1]}")
PY
)
EOF
    export ROVER_START FIRE_CELL CONTAINER="${CONTAINER:-sverk_sitl}"
    echo "[gazebo] rover A=$ROVER_START -> fire B=$FIRE_CELL (container $CONTAINER)"
    ROVER_BRIDGES="drone-1 drone-2 drone-3 drone-4"   # rover uses the gazebo bridge
  else
    ROVER_BRIDGES="drone-1 drone-2 drone-3 drone-4 rover"
  fi
  for r in $ROVER_BRIDGES; do
    AGENT_ID="$r" PORT="${PORT[$r]}" start python3 "$ROOT/bridge/mock.py" >"$LOG/bridge-$r.log" 2>&1
  done
  if [ "$GZ" != "0" ] && [ "$TASK" = "survey" ]; then
    # env PORT=... because PORT is an assoc array here (as with the viz start below)
    start env PORT=9105 python3 "$ROOT/bridge/gazebo_rover_bridge.py" >"$LOG/bridge-gazebo-rover.log" 2>&1
    start python3 "$ROOT/bridge/gazebo_drone_mirror.py" >"$LOG/gazebo-mirror.log" 2>&1
    sleep 2   # let the rover bridge spawn the scene before the mirror moves drones
  fi
  sleep 1
  AGENT_ID=coordinator ROLE=coordinator SOUL="$ROOT/souls/coordinator.md" \
    start python3 "$ROOT/agent/loop.py" >"$LOG/coordinator.log" 2>&1
  for r in drone-1 drone-2 drone-3 drone-4; do
    AGENT_ID="$r" ROLE=scout BRIDGE_URL="http://localhost:${PORT[$r]}" SOUL="$ROOT/souls/$r.md" \
      start python3 "$ROOT/agent/loop.py" >"$LOG/$r.log" 2>&1
  done
  if [ "$GZ" != "0" ] && [ "$TASK" = "survey" ]; then
    ROVER_BRIDGE_URL="http://localhost:9105"
  else
    ROVER_BRIDGE_URL="http://localhost:${PORT[rover]}"
  fi
  AGENT_ID=rover ROLE=rover BRIDGE_URL="$ROVER_BRIDGE_URL" SOUL="$ROOT/souls/rover.md" \
    start python3 "$ROOT/agent/loop.py" >"$LOG/rover.log" 2>&1
  if [ "$TASK" = "survey" ] && [ "${HEADLESS:-0}" != "1" ]; then
    VIZ_PORT="${VIZ_PORT:-8080}"
    env PORT="$VIZ_PORT" python3 "$ROOT/viz/server.py" >"$LOG/viz.log" 2>&1 & PIDS+=($!)
    echo "survey dashboard: http://localhost:$VIZ_PORT/survey"
  fi
fi

echo "${PIDS[@]}" > "$LOG/pids"
echo "started ${#PIDS[@]} processes (task=$TASK, scenario=$SCENARIO); logs in $LOG"
echo "blackboard: $BLACKBOARD"
