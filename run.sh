#!/usr/bin/env bash
set -euo pipefail

export FREIGHTVOICE_TMS="${FREIGHTVOICE_TMS:-fake}"
export FREIGHTVOICE_FACTORING="${FREIGHTVOICE_FACTORING:-fake}"
export FAKETMS_PORT="${FAKETMS_PORT:-5001}"
export FAKETMS_URL="${FAKETMS_URL:-http://localhost:${FAKETMS_PORT}}"

if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" -m faketms.app &
FAKETMS_PID=$!

"$PYTHON_BIN" -m freightvoice.app &
FREIGHTVOICE_PID=$!

trap 'kill "$FAKETMS_PID" "$FREIGHTVOICE_PID" 2>/dev/null || true' EXIT

echo "Dashboard: http://localhost:${FREIGHTVOICE_PORT:-5000}/dashboard"
echo "FakeTMS:   ${FAKETMS_URL}/state"
wait
