"""Happy-path tests. They pass on the buggy program and should still pass after a fix."""

from marks import calculate


def test_typical_student():
    result = calculate([70, 80, 90])
    assert result["total"] == 240
    assert result["percentage"] == 80
    assert result["grade"] == "A"
