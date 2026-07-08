#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

fail() {
  echo
  echo "Errore: $1"
  exit 1
}

echo "[check] verifico i prerequisiti"

if ! command -v uv >/dev/null 2>&1; then
  echo
  echo "Errore: uv non trovato."
  echo
  echo "Arch Linux:"
  echo "  sudo pacman -S uv"
  echo
  echo "Installer ufficiale:"
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

echo "[ok] $(uv --version)"

if ! PYTHON_VERSION=$(uv python find --show-version 2>/dev/null); then
  echo
  echo "Errore: non trovo un Python compatibile con il progetto."
  echo
  echo "Soluzioni possibili:"
  echo "  uv python install 3.13"
  echo "  oppure installa Python 3.11+ da https://www.python.org/downloads/"
  exit 1
fi

echo "[ok] Python $PYTHON_VERSION"

echo
echo "[sync] preparo l'ambiente Python"
uv sync || fail "uv sync non riuscito. Controlla la connessione Internet e la configurazione di uv."

echo
echo "[build] creo il pacchetto MoonTransfer"
uv run --frozen --dev python tools/build.py || fail "build non riuscita."
