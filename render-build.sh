#!/usr/bin/env bash
set -euo pipefail

python -m pip install -r requirements.txt
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/render/project/src/.cache/ms-playwright}"
python -m playwright install chromium
npm --prefix frontend ci
npm --prefix frontend run build
