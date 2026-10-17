#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -r requirements-client.txt || echo 'Optional gamepad scan unavailable: install pygame to enable it.'
exec .venv/bin/python client.py
