#!/usr/bin/env bash
# Read-only dashboard for preview/screenshot on an alternate port, pointed at the
# live ./blackboard written by a running `make local-city` stack. Not part of the
# product flow — a harness helper for verifying the UI.
set -euo pipefail
cd "$(dirname "$0")/.."
export BLACKBOARD="$PWD/blackboard"
export FIXTURES="$PWD/test_fixtures"
export SCENARIO="${SCENARIO:-city-1}"
export TASK="${TASK:-city_missions}"
export PORT="${PREVIEW_PORT:-8091}"
export FLEET_BRIDGE_HOST="${FLEET_BRIDGE_HOST:-localhost}"
export PYTHONPATH="$PWD/agent"
exec python3 viz/server.py
