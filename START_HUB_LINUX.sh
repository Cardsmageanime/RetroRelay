#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install -r requirements.txt
export RETRORELAY_HOST="${RETRORELAY_HOST:-127.0.0.1}"
exec .venv/bin/python server.py
