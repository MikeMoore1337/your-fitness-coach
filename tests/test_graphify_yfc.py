from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts import graphify_yfc


def test_child_environment_forces_canonical_artifacts(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / ".artifacts" / "shared" / "graphify"
    monkeypatch.setattr(graphify_yfc, "GRAPHIFY_OUTPUT", output)

    environment = graphify_yfc.child_environment(
        {"PATH": "example", "GRAPHIFY_OUT": "wrong", "GRAPHIFY_QUERY_LOG": "wrong"}
    )

    assert environment["PATH"] == "example"
    assert environment["GRAPHIFY_OUT"] == str(output)
    assert environment["GRAPHIFY_QUERY_LOG"] == str(output / "queries.jsonl")


def test_find_graphify_uses_uv_tool_bin(monkeypatch, tmp_path: Path) -> None:
    tool_bin = tmp_path / "bin"
    tool_bin.mkdir()
    executable = tool_bin / "graphify"
    executable.write_text("", encoding="utf-8")
    monkeypatch.setattr(graphify_yfc.shutil, "which", lambda _: None)
    monkeypatch.setattr(graphify_yfc, "_uv_tool_bin", lambda _: tool_bin)

    assert graphify_yfc.find_graphify("/tools/uv") == str(executable)


def test_ensure_graphify_keeps_supported_install(monkeypatch) -> None:
    monkeypatch.setattr(
        graphify_yfc.shutil,
        "which",
        lambda command: "/tools/uv" if command == "uv" else None,
    )
    monkeypatch.setattr(graphify_yfc, "find_graphify", lambda _: "/tools/graphify")
    monkeypatch.setattr(
        graphify_yfc,
        "graphify_version",
        lambda _: graphify_yfc.SUPPORTED_GRAPHIFY_VERSION,
    )

    def unexpected_run(*args, **kwargs):
        del args, kwargs
        raise AssertionError("pinned Graphify must not be reinstalled")

    monkeypatch.setattr(graphify_yfc, "_run", unexpected_run)

    assert graphify_yfc.ensure_graphify() == "/tools/graphify"


def test_ensure_graphify_installs_missing_tool(monkeypatch) -> None:
    calls: list[list[str]] = []
    executables = iter([None, "/uv/bin/graphify"])
    monkeypatch.setattr(
        graphify_yfc.shutil,
        "which",
        lambda command: "/tools/uv" if command == "uv" else None,
    )
    monkeypatch.setattr(graphify_yfc, "find_graphify", lambda _: next(executables))
    monkeypatch.setattr(
        graphify_yfc,
        "graphify_version",
        lambda _: graphify_yfc.SUPPORTED_GRAPHIFY_VERSION,
    )

    def fake_run(command, **kwargs):
        del kwargs
        calls.append(list(command))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(graphify_yfc, "_run", fake_run)

    assert graphify_yfc.ensure_graphify() == "/uv/bin/graphify"
    assert calls == [["/tools/uv", "tool", "install", graphify_yfc.INSTALL_SPEC]]


def test_ensure_graphify_repairs_version_drift(monkeypatch) -> None:
    calls: list[list[str]] = []
    versions = iter(["0.9.62", graphify_yfc.SUPPORTED_GRAPHIFY_VERSION])
    monkeypatch.setattr(
        graphify_yfc.shutil,
        "which",
        lambda command: "/tools/uv" if command == "uv" else None,
    )
    monkeypatch.setattr(graphify_yfc, "find_graphify", lambda _: "/tools/graphify")
    monkeypatch.setattr(graphify_yfc, "graphify_version", lambda _: next(versions))

    def fake_run(command, **kwargs):
        del kwargs
        calls.append(list(command))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(graphify_yfc, "_run", fake_run)

    assert graphify_yfc.ensure_graphify() == "/tools/graphify"
    assert calls == [["/tools/uv", "tool", "install", "--force", graphify_yfc.INSTALL_SPEC]]


def test_bootstrap_builds_missing_graph(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / ".artifacts" / "shared" / "graphify"
    graph = output / "graph.json"
    calls: list[list[str]] = []
    monkeypatch.setattr(graphify_yfc, "GRAPHIFY_OUTPUT", output)
    monkeypatch.setattr(graphify_yfc, "GRAPHIFY_GRAPH", graph)
    monkeypatch.setattr(graphify_yfc, "ensure_graphify", lambda: "/tools/graphify")

    def fake_run(command, **kwargs):
        del kwargs
        calls.append(list(command))
        graph.parent.mkdir(parents=True, exist_ok=True)
        graph.write_text("{}", encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(graphify_yfc, "_run", fake_run)

    assert graphify_yfc.bootstrap() == 0
    assert calls == [["/tools/graphify", "extract", ".", "--code-only", "--no-cluster"]]


def test_bootstrap_refreshes_existing_graph(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / ".artifacts" / "shared" / "graphify"
    graph = output / "graph.json"
    graph.parent.mkdir(parents=True)
    graph.write_text("{}", encoding="utf-8")
    calls: list[list[str]] = []
    monkeypatch.setattr(graphify_yfc, "GRAPHIFY_OUTPUT", output)
    monkeypatch.setattr(graphify_yfc, "GRAPHIFY_GRAPH", graph)
    monkeypatch.setattr(graphify_yfc, "ensure_graphify", lambda: "/tools/graphify")

    def fake_run(command, **kwargs):
        del kwargs
        calls.append(list(command))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(graphify_yfc, "_run", fake_run)

    assert graphify_yfc.bootstrap() == 0
    assert calls == [["/tools/graphify", "extract", ".", "--code-only", "--no-cluster"]]


def test_bootstrap_degrades_cleanly_when_tooling_is_unavailable(monkeypatch, capsys) -> None:
    def fail():
        raise graphify_yfc.GraphifyBootstrapError("uv is unavailable")

    monkeypatch.setattr(graphify_yfc, "ensure_graphify", fail)

    assert graphify_yfc.bootstrap() == 127
    assert "uv is unavailable" in capsys.readouterr().err


def test_main_passes_arguments_without_shell(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / ".artifacts" / "shared" / "graphify"
    captured: dict[str, object] = {}
    monkeypatch.setattr(graphify_yfc, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(graphify_yfc, "GRAPHIFY_OUTPUT", output)
    monkeypatch.setattr(graphify_yfc, "find_graphify", lambda _: "/tools/graphify")
    monkeypatch.setattr(
        graphify_yfc,
        "graphify_version",
        lambda _: graphify_yfc.SUPPORTED_GRAPHIFY_VERSION,
    )

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        captured.update(kwargs)
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(graphify_yfc, "_run", fake_run)
    dangerous_argument = "; rm -rf /"

    result = graphify_yfc.main(["query", dangerous_argument])

    assert result == 7
    assert captured["command"] == ["/tools/graphify", "query", dangerous_argument]
    assert captured["environment"]["GRAPHIFY_OUT"] == str(output)
    assert captured["environment"]["GRAPHIFY_QUERY_LOG"] == str(output / "queries.jsonl")


def test_main_requires_graphify_arguments(capsys) -> None:
    assert graphify_yfc.main([]) == 2
    assert "Usage:" in capsys.readouterr().err


def test_bootstrap_rejects_extra_arguments(capsys) -> None:
    assert graphify_yfc.main(["bootstrap", "--force"]) == 2
    assert "graphify_yfc.py bootstrap" in capsys.readouterr().err
