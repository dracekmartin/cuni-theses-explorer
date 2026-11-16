"""Tests marked network call real external services and run only on request (decision 0020)."""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add the option that turns on the tests marked network."""
    parser.addoption(
        "--network",
        action="store_true",
        help="also run the tests marked network, which call real external services",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip the tests marked network unless the run asked for them."""
    if config.getoption("--network"):
        return
    skip = pytest.mark.skip(reason="calls a real external service, run with --network")
    for item in items:
        if item.get_closest_marker("network") is not None:
            item.add_marker(skip)
