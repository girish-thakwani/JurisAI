import pytest

from pingpilot.config import Settings
from pingpilot.exceptions import Fatal, Permanent
from pingpilot.messages import StaticMessage
from pingpilot.runner import Runner
from tests.fakes import FakeChannel, FakeSource

S = Settings(delay_min=0, delay_max=0, batch_size=1000, row_retries=2, max_consecutive_fails=3)
A, B, C, D = "9876543210", "9876543211", "9876543212", "9876543213"


def run(rows, channel=None, settings=S):
    src, ch = FakeSource(rows), channel or FakeChannel()
    summary = Runner(src, ch, StaticMessage("hi"), settings).run()
    return src, ch, summary


def final(src, number):
    return [u for u in src.updates if u[0] == number][-1][1:]


def test_happy_path():
    src, ch, summary = run([(A,), (B,)])
    assert ch.sent == [A, B] and summary.sent == 2
    assert final(src, A) == ("Completed", "")


def test_skips_finished_rows_and_retries_failed_under_limit():
    rows = [(A, "Completed"), (B, "Invalid: not on WhatsApp"), (C, "Review: x"),
            (D, "Failed: boom", 1), ("9876543299", "Failed: boom", 3)]
    _, ch, _ = run(rows)
    assert ch.sent == [D]


def test_permanent_error_is_not_retried():
    ch = FakeChannel(prepare_plan={A: [Permanent("not on WhatsApp")]})
    src, ch, _ = run([(A,)], ch)
    assert ch.prepare_calls[A] == 1 and final(src, A) == ("Invalid", "not on WhatsApp")


def test_transient_error_is_retried_then_succeeds():
    ch = FakeChannel(prepare_plan={A: [RuntimeError("flaky"), None]})
    src, ch, _ = run([(A,)], ch)
    assert ch.prepare_calls[A] == 2 and ch.sent == [A]
    assert src.contacts[0].attempts == 1  # one attempt per run, not per retry


def test_error_after_send_click_never_resends():
    ch = FakeChannel(send_plan={A: [RuntimeError("socket died")]})
    src, ch, _ = run([(A,)], ch)
    assert ch.send_calls[A] == 1 and ch.sent == []
    assert final(src, A)[0] == "Review"


def test_duplicates_and_bad_numbers():
    src, ch, _ = run([(A,), ("+91 98765 43210",), ("123",)])
    assert ch.sent == [A]
    assert final(src, "+91 98765 43210")[0] == "Duplicate"
    assert final(src, "123") == ("Invalid", "bad number format")


def test_circuit_breaker_aborts_run():
    ch = FakeChannel(always_fail=[A, B, C, D])
    with pytest.raises(Fatal):
        run([(A,), (B,), (C,), (D,)], ch)


def test_max_per_run():
    _, ch, _ = run([(A,), (B,), (C,)], settings=Settings(delay_min=0, delay_max=0, max_per_run=2))
    assert ch.sent == [A, B]
