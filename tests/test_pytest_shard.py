"""Tests of single-collection Python CI sharding."""

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import pytest_shard, verify_playwright_shards, verify_pytest_shards


def _invoke(value: str | None, nodeids: list[str]):
    deselected = []
    config = SimpleNamespace(
        getoption=lambda name: value if name == "--yfc-shard" else None,
        hook=SimpleNamespace(pytest_deselected=lambda *, items: deselected.extend(items)),
    )
    items = [SimpleNamespace(nodeid=nodeid) for nodeid in nodeids]
    pytest_shard.pytest_collection_modifyitems(config, items)
    return [item.nodeid for item in items], [item.nodeid for item in deselected]


def _ranked_shard(nodes: list[str], number: int, count: int) -> list[str]:
    selected = set(sorted(nodes)[number - 1 :: count])
    return [node for node in nodes if node in selected]


@pytest.mark.parametrize("count", [5, 10])
def test_every_test_is_selected_exactly_once_across_shards(count: int) -> None:
    nodes = [f"backend/tests/test_example.py::test_{number}" for number in range(102)]
    selections = [_invoke(f"{index}/{count}", nodes) for index in range(1, count + 1)]
    assert sorted(node for selected, _ in selections for node in selected) == sorted(nodes)
    assert all(len(selected) + len(skipped) == len(nodes) for selected, skipped in selections)


@pytest.mark.parametrize("count", [5, 10])
def test_shard_membership_is_stable_when_collection_order_changes(count: int) -> None:
    nodes = [f"backend/tests/test_example.py::test_{number}" for number in range(101)]
    reversed_nodes = list(reversed(nodes))
    for number in range(1, count + 1):
        actual, _ = _invoke(f"{number}/{count}", nodes)
        reversed_actual, _ = _invoke(f"{number}/{count}", reversed_nodes)
        assert set(actual) == set(reversed_actual)
        assert actual == [node for node in nodes if node in set(actual)]


def test_without_shard_no_tests_are_removed() -> None:
    nodes = ["test_a", "test_b"]
    assert _invoke(None, nodes) == (nodes, [])


@pytest.mark.parametrize("value", ["0/5", "1/0", "2/1", "1/foo", "not-a-shard"])
def test_invalid_shard_configuration_fails_closed(value: str) -> None:
    with pytest.raises(pytest.UsageError):
        _invoke(value, ["a", "b"])


def test_empty_shard_fails_closed() -> None:
    with pytest.raises(pytest.UsageError, match="Empty pytest shard"):
        _invoke("2/5", ["a"])


def test_duplicate_node_ids_fail_closed() -> None:
    with pytest.raises(pytest.UsageError, match="Duplicate pytest nodeids"):
        _invoke("1/2", ["a", "a"])


def test_receipts_reject_missing_duplicate_or_inconsistent_shards(tmp_path) -> None:
    nodes = [pytest_shard._digest(str(index)) for index in range(4)]
    for index in (1, 2):
        directory = tmp_path / str(index)
        directory.mkdir()
        (directory / "receipt.json").write_text(
            json.dumps(
                {"shard": f"{index}/2", "all": nodes, "selected": _ranked_shard(nodes, index, 2)}
            ),
            encoding="utf-8",
        )
    verify_pytest_shards.verify(tmp_path, 2)
    second = tmp_path / "2" / "receipt.json"
    receipt = json.loads(second.read_text(encoding="utf-8"))
    receipt["selected"] = [nodes[0], nodes[0]]
    second.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="selection differs"):
        verify_pytest_shards.verify(tmp_path, 2)
    receipt["selected"] = _ranked_shard(nodes, 2, 2)
    receipt["all"] = list(reversed(nodes))
    second.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="collection or selection differs"):
        verify_pytest_shards.verify(tmp_path, 2)
    receipt["all"] = nodes
    receipt["shard"] = "1/2"
    second.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate shard"):
        verify_pytest_shards.verify(tmp_path, 2)
    second.unlink()
    with pytest.raises(ValueError, match="Expected 2 receipts"):
        verify_pytest_shards.verify(tmp_path, 2)


def test_playwright_receipts_reject_duplicate_or_missing_tests(tmp_path) -> None:
    nodes = ["a", "b", "c", "d"]
    for index in (1, 2):
        directory = tmp_path / str(index)
        directory.mkdir()
        (directory / "receipt.json").write_text(
            json.dumps({"shard": f"{index}/2", "all": nodes, "selected": nodes[index - 1 :: 2]}),
            encoding="utf-8",
        )
    verify_playwright_shards.verify(tmp_path, 2)
    second = tmp_path / "2" / "receipt.json"
    receipt = json.loads(second.read_text(encoding="utf-8"))
    receipt["selected"] = ["a", "d"]
    second.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="coverage differs"):
        verify_playwright_shards.verify(tmp_path, 2)
    second.unlink()
    with pytest.raises(ValueError, match="Expected 2 receipts"):
        verify_playwright_shards.verify(tmp_path, 2)


def test_receipt_fails_when_execution_is_missing_or_duplicated(tmp_path) -> None:
    receipt = pytest_shard.ShardReceipt(str(tmp_path / "receipt.json"))
    receipt.collections = [{"shard": "1/1", "all": ["a"], "selected": ["a"]}]
    for executed in ([], ["a", "a"]):
        receipt.executed = executed
        session = SimpleNamespace(exitstatus=0)
        receipt.pytest_sessionfinish(session, 0)
        assert session.exitstatus == 1
        assert not receipt.path.exists()


def test_receipt_tracks_all_test_phases_without_changing_selection(tmp_path) -> None:
    nodeid = "backend/tests/test_example.py::test_case"
    digest = pytest_shard._digest(nodeid)
    receipt = pytest_shard.ShardReceipt(str(tmp_path / "receipt.json"))
    receipt.collections = [{"shard": "1/1", "all": [digest], "selected": [digest]}]
    for phase, seconds in (("setup", 0.25), ("call", 1.0), ("teardown", 0.005)):
        receipt.pytest_runtest_logreport(
            SimpleNamespace(nodeid=nodeid, when=phase, duration=seconds)
        )
    session = SimpleNamespace(exitstatus=0)
    receipt.pytest_sessionfinish(session, 0)

    assert session.exitstatus == 0
    payload = json.loads(receipt.path.read_text(encoding="utf-8"))
    assert payload["selected"] == [digest]
    assert payload["duration_ms"] == {digest: 1255}


def test_receipt_refuses_success_when_timing_is_incomplete(tmp_path) -> None:
    nodeid = "backend/tests/test_example.py::test_case"
    digest = pytest_shard._digest(nodeid)
    receipt = pytest_shard.ShardReceipt(str(tmp_path / "receipt.json"))
    receipt.collections = [{"shard": "1/1", "all": [digest], "selected": [digest]}]
    receipt.executed = [digest]
    session = SimpleNamespace(exitstatus=0)
    receipt.pytest_sessionfinish(session, 0)

    assert session.exitstatus == 1
    assert not receipt.path.exists()


def test_receipts_cover_real_xdist_execution(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    suite = tmp_path / "test_cases.py"
    suite.write_text(
        "import pytest\n@pytest.mark.parametrize('x', range(8))\ndef test_case(x):\n"
        "    if x == 1: pytest.skip('expected')\n    assert x >= 0\n",
        encoding="utf-8",
    )
    for index in (1, 2):
        receipt = tmp_path / f"shard-{index}" / "receipt.json"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(suite),
                "-p",
                "scripts.pytest_shard",
                f"--yfc-shard={index}/2",
                "-n",
                "2",
                "-q",
                "-o",
                f"cache_dir={tmp_path / 'cache'}",
                f"--basetemp={tmp_path / f'tmp-{index}'}",
            ],
            cwd=root,
            env={**os.environ, "YFC_PYTEST_SHARD_RECEIPT": str(receipt)},
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    verify_pytest_shards.verify(tmp_path, 2)
