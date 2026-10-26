import logging

from ... import control
from ...exceptions import Fatal
from ...net import wait_for_internet

log = logging.getLogger("pingpilot")
WA_URL = "https://web.whatsapp.com"


class BrowserSession:
    """Holds the Playwright page and re-attaches to Chrome if it dies."""

    def __init__(self, playwright, cdp_url, max_offline_wait):
        self.p = playwright
        self.cdp_url = cdp_url
        self.max_offline_wait = max_offline_wait
        self.page = None

    def connect(self):
        for n in range(1, 6):
            try:
                browser = self.p.chromium.connect_over_cdp(self.cdp_url)
                ctx = browser.contexts[0]
                page = next((pg for pg in ctx.pages if "web.whatsapp.com" in pg.url), None)
                if not page:
                    page = ctx.new_page()
                    wait_for_internet(self.max_offline_wait)
                    page.goto(WA_URL)
                self.page = page
                return
            except Exception as e:
                log.warning("Can't attach to Chrome (%s), retry %s/5", str(e).splitlines()[0], n)
                control.nap(5 * n)
        raise Fatal(
            "Can't attach to Chrome. Start it with scripts/start_chrome.sh (or .bat) and log in to WhatsApp Web."
        )
