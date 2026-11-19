"""A very small bank account."""


class Account:
    """One customer's balance."""

    def __init__(self, owner, balance=0):
        self.owner = owner
        self.balance = balance

    def deposit(self, amount):
        """Add money to the account."""
        self.balance += amount
        return self.balance

    def withdraw(self, amount):
        """Take money out of the account."""
        self.balance -= amount
        return self.balance
