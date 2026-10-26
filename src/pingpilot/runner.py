"""Orchestrator: source -> policy -> channel. Knows nothing about WhatsApp or Google Sheets."""
import logging
import random
from dataclasses import dataclass

from . import control
from .exceptions import Fatal, NeedsReview, Permanent
from .journal import NullJournal
from .models import SKIP_STATUSES, Status, status_text
from .phone import normalize

log = logging.getLogger("pingpilot")

SENT, SKIPPED, FAILED = "sent", "skipped", "failed"


@dataclass
class Summary:
    sent: int = 0
    skipped: int = 0   # invalid / duplicate / needs review
    failed: int = 0


class Runner:
    def __init__(self, source, channel, messages, settings, journal=None):
        self.source = source
        self.channel = channel
        self.messages = messages
        self.s = settings
        self.journal = journal or NullJournal()

    # ── status write-back: local journal first, then the source (never fatal) ──
    def _mark(self, contact, status, detail=""):
        text = status_text(status, detail)
        self.journal.write(contact, text)
        try:
            self.source.update(contact, status, detail)
        except Exception as e:
            log.error("Could not write status for %s (%s). It is in the journal.", contact.raw, e)
        contact.status_text = text

    def run(self) -> Summary:
        s, summary = self.s, Summary()
        self.channel.start()
        try:
            seen, consecutive, since_pause = set(), 0, 0
            for c in self.source.load():
                control.check()
                c.number = normalize(c.raw, s.default_country_code)
                is_dup = bool(c.number) and c.number in seen
                if c.number:
                    seen.add(c.number)

                if c.status in SKIP_STATUSES:
                    continue
                if c.number is None:
                    self._mark(c, Status.INVALID, "bad number format")
                    summary.skipped += 1
                    continue
                if is_dup:
                    self._mark(c, Status.DUPLICATE)
                    summary.skipped += 1
                    continue
                if c.status == Status.FAILED and c.attempts >= s.max_attempts:
                    continue
                if summary.sent >= s.max_per_run:
                    log.info("Reached MAX_PER_RUN=%s. Re-run later to continue.", s.max_per_run)
                    break

                outcome = self._process(c)
                if outcome == SENT:
                    summary.sent += 1
                    since_pause += 1
                    consecutive = 0
                elif outcome == SKIPPED:
                    summary.skipped += 1
                else:
                    summary.failed += 1
                    consecutive += 1
                    if consecutive >= s.max_consecutive_fails:
                        raise Fatal(
                            f"{consecutive} failures in a row. The UI probably changed, selectors broke, "
                            "or the account is restricted. Check manually."
                        )

                if since_pause >= s.batch_size:
                    pause = random.randint(s.batch_pause_min, s.batch_pause_max)
                    log.info("Batch of %s done, resting %ss", s.batch_size, pause)
                    control.nap(pause)
                    since_pause = 0
                else:
                    control.nap(random.uniform(s.delay_min, s.delay_max))
        finally:
            self.channel.close()
        log.info("Run finished: %s", summary)
        return summary

    def _process(self, c):
        c.attempts += 1
        text = self.messages.render(c)
        committed = False  # True once we've entered the point of no return
        last_err = ""
        for attempt in range(self.s.row_retries + 1):
            try:
                self.channel.ensure_ready()
                handle = self.channel.prepare(c, text)
                self._mark(c, Status.IN_PROGRESS)  # if we crash now the row is flagged, not re-sent
                committed = True
                self.channel.send(handle)
                self._mark(c, Status.COMPLETED)
                log.info("%s: sent", c.raw)
                return SENT
            except Permanent as e:
                self._mark(c, Status.INVALID, str(e))
                log.info("%s: invalid (%s)", c.raw, e)
                return SKIPPED
            except NeedsReview as e:
                self._mark(c, Status.REVIEW, str(e))
                log.warning("%s: needs review (%s)", c.raw, e)
                return SKIPPED
            except Exception as e:
                msg = (str(e).splitlines() or [type(e).__name__])[0]
                if committed:  # a channel bug must never cause a duplicate send
                    self._mark(c, Status.REVIEW, f"send outcome unknown: {msg}")
                    return SKIPPED
                last_err = msg
                log.warning("%s: attempt %s failed: %s", c.raw, attempt + 1, msg)
                self.channel.recover()
        self._mark(c, Status.FAILED, last_err)
        return FAILED
