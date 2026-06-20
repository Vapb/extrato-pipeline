#!/usr/bin/env bash
# Fluxo: gold JSONs → merchant_map.json
#
# Se merchant_map.json não existir, cria um novo com esqueleto padrão.
# Se existir, adiciona entradas novas sem sobrescrever as existentes.
#
# Entradas em nao_mapear (marketplaces, farmácias, iFood) são ignoradas —
# cada compra é única e deve ser preenchida manualmente no gold.
#
# Uso:
#   bash scripts/40_sync_map.sh
#   bash scripts/40_sync_map.sh --owner person1
#   bash scripts/40_sync_map.sh --month 2026-01
set -euo pipefail

python src/merchant_map.py "$@"
