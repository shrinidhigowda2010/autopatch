"""Shopping cart helper."""


def add_item(item, cart=[]):
    """Append one item and return the cart."""
    cart.append(item)
    return cart


def item_count(cart):
    """How many items are in a cart the caller owns."""
    return len(cart)
