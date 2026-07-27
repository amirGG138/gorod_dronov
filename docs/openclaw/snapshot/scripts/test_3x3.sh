#!/usr/bin/env bash
# test-3x3 scan_debate: ONE flyer bort scans a 3×3 field; TWO pilot agents argue
# (live LLM) over the route; the operator switches the helm in a pause. No rover,
# no fire/delivery — a clean end-to-end smoke test of the whole stack.
#
#   bash scripts/test_3x3.sh                 # mock brain (offline, deterministic)
#   MODEL_PROVIDER=sverk bash scripts/test_3x3.sh   # live-LLM dispute
#
# Real bort: uncomment flyer BRIDGE_URL in docker-compose.test.yml + run
# bridge/real_bridge.py at fleet:9001 (see docs/test-3x3.md). Without a bort the
# flyer SIMULATES the flight so the dashboard still animates the path.
set +e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CF="-f $ROOT/docker-compose.yml -f $ROOT/docker-compose.test.yml"
VOL=openclaw-stack_blackboard
PORT="${VIZ_HOST_PORT:-8095}"
say(){ echo -e "\n=== $* ==="; }
set -a; [ -f "$ROOT/.env" ] && . "$ROOT/.env"; set +a

say "1/4  build images (scan_debate agent code + Test Front)"
docker compose $CF build coordinator viz 2>&1 | tail -4

say "2/4  reset the blackboard"
docker compose $CF stop coordinator pilot-a pilot-b flyer viz >/dev/null 2>&1
docker run --rm -v "$VOL:/bb" alpine sh -lc \
  'rm -rf /bb/state /bb/messages /bb/progress /bb/events.jsonl /bb/.seq' >/dev/null 2>&1

say "3/4  up: coordinator + pilot-a + pilot-b + flyer + viz  (brain: ${MODEL_PROVIDER:-mock})"
docker compose $CF up -d --force-recreate coordinator pilot-a pilot-b flyer viz 2>&1 | tail -6

say "4/4  watch phase (~40s: DEBATE -> SCAN -> DONE)"
for t in $(seq 1 16); do
  ph=$(docker run --rm -v "$VOL:/bb" alpine sh -lc \
        'grep -oE "\"phase\":\"[A-Z]+\"" /bb/events.jsonl 2>/dev/null | tail -1')
  echo "  t=$((t*3))s ${ph:-—}"
  echo "$ph" | grep -q DONE && break
  sleep 3
done

echo
echo "Test Front:  http://localhost:$PORT/test    (или '/' — авто-роут по сценарию)"
echo "Живой спор:  перезапусти с  MODEL_PROVIDER=sverk bash scripts/test_3x3.sh"
echo "Переключение: ⏸ Пауза -> отдать руль другому пилоту -> ▶ -> дрон летит по его пути."
echo "Реальный борт: docs/test-3x3.md"
