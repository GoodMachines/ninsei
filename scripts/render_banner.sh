#!/bin/sh
# Renders docs/media/banner.png (1200x600, catalog card) and docs/media/social.png (1280x640, GitHub
# social preview) from docs/media/src/banner.html with headless Chrome. Needs network for Google Fonts.
set -eu
cd "$(dirname "$0")/.."
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
SRC="file://$PWD/docs/media/src/banner.html"
render() {
  "$CHROME" --headless=new --hide-scrollbars --force-device-scale-factor=1 --virtual-time-budget=8000 \
    --window-size="$1,$2" --screenshot="$PWD/docs/media/$3" "$SRC?w=$1" >/dev/null 2>&1
  echo "docs/media/$3"
}
render 1200 600 banner.png
render 1280 640 social.png
