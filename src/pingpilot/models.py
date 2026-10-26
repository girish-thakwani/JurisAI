from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Status(str, Enum):
    COMPLETED = "Completed"
    IN_PROGRESS = "In progress"
    FAILED = "Failed"
    INVALID = "Invalid"
    REVIEW = "Review"
    DUPLICATE = "Duplicate"

    @classmethod
    def parse(cls, text) -> Optional["Status"]:
        t = (text or "").strip()
        for s in cls:
            if t.startswith(s.value):
                return s
        return None


# Never touched again automatically. FAILED is retried until max_attempts.
SKIP_STATUSES = {
    Status.COMPLETED,
    Status.IN_PROGRESS,
    Status.INVALID,
    Status.REVIEW,
    Status.DUPLICATE,
}


def status_text(status, detail="", limit=100):
    text = f"{status.value}: {detail}" if detail else status.value
    return text[:limit]


@dataclass
class Contact:
    row: int                      # position in the source (used for write-back)
    raw: str                      # number exactly as stored in the source
    status_text: str = ""
    attempts: int = 0
    number: Optional[str] = None  # normalized by the runner

    @property
    def status(self) -> Optional[Status]:
        return Status.parse(self.status_text)
