from abc import ABC, abstractmethod
from typing import List

from ..models import Contact, Status


class ContactSource(ABC):
    """Where contacts come from and where progress is written back."""

    @abstractmethod
    def load(self) -> List[Contact]: ...

    @abstractmethod
    def update(self, contact: Contact, status: Status, detail: str = "") -> None: ...
