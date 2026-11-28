#!/usr/bin/env bash
# Install the newest VANTA app (or a given .ipa) on an iPhone connected to this server via USB.
# Signing uses the free Apple ID that was set up once with "xtool auth".
#
# Usage:
#   vanta-app-update.sh            # newest release from GitHub
#   vanta-app-update.sh app.ipa    # a local .ipa, e.g. a test build from a pull request
set -euo pipefail

REPO="${VANTA_REPO:-ITPetya/VANTA}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if ! command -v xtool >/dev/null 2>&1; then
  echo "xtool fehlt, siehe docs/APP-PER-USB.md" >&2
  exit 1
fi

if ! idevice_id -l | grep -q .; then
  echo "Kein iPhone per USB gefunden. Kabel prüfen, iPhone entsperren, \"Vertrauen\" bestätigen." >&2
  exit 1
fi

if [ "${1:-}" != "" ]; then
  IPA="$1"
else
  IPA="$WORK/VANTA.ipa"
  echo "Lade neueste VANTA-Version ..."
  curl -fsSL -o "$IPA" "https://github.com/$REPO/releases/latest/download/VANTA.ipa"
fi

echo "Signiere und installiere $(basename "$IPA") ..."
xtool install "$IPA"
echo "Fertig. VANTA ist installiert und 7 Tage gültig."
