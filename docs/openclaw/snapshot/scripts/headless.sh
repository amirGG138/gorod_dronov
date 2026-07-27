#!/usr/bin/env bash
# Headless run: запускает сценарий БЕЗ фронта (viz), ждёт DONE и печатает
# текстовый разбор — что дроны увидели, какой вердикт, какие артефакты и
# примеры реплик (чтобы глазами проверить, что нейронки говорят по-русски).
#
# Зачем: фронт (frontend-recovered/dist) устарел и не рисует поле города
# дронов; бэкенд при этом работает. Этот режим показывает реальную работу
# протокола без браузера.
#
#   TASK=safe_passage|survey|painting|debate   (по умолчанию safe_passage)
#   SCENARIO=scenario-1|survey-1|...            (по умолчанию под TASK)
#   MODEL_PROVIDER=mock|sverk|...               (по умолчанию из .env, иначе mock)
#   TIMEOUT=60                                  (сек ожидания DONE)
#
# Пример: make headless                       — город дронов, mock-мозг
#         MODEL_PROVIDER=sverk make headless   — реальный мозг (проверить русский)
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

export TASK="${TASK:-safe_passage}"
export HEADLESS=1                      # флаг для run_local: не поднимать viz
TIMEOUT="${TIMEOUT:-60}"

echo "== headless: task=$TASK scenario=${SCENARIO:-auto} brain=${MODEL_PROVIDER:-<.env/mock>} =="
bash scripts/stop_local.sh >/dev/null 2>&1 || true
rm -rf "$ROOT/blackboard/events.jsonl" "$ROOT/blackboard/state" 2>/dev/null || true

bash scripts/run_local.sh >/tmp/headless-start.log 2>&1
BB="$ROOT/blackboard"

DEADLINE=$(( $(date +%s) + TIMEOUT ))
phase="?"
while :; do
  phase=$(python3 -c "import json;print(json.load(open('$BB/state/phase.json'))['phase'])" 2>/dev/null || echo "?")
  printf "\r  phase=%-10s" "$phase"
  [ "$phase" = "DONE" ] && { echo; break; }
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then echo; echo "⏱  timeout (phase=$phase)"; break; fi
  sleep 2
done

python3 - "$BB" <<'PY'
import json, sys, collections, pathlib
bb = pathlib.Path(sys.argv[1])
def load(p, d=None):
    try: return json.load(open(bb/p))
    except Exception: return d
ev = []
try:
    for line in open(bb/"events.jsonl", encoding="utf-8"):
        line=line.strip()
        if line: ev.append(json.loads(line))
except FileNotFoundError:
    pass

print("\n=== РАЗБОР ПРОГОНА (headless) ===")
ph = load("state/phase.json", {})
dec = load("state/decision.json", {})
print(f"phase   : {ph.get('phase','?')}")
print(f"вердикт : {dec.get('result') or '(нет)'}")

kinds = collections.Counter(e.get("kind") for e in ev)
print(f"событий : {len(ev)}  " + " ".join(f"{k}={v}" for k,v in kinds.most_common()))

arts = [e for e in ev if e.get("kind")=="artifact"]
if arts:
    print(f"\nсканы секторов ({len(arts)}):")
    for a in arts:
        print(f"  {a.get('from')} -> сектор {a.get('sector')}  ({a.get('path')})")

# что дроны «увидели»: реплики/сообщения с признаками детекций
msgs = [e for e in ev if e.get("kind")=="message"]
if msgs:
    print(f"\nреплики агентов ({len(msgs)}), первые 12:")
    for m in msgs[:12]:
        who = m.get("from") or m.get("id") or "?"
        txt = (m.get("body") or m.get("text") or m.get("line") or m.get("content") or "").replace("\n"," ").strip()
        if txt: print(f"  [{who}] {txt[:120]}")

# проверка языка: считаем ТОЛЬКО реплики агентов (то, что нейронки «говорят»).
# Служебные строки координатора/ровера — фиксированный английский каркас
# протокола (не вывод LLM), поэтому в метрику их не берём.
lines = [ (m.get("from"), (m.get("body") or "")) for m in msgs ]
llm_lines = [t for who,t in lines if who not in ("coordinator","rover") and t]
blob = " ".join(llm_lines)
cyr = sum('а' <= c.lower() <= 'я' or c.lower()=='ё' for c in blob)
lat = sum('a' <= c.lower() <= 'z' for c in blob)
tot = cyr+lat
if tot:
    ok = cyr > lat
    print(f"\nязык реплик дронов: кириллица {100*cyr//tot}% / латиница {100*lat//tot}%"
          + ("  ✅ нейронки говорят по-русски" if ok
             else "  ⚠️ латиница преобладает (mock-мозг не генерит текст — проверяйте с MODEL_PROVIDER=sverk)"))
else:
    print("\nязык: реплик от LLM нет (mock-мозг). Запустите MODEL_PROVIDER=sverk make headless")
PY

echo
echo "логи агентов: $ROOT/.local-logs   |  остановить: make stop-local"
bash scripts/stop_local.sh >/dev/null 2>&1 || true
