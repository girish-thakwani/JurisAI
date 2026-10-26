class ConfigError(Exception):
    """Bad or missing configuration."""


class Permanent(Exception):
    """Contact can never be messaged (not on the channel, bad format). Never retry."""


class NeedsReview(Exception):
    """Outcome unknown or ambiguous. Never retry automatically, a human should look."""


# BaseException on purpose: a blanket `except Exception` in retry code must never swallow these.
class Fatal(BaseException):
    """Abort the whole run (progress is already saved)."""


class Stop(BaseException):
    """User asked to stop (Ctrl+C)."""
