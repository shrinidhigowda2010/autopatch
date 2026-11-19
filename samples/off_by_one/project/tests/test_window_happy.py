"""The existing test never reaches the crashing loop."""

from window import reading_count


def test_reading_count():
    assert reading_count([1, 2, 3]) == 3
