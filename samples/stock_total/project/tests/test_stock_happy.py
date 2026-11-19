"""Row counting is fine. The total is not covered here."""

from stock import row_count


def test_row_count():
    assert row_count([{"qty": 1}, {"qty": 2}]) == 2
