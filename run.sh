#!/usr/bin/env bash
# One-step install + run.
#   ./run.sh                      # list + details for all consoles
#   ./run.sh list -c nes ps2      # any pricecharter CLI args pass through
#   ./run.sh details --limit 20
#   ./run.sh serve                # web UI on http://127.0.0.1:8000
set -euo pipefail
cd "$(dirname "$0")"

CHROME="${PRICECHARTER_CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
# Only the crawl stages drive Chrome; analyze and serve just read the DB.
if [[ "${1:-all}" != "serve" && "${1:-all}" != "analyze" && ! -x "$CHROME" ]]; then
  echo "Google Chrome is required (the crawler drives real headed Chrome)." >&2
  echo "Install it from https://www.google.com/chrome/ and re-run." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

uv sync --quiet

if [[ $# -eq 0 ]]; then
  set -- all
fi
exec uv run pricecharter "$@"
