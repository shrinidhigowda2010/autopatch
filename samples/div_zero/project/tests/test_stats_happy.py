"""Existing tests stay on the inputs that already work."""

from stats import clamp_percent, mean, ratio


def test_mean_of_two():
    assert mean([2, 4]) == 3


def test_ratio_of_ten():
    assert ratio(10, 2) == 5


def test_clamp():
    assert clamp_percent(120) == 100
    assert clamp_percent(-4) == 0
