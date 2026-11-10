#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

echo "=== 1. PHP Syntax Check (php -l) ==="
find public src tests -name "*.php" -print0 | xargs -0 -n1 php -l

echo ""
echo "=== 2. PHP Bridge Unit Tests ==="
php tests/run.php
