#!/usr/bin/env bash
# Boot the whole FreightVoice demo with one command:
#   - creates a venv + installs deps on first run
#   - starts the fake TMS (port 5001), seeded with 3 demo loads
#   - starts the FreightVoice middleware + dashboard (port 5000)
#
# Ctrl-C tears both down. Open http://127.0.0.1:5000 for the dashboard,
# then run:  ./.venv/bin/python demo/simulate_call.py
set -euo pipefail
cd "$(dirname "$0")"

# Auto-load a local .env (gitignored) if present, so teammates can drop their
# InsForge creds (or any FREIGHTVOICE_*/FAKETMS_* vars) in one file instead of
# exporting them by hand each run. Values in .env take effect for this run; to
# override once, edit .env (or comment the line and export inline).
if [ -f .env ]; then
  echo "▸ loading .env"
  set -a; . ./.env; set +a
fi

PY=python3
VENV=.venv

if [ ! -d "$VENV" ]; then
  echo "▸ creating virtualenv + installing deps…"
  $PY -m venv "$VENV"
  ./"$VENV"/bin/python -m pip install -q --upgrade pip
  ./"$VENV"/bin/python -m pip install -q -r requirements.txt
fi
PYBIN=./"$VENV"/bin/python

export FAKETMS_URL="${FAKETMS_URL:-http://127.0.0.1:5001}"
export FREIGHTVOICE_TMS="${FREIGHTVOICE_TMS:-fake}"

cleanup() { echo; echo "▸ shutting down…"; kill "${FAKETMS_PID:-}" "${FV_PID:-}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "▸ starting fake TMS on :5001"
$PYBIN -m faketms.app &
FAKETMS_PID=$!

# Wait for the TMS to answer before starting the middleware.
for _ in $(seq 1 30); do
  if curl -sf http://127.0.0.1:5001/health >/dev/null 2>&1; then break; fi
  sleep 0.2
done

echo "▸ starting FreightVoice middleware + dashboard on :5000"
echo "  dashboard → http://127.0.0.1:5000"
$PYBIN -m freightvoice.app &
FV_PID=$!

wait $FV_PID
