"""Warehouse quantity totals."""


def total_stock(items):
    """Sum the qty field of every row."""
    total = 0
    for index in range(1, len(items)):
        total += items[index]["qty"]
    return total


def row_count(items):
    """Number of rows in the sheet."""
    return len(items)
