#!/usr/bin/env bash
# Poll the running stack until phase=DONE, then print the verdict.
# Exit 0 on success, 1 on timeout/FAIL. Used by the `make demo*` targets.
#
#   DC        = compose invocation that holds /blackboard (default "docker compose")
#   WAIT_SVC  = service to exec into (default viz; hub in distributed mode)
#   PAINTING  = 1 for the painters scenario (success = DONE with a painting result;
#               no rover gate)
#   TIMEOUT   = seconds before giving up (default 180)
set -uo pipefail
cd "$(dirname "$0")/.."

DC=${DC:-docker compose}
SVC=${WAIT_SVC:-viz}
PAINTING=${PAINTING:-0}
DEADLINE=$(( $(date +%s) + ${TIMEOUT:-180} ))
read_state='import json
def g(p):
 try:
  return json.load(open(p))
 except Exception:
  return {}
ph=g("/blackboard/state/phase.json").get("phase","?")
dec=g("/blackboard/state/decision.json").get("result")
rp=g("/blackboard/state/progress/rover.json")
print(ph, dec, rp.get("arrived"))'

while :; do
  out=$($DC exec -T "$SVC" python -c "$read_state" 2>/dev/null || true)
  phase=$(echo "$out" | awk '{print $1}')
  echo "  phase=${phase:-starting} verdict=$(echo "$out" | cut -d' ' -f2-)"
  if [ "$phase" = "DONE" ]; then
    if [ "$PAINTING" = "1" ]; then
      # the coordinator writes the verdict in Russian («Картина готова: …») —
      # the old English-only grep made every docker painters demo exit FAIL
      echo "$out" | grep -qiE "complete|готова" && { echo "✅ DONE — canvas painted. Dashboard: http://localhost:${VIZ_HOST_PORT:-8095}"; exit 0; }
      echo "❌ DONE but painting not complete"; exit 1
    fi
    echo "$out" | grep -q "PASS" && { echo "✅ DONE — PASS, rover arrived. Dashboard: http://localhost:${VIZ_HOST_PORT:-8095}"; exit 0; }
    echo "❌ DONE but not PASS"; exit 1
  fi
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then
    echo "⏱  timeout waiting for DONE"; exit 1
  fi
  sleep 3
done
