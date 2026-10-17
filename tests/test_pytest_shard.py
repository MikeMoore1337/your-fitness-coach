"""Tests of single-collection Python CI sharding."""

from types import SimpleNamespace

import pytest
from scripts import pytest_shard


def _invoke(value: str | None, nodeids: list[str]):
    deselected = []
    config = SimpleNamespace(
        getoption=lambda name: value if name == "--yfc-shard" else None,
        hook=SimpleNamespace(pytest_deselected=lambda *, items: deselected.extend(items)),
    )
    items = [SimpleNamespace(nodeid=nodeid) for nodeid in nodeids]
    pytest_shard.pytest_collection_modifyitems(config, items)
    return [item.nodeid for item in items], [item.nodeid for item in deselected]


def test_every_test_is_selected_exactly_once_across_five_shards() -> None:
    nodes = [f"backend/tests/test_example.py::test_{number}" for number in range(102)]
    selections = [_invoke(f"{index}/5", nodes) for index in range(1, 6)]
    assert sorted(node for selected, _ in selections for node in selected) == sorted(nodes)
    assert all(len(selected) + len(skipped) == len(nodes) for selected, skipped in selections)


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
