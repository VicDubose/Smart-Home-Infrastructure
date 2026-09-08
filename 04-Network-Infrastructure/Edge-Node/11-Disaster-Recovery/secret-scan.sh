#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
PATTERN='BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY|password\s*[:=]\s*[^<[:space:]]|passwd\s*[:=]|bearer [A-Za-z0-9._-]{16,}|api[_-]?key\s*[:=]\s*[A-Za-z0-9._-]{12,}|token\s*[:=]\s*[A-Za-z0-9._-]{16,}'
if grep -RInE --exclude='secret-scan.sh' --exclude-dir='.git' "$PATTERN" "$ROOT"; then
  echo "Potential secret patterns found. Review before commit." >&2
  exit 1
fi
echo "No high-confidence secret patterns found."
