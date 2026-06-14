#!/usr/bin/env bash
# Fluxo de atualização: gold JSONs → merchant_map.json
#
# Se merchant_map.json não existir, cria um novo com esqueleto padrão.
# Se existir, adiciona entradas novas sem sobrescrever as existentes.
#
# Entradas em nao_mapear (marketplaces, farmácias, iFood) são ignoradas —
# cada compra é única e deve ser preenchida manualmente no gold.
#
# Uso:
#   bash scripts/sync_merchant_map.sh
#   bash scripts/sync_merchant_map.sh --owner person1
#   bash scripts/sync_merchant_map.sh --month 2026-01

set -euo pipefail

python src/merchant_map.py "$@"
