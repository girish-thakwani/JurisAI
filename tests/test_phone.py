import pytest

from pingpilot.phone import normalize


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+91 98765-43210", "919876543210"),
        ("9876543210", "919876543210"),
        ("09876543210", "919876543210"),
        ("00919876543210", "919876543210"),
        ("919876543210", "919876543210"),
        ("abc", None),
        ("12345", None),
        ("", None),
    ],
)
def test_normalize(raw, expected):
    assert normalize(raw, "91") == expected
