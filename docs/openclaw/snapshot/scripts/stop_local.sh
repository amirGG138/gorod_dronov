#!/usr/bin/env bash
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
if [ -f .local-logs/pids ]; then
  for p in $(cat .local-logs/pids); do kill "$p" 2>/dev/null || true; done
  rm -f .local-logs/pids
fi
# belt-and-suspenders: kill stragglers, but ONLY ones launched from THIS checkout
# (unscoped `pkill -f agent/loop.py` used to kill unrelated stacks — and never
# touched viz/server.py, which kept port 8080 hostage)
for script in agent/loop.py bridge/mock.py viz/server.py; do
  pkill -f "$ROOT/$script" 2>/dev/null || true
done
echo "stopped."
