import json
from datetime import datetime
from pathlib import Path


class NullJournal:
    def write(self, contact, status_text):
        pass


class Journal:
    """Append-only local log. Survives sheet/API outages and crashes."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, contact, status_text):
        rec = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "row": contact.row,
            "number": contact.raw,
            "status": status_text,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
