#!/usr/bin/env bash
# Regenerate every result file and table used in paper/main.tex from the raw data, then compare with the committed
# files. Run from anywhere:  research/insdn_controller/reproduce.sh [OUT_DIR]   (default: research/insdn_controller/repro_out)
# Needs: the repo .venv (GPU torch + xgboost), data fetched as described in data/MANIFEST.md, and the live captures
# whose hashes are in capture_hashes.sha256. No root needed (re-recording the live captures needs root: see README.md).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
OUT="${1:-$HERE/repro_out}"; mkdir -p "$OUT/res"
PY="$ROOT/.venv/bin/python"; PCAPS="$ROOT/data/raw/insdn_pcaps"
cd "$HERE"
"$PY" -c "import torch; assert torch.cuda.is_available(), 'GPU required (CLAUDE.md rule 1)'"

echo "== 0. verify raw-capture hashes"
(cd "$PCAPS" && sha256sum -c "$HERE/capture_hashes.sha256" 2>/dev/null | grep -v '^live/' | grep -c ': OK' | sed 's/^/InSDN ONOS+archives OK: /')
sha256sum -c capture_hashes.sha256 2>/dev/null | grep '^live/' | grep -c ': OK' | sed 's/^/live captures OK: /'

echo "== 1. InSDN: attack-only IPs, controller features (44 ONOS captures, W=1 s and 5 s)"
"$PY" -I ofgap/attacker_ips.py
"$PY" -I ofgap/ctrlfeat.py "$PCAPS/ex" "$OUT/feats" > "$OUT/ctrlfeat.log"

echo "== 2. detection experiments (GPU, 10 seeds)"
"$PY" -I ofgap/exp_ctrl2.py "$OUT/feats" "$OUT/res/v4_strict_W1.json"   --W 1 --labels strict
"$PY" -I ofgap/exp_ctrl2.py "$OUT/feats" "$OUT/res/v4_strict_W5_xgb.json" --W 5 --labels strict
"$PY" -I ofgap/exp_ctrl2.py "$OUT/feats" "$OUT/res/v4_iprule_W1.json"   --W 1 --labels iprule
"$PY" -I ofgap/exp_ctrl2.py "$OUT/feats" "$OUT/res/v4_iprule_W5.json"   --W 5 --labels iprule

echo "== 3. granularity, PacketIn ratio, validity checks"
"$PY" -I ofgap/flowmod_check.py "$PCAPS/ex" "$OUT/res/flowmod_matches.json" > /dev/null
"$PY" -I ofgap/gap_measure.py   "$PCAPS/ex" "$OUT/res/gap_attack_v2.json" > /dev/null
"$PY" -I ofgap/review_checks.py "$OUT/feats" "$OUT/res/review_checks.json" > /dev/null

echo "== 4. Mininet/Ryu forwarding study (analysis of recorded captures)"
"$PY" -I live/live_table.py live/campaign2   "$OUT/res/live_modes_v4_one10.json"   "$OUT/live_table.tex"         "" tab:live > /dev/null
"$PY" -I live/live_table.py live/out_linear3 "$OUT/res/live_modes_v4_linear3.json" "$OUT/live_table_linear3.tex" "" tab:live_l3 > /dev/null
"$PY" -I ofgap/flowmod_stock.py live/out_stock "$OUT/res/stock_ryu_flowmods.json" > /dev/null
# flawed first campaign (live_modes_v2.json): captures not retained; the committed JSON is the record (see README.md)
cp results/live_modes_v2.json "$OUT/res/"

echo "== 5. host-side flow-CSV baseline (GPU)"
(cd "$ROOT" && "$PY" research/insdn_controller/ofgap/hostside_baseline.py "$OUT/res/hostside_xgb.json" > /dev/null)
(cd "$ROOT" && "$PY" research/insdn_controller/ofgap/protocol_inflation.py "$OUT/res/protocol_inflation.json" > /dev/null)
(cd "$ROOT" && "$PY" research/insdn_controller/ofgap/protocol_audit.py --dataset insdn --out "$OUT/res/protocol_audit_insdn.json" > /dev/null)
(cd "$ROOT" && "$PY" research/insdn_controller/ofgap/protocol_audit.py --dataset cicids2017 --out "$OUT/res/protocol_audit_cicids2017.json" > /dev/null)
(cd "$ROOT" && "$PY" research/insdn_controller/ofgap/recipe_replication.py "$OUT/res/recipe_replication.json" > /dev/null)

"$PY" -I ofgap/make_figures.py "$OUT" > /dev/null   # paper figures from results/*.json

echo "== 6. tables and comparison"
"$PY" -I ofgap/make_tables.py "$OUT/res/v4_strict_W1.json" "$OUT/res/gap_attack_v2.json" "$OUT/feats/meta.json" \
      "$OUT/tables.tex" "$OUT/res/review_checks.json" > /dev/null
cmp "$OUT/tables.tex" paper/tables.tex && echo "tables.tex identical"
cmp "$OUT/live_table.tex" paper/live_table.tex && cmp "$OUT/live_table_linear3.tex" paper/live_table_linear3.tex && echo "live tables identical"
"$PY" -I ofgap/compare_results.py "$OUT/res"
"$PY" paper/verify_numbers.py | grep -c '^OK' | sed 's/^/paper numbers verified against results\/*.json: /'
