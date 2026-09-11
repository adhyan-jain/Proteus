#!/usr/bin/env bash
# Stage 5 smoke test -- this is the check Stage 0 originally asked for: bring up the trivial
# Mininet topology, confirm it starts and tears down cleanly, confirm the Ryu controller
# attaches, and inject a known-benign and a known-attack-like traffic sample through the
# controller path.
#
# REQUIRES ROOT (Mininet creates network namespaces at runtime) and cannot be run by an agent
# session in this repo -- no sudo access is available there (see STATUS.md). Run this yourself:
#
#   sudo bash sdn/topology/smoke_test.sh
#
# What happens, step by step:
#   1. Starts the Ryu controller (.venv-ryu/bin/ryu-manager, this repo's app) in the background,
#      logging to /tmp/proteus_ryu_smoke.log.
#   2. Starts the 4-host/2-switch Mininet topology (topo.py, system python3 -- Mininet is
#      installed there, not in .venv-ryu) pointed at that controller, non-interactively
#      (--no-cli), which runs a pingAll as its own built-in connectivity check.
#   3. Runs gen_traffic.py inside h1's namespace: a "benign" burst of spaced TCP connects to h3,
#      then an "attack-like" fast multi-port scan of h3 -- both routed through s1/s2/the
#      controller, so the Ryu app's periodic flow-stats poll (every 10s, see
#      ryu_ids_app.py's POLL_INTERVAL_SEC) picks up both flows.
#   4. Waits long enough for at least one flow-stats poll cycle, then tears everything down and
#      reports pass/fail.
#
# WHAT SUCCESS LOOKS LIKE:
#   - Step 2's pingAll reports 0% packet loss (topo.py prints this explicitly). Non-zero loss
#     means the controller never attached or isn't installing forwarding flows -- check
#     /tmp/proteus_ryu_smoke.log for "datapath connected: ...".
#   - /tmp/proteus_ryu_smoke.log contains "datapath connected: 0000000000000001" and
#     "...0000000000000002" (both switches attached).
#   - /tmp/proteus_ryu_smoke.log contains at least one "[schema-row] dpid=... flow=... -> {...}"
#     line per switch after the traffic step, with non-empty dicts containing keys like
#     flow_duration/protocol/dst_port/total_fwd_packet (confirms feature_mapper.py's live export
#     path is working end-to-end, not just unit-tested).
#   - The script exits 0 and prints "SMOKE TEST PASSED".
#
# WHAT FAILURE LOOKS LIKE (and where to look):
#   - "mn: command not found" / import errors -- Mininet isn't actually installed/working;
#     re-check `mn --version`.
#   - pingAll loss > 0% -- see /tmp/proteus_ryu_smoke.log; if no "datapath connected" lines
#     appear at all, the switches couldn't reach the controller (check controller IP/port,
#     firewall, or that ryu-manager actually started -- see /tmp/proteus_ryu_smoke.log's tail
#     for a Python traceback if it crashed on load).
#   - No "[schema-row]" lines -- either no traffic reached a flow the poller catches (unlikely
#     given step 3), or the 10s poll interval hasn't elapped yet (rare -- the wait in step 4 is
#     sized for this).

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "This script needs root (Mininet requires it at runtime). Run: sudo bash $0" >&2
    exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RYU_LOG="/tmp/proteus_ryu_smoke.log"
RYU_BIN="$REPO_ROOT/.venv-ryu/bin/ryu-manager"
APP="$REPO_ROOT/sdn/topology/ryu_ids_app.py"
TOPO="$REPO_ROOT/sdn/topology/topo.py"

if [[ ! -x "$RYU_BIN" ]]; then
    echo "FAIL: $RYU_BIN not found -- run sdn/setup_ryu_venv.sh first (per STATUS.md, this is" >&2
    echo "already done on this machine as of the last handoff, but check)." >&2
    exit 1
fi

if ! command -v mn >/dev/null 2>&1; then
    echo "FAIL: 'mn' not found -- Mininet isn't installed. See STATUS.md's Blocked section." >&2
    exit 1
fi

echo "=== Cleaning up any stale Mininet state ==="
mn -c >/dev/null 2>&1 || true

echo "=== Starting Ryu controller (log: $RYU_LOG) ==="
: > "$RYU_LOG"
"$RYU_BIN" --verbose "$APP" >"$RYU_LOG" 2>&1 &
RYU_PID=$!
trap 'kill "$RYU_PID" 2>/dev/null || true; mn -c >/dev/null 2>&1 || true' EXIT

sleep 3
if ! kill -0 "$RYU_PID" 2>/dev/null; then
    echo "FAIL: Ryu controller exited immediately. Log tail:" >&2
    tail -30 "$RYU_LOG" >&2
    exit 1
fi
echo "Ryu controller running (pid $RYU_PID)"

echo "=== Starting Mininet topology (pingAll, non-interactive) ==="
python3 "$TOPO" --no-cli

echo "=== Injecting benign + attack-like traffic (h1 -> h3) ==="
python3 - "$REPO_ROOT" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1] + "/sdn/topology")
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, RemoteController
from mininet.link import TCLink
from mininet.log import setLogLevel
from topo import ProteusTopo

setLogLevel("info")
net = Mininet(topo=ProteusTopo(), switch=OVSKernelSwitch, link=TCLink,
              controller=None, autoSetMacs=True)
net.addController("c0", controller=RemoteController, ip="127.0.0.1", port=6653)
net.start()
h1, h3 = net.get("h1"), net.get("h3")
script = sys.argv[1] + "/sdn/topology/gen_traffic.py"
print(h1.cmd(f"python3 {script} benign 10.0.0.3"))
print(h1.cmd(f"python3 {script} attack-like 10.0.0.3"))
net.stop()
PYEOF

echo "=== Waiting for a flow-stats poll cycle (12s) ==="
sleep 12

kill "$RYU_PID" 2>/dev/null || true
wait "$RYU_PID" 2>/dev/null || true
trap - EXIT
mn -c >/dev/null 2>&1 || true

echo "=== Checking results in $RYU_LOG ==="
CONNECTED=$(grep -c "datapath connected" "$RYU_LOG" || true)
SCHEMA_ROWS=$(grep -c "\[schema-row\]" "$RYU_LOG" || true)

echo "datapath connected lines: $CONNECTED"
echo "schema-row export lines: $SCHEMA_ROWS"

if [[ "$CONNECTED" -ge 2 && "$SCHEMA_ROWS" -ge 1 ]]; then
    echo "SMOKE TEST PASSED"
    exit 0
else
    echo "SMOKE TEST FAILED -- see $RYU_LOG for detail" >&2
    exit 1
fi
