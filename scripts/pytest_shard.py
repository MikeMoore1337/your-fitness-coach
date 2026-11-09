"""Single-collection deterministic pytest sharding for GitHub Actions.

Loaded with ``pytest -p scripts.pytest_shard --yfc-shard=1/5``.
Sharding happens during normal test collection, eliminating the separate
``pytest --collect-only`` subprocess formerly started by every CI runner.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

_SHARD_RE = re.compile(r"([1-9][0-9]*)/([1-9][0-9]*)\Z")


def _digest(nodeid: str) -> str:
    return hashlib.sha256(nodeid.encode("utf-8")).hexdigest()


class ShardReceipt:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.collections: list[dict] = []
        self.executed: list[str] = []
        # Worker-reported setup/call/teardown time per hashed test id (not CI wall time).
        self.duration_ms: dict[str, float] = {}

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodedown(self, node, error) -> None:
        if not error and "yfc_shard_receipt" in node.workeroutput:
            self.collections.append(node.workeroutput["yfc_shard_receipt"])

    def pytest_runtest_logreport(self, report) -> None:
        digest = _digest(report.nodeid)
        if report.when == "setup":
            self.executed.append(digest)
        if report.when in {"setup", "call", "teardown"}:
            self.duration_ms[digest] = self.duration_ms.get(digest, 0.0) + max(
                report.duration, 0.0
            ) * 1000

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        if exitstatus != 0:
            return
        if not self.collections or any(c != self.collections[0] for c in self.collections):
            print("Python shard worker collections are missing or inconsistent", file=sys.stderr)
            session.exitstatus = 1
            return
        receipt = self.collections[0]
        if Counter(receipt["selected"]) != Counter(self.executed):
            print("Python shard execution differs from selection", file=sys.stderr)
            session.exitstatus = 1
            return
        if set(self.duration_ms) != set(receipt["selected"]):
            print("Python shard timing report is incomplete", file=sys.stderr)
            session.exitstatus = 1
            return
        receipt["duration_ms"] = {
            digest: round(self.duration_ms[digest]) for digest in receipt["selected"]
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(receipt), encoding="utf-8")


def pytest_configure(config: pytest.Config) -> None:
    path = os.environ.get("YFC_PYTEST_SHARD_RECEIPT")
    if path and not hasattr(config, "workerinput"):
        config.pluginmanager.register(ShardReceipt(path), "yfc-shard-receipt")


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
    if hasattr(config, "workeroutput") and os.environ.get("YFC_PYTEST_SHARD_RECEIPT"):
        config.workeroutput["yfc_shard_receipt"] = {
            "shard": value,
            "all": [_digest(item.nodeid) for item in items],
            "selected": [_digest(item.nodeid) for item in chosen],
        }
    deselected = [item for index, item in enumerate(items) if index % count != number - 1]
    items[:] = chosen
    config.hook.pytest_deselected(items=deselected)
