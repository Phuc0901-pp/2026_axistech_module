#!/usr/bin/env bash
set -euo pipefail

# Map Render dynamic PORT and internal loopback Bridge defaults
export ERP_PORT="${PORT:-10000}"
export BRIDGE_BASE_URL="http://127.0.0.1:8001"
export BRIDGE_API_KEY="${BRIDGE_API_KEY:-${AXISSTREAM_INBOUND_API_KEY:-render-internal-bridge-key}}"
export AXISSTREAM_INBOUND_API_KEY="${AXISSTREAM_INBOUND_API_KEY:-$BRIDGE_API_KEY}"
export AXISSTREAM_SQLITE_PATH="${AXISSTREAM_SQLITE_PATH:-/data/bridge_state.db}"
export ERP_DATA_FILE_PATH="${ERP_DATA_FILE_PATH:-/data/erp_state.json}"

# Auto-fallback to demo mode on initial deploy if live credentials are not yet configured
if [ "${AXISSTREAM_MODE:-demo}" = "live" ]; then
  if [ -z "${AXISSTREAM_AXISSTREAM_USERNAME:-}" ] || [[ "${AXISSTREAM_AXISSTREAM_USERNAME}" == CHANGE_ME* ]]; then
    echo "[entrypoint] AXISSTREAM_AXISSTREAM_USERNAME not configured yet -> starting in 'demo' mode until credentials are set."
    export AXISSTREAM_MODE="demo"
  fi
fi

UVICORN_LOG_LEVEL="$(printf '%s' "${AXISSTREAM_LOG_LEVEL:-info}" | tr '[:upper:]' '[:lower:]')"
echo "[entrypoint] Starting Python AxisTech Bridge on 127.0.0.1:8001 (mode=${AXISSTREAM_MODE:-demo})..."
uvicorn axisstream_bridge.interfaces.api.app:app \
  --host 127.0.0.1 \
  --port 8001 \
  --log-level "$UVICORN_LOG_LEVEL" &
BRIDGE_PID=$!

cleanup() {
  if kill -0 "$BRIDGE_PID" 2>/dev/null; then
    kill "$BRIDGE_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

for i in $(seq 1 40); do
  if curl -fsS http://127.0.0.1:8001/health/ready >/dev/null 2>&1; then
    echo "[entrypoint] Bridge is ready (${i}/40). Starting Go ISO ERP on :${ERP_PORT}..."
    exec /erp-server
  fi
  if ! kill -0 "$BRIDGE_PID" 2>/dev/null; then
    echo "[entrypoint] Bridge exited prematurely." >&2
    exit 1
  fi
  sleep 0.5
done

echo "[entrypoint] Timed out waiting for Bridge /health/ready." >&2
exit 1
