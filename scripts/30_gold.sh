#!/usr/bin/env bash
# Aceita --month YYYY-MM e --owner X
set -euo pipefail

python src/pipeline.py --layer gold "$@"
