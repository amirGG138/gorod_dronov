#!/usr/bin/env bash
# Debug dashboard test: mock flight + real messages, no real drone.
#
#   bash scripts/test_debug.sh
#   open http://localhost:8095/debug
#
# Requires .env with SVERK_API_KEY for live LLM agents.
set +e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CF="-f $ROOT/docker-compose.yml -f $ROOT/docker-compose.debug.yml"
VOL=openclaw-stack_blackboard
PORT="${VIZ_HOST_PORT:-8095}"
say(){ echo -e "\n=== $* ==="; }
set -a; [ -f "$ROOT/.env" ] && . "$ROOT/.env"; set +a

say "1/4  build images"
docker compose $CF build viz 2>&1 | tail -3

say "2/4  reset blackboard + fix soul permissions"
chmod 666 "$ROOT/test_fixtures/souls/"*.md 2>/dev/null || true
docker compose $CF stop coordinator pilot-a pilot-b flyer viz mock >/dev/null 2>&1
docker run --rm -v "$VOL:/bb" alpine sh -lc \
  'rm -rf /bb/state /bb/messages /bb/progress /bb/events.jsonl /bb/.seq' >/dev/null 2>&1

say "3/4  up: mock bridge + coordinator + 2 pilots + flyer + viz"
docker compose $CF up -d --force-recreate mock coordinator pilot-a pilot-b flyer viz 2>&1 | tail -6

say "4/4  health checks"
for t in $(seq 1 10); do
  status=$(curl -s --max-time 3 "http://localhost:$PORT/healthz" 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('ok','?'))" 2>/dev/null)
  if [ "$status" = "True" ]; then echo "  viz UP"; break; fi
  echo "  wait viz ($t/10)…"; sleep 2
done

# check debug page loads
curl -s --max-time 3 "http://localhost:$PORT/debug" 2>/dev/null | grep -q "Debug Dashboard" && echo "  debug.html OK" || echo "  debug.html MISSING"

# check souls API
curl -s --max-time 3 "http://localhost:$PORT/debug/souls" 2>/dev/null | python3 -c "import sys,json;d=json.load(sys.stdin);print(f'  souls: {len(d)} files')" 2>/dev/null || echo "  souls API FAIL"

# check mock bridge
curl -s --max-time 3 "http://localhost:9001/healthz" 2>/dev/null && echo "  mock bridge OK" || echo "  mock bridge DOWN"

echo
echo "🐛 Debug Dashboard:  http://localhost:$PORT/debug"
echo "   Вкладки: Souls (редактировать души) · Control (Re-run/Pause/Step) · Live (поле+чат)"
echo "   Re-run без полёта: жми ⟲ Re-run — координатор перезапустит фазу с новыми душами"
