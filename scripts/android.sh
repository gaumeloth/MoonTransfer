#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

if ! command -v uv >/dev/null 2>&1; then
    printf '%s\n' \
        "Error: uv is required. Install it from https://docs.astral.sh/uv/." \
        >&2
    exit 1
fi

if [ -n "${JAVA_HOME:-}" ] && [ -x "$JAVA_HOME/bin/javac" ]; then
    PATH="$JAVA_HOME/bin:$PATH"
    export JAVA_HOME PATH
fi

cd "$ROOT"
exec uv run --project "$ROOT/android" --group build \
    python -m tools.android "$@"
