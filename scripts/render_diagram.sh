#!/usr/bin/env bash
# Render docs/architecture.svg to docs/architecture.png.
#
# The SVG is the source and is committed; the PNG is a build product and is
# also committed, because the contest submission and the README both want an
# image and neither can render SVG reliably everywhere.
#
# Headless Chrome is used because this machine has no rsvg-convert, inkscape
# or ImageMagick, and adding a Python imaging dependency to a package that
# deliberately declares zero runtime dependencies would be a poor trade for
# one diagram.
#
#   ./scripts/render_diagram.sh
set -euo pipefail

DOCS="$(cd "$(dirname "${BASH_SOURCE[0]}")/../docs" && pwd)"

CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
if [ ! -x "$CHROME" ]; then
  CHROME="$(command -v google-chrome || command -v chromium || true)"
fi
if [ -z "$CHROME" ] || [ ! -x "$CHROME" ]; then
  echo "no Chrome/Chromium found; set CHROME=/path/to/chrome" >&2
  exit 1
fi

"$CHROME" --headless --disable-gpu --no-sandbox \
  --screenshot="$DOCS/architecture.png" \
  --window-size=1280,1080 \
  --default-background-color=FFFFFFFF \
  --hide-scrollbars \
  "file://$DOCS/architecture.svg" 2>/dev/null

echo "wrote docs/architecture.png"
