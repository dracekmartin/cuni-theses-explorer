"""Rules for tests that need infrastructure (decisions 0020 and 0021)."""

from collections.abc import Generator

import pytest

# A skipped test of these kinds would look like a pass while its check never ran.
_NEVER_SKIP = ("db", "model")


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


def _must_not_skip(item: pytest.Item) -> bool:
    if any(item.get_closest_marker(name) is not None for name in _NEVER_SKIP):
        return True
    return item.get_closest_marker("network") is not None and bool(
        item.config.getoption("--network")
    )


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    """Turn a skip of a test that needs infrastructure into a failure."""
    del call
    report = yield
    if report.skipped and not hasattr(report, "wasxfail") and _must_not_skip(item):
        report.outcome = "failed"
        report.longrepr = f"a test that needs infrastructure must not skip: {report.longrepr}"
    return report
