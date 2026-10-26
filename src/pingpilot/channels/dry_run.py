import logging

from .base import Channel

log = logging.getLogger("pingpilot")


class DryRunChannel(Channel):
    """Walks the whole pipeline without touching a browser."""

    def ensure_ready(self):
        pass

    def prepare(self, contact, text):
        return (contact.raw, text)

    def send(self, handle):
        log.info("[dry-run] would send to %s: %s", handle[0], handle[1])
