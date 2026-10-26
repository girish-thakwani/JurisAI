"""Sheet layout: A = number | B = status | C = attempts | D = last updated."""
import logging
import random
import time
from datetime import datetime

import gspread
import requests
from gspread.exceptions import APIError

from ..models import Contact, status_text
from ..net import wait_for_internet
from .base import ContactSource

log = logging.getLogger("pingpilot")


class GoogleSheetSource(ContactSource):
    def __init__(self, sheet_url, creds_file, max_offline_wait=1800):
        self.max_offline_wait = max_offline_wait
        self.ws = self._retry(
            lambda: gspread.service_account(filename=creds_file).open_by_url(sheet_url).sheet1
        )

    def _retry(self, fn, tries=8):
        for n in range(tries):
            try:
                return fn()
            except APIError as e:
                code = getattr(e.response, "status_code", 0)
                if code in (429, 500, 502, 503, 504) and n < tries - 1:
                    time.sleep(min(60, 2 ** n + random.random()))
                    continue
                raise
            except requests.RequestException:
                wait_for_internet(self.max_offline_wait)
        raise RuntimeError("Google Sheets retries exhausted")

    def load(self):
        contacts = []
        for i, row in enumerate(self._retry(self.ws.get_all_values), 1):
            raw = (row[0] if row else "").strip()
            if not raw or (i == 1 and not any(ch.isdigit() for ch in raw)):
                continue  # blank row or header
            status = row[1].strip() if len(row) > 1 else ""
            attempts = int(row[2]) if len(row) > 2 and row[2].strip().isdigit() else 0
            contacts.append(Contact(row=i, raw=raw, status_text=status, attempts=attempts))
        return contacts

    def update(self, contact, status, detail=""):
        text = status_text(status, detail)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._retry(
            lambda: self.ws.update(
                values=[[text, contact.attempts, now]],
                range_name=f"B{contact.row}:D{contact.row}",
            )
        )
