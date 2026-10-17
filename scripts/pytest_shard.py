"""Single-collection deterministic pytest sharding for GitHub Actions.

Loaded with ``pytest -p scripts.pytest_shard --yfc-shard=1/5``.
Sharding happens during normal test collection, eliminating the separate
``pytest --collect-only`` subprocess formerly started by every CI runner.
"""

from __future__ import annotations

import re

import pytest

_SHARD_RE = re.compile(r"([1-9][0-9]*)/([1-9][0-9]*)\Z")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.getgroup("yfc").addoption(
        "--yfc-shard",
        action="store",
        default=None,
        help="Deterministic test shard index/count, e.g. 2/5.",
    )


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    value = config.getoption("--yfc-shard")
    if value is None:
        return
    match = _SHARD_RE.fullmatch(value)
    if match is None:
        raise pytest.UsageError(f"Invalid --yfc-shard value: {value!r}")
    number, count = map(int, match.groups())
    if number > count:
        raise pytest.UsageError(f"Invalid --yfc-shard index: {value!r}")
    if len({item.nodeid for item in items}) != len(items):
        raise pytest.UsageError("Duplicate pytest nodeids; cannot shard safely")

    # Every xdist worker collects the same ordered node list.
    chosen = items[number - 1 :: count]
    if not chosen:
        raise pytest.UsageError(f"Empty pytest shard {value}; refusing false green")
    deselected = [item for index, item in enumerate(items) if index % count != number - 1]
    items[:] = chosen
    config.hook.pytest_deselected(items=deselected)
