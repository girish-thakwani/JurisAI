import os
import random

import gspread
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

SHEET_URL = os.getenv("SHEET_URL")
MESSAGE = os.getenv("MESSAGE")
CREDS_FILE = os.getenv("CREDS_FILE", "creds.json")
CDP_URL = os.getenv("CDP_URL", "http://localhost:9222")

if not SHEET_URL or not MESSAGE:
    raise RuntimeError("SHEET_URL and MESSAGE must be set in the .env file")

gc = gspread.service_account(filename=CREDS_FILE)
sh = gc.open_by_url(SHEET_URL)
ws = sh.sheet1


def human_delay(page, a=1500, b=3500):
    page.wait_for_timeout(random.randint(a, b))

def safe_escape(page):
    try:
        page.keyboard.press("Escape", timeout=2000)
    except Exception:
        pass
    try:
        page.locator('div[aria-label="Chat list"]').click(position={"x": 5, "y": 5}, timeout=3000)
    except Exception:
        pass
    page.wait_for_timeout(300)

def clear_search_box(page):
    search_box = page.get_by_role("textbox", name="Search or start a new chat")
    if search_box.count() == 0:
        search_box = page.locator('div[contenteditable="true"]').first
    search_box.click(timeout=10000)
    page.keyboard.press("Control+A")
    page.keyboard.press("Delete")
    return search_box

def wait_for_chat_loaded(page, timeout=15000):
    message_box = page.locator('div[data-testid="conversation-compose-box-input"]')
    message_box.wait_for(state="visible", timeout=timeout)
    return message_box

def initiate():
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0]

        page = next((pg for pg in context.pages if "web.whatsapp.com" in pg.url), None)
        if not page:
            page = context.new_page()
            page.goto("https://web.whatsapp.com")
        page.wait_for_selector('div[aria-label="Chat list"]', timeout=60000)

        nums = ws.get("A1:A275")
        statuses = ws.get("B1:B275")

        for i, n in enumerate(nums, 1):
            status = statuses[i-1][0] if i-1 < len(statuses) and statuses[i-1] else ""
            if status == "Completed":
                continue

            number = n[0]
            try:
                safe_escape(page)
                search_box = clear_search_box(page)
                search_box.fill(number)
                human_delay(page)

                opened = False
                try:
                    page.get_by_text(number, exact=True).first.click(timeout=5000)
                    opened = True
                except Exception:
                    pass

                if not opened:
                    print(f"{number}: not found, adding as new contact...")
                    try:
                        page.locator('button[aria-label="New chat"]').click(timeout=5000)
                        page.wait_for_timeout(500)
                        page.keyboard.type(number)

                        no_results = page.locator('div[data-testid="search-no-results-without-keyword-container"]')
                        result_row = page.locator('div[data-testid="cell-frame-container"][role="button"]').first

                        try:
                            page.locator(
                                'div[data-testid="search-no-results-without-keyword-container"], '
                                'div[data-testid="cell-frame-container"][role="button"]'
                            ).first.wait_for(state="visible", timeout=10000)
                        except Exception:
                            raise RuntimeError("neither result nor no-results state appeared")

                        if no_results.count() > 0:
                            page.locator('button[aria-label="Back"]').click(timeout=3000)
                            page.wait_for_timeout(300)

                            # clear the stale query left in the main search box after returning
                            clear_btn = page.locator(
                                'div[data-testid="chat-list-search-container"] button[aria-label="End icon button"]'
                            )
                            try:
                                clear_btn.click(timeout=3000)
                            except Exception:
                                pass  # non-fatal — next iteration's clear_search_box will also handle leftover text

                            raise RuntimeError("number not on WhatsApp")

                        result_row.wait_for(state="visible", timeout=5000)

                        title_span = result_row.locator('span[title]').first
                        displayed = title_span.get_attribute("title") or ""
                        digits_only = "".join(filter(str.isdigit, displayed))
                        if number[-10:] not in digits_only:
                            raise RuntimeError(f"result mismatch: expected {number}, found {displayed}")

                        result_row.click(timeout=5000)
                        opened = True
                    except Exception as e2:
                        raise RuntimeError(f"new-contact flow failed: {e2}")

                message_box = wait_for_chat_loaded(page)
                message_box.click(timeout=5000)
                human_delay(page, 500, 1000)
                page.keyboard.type(MESSAGE, delay=random.randint(20, 60))
                human_delay(page)
                page.locator('span[data-icon="send"], span[data-icon="wds-ic-send-filled"]').click(timeout=5000)

                ws.update_acell(f"B{i}", "Completed")
                print(f"{number}: sent")

            except Exception as e:
                ws.update_acell(f"B{i}", f"Failed: {str(e)[:100]}")
                print(f"{number}: FAILED - {e}")
                safe_escape(page)

            human_delay(page, 2000, 5000)

initiate()
