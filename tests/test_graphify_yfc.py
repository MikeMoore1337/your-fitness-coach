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


def test_main_reports_missing_graphify(monkeypatch, capsys) -> None:
    monkeypatch.setattr(graphify_yfc.shutil, "which", lambda _: None)

    assert graphify_yfc.main(["query", "workout program"]) == 127
    assert graphify_yfc.INSTALL_COMMAND in capsys.readouterr().err


def test_main_passes_arguments_without_shell(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / ".artifacts" / "shared" / "graphify"
    captured: dict[str, object] = {}
    monkeypatch.setattr(graphify_yfc, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(graphify_yfc, "GRAPHIFY_OUTPUT", output)
    monkeypatch.setattr(graphify_yfc.shutil, "which", lambda _: "/tools/graphify")

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(graphify_yfc.subprocess, "run", fake_run)
    dangerous_argument = "; rm -rf /"

    result = graphify_yfc.main(["query", dangerous_argument])

    assert result == 7
    assert captured["command"] == ["/tools/graphify", "query", dangerous_argument]
    assert captured["cwd"] == tmp_path
    assert captured["check"] is False
    assert "shell" not in captured
    assert captured["env"]["GRAPHIFY_OUT"] == str(output)
    assert captured["env"]["GRAPHIFY_QUERY_LOG"] == str(output / "queries.jsonl")
    assert output.is_dir()


def test_main_requires_graphify_arguments(monkeypatch, capsys) -> None:
    called = False

    def fake_which(_):
        nonlocal called
        called = True
        return "/tools/graphify"

    monkeypatch.setattr(graphify_yfc.shutil, "which", fake_which)

    assert graphify_yfc.main([]) == 2
    assert called is False
    assert "Usage:" in capsys.readouterr().err
