import re
from typing import Optional


def normalize(raw, default_cc="91") -> Optional[str]:
    """Return digits including country code, or None if it can't be a valid number."""
    s = re.sub(r"[^\d+]", "", str(raw))
    if s.startswith("00"):
        s = s[2:]
    s = s.lstrip("+")
    if len(s) == 10:
        s = default_cc + s
    elif len(s) == 11 and s.startswith("0"):
        s = default_cc + s[1:]
    return s if 11 <= len(s) <= 15 else None
