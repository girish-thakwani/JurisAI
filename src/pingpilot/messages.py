"""Message providers. Add an LLM-backed provider here (see README roadmap)."""
from abc import ABC, abstractmethod
from pathlib import Path

from .models import Contact


class MessageProvider(ABC):
    @abstractmethod
    def render(self, contact: Contact) -> str: ...


class StaticMessage(MessageProvider):
    def __init__(self, text: str):
        self.text = text

    def render(self, contact: Contact) -> str:
        return self.text


def build_message_provider(settings) -> MessageProvider:
    if settings.message_file:
        return StaticMessage(Path(settings.message_file).read_text(encoding="utf-8").strip())
    return StaticMessage(settings.message)
