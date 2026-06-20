#!/usr/bin/env bash
# Roda toda a pipeline: bronze → silver → gold → sync_map
# --owner X   filtra por owner em todas as camadas
# --month YYYY-MM   só afeta o gold
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"

bash "$SCRIPTS_DIR/10_bronze.sh" "$@"
bash "$SCRIPTS_DIR/20_silver.sh" "$@"
bash "$SCRIPTS_DIR/30_gold.sh" "$@"
bash "$SCRIPTS_DIR/40_sync_map.sh" "$@"
