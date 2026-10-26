from abc import ABC, abstractmethod
from typing import Any

from ..models import Contact


class Channel(ABC):
    """A delivery channel. Contract the Runner relies on:

    prepare()  everything up to (not including) the send click. Safe to retry.
    send()     the point of no return. Raise NeedsReview if the outcome is unknown.
               The runner never retries after send() has been entered.
    """

    def start(self) -> None: ...

    def close(self) -> None: ...

    @abstractmethod
    def ensure_ready(self) -> None:
        """Block until the channel is usable (online, logged in). Raise Fatal if hopeless."""

    @abstractmethod
    def prepare(self, contact: Contact, text: str) -> Any: ...

    @abstractmethod
    def send(self, handle: Any) -> None: ...

    def recover(self) -> None:
        """Best-effort cleanup after a failed attempt."""
