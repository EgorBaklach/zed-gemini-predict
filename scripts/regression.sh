#!/usr/bin/env bash
# Full regression against the RUNNING bridge (deploy first!). Run inside WSL:
#   bash scripts/regression.sh        # emulator x3 (~90k Gemini tokens, ~2 min)
#   bash scripts/regression.sh 1      # one emulator session
set -u
cd "$(dirname "$0")/.."
RUNS="${1:-3}"

echo "=== OFFLINE (no tokens) ==="
python3 tests/test_postprocessor_offline.py | tail -1

echo "=== EMULATOR x$RUNS ==="
python3 tests/simulate_mvc_live_coding.py --runs "$RUNS" > /tmp/sim_full.log 2>&1
echo "exit=$?  (full log: /tmp/sim_full.log)"
awk '/^SUMMARY/{f=1} f' /tmp/sim_full.log
echo "--- distinct problems ---"
grep -E '!!|keeps writing|^❌' /tmp/sim_full.log | sed 's/([0-9]* ms)//' | sort | uniq -c

echo "=== DETERMINISM ==="
python3 tests/test_determinism.py > /tmp/det.log
echo "OK: $(grep -c '^\[OK' /tmp/det.log)/26"
grep FAIL /tmp/det.log

echo "=== PHP / PHP 8.3 cases (review answers by eye) ==="
python3 tests/test_php_cases.py | grep -E '^\[|>>>'
python3 tests/test_php83_cases.py | grep -E '^\[|>>>'
