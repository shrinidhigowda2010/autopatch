"""Happy path for a normal deposit and withdrawal."""

from bank import Account


def test_ordinary_movement():
    account = Account("Ada", 100)
    assert account.deposit(50) == 150
    assert account.withdraw(20) == 130
