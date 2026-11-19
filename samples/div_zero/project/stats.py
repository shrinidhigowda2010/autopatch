"""Small numeric helpers."""


def mean(nums):
    """Average of the numbers."""
    return sum(nums) / len(nums)


def ratio(part, whole):
    """How large part is compared with whole."""
    return part / whole


def clamp_percent(value):
    """Keep a percentage inside 0 to 100. The existing tests cover this."""
    if value < 0:
        return 0
    if value > 100:
        return 100
    return value
