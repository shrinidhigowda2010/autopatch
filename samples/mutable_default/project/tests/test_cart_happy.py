"""Passing a cart explicitly hides the shared-default bug."""

from cart import add_item, item_count


def test_explicit_cart():
    assert add_item("apple", []) == ["apple"]
    assert item_count(["apple", "pear"]) == 2
