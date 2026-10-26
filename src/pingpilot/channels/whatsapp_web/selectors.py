"""Every WhatsApp Web selector lives here. When the UI changes, this is the only file to touch."""
import re
import sys

CHAT_LIST = 'div[aria-label="Chat list"]'
QR = '[data-testid="qrcode"], canvas[aria-label*="QR" i]'
SEND_BTN = 'span[data-icon="send"], span[data-icon="wds-ic-send-filled"]'
COMPOSE_BOX = 'div[data-testid="conversation-compose-box-input"]'
NEW_CHAT_BTN = 'button[aria-label="New chat"]'
BACK_BTN = 'button[aria-label="Back"]'
SEARCH_CLEAR_BTN = 'div[data-testid="chat-list-search-container"] button[aria-label="End icon button"]'
NO_RESULTS = 'div[data-testid="search-no-results-without-keyword-container"]'
RESULT_ROW = 'div[data-testid="cell-frame-container"][role="button"]'
OUTGOING_MSG = "div.message-out"
PENDING_ICON = 'span[data-icon="msg-time"]'
SEARCH_BOX_NAME = "Search or start a new chat"

BANNER_RE = re.compile(
    r"Phone not connected|Computer not connected|Connecting to WhatsApp|"
    r"Trying to reach phone|Waiting for this device|Retrieving messages|"
    r"Click to reload QR code",
    re.I,
)
USE_HERE_RE = re.compile(r"use here", re.I)

MOD = "Meta" if sys.platform == "darwin" else "Control"
