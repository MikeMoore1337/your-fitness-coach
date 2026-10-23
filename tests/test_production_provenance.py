import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from scripts import production_provenance as provenance

SHA_A = "a" * 40
SHA_B = "b" * 40
IMAGE_REPOSITORY = "ghcr.io/example/your-fitness-coach-backend"
IMAGE_DIGEST = "sha256:" + "d" * 64


@pytest.mark.parametrize(
    ("image_ref", "repo_digests"),
    [
        (f"{IMAGE_REPOSITORY}:{SHA_A}", [f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}"]),
        (f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}", [f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}"]),
    ],
)
def test_validate_image_reference_accepts_verified_tag_or_digest(
    image_ref: str, repo_digests: list[str]
) -> None:
    provenance._validate_image_reference(
        image_ref,
        revision=SHA_A,
        repo_digests=repo_digests,
    )


@pytest.mark.parametrize(
    ("image_ref", "repo_digests", "revision"),
    [
        (f"{IMAGE_REPOSITORY}:{SHA_B}", [f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}"], SHA_A),
        (f"{IMAGE_REPOSITORY}:latest", [f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}"], SHA_A),
        (f"{IMAGE_REPOSITORY}@sha256:{'e' * 63}", [f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}"], SHA_A),
        (f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}", [], SHA_A),
        (
            f"ghcr.io/other/repository@{IMAGE_DIGEST}",
            [f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}"],
            SHA_A,
        ),
        (IMAGE_REPOSITORY, [f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}"], SHA_A),
        (f"{IMAGE_REPOSITORY}:{SHA_A}", [f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}"], ""),
    ],
)
def test_validate_image_reference_rejects_unverified_forms(
    image_ref: str, repo_digests: list[str], revision: str
) -> None:
    with pytest.raises(provenance.ProvenanceError):
        provenance._validate_image_reference(
            image_ref,
            revision=revision,
            repo_digests=repo_digests,
        )


def test_service_snapshot_accepts_production_digest_reference(monkeypatch) -> None:
    image_ref = f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}"
    image_id = "sha256:" + "i" * 64
    responses = {
        ("docker", "ps"): "backend-container\n",
        ("docker", "inspect", "backend-container"): json.dumps(
            [
                {
                    "Config": {"Image": image_ref},
                    "State": {"Status": "running", "Health": {"Status": "healthy"}},
                    "Image": image_id,
                }
            ]
        ),
        ("docker", "image", "inspect", image_ref): json.dumps(
            [
                {
                    "Config": {"Labels": {provenance.REVISION_LABEL: SHA_A}},
                    "Id": image_id,
                    "RepoDigests": [image_ref],
                }
            ]
        ),
    }

    def run(command: list[str]) -> str:
        if command[:2] == ["docker", "ps"]:
            return responses[("docker", "ps")]
        return responses[tuple(command[:4])]

    monkeypatch.setattr(provenance, "_run", run)

    result = provenance._service_snapshot("backend")

    assert result["image_ref"] == image_ref
    assert result["revision"] == SHA_A
    assert result["immutable_image"] is True


def test_service_snapshot_rejects_container_image_id_mismatch(monkeypatch) -> None:
    image_ref = f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}"
    responses = {
        ("docker", "ps"): "backend-container\n",
        ("docker", "inspect", "backend-container"): json.dumps(
            [
                {
                    "Config": {"Image": image_ref},
                    "State": {"Status": "running", "Health": {"Status": "healthy"}},
                    "Image": "sha256:" + "c" * 64,
                }
            ]
        ),
        ("docker", "image", "inspect", image_ref): json.dumps(
            [
                {
                    "Config": {"Labels": {provenance.REVISION_LABEL: SHA_A}},
                    "Id": "sha256:" + "i" * 64,
                    "RepoDigests": [image_ref],
                }
            ]
        ),
    }

    def run(command: list[str]) -> str:
        if command[:2] == ["docker", "ps"]:
            return responses[("docker", "ps")]
        return responses[tuple(command[:4])]

    monkeypatch.setattr(provenance, "_run", run)

    with pytest.raises(provenance.ProvenanceError, match="immutable image ID"):
        provenance._service_snapshot("backend")


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("0126_plan_source_constraint (head)", {"0126_plan_source_constraint"}),
        ("0125_grocery_lists (head)", {"0125_grocery_lists"}),
        ("abcdef1234567890 (head)", {"abcdef1234567890"}),
        ("", set()),
        ("not a revision line", set()),
        (
            "0126_plan_source_constraint (head)\n0127_another_head (head)",
            {"0126_plan_source_constraint", "0127_another_head"},
        ),
    ],
)
def test_parse_alembic_revisions_supports_symbolic_hex_like_and_multiple_heads(
    output: str, expected: set[str]
) -> None:
    assert provenance.parse_alembic_revisions(output) == expected


@pytest.mark.parametrize(
    ("current", "heads", "expected"),
    [
        ({"0126_plan_source_constraint"}, {"0126_plan_source_constraint"}, True),
        (
            {"0125_grocery_lists", "0126_plan_source_constraint"},
            {"0126_plan_source_constraint"},
            True,
        ),
        (set(), {"0126_plan_source_constraint"}, False),
        ({"0126_plan_source_constraint"}, set(), False),
        ({"not a revision line"}, {"0126_plan_source_constraint"}, False),
        ({"0125_grocery_lists"}, {"0126_plan_source_constraint"}, False),
    ],
)
def test_alembic_revision_consistency_is_fail_closed(
    current: set[str], heads: set[str], expected: bool
) -> None:
    assert provenance.alembic_revisions_are_consistent(current, heads) is expected


def test_database_snapshot_parses_symbolic_revision_output(monkeypatch) -> None:
    outputs = iter(
        [
            "INFO [alembic.runtime.migration] Context impl PostgresqlImpl.\n"
            "0126_plan_source_constraint (head)\n",
            "0126_plan_source_constraint (head)\n",
        ]
    )
    monkeypatch.setattr(provenance, "_run", lambda _command: next(outputs))

    result = provenance._database_snapshot("backend-container")

    assert result["current_revisions"] == ["0126_plan_source_constraint"]
    assert result["head_revisions"] == ["0126_plan_source_constraint"]
    assert result["consistent"] is True


@pytest.mark.parametrize(
    ("recorded", "runtime", "expected"),
    [
        (SHA_A, [SHA_A, SHA_A, SHA_A], "OK"),
        (SHA_A, [SHA_B, SHA_B, SHA_B], "PROVENANCE_RECONCILIATION_REQUIRED"),
        (SHA_A, [SHA_A, SHA_B, SHA_A], "MIXED_RUNTIME"),
        ("invalid", [SHA_A, SHA_A, SHA_A], "INVALID_MARKER"),
        (SHA_A, [SHA_A, None, SHA_A], "INVALID_RUNTIME"),
    ],
)
def test_marker_runtime_classification_is_fail_closed(recorded, runtime, expected) -> None:
    assert provenance.classify_marker_runtime(recorded, runtime) == expected


def _verified_snapshot(runtime_revision: str = SHA_B) -> dict[str, object]:
    services = {
        service: {
            "revision": runtime_revision,
            "immutable_image": True,
            "error": None,
            "polling_owner": {"verified": True} if service == "bot" else None,
        }
        for service in provenance.SERVICES
    }
    return {
        "status": "PROVENANCE_RECONCILIATION_REQUIRED",
        "recorded_revision": SHA_A,
        "runtime_revision": runtime_revision,
        "runtime_uniform": True,
        "services": services,
        "release": {
            "path": f"/srv/yfc/fit-mini-app/releases/{runtime_revision}",
            "exists_and_matches": True,
        },
        "current": {"target": f"/srv/yfc/fit-mini-app/releases/{SHA_A}"},
        "database": {"consistent": True},
        "errors": [],
    }


def test_verification_rejects_runtime_revision_not_expected() -> None:
    snapshot = _verified_snapshot(runtime_revision=SHA_B)

    errors = provenance._verification_errors(snapshot, SHA_A)

    assert any("runtime revision" in error for error in errors)


def test_reconcile_changes_only_existing_metadata(monkeypatch, tmp_path: Path) -> None:
    snapshot = _verified_snapshot()
    writes: list[tuple[Path, str]] = []
    links: list[tuple[Path, Path]] = []

    monkeypatch.setattr(provenance, "inspect_production", lambda _root: snapshot)
    monkeypatch.setattr(
        provenance,
        "_atomic_text",
        lambda path, value: writes.append((path, value)),
    )

    def record_link(link: Path, target: Path) -> None:
        links.append((link, target))
        link.write_text(str(target), encoding="utf-8")

    monkeypatch.setattr(provenance, "_atomic_symlink", record_link)
    monkeypatch.setattr(provenance, "_read_revision", lambda _path: SHA_B)

    result = provenance.reconcile(tmp_path, SHA_B)

    assert result["status"] == "RECONCILED"
    assert result["application_mutation"] is False
    assert writes == [
        (tmp_path / ".artifacts/operations/deployments/last-successful-revision", f"{SHA_B}\n")
    ]
    assert links == [
        (tmp_path / "current", Path("/srv/yfc/fit-mini-app/releases") / SHA_B),
    ]


def test_reconcile_rejects_mixed_runtime_before_any_metadata_write(
    monkeypatch, tmp_path: Path
) -> None:
    snapshot = _verified_snapshot()
    snapshot["status"] = "MIXED_RUNTIME"
    snapshot["runtime_revision"] = None
    snapshot["runtime_uniform"] = False
    writes: list[object] = []
    monkeypatch.setattr(provenance, "inspect_production", lambda _root: snapshot)
    monkeypatch.setattr(provenance, "_atomic_text", lambda *args: writes.append(args))

    with pytest.raises(provenance.ProvenanceError, match=r"does not match|not uniform"):
        provenance.reconcile(tmp_path, SHA_B)

    assert writes == []


def test_deploy_preflight_is_before_bundle_transfer_and_reconcile_is_metadata_only() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/deploy.yml").read_text(encoding="utf-8")

    assert (
        workflow.index("Read the active deployed revision")
        < workflow.index("Build immutable deployment bundle")
        < workflow.index("Transfer immutable bundle to production")
    )
    assert "Production provenance mismatch before transfer" in workflow
    assert "options: [deploy, repair, verify, reconcile, rollback]" in workflow
    reconcile = workflow.split("\n  reconcile:\n", maxsplit=1)[1].split(
        "\n  rollback:", maxsplit=1
    )[0]
    assert "python3 - reconcile" in reconcile
    assert "application_mutation == false" in reconcile
    assert "deploy_production.sh" not in reconcile
    assert "docker compose" not in reconcile


CONTAINER_ID = "c" * 64
STARTED_AT = "2026-10-21T00:00:00.000000000Z"


@pytest.fixture
def bot_container():
    return {
        "Id": CONTAINER_ID,
        "Image": IMAGE_DIGEST,
        "State": {"Status": "running", "Pid": 1234, "StartedAt": STARTED_AT},
    }


@pytest.fixture
def bot_runtime(monkeypatch, bot_container):
    monkeypatch.setattr(provenance, "_container_id", lambda _service: CONTAINER_ID[:12])
    monkeypatch.setattr(provenance, "_json_command", lambda _command: [bot_container])
    monkeypatch.setattr(provenance, "_run", lambda _command: "PID\n1234\n")
    monkeypatch.setattr(provenance, "_bot_process_owner", lambda _pid: "100")
    monkeypatch.setattr(
        provenance,
        "_bot_startup_markers",
        lambda *_args: dict.fromkeys(provenance.BOT_RUNTIME_MARKERS, True),
    )


def test_bot_runtime_requires_consistent_live_owner(bot_runtime, bot_container):
    result = provenance._bot_runtime_snapshot(bot_container)
    assert result["polling_owner"] == {"verified": True, "pid": 1234}


@pytest.mark.parametrize("change", ["restart", "replacement", "image", "duplicate", "pid_reused"])
def test_bot_runtime_rejects_changed_or_ambiguous_identity(
    monkeypatch, bot_runtime, bot_container, change
):
    current = {**bot_container, "State": dict(bot_container["State"])}
    if change == "restart":
        current["State"]["StartedAt"] = "2026-10-21T01:00:00Z"
    elif change == "image":
        current["Image"] = "sha256:" + "e" * 64
    elif change == "replacement":
        monkeypatch.setattr(provenance, "_container_id", lambda _: "f" * 12)
    elif change == "duplicate":
        monkeypatch.setattr(provenance, "_run", lambda _: "PID\n1234\n1235\n")
    else:
        identities = iter(["100", "101"])
        monkeypatch.setattr(provenance, "_bot_process_owner", lambda _: next(identities))
    monkeypatch.setattr(provenance, "_json_command", lambda _: [current])
    with pytest.raises(provenance.ProvenanceError, match=r"changed|ambiguous"):
        provenance._bot_runtime_snapshot(bot_container)


@pytest.mark.parametrize("source", ["process", "logs", "docker"])
def test_bot_runtime_sanitizes_evidence_errors(monkeypatch, bot_runtime, bot_container, source):
    def fail(*_args):
        raise PermissionError("secret token-derived polling-name.lock and raw user log")

    target = {
        "process": "_bot_process_owner",
        "logs": "_bot_startup_markers",
        "docker": "_json_command",
    }[source]
    monkeypatch.setattr(provenance, target, fail)
    with pytest.raises(provenance.ProvenanceError) as error:
        provenance._bot_runtime_snapshot(bot_container)
    assert str(error.value) == "bot runtime evidence unavailable or malformed"


def _marker_line(marker, timestamp=STARTED_AT, **changes):
    event = {"service": "telegram-bot", "logger": "__main__", "message": marker, **changes}
    return (timestamp + " " + json.dumps(event) + "\n").encode()


def _logs(monkeypatch, content, returncode=0):
    calls = []

    class Process:
        stdout = io.BytesIO(content)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.stdout.close()

        def wait(self):
            return returncode

        def kill(self):
            pass

    def popen(command, **_kwargs):
        calls.append(command)
        return Process()

    monkeypatch.setattr(provenance.subprocess, "Popen", popen)
    return calls


def test_long_lived_bot_streams_markers_outside_last_200_lines(monkeypatch):
    content = b"".join(_marker_line(marker) for marker in provenance.BOT_RUNTIME_MARKERS)
    content += b"2026-10-21T01:00:00Z ordinary user activity\n" * 10000
    calls = _logs(monkeypatch, content)
    assert all(provenance._bot_startup_markers(CONTAINER_ID, STARTED_AT).values())
    assert calls == [["docker", "logs", "--timestamps", "--since", STARTED_AT, CONTAINER_ID]]


@pytest.mark.parametrize(
    "kind", ["stale", "substring", "wrong_logger", "wrong_service", "missing", "error"]
)
def test_bot_startup_evidence_rejects_stale_spoofed_or_unavailable_logs(monkeypatch, kind):
    timestamp = "2026-10-20T23:00:00Z" if kind == "stale" else STARTED_AT
    changes = {"logger": "other"} if kind == "wrong_logger" else {}
    if kind == "wrong_service":
        changes["service"] = "other"
    markers = (
        provenance.BOT_RUNTIME_MARKERS[:1] if kind == "missing" else provenance.BOT_RUNTIME_MARKERS
    )
    content = b"".join(_marker_line(marker, timestamp, **changes) for marker in markers)
    if kind == "substring":
        content = _marker_line(" ".join(provenance.BOT_RUNTIME_MARKERS))
    _logs(monkeypatch, content, returncode=1 if kind == "error" else 0)
    with pytest.raises(provenance.ProvenanceError, match="evidence"):
        provenance._bot_startup_markers(CONTAINER_ID, STARTED_AT)


@pytest.fixture
def proc_evidence(tmp_path, monkeypatch):
    root = tmp_path / "proc"
    process = root / "1234"
    for directory in ("fd", "fdinfo", "root/var/lock/fitminiapp-bot"):
        (process / directory).mkdir(parents=True)
    (process / "stat").write_text("1234 (python) S " + "0 " * 18 + "100\n")
    (process / "cmdline").write_bytes(b"python\0-m\0fitminiapp_bot.bot\0")
    token = b"synthetic-test-token"
    (process / "environ").write_bytes(b"TELEGRAM_BOT_TOKEN=" + token + b"\0")
    lock = (
        process
        / "root/var/lock/fitminiapp-bot"
        / ("polling-" + hashlib.sha256(token).hexdigest()[:24] + ".lock")
    )
    lock.touch()
    os.link(lock, process / "fd/3")
    stat = lock.stat()
    monkeypatch.setattr(provenance.os, "makedev", lambda _major, _minor: stat.st_dev, raising=False)
    record = f"1: FLOCK ADVISORY WRITE 1234 00:01:{stat.st_ino} 0 EOF\n"
    (root / "locks").write_text(record)
    (process / "fdinfo/3").write_text("lock:\t" + record)
    return root, process, lock


def test_process_owner_matches_descriptor_and_kernel_inode(proc_evidence):
    root, _, _ = proc_evidence
    assert provenance._bot_process_owner(1234, proc_root=root) == "100"


@pytest.mark.parametrize("target", ["/run/lock", "../run/lock", "/../../run/lock"])
def test_process_owner_resolves_lock_alias_inside_container(proc_evidence, monkeypatch, target):
    root, process, lock = proc_evidence
    destination = process / "root/run/lock/fitminiapp-bot"
    destination.parent.mkdir(parents=True)
    lock.parent.rename(destination)
    alias = process / "root/var/lock"
    is_symlink, readlink = Path.is_symlink, os.readlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == alias or is_symlink(path))
    monkeypatch.setattr(os, "readlink", lambda path: target if path == alias else readlink(path))

    assert provenance._bot_process_owner(1234, proc_root=root) == "100"


def test_process_owner_rejects_container_symlink_loop(proc_evidence, monkeypatch):
    root, process, _ = proc_evidence
    alias = process / "root/var/lock"
    is_symlink, readlink = Path.is_symlink, os.readlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == alias or is_symlink(path))
    monkeypatch.setattr(
        os, "readlink", lambda path: "/var/lock" if path == alias else readlink(path)
    )

    with pytest.raises(provenance.ProvenanceError, match="symlink"):
        provenance._bot_process_owner(1234, proc_root=root)


@pytest.mark.skipif(sys.platform != "linux", reason="requires a real absolute POSIX symlink")
def test_process_owner_resolves_real_absolute_container_symlink(proc_evidence):
    root, process, lock = proc_evidence
    destination = process / "root/run/lock/fitminiapp-bot"
    destination.parent.mkdir(parents=True)
    lock.parent.rename(destination)
    alias = process / "root/var/lock"
    alias.rmdir()
    alias.symlink_to("/run/lock", target_is_directory=True)

    assert provenance._bot_process_owner(1234, proc_root=root) == "100"


@pytest.mark.parametrize(
    "problem",
    [
        "missing",
        "wrong_pid",
        "shared",
        "posix",
        "ambiguous",
        "fdinfo",
        "descriptor",
        "wrong_inode",
        "wrong_command",
        "zombie",
    ],
)
def test_process_owner_fails_closed(proc_evidence, problem):
    root, process, lock = proc_evidence
    record = (root / "locks").read_text()
    if problem == "missing":
        record = ""
    elif problem == "wrong_pid":
        record = record.replace("WRITE 1234", "WRITE 9999")
    elif problem == "shared":
        record = record.replace("WRITE", "READ")
    elif problem == "posix":
        record = record.replace("FLOCK", "POSIX")
    elif problem == "ambiguous":
        record *= 2
    elif problem == "fdinfo":
        (process / "fdinfo/3").write_text("")
    elif problem == "descriptor":
        os.link(lock, process / "fd/4")
    elif problem == "wrong_inode":
        record = record.replace(str(lock.stat().st_ino), "99999999")
    elif problem == "wrong_command":
        (process / "cmdline").write_bytes(b"python\0-m\0other.bot\0")
    else:
        (process / "stat").write_text("1234 (python) Z " + "0 " * 18 + "100\n")
    (root / "locks").write_text(record)
    with pytest.raises(provenance.ProvenanceError):
        provenance._bot_process_owner(1234, proc_root=root)


def test_invalid_runtime_blocks_cli_verification_and_reconciliation(monkeypatch, tmp_path, capsys):
    snapshot = _verified_snapshot()
    snapshot["status"] = "INVALID_RUNTIME"
    snapshot["services"]["bot"]["polling_owner"] = {"verified": False}
    monkeypatch.setattr(provenance, "inspect_production", lambda _: snapshot)
    for command in ("verify", "reconcile"):
        assert (
            provenance.main([command, "--app-root", str(tmp_path), "--expected-revision", SHA_B])
            == 1
        )
        assert "INVALID_RUNTIME" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_deploy_workflow_requires_live_owner_and_blocks_invalid_runtime_before_transfer():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/deploy.yml").read_text()
    preflight = workflow.split("name: Read the active deployed revision", 1)[1].split(
        "name: Build immutable deployment bundle", 1
    )[0]
    assert 'if [ "$status" != OK ]; then' in preflight
    assert "exit 1" in preflight
    assert workflow.count("(.services.bot.polling_owner.verified == true) and") == 2


@pytest.mark.parametrize("failure", [None, "flock", "stale", "revision", "access"])
def test_full_snapshot_combines_container_process_lock_and_startup_evidence(
    monkeypatch, tmp_path, proc_evidence, bot_container, failure
):
    proc_root, _, _ = proc_evidence
    real_owner = provenance._bot_process_owner
    monkeypatch.setattr(
        provenance, "_bot_process_owner", lambda pid: real_owner(pid, proc_root=proc_root)
    )
    if failure == "flock":
        (proc_root / "locks").write_text("")
    elif failure == "access":

        def denied(_pid):
            raise PermissionError("secret-lock-name")

        monkeypatch.setattr(provenance, "_bot_process_owner", denied)
    timestamp = "2026-10-20T00:00:00Z" if failure == "stale" else STARTED_AT
    _logs(
        monkeypatch,
        b"".join(_marker_line(marker, timestamp) for marker in provenance.BOT_RUNTIME_MARKERS),
    )

    def run(command):
        if command[:2] == ["docker", "ps"]:
            service = command[command.index("--filter") + 1].split("=")[-1]
            return CONTAINER_ID[:12] if service == "bot" else service
        if command[:2] == ["docker", "top"]:
            return "PID\n1234\n"
        if command[:2] == ["docker", "inspect"]:
            service = "bot" if command[2].startswith(CONTAINER_ID[:12]) else command[2]
            revision = SHA_B if failure == "revision" and service == "bot" else SHA_A
            return json.dumps(
                [
                    {
                        **bot_container,
                        "Config": {"Image": service + ":" + revision},
                        "State": {**bot_container["State"], "Health": {"Status": "healthy"}},
                    }
                ]
            )
        if command[:3] == ["docker", "image", "inspect"]:
            revision = SHA_B if failure == "revision" and command[-1].startswith("bot:") else SHA_A
            return json.dumps(
                [
                    {
                        "Id": IMAGE_DIGEST,
                        "Config": {"Labels": {provenance.REVISION_LABEL: revision}},
                        "RepoDigests": ["repo@" + IMAGE_DIGEST],
                    }
                ]
            )
        if command[:2] == ["docker", "exec"]:
            return "0130_workout_rest_sessions (head)"
        raise AssertionError(command)

    monkeypatch.setattr(provenance, "_run", run)
    state_root = tmp_path / ".artifacts/operations/deployments"
    state_root.mkdir(parents=True)
    (state_root / "last-successful-revision").write_text(SHA_A)
    release = tmp_path / "releases" / SHA_A
    release.mkdir(parents=True)
    (release / ".deployment-sha").write_text(SHA_A)
    snapshot = provenance.inspect_production(tmp_path)
    if failure:
        assert snapshot["status"] == (
            "MIXED_RUNTIME" if failure == "revision" else "INVALID_RUNTIME"
        )
        assert provenance._verification_errors(snapshot, SHA_A)
        assert "secret-lock-name" not in json.dumps(snapshot)
    else:
        assert snapshot["status"] == "OK"
        assert snapshot["services"]["bot"]["polling_owner"]["verified"] is True
        assert provenance._verification_errors(snapshot, SHA_A) == []


@pytest.mark.skipif(sys.platform != "linux", reason="requires Linux procfs and real kernel FLOCK")
def test_real_linux_kernel_flock_owner(tmp_path):
    import select

    package = tmp_path / "fitminiapp_bot"
    package.mkdir()
    (package / "__init__.py").touch()
    (package / "bot.py").write_text(
        "import fcntl, hashlib, os, pathlib, sys\n"
        "name = hashlib.sha256(os.environ['TELEGRAM_BOT_TOKEN'].encode()).hexdigest()[:24]\n"
        "path = pathlib.Path(os.environ['BOT_POLLING_LOCK_DIR']) / f'polling-{name}.lock'\n"
        "with path.open('a+') as lock:\n"
        " fcntl.flock(lock, fcntl.LOCK_EX)\n"
        " print('ready', flush=True)\n"
        " sys.stdin.readline()\n"
        " fcntl.flock(lock, fcntl.LOCK_UN)\n"
        " print('released', flush=True)\n"
        " sys.stdin.read()\n"
    )
    environment = {
        **os.environ,
        "TELEGRAM_BOT_TOKEN": "synthetic-kernel-test",
        "BOT_POLLING_LOCK_DIR": str(tmp_path),
    }
    with subprocess.Popen(
        [sys.executable, "-m", "fitminiapp_bot.bot"],
        cwd=tmp_path,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as process:
        try:
            assert select.select([process.stdout], [], [], 10)[0], "lock child did not become ready"
            assert process.stdout.readline() == b"ready\n"
            assert provenance._bot_process_owner(process.pid).isdigit()
            process.stdin.write(b"release\n")
            process.stdin.flush()
            assert select.select([process.stdout], [], [], 10)[0]
            assert process.stdout.readline() == b"released\n"
            try:
                provenance._bot_process_owner(process.pid)
            except provenance.ProvenanceError:
                pass
            else:
                raise AssertionError("a live bot process without FLOCK must be rejected")
        finally:
            process.terminate()
            process.wait(timeout=10)



def test_restricted_host_proc_uses_nonroot_container_proof(monkeypatch):
    def denied(_pid):
        raise PermissionError("host /proc/host-pid/environ is not readable")

    calls = []
    monkeypatch.setattr(provenance, "_bot_process_owner", denied)
    monkeypatch.setattr(
        provenance,
        "_bot_process_owner_in_container",
        lambda container_id, pid: calls.append((container_id, pid)) or "123",
    )
    assert provenance._bot_process_owner_with_container_fallback(CONTAINER_ID, 1234) == "123"
    assert calls == [(CONTAINER_ID, 1234)]


def test_restricted_proc_does_not_fallback_on_invalid_host_lock(monkeypatch):
    monkeypatch.setattr(
        provenance,
        "_bot_process_owner",
        lambda _pid: (_ for _ in ()).throw(
            provenance.ProvenanceError("bot exclusive kernel FLOCK owner is unverified")
        ),
    )
    monkeypatch.setattr(
        provenance,
        "_bot_process_owner_in_container",
        lambda *_args: pytest.fail("invalid owner must never be treated as permissions"),
    )
    with pytest.raises(provenance.ProvenanceError, match="FLOCK"):
        provenance._bot_process_owner_with_container_fallback(CONTAINER_ID, 1234)


@pytest.mark.skipif(sys.platform != "linux", reason="requires /proc on Linux")
def test_container_probe_requires_same_uid_and_matches_host_starttime(monkeypatch):
    current_pid = os.getpid()
    host_stat = (Path("/proc") / str(current_pid) / "stat").read_text()
    starttime = host_stat.rsplit(")", 1)[1].split()[19]
    executed = []

    def run(command, **kwargs):
        executed.append((command, kwargs))
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps({"verified": True, "starttime": starttime})
        )

    monkeypatch.setattr(provenance.subprocess, "run", run)
    assert provenance._bot_process_owner_in_container(CONTAINER_ID, current_pid) == starttime
    command, options = executed[0]
    assert command[:5] == ["docker", "exec", "--user", "10001:10001", CONTAINER_ID]
    assert command[5:7] == ["python", "-c"]
    assert "_BOT_CONTAINER_OWNER_PROBE" not in command[7]
    assert "FLOCK" in command[7]
    assert options["timeout"] == 20
    assert options["check"] is True


@pytest.mark.parametrize("output", [
    "{}",
    '{"verified": false, "starttime": "1"}',
    '{"verified": true, "starttime": "unrelated"}',
    '{"verified": true, "starttime": "1", "token": "sensitive"}',
    "invalid-json",
])
@pytest.mark.skipif(sys.platform != "linux", reason="requires /proc on Linux")
def test_container_probe_fails_closed_on_untrusted_response(monkeypatch, output):
    current_pid = os.getpid()
    monkeypatch.setattr(
        provenance.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 0, stdout=output),
    )
    with pytest.raises((provenance.ProvenanceError, ValueError)):
        provenance._bot_process_owner_in_container(CONTAINER_ID, current_pid)


@pytest.mark.skipif(sys.platform != "linux", reason="requires /proc on Linux")
def test_container_probe_fails_closed_if_docker_exec_denied(monkeypatch):
    current_pid = os.getpid()

    def fail(command, **_kwargs):
        raise subprocess.CalledProcessError(1, command, stderr="secret-token-not-for-logs")

    monkeypatch.setattr(provenance.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        provenance._bot_process_owner_in_container(CONTAINER_ID, current_pid)
