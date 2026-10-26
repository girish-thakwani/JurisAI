from __future__ import annotations

import os
from dataclasses import dataclass, fields

from dotenv import load_dotenv

from .exceptions import ConfigError


@dataclass(frozen=True)
class Settings:
    # wiring
    source: str = "sheet"            # sheet | csv
    channel: str = "whatsapp_web"    # whatsapp_web | dry_run
    sheet_url: str = ""
    creds_file: str = "creds.json"
    csv_path: str = "contacts.csv"
    message: str = ""
    message_file: str = ""
    cdp_url: str = "http://localhost:9222"
    default_country_code: str = "91"
    # policy
    max_attempts: int = 3            # per contact, across runs
    row_retries: int = 2             # in-run retries, only before the send click
    max_offline_wait: int = 1800     # seconds before aborting when offline / logged out
    pending_wait: int = 300          # seconds to wait for a queued message to flush
    batch_size: int = 20
    batch_pause_min: int = 300
    batch_pause_max: int = 600
    max_per_run: int = 250
    max_consecutive_fails: int = 5
    delay_min: float = 2.0
    delay_max: float = 5.0
    # files
    journal_path: str = "data/progress.jsonl"
    log_file: str = "data/run.log"

    @classmethod
    def from_env(cls, **overrides) -> "Settings":
        load_dotenv()
        kwargs = {}
        for f in fields(cls):
            raw = os.getenv(f.name.upper())
            if raw not in (None, ""):
                kwargs[f.name] = type(f.default)(raw)
        kwargs.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**kwargs)

    def validate(self, need_message=True):
        if self.source == "sheet" and not self.sheet_url:
            raise ConfigError("SHEET_URL is required when SOURCE=sheet")
        if need_message and not (self.message or self.message_file):
            raise ConfigError("Set MESSAGE or MESSAGE_FILE")
