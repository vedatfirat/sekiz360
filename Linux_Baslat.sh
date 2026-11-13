#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
HOST=${HOST:-127.0.0.1} PORT=${PORT:-8765} exec .venv/bin/python app.py
