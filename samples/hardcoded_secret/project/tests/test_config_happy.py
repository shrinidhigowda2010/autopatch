"""The service still has a name. This test does not read the secret."""

from config import service_name


def test_service_name():
    assert service_name() == "billing"
