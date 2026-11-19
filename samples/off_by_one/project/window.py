"""Pairwise averages of neighbouring sensor readings."""


def average_pairs(nums):
    """Average each number with the one after it."""
    result = []
    for index in range(len(nums)):
        result.append((nums[index] + nums[index + 1]) / 2)
    return result


def reading_count(nums):
    """How many readings were stored."""
    return len(nums)
