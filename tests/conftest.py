import pytest

from pingpilot import control


@pytest.fixture(autouse=True)
def _reset_control():
    control.reset()
    yield
    control.reset()
