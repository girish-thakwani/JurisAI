from pingpilot.models import Status
from pingpilot.sources.csv_source import CsvSource


def test_roundtrip_preserves_extra_columns(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("number,name\n9876543210,Asha\n", encoding="utf-8")
    src = CsvSource(p)
    c = src.load()[0]
    c.attempts = 1
    src.update(c, Status.COMPLETED)

    again = CsvSource(p).load()[0]
    assert again.status == Status.COMPLETED and again.attempts == 1
    assert "Asha" in p.read_text(encoding="utf-8")
