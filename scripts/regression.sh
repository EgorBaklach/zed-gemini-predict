#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

echo "=== 1. PHP Syntax Check (php -l) ==="
find public src tests -name "*.php" -print0 | xargs -0 -n1 php -l

echo ""
echo "=== 2. PHP Bridge Unit Tests ==="
php tests/run.php

echo ""
echo "=== 3. Live HTTP Endpoint Check (127.0.0.1:8089) ==="
curl -s http://127.0.0.1:8089/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"prompt":"<|fim_prefix|><?php\n\n<|fim_suffix|>\n<|fim_middle|>"}'
echo ""
curl -s http://127.0.0.1:8089/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"prompt":"<|fim_prefix|><?php\n$a = 1;\n<|fim_suffix|>\n<|fim_middle|>"}'
echo ""
