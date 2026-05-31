#!/usr/bin/env bash
set -euo pipefail

RAW_DIR="data/raw_data/santander"
SCRIPT="src/santander_debito.py"

echo "=== Santander Débito — extração ==="

pdfs=("$RAW_DIR"/*santander_debito*.pdf)

if [ ${#pdfs[@]} -eq 0 ] || [ ! -f "${pdfs[0]}" ]; then
    echo "[WARN] Nenhum PDF encontrado em $RAW_DIR"
    exit 0
fi

for pdf in "${pdfs[@]}"; do
    echo ""
    echo "--- $pdf ---"
    python "$SCRIPT" "$pdf"
done

echo ""
echo "=== Concluído ==="
