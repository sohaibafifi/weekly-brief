#!/usr/bin/env bash
# Install + load weekly-brief launchd agent.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.sohaibafifi.weekly-brief"
OLD_LABEL="com.afifi.weekly-brief"
SRC_PLIST="$PROJECT_DIR/ops/$LABEL.plist"
DST_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
OLD_DST_PLIST="$HOME/Library/LaunchAgents/$OLD_LABEL.plist"
SECRETS_DIR="$HOME/.config/weekly-brief"

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs" "$SECRETS_DIR"

# Render plist with absolute paths.
sed \
  -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
  -e "s|__HOME__|$HOME|g" \
  "$SRC_PLIST" > "$DST_PLIST"

chmod +x "$PROJECT_DIR/ops/run.sh"

# Migrate from previous label, if loaded.
if launchctl print "gui/$UID/$OLD_LABEL" >/dev/null 2>&1; then
  launchctl bootout "gui/$UID/$OLD_LABEL" || true
fi
[[ -f "$OLD_DST_PLIST" ]] && rm -f "$OLD_DST_PLIST"

# Bootstrap (replaces existing).
if launchctl print "gui/$UID/$LABEL" >/dev/null 2>&1; then
  launchctl bootout "gui/$UID/$LABEL" || true
fi
launchctl bootstrap "gui/$UID" "$DST_PLIST"

echo "Installed: $DST_PLIST"
echo "Logs: $HOME/Library/Logs/weekly-brief.{out,err}.log"
echo
if [[ ! -f "$SECRETS_DIR/secrets.env" ]]; then
  cat > "$SECRETS_DIR/secrets.env" <<'EOF'
# Fill in:
IMAP_PWD=
SMTP_PWD=
MISTRAL_API_KEY=
NOTION_API_KEY=
EOF
  chmod 600 "$SECRETS_DIR/secrets.env"
  echo "Created secrets template at $SECRETS_DIR/secrets.env — fill it in."
fi
echo
echo "To run NOW: launchctl kickstart -k gui/$UID/$LABEL"
echo "To uninstall: launchctl bootout gui/$UID/$LABEL && rm $DST_PLIST"
