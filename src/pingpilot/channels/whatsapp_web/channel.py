import time

from ... import control
from ...exceptions import Fatal
from ...logging_setup import note, reset_note
from ...net import internet_up
from ..base import Channel
from . import actions
from . import selectors as sel
from .browser import BrowserSession


class WhatsAppWebChannel(Channel):
    def __init__(self, settings):
        self.s = settings
        self._pw = None
        self.session = None

    def start(self):
        from playwright.sync_api import sync_playwright  # lazy: keeps tests/dry-run dependency-free

        self._pw = sync_playwright().start()
        self.session = BrowserSession(self._pw, self.s.cdp_url, self.s.max_offline_wait)
        self.session.connect()

    def close(self):
        if self._pw:
            self._pw.stop()
            self._pw = None

    def ensure_ready(self):
        """Wait out: PC offline, tab/Chrome died, logged out (QR), 'Use here', phone-offline banner."""
        sess = self.session
        start = last_reload = time.time()
        while True:
            control.check()
            if time.time() - start > self.s.max_offline_wait:
                raise Fatal("WhatsApp Web wasn't usable for too long (phone offline / logged out?)")
            if not internet_up():
                note("Internet is down on this machine, waiting...")
                control.nap(10)
                continue
            if sess.page is None or sess.page.is_closed():
                sess.connect()
                continue
            page = sess.page
            try:
                use_here = page.get_by_role("button", name=sel.USE_HERE_RE)
                if use_here.count():
                    note("WhatsApp is open in another window, clicking 'Use here'")
                    use_here.first.click(timeout=3000)
                    control.nap(2)
                    continue
                if page.locator(sel.QR).first.is_visible():
                    note("Logged out: scan the QR code in Chrome (waiting...)")
                    control.nap(5)
                    continue
                banner = page.get_by_text(sel.BANNER_RE)
                if banner.count() and banner.first.is_visible():
                    note("WhatsApp shows a connection banner (phone offline?), waiting...")
                    control.nap(5)
                    continue
                if page.locator(sel.CHAT_LIST).first.is_visible():
                    reset_note()
                    return
            except Exception:
                sess.page = None  # tab/browser died, reconnect on the next loop
                continue
            if time.time() - last_reload > 90:
                note("WhatsApp Web looks stuck, reloading the tab")
                try:
                    page.reload()
                except Exception:
                    sess.page = None
                last_reload = time.time()
            control.nap(3)

    def prepare(self, contact, text):
        return actions.prepare_message(self.session.page, contact.raw, contact.number, text)

    def send(self, handle):
        page, before = handle
        actions.send_and_confirm(page, before, self.s.pending_wait)

    def recover(self):
        try:
            page = self.session.page
            if page and not page.is_closed():
                actions.safe_escape(page)
            else:
                self.session.page = None
        except Exception:
            self.session.page = None
