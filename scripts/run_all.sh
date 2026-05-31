#!/usr/bin/env bash
set -euo pipefail

SCRIPTS_DIR="$(dirname "$0")"

bash "$SCRIPTS_DIR/00_itau_credito.sh"
bash "$SCRIPTS_DIR/00_itau_debito.sh"
bash "$SCRIPTS_DIR/00_santander_debito.sh"

echo ""
echo "=== Todos os extratos processados ==="
