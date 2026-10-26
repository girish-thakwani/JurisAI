"""Local CSV source: handy for tests, offline use, or no Google credentials."""
import csv
import os
from datetime import datetime
from pathlib import Path

from ..models import Contact, status_text
from .base import ContactSource

CORE = ["number", "status", "attempts", "updated_at"]


class CsvSource(ContactSource):
    def __init__(self, path):
        self.path = Path(path)
        self._rows = []
        self._fields = list(CORE)

    def load(self):
        with open(self.path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            header = list(reader.fieldnames or [])
            self._fields = header + [c for c in CORE if c not in header]
            self._rows = [{k: (v or "") for k, v in r.items() if k is not None} for r in reader]
        contacts = []
        for idx, r in enumerate(self._rows):
            raw = r.get("number", "").strip()
            if not raw:
                continue
            att = r.get("attempts", "").strip()
            contacts.append(
                Contact(
                    row=idx,
                    raw=raw,
                    status_text=r.get("status", "").strip(),
                    attempts=int(att) if att.isdigit() else 0,
                )
            )
        return contacts

    def update(self, contact, status, detail=""):
        r = self._rows[contact.row]
        r["status"] = status_text(status, detail)
        r["attempts"] = str(contact.attempts)
        r["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._flush()

    def _flush(self):
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=self._fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(self._rows)
        os.replace(tmp, self.path)
