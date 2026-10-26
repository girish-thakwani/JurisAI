"""Low-level page interactions. No retry policy here, that belongs to the Runner."""
import logging
import random
import time

from ... import control
from ...exceptions import NeedsReview, Permanent
from ...logging_setup import note, reset_note
from . import selectors as sel

log = logging.getLogger("pingpilot")


def sleep_ms(page, a=1500, b=3500):
    ms = random.randint(a, b)
    try:
        page.wait_for_timeout(ms)
    except Exception:
        time.sleep(ms / 1000)


def safe_escape(page):
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    try:
        page.locator(sel.CHAT_LIST).click(position={"x": 5, "y": 5}, timeout=3000)
    except Exception:
        pass
    page.wait_for_timeout(300)


def clear_search_box(page):
    box = page.get_by_role("textbox", name=sel.SEARCH_BOX_NAME)
    if box.count() == 0:
        box = page.locator('div[contenteditable="true"]').first
    box.click(timeout=10000)
    page.keyboard.press(f"{sel.MOD}+A")
    page.keyboard.press("Delete")
    return box


def go_back(page):
    try:
        page.locator(sel.BACK_BTN).click(timeout=3000)
        page.wait_for_timeout(300)
        page.locator(sel.SEARCH_CLEAR_BTN).click(timeout=3000)
    except Exception:
        pass  # clear_search_box on the next contact cleans up anyway


def open_chat(page, raw, norm):
    safe_escape(page)
    search = clear_search_box(page)
    search.fill(raw)
    sleep_ms(page)
    try:
        page.get_by_text(raw, exact=True).first.click(timeout=5000)
        return
    except Exception:
        pass

    log.info("%s: not in chat list, trying New chat search", raw)
    page.locator(sel.NEW_CHAT_BTN).click(timeout=5000)
    page.wait_for_timeout(500)
    page.keyboard.type(raw)
    page.locator(f"{sel.NO_RESULTS}, {sel.RESULT_ROW}").first.wait_for(state="visible", timeout=10000)

    if page.locator(sel.NO_RESULTS).count() > 0:
        go_back(page)
        raise Permanent("not on WhatsApp")

    row = page.locator(sel.RESULT_ROW).first
    title = row.locator("span[title]").first.get_attribute("title") or ""
    if norm[-10:] not in "".join(filter(str.isdigit, title)):
        go_back(page)
        raise NeedsReview(f"result mismatch, expected {norm}, found {title}")
    row.click(timeout=5000)


def prepare_message(page, raw, norm, text):
    """Open the chat and type the message. Safe to retry. Returns (page, outgoing count before)."""
    open_chat(page, raw, norm)
    box = page.locator(sel.COMPOSE_BOX)
    box.wait_for(state="visible", timeout=15000)
    box.click(timeout=5000)
    sleep_ms(page, 500, 1000)
    before = page.locator(sel.OUTGOING_MSG).count()
    page.keyboard.type(text, delay=random.randint(20, 60))
    if not box.inner_text().strip():
        raise RuntimeError("typed text did not land in the compose box")
    sleep_ms(page)
    return page, before


def send_and_confirm(page, before, pending_wait):
    """Point of no return. Every failure from here on is NeedsReview, never a retry."""
    try:
        page.locator(sel.SEND_BTN).first.click(timeout=5000)
        deadline = time.time() + 25
        appeared = False
        while time.time() < deadline:
            out = page.locator(sel.OUTGOING_MSG)
            if out.count() > before:
                appeared = True
                if out.last.locator(sel.PENDING_ICON).count() == 0:
                    return  # clock icon gone: really sent
            page.wait_for_timeout(500)
        if not appeared:
            raise NeedsReview("clicked send but no outgoing message appeared")

        # queued with a clock icon: phone/net offline. Wait for it to flush.
        note("Message queued but not delivered yet (phone offline?), waiting...")
        deadline = time.time() + pending_wait
        while time.time() < deadline:
            control.check()
            if page.locator(sel.OUTGOING_MSG).last.locator(sel.PENDING_ICON).count() == 0:
                reset_note()
                return
            control.nap(3)
        raise NeedsReview("message still pending after wait, check manually")
    except NeedsReview:
        raise
    except Exception as e:
        raise NeedsReview(f"send outcome unknown: {str(e).splitlines()[0]}")
