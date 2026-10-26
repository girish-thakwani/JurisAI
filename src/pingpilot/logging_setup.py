import logging
from pathlib import Path

_last_note = None


def setup_logging(log_file=None):
    handlers = [logging.StreamHandler()]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
        force=True,
    )


def note(msg):
    """Log a 'waiting because...' reason once instead of on every poll."""
    global _last_note
    if msg != _last_note:
        logging.getLogger("pingpilot").warning(msg)
        _last_note = msg


def reset_note():
    global _last_note
    _last_note = None
