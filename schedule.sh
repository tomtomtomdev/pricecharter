#!/usr/bin/env bash
# Weekend crawl schedule (Sat & Sun 01:00 -> 23:00) via launchd.
#   ./schedule.sh install [--start 01:00 --until 23:00]
#   ./schedule.sh status | uninstall | print
set -euo pipefail
cd "$(dirname "$0")"
command -v uv >/dev/null 2>&1 || { curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"; }
uv sync --quiet
exec uv run python -m pricecharter.schedule "${@:-status}"
