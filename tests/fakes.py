from pingpilot.channels.base import Channel
from pingpilot.models import Contact
from pingpilot.sources.base import ContactSource


class FakeSource(ContactSource):
    def __init__(self, rows):
        self.contacts = [
            Contact(row=i, raw=r[0], status_text=r[1] if len(r) > 1 else "", attempts=r[2] if len(r) > 2 else 0)
            for i, r in enumerate(rows, 1)
        ]
        self.updates = []

    def load(self):
        return self.contacts

    def update(self, contact, status, detail=""):
        self.updates.append((contact.raw, status.value, detail))


class FakeChannel(Channel):
    """prepare_plan / send_plan: {number: [exception-or-None, ...]} consumed one per call."""

    def __init__(self, prepare_plan=None, send_plan=None, always_fail=()):
        self.prepare_plan = prepare_plan or {}
        self.send_plan = send_plan or {}
        self.always_fail = set(always_fail)
        self.prepare_calls, self.send_calls, self.sent = {}, {}, []

    def ensure_ready(self):
        pass

    def prepare(self, contact, text):
        n = contact.raw
        self.prepare_calls[n] = self.prepare_calls.get(n, 0) + 1
        if n in self.always_fail:
            raise RuntimeError("boom")
        plan = self.prepare_plan.get(n)
        if plan:
            err = plan.pop(0)
            if err:
                raise err
        return n

    def send(self, handle):
        self.send_calls[handle] = self.send_calls.get(handle, 0) + 1
        plan = self.send_plan.get(handle)
        if plan:
            err = plan.pop(0)
            if err:
                raise err
        self.sent.append(handle)
