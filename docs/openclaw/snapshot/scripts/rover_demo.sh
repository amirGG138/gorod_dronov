#!/usr/bin/env bash
# Демо-пульт ровера: поднимает мост к РЕАЛЬНОМУ роверу (sverk_rover, control
# API v1) + мок-дрон + веб-пульт /demo, где полем можно рулить руками через те
# же HTTP-эндпоинты, которыми пользуются LLM-агенты.
#
#   bash scripts/rover_demo.sh              # ровер на 192.168.4.9 + мок-дрон
#   ROVER_IP=192.168.1.50 bash scripts/rover_demo.sh
#   bash scripts/rover_demo.sh --stop       # погасить всё
#
# Открыть: http://localhost:8097/demo
# Логи:    /tmp/openclaw-demo/*.log
set +e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROVER_IP="${ROVER_IP:-192.168.4.9}"
PORT="${DEMO_PORT:-8097}"
ROVER_BRIDGE_PORT="${ROVER_BRIDGE_PORT:-9106}"
DRONE_BRIDGE_PORT="${DRONE_BRIDGE_PORT:-9101}"   # первый борт, дальше +1
DRONES="${DRONES:-4}"                            # штатный флот города дронов
SCENARIO="${SCENARIO:-survey-1}"                 # поле 5×5
TASK="${TASK:-survey}"
RUN=/tmp/openclaw-demo
BB="$RUN/blackboard"

# привязка сетки к SLAM-карте ровера (можно менять прямо в пульте)
MAP_X0="${MAP_X0:--0.46}" MAP_Y0="${MAP_Y0:--0.15}"
CELL_SIZE="${CELL_SIZE:-0.6}" GRID_NX="${GRID_NX:-5}" GRID_NY="${GRID_NY:-5}"

say(){ echo -e "\n=== $* ==="; }
kill_by(){ for p in $(pgrep -f "$1" 2>/dev/null); do kill "$p" 2>/dev/null; done; }

stop_all(){
  kill_by "sverk_rover_brid""ge.py"
  kill_by "bridge/moc""k.py"
  kill_by "viz/serve""r.py"
  echo "остановлено"
}

if [ "$1" = "--stop" ] || [ "$1" = "stop" ]; then stop_all; exit 0; fi

say "0/4  проверка связи с ровером $ROVER_IP"
if ! ping -c1 -W2 "$ROVER_IP" >/dev/null 2>&1; then
  echo "!! ровер $ROVER_IP не пингуется."
  echo "   - ровер включён? он и ноутбук в ОДНОЙ сети (его wifi)?"
  if ip route get "$ROVER_IP" 2>/dev/null | grep -q mullvad; then
    echo "   - !! маршрут уходит в Mullvad VPN: выключи VPN (allow-LAN не спасает"
    echo "        для чужой подсети) и запусти скрипт заново"
  fi
  echo "   пульт всё равно поднимется — ровер будет 'недоступен', мок-дрон живой"
else
  H=$(curl -s --max-time 4 "http://$ROVER_IP:8767/v1/health")
  echo "control API: ${H:-НЕ ОТВЕЧАЕТ (:8767) — на ровере поднят rover-bringup?}"
fi

say "1/4  чистим прошлый запуск"
stop_all
mkdir -p "$BB/artifacts" "$RUN"
sleep 1

say "2/4  мост к реальному роверу :$ROVER_BRIDGE_PORT -> $ROVER_IP:8767"
cd "$ROOT" || exit 1
PORT="$ROVER_BRIDGE_PORT" ROVER_API="http://$ROVER_IP:8767" \
  MAP_X0="$MAP_X0" MAP_Y0="$MAP_Y0" CELL_SIZE="$CELL_SIZE" \
  GRID_NX="$GRID_NX" GRID_NY="$GRID_NY" \
  nohup python3 bridge/sverk_rover_bridge.py > "$RUN/rover_bridge.log" 2>&1 &

say "3/4  мок-дроны: $DRONES бортов с :$DRONE_BRIDGE_PORT (поле не только про ровера)"
BRIDGES=""
for i in $(seq 1 "$DRONES"); do
  p=$((DRONE_BRIDGE_PORT + i - 1))
  BLACKBOARD="$BB" FIXTURES="$ROOT/test_fixtures" SCENARIO="$SCENARIO" \
    AGENT_ID="drone-$i" PORT="$p" \
    nohup python3 bridge/mock.py > "$RUN/drone_bridge_$i.log" 2>&1 &
  BRIDGES="$BRIDGES,drone-$i=http://localhost:$p"
done

say "4/4  пульт :$PORT"
PYTHONPATH="$ROOT/agent" BLACKBOARD="$BB" FIXTURES="$ROOT/test_fixtures" \
  SCENARIO="$SCENARIO" TASK="$TASK" PORT="$PORT" \
  DEMO_BRIDGES="${BRIDGES#,},rover=http://localhost:$ROVER_BRIDGE_PORT" \
  nohup python3 viz/server.py > "$RUN/viz.log" 2>&1 &

sleep 3
echo
curl -s --max-time 5 "http://localhost:$ROVER_BRIDGE_PORT/healthz" | head -c 400; echo
echo "--------------------------------------------------------------"
echo " ПУЛЬТ:  http://localhost:$PORT/demo"
echo " логи:   $RUN/*.log        стоп: bash scripts/rover_demo.sh --stop"
echo "--------------------------------------------------------------"
