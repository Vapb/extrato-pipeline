#!/usr/bin/env bash
set -euo pipefail

echo "=== Bronze — extração PDF → CSV ==="
python src/bronze.py

echo ""
echo "=== Silver — normalização ==="
python src/silver.py

echo ""
echo "=== Pipeline concluído ==="
