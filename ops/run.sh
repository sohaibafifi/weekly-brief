#!/usr/bin/env bash
# Wrapper for launchd: source secrets, then run weekly-brief.
set -euo pipefail

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

PROJECT_DIR="${PROJECT_DIR:-$HOME/Codes/VP/Assistant}"
SECRETS_FILE="${SECRETS_FILE:-$HOME/.config/weekly-brief/secrets.env}"
UV_BIN="${UV_BIN:-$(command -v uv || echo /usr/local/bin/uv)}"

if [[ -f "$SECRETS_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$SECRETS_FILE"
  set +a
fi

cd "$PROJECT_DIR"
exec "$UV_BIN" run --project "$PROJECT_DIR" weekly-brief run "$@"
