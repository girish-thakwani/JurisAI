"""Cooperative stop flag + interruptible sleep, shared by every component."""
import logging
import signal
import time

from .exceptions import Stop

log = logging.getLogger("pingpilot")
_stop = False


def reset():
    global _stop
    _stop = False


def is_stopped():
    return _stop


def request_stop():
    global _stop
    _stop = True


def check():
    if _stop:
        raise Stop()


def nap(seconds):
    """Sleep, but wake up and raise Stop as soon as the user asks."""
    end = time.time() + seconds
    while True:
        check()
        remaining = end - time.time()
        if remaining <= 0:
            return
        time.sleep(min(1.0, remaining))


def _handler(*_):
    global _stop
    if _stop:
        raise KeyboardInterrupt
    _stop = True
    log.warning("Stop requested: finishing the current contact (Ctrl+C again to force quit)")


def install_signal_handlers():
    signal.signal(signal.SIGINT, _handler)
