#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v uv >/dev/null 2>&1; then
  echo "Errore: uv non trovato."
  echo
  echo "Arch Linux:"
  echo "  sudo pacman -S uv"
  echo
  echo "Installer ufficiale:"
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

uv sync
uv run --frozen --dev python tools/build.py
