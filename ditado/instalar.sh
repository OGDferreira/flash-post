#!/usr/bin/env bash
# Instala o Ditado no macOS ou Linux.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
echo "Pronto. Inicie com: $(pwd)/.venv/bin/python $(pwd)/ditado.py"
