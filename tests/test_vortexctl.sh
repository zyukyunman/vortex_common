#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
VCTL="$HERE/deploy/bin/vortexctl"

TMP="$(mktemp -d)"
mkdir -p "$TMP/config" "$TMP/services"
cat > "$TMP/config/vortex.generated.env" <<'EOF'
VORTEX_DATA_PORT=8765
VORTEX_QMT_PORT=8767
VORTEX_BACKTEST_PORT=8766
VORTEX_TRADER_PORT=8768
TZ=Asia/Shanghai
EOF

out="$(VORTEX_GENERATED_ENV="$TMP/config/vortex.generated.env" VORTEX_SERVICES_DIR="$TMP/services" \
       VORTEX_DEBUG_PORTS=1 bash "$VCTL" list 2>&1 || true)"
echo "$out"
echo "$out" | grep -q 'VORTEX_QMT_PORT=8767' || { echo "FAIL: qmt 端口未取自生成 env"; exit 1; }
echo "$out" | grep -q 'VORTEX_BACKTEST_PORT=8766' || { echo "FAIL: backtest 端口未取自生成 env"; exit 1; }
grep -q 'VORTEX_QMT_STATE_DIR' "$VCTL" && { echo "FAIL: 仍有 legacy VORTEX_QMT_STATE_DIR"; exit 1; }
grep -q 'VORTEX_DATA_WORKSPACE' "$VCTL" && { echo "FAIL: 仍有 legacy VORTEX_DATA_WORKSPACE"; exit 1; }
echo "PASS"
