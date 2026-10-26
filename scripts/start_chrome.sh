#!/usr/bin/env bash
# Launch Chrome with the debug port PingPilot attaches to. Log in to WhatsApp Web once in this profile.
PROFILE="${HOME}/.pingpilot-profile"
case "$(uname)" in
  Darwin) CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ;;
  *)      CHROME="$(command -v google-chrome || command -v chromium || command -v chromium-browser)" ;;
esac
"$CHROME" --remote-debugging-port=9222 --user-data-dir="$PROFILE" https://web.whatsapp.com
