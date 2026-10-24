from __future__ import annotations

import pytest
from scripts import sequential_deploy_safety as safety


def snapshot():
    return {
        "version": 16,
        "maximum": 100,
        "reserved": 3,
        "superuser": False,
        "stats": True,
        "connection_limit": 1,
        "dangerous": False,
        "readonly": True,
        "application_access": False,
        "unsupported": 0,
        "server": "172.20.0.2",
        "port": 5432,
        "database": "test",
        "observer": 99,
        "clients": [{"pid": 99, "start": "now", "address": "172.20.0.1", "port": 1200}],
    }


def test_socket_probe_ignores_only_known_database_free_healthchecks():
    assert safety.SOCKET_PROBE_PROCESS_RULE in safety.SOCKET_PROBE
    assert safety.SOCKET_PROBE.index("def is_known_healthcheck") < safety.SOCKET_PROBE.index(
        "known_healthcheck = command.startswith"
    )
    namespace = {}
    exec(safety.SOCKET_PROBE_PROCESS_RULE, namespace)
    is_known_healthcheck = namespace["is_known_healthcheck"]
    count = namespace["application_process_count"]

    backend = [b"python", b"-c", safety.SOCKET_PROBE_HEALTHCHECK_COMMANDS[0].encode(), b""]
    worker = [b"python", b"-c", safety.SOCKET_PROBE_HEALTHCHECK_COMMANDS[1].encode(), b""]
    unknown_inline = [b"python", b"-c", b"print('not a Docker healthcheck')", b""]
    unknown_command = [b"python", b"worker.py", b""]
    extra_argument = [*backend[:-1], b"unexpected", b""]

    assert is_known_healthcheck(backend)
    assert is_known_healthcheck(worker)
    assert not is_known_healthcheck(unknown_inline)
    assert not is_known_healthcheck(unknown_command)
    assert not is_known_healthcheck(extra_argument)

    assert count([(False, set()), (True, set())], set()) == 1
    assert count([(False, set()), (True, {"db-socket"})], {"db-socket"}) == 2
    for unknown in (unknown_inline, unknown_command, extra_argument):
        assert count([(False, set()), (is_known_healthcheck(unknown), set())], set()) == 2


def container(name="backend", *, running=True, restart="no", exit_code=0):
    return {
        "id": name,
        "labels": {"com.docker.compose.service": name, "com.docker.compose.project": "yfc"},
        "restart": restart,
        "state": {"Running": running, "StartedAt": "now", "Paused": False, "ExitCode": exit_code},
    }


@pytest.fixture
def guard(tmp_path, monkeypatch):
    guard = safety.SequentialSafety(tmp_path, 10)
    guard.project = "yfc"
    guard.caps = {"backend": 30, "worker": 30, "setup": 30}
    monkeypatch.setattr(guard, "inventory", lambda: [container()])
    monkeypatch.setattr(guard, "observe", lambda _items: (snapshot(), [], {"172.20.0.2"}))
    monkeypatch.setattr(
        guard, "run", lambda *args: b"true" if args[-1] in safety.DB_CONSUMERS else b""
    )
    monkeypatch.setattr(
        guard, "json", lambda *args: {"processes": 1, "sockets": [], "size": 10, "overflow": 20}
    )
    return guard


def test_every_reachable_phase_includes_observer_and_positive_margin():
    report = safety.phase_budget(snapshot(), {"backend": 30, "worker": 30, "setup": 30}, 10)
    assert max(report.values()) == 72
    assert report["migration"] == 12
    assert report["setup_seed"] == 41
    assert report["rollback_worker"] == 71
    assert {
        "steady",
        "backup",
        "drained",
        "migration",
        "setup_readiness",
        "setup_seed",
        "backend_start",
        "worker_readiness",
        "worker_start",
        "bot_start",
        "rollback_stop",
        "rollback_backend",
        "rollback_worker",
        "rollback_bot",
    } == report.keys()


@pytest.mark.parametrize("margin", [None, 0, -1, True, "10", 36])
def test_unknown_or_excessive_policy_never_passes(margin):
    with pytest.raises(safety.SafetyError):
        safety.phase_budget(snapshot(), {"backend": 30, "worker": 30, "setup": 30}, margin)


@pytest.mark.parametrize(
    "key,value",
    [
        ("superuser", True),
        ("stats", False),
        ("dangerous", True),
        ("unsupported", 1),
        ("server", "192.0.2.1"),
        ("database", "wrong"),
        ("version", 15),
        ("port", 6432),
    ],
)
def test_wrong_database_or_privileged_observer_is_rejected(key, value):
    observed = snapshot()
    observed[key] = value
    with pytest.raises(safety.SafetyError, match="identity_or_visibility"):
        safety.validate_snapshot(observed, addresses={"172.20.0.2"}, database="test")


def test_observer_and_background_processes_are_not_application_connections():
    observed = snapshot()
    assert safety.validate_snapshot(observed, addresses={"172.20.0.2"}, database="test") == []
    observed["clients"].append(observed["clients"][0])
    with pytest.raises(safety.SafetyError, match="inconsistent"):
        safety.validate_snapshot(observed, addresses={"172.20.0.2"}, database="test")


def test_live_attribution_works_without_application_name_and_without_backend_observer(
    guard, monkeypatch
):
    observed = snapshot()
    legacy = {"pid": 101, "start": "now", "address": "172.20.0.3", "port": 55000}
    observed["clients"].append(legacy)
    monkeypatch.setattr(guard, "observe", lambda _: (observed, [legacy], {"172.20.0.2"}))
    monkeypatch.setattr(
        guard,
        "json",
        lambda *args: {
            "processes": 1,
            "size": 10,
            "overflow": 20,
            "sockets": [["172.20.0.3", 55000, "172.20.0.2", 5432]],
        },
    )
    guard.check(frozenset({"backend"}))
    monkeypatch.setattr(guard, "inventory", lambda: [container(running=False)])
    monkeypatch.setattr(guard, "observe", lambda _: (snapshot(), [], {"172.20.0.2"}))
    guard.released()
    assert guard.last_report["backup"] == 72


def test_transient_unmatched_client_requires_two_fresh_clean_checks(guard, monkeypatch):
    observations = 0
    sleeps = []

    def observe(_):
        nonlocal observations
        observations += 1
        if observations == 1:
            return (
                snapshot(),
                [{"pid": 42, "start": "now", "address": None, "port": -1}],
                {"172.20.0.2"},
            )
        return snapshot(), [], {"172.20.0.2"}

    monkeypatch.setattr(guard, "observe", observe)
    monkeypatch.setattr(safety.time, "sleep", sleeps.append)
    guard.check(frozenset({"backend"}))

    assert observations == 5  # failed join, then two complete two-snapshot checks
    assert sleeps == [0.15, 0.15]


def test_persistent_unmatched_client_blocks_after_bounded_rechecks(guard, monkeypatch):
    observations = 0
    sleeps = []

    def observe(_):
        nonlocal observations
        observations += 1
        return (
            snapshot(),
            [{"pid": 43, "start": "now", "address": None, "port": -1}],
            {"172.20.0.2"},
        )

    monkeypatch.setattr(guard, "observe", observe)
    monkeypatch.setattr(safety.time, "sleep", sleeps.append)

    with pytest.raises(safety.SafetyError, match="unknown_or_unreleased_database_client"):
        guard.check(frozenset({"backend"}))

    assert observations == 5
    assert sleeps == [0.15] * 4


@pytest.mark.parametrize("name", ["backend-blue", "worker-green", "setup", "bot-blue"])
def test_unexpected_slot_or_orphaned_setup_blocks_before_launch(guard, monkeypatch, name):
    monkeypatch.setattr(guard, "inventory", lambda: [container(), container(name)])
    with pytest.raises(safety.SafetyError, match="unexpected_active"):
        guard.check(frozenset({"backend"}))


@pytest.mark.parametrize(
    "case",
    [
        "stuck_stop",
        "killed",
        "restart",
        "missing",
        "unknown_db",
        "no_observer",
        "multiprocess",
        "oversized_pool",
        "capacity",
    ],
)
def test_failures_stop_at_the_barrier(guard, monkeypatch, case):
    expected = frozenset({"backend"})
    if case == "stuck_stop":
        expected = frozenset()
    elif case == "killed":
        expected = frozenset()
        monkeypatch.setattr(guard, "inventory", lambda: [container(running=False, exit_code=137)])
    elif case == "restart":
        monkeypatch.setattr(guard, "inventory", lambda: [container(restart="always")])
    elif case == "missing":
        monkeypatch.setattr(guard, "inventory", lambda: [])
    elif case == "unknown_db":
        monkeypatch.setattr(
            guard, "observe", lambda _: (snapshot(), [{"address": "unknown", "port": 12}], set())
        )
    elif case == "no_observer":

        def unavailable(_):
            raise OSError("do not leak credentials")

        monkeypatch.setattr(guard, "observe", unavailable)
    elif case in {"multiprocess", "oversized_pool"}:
        monkeypatch.setattr(
            guard,
            "json",
            lambda *args: {
                "processes": 2 if case == "multiprocess" else 1,
                "size": 90 if case == "oversized_pool" else 10,
                "overflow": 20,
                "sockets": [],
            },
        )
    else:
        guard.margin = 40
    with pytest.raises(safety.SafetyError) as error:
        guard.check(expected)
    assert "credentials" not in str(error.value)


def test_observation_is_never_reused_after_runtime_changes(guard, monkeypatch):
    calls = 0

    def inventory():
        nonlocal calls
        calls += 1
        item = container()
        if calls > 1:
            item["state"]["StartedAt"] = "restarted"
        return [item]

    monkeypatch.setattr(guard, "inventory", inventory)
    with pytest.raises(safety.SafetyError, match="runtime_changed"):
        guard.check(frozenset({"backend"}))


def test_new_client_between_socket_join_and_recheck_blocks(guard, monkeypatch):
    calls = 0

    def observe(_):
        nonlocal calls
        calls += 1
        clients = (
            [] if calls == 1 else [{"pid": 123, "start": "later", "address": "bad", "port": 11}]
        )
        return snapshot(), clients, set()

    monkeypatch.setattr(guard, "observe", observe)
    with pytest.raises(safety.SafetyError, match="clients_changed"):
        guard.check(frozenset({"backend"}))


def test_unknown_consumer_is_denied_even_before_its_first_connection(guard, monkeypatch):
    monkeypatch.setattr(guard, "run", lambda *args: b"true")
    monkeypatch.setattr(guard, "inventory", lambda: [container(), container("new-service")])
    with pytest.raises(safety.SafetyError, match="unknown_configured"):
        guard.check(frozenset({"backend"}))


def test_disarm_covers_all_existing_slots_and_does_not_start_anything(guard, monkeypatch):
    items = [container(), container("worker-blue", running=False), container("bot-green")]
    calls = []
    monkeypatch.setattr(guard, "inventory", lambda: items)
    monkeypatch.setattr(guard, "run", lambda *args: calls.append(args))
    guard.disarm()
    assert calls == [("docker", "update", "--restart=no", item["id"]) for item in items]


def test_observer_command_clears_ambient_credentials_and_uses_fixed_service(guard, monkeypatch):
    calls = []
    db = container("db")
    db["networks"] = {"default": {"IPAddress": "172.20.0.2"}}
    monkeypatch.setattr(safety, "_protected_observer_files", lambda: None)
    monkeypatch.setattr(guard, "run", lambda *args: b"test\n")
    monkeypatch.setattr(guard, "json", lambda *args: calls.append(args) or snapshot())
    safety.SequentialSafety.observe(guard, [db])
    assert calls[0][:3] == ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin")
    assert any(arg.startswith("--dbname=service=yfc_observer ") for arg in calls[0])
    assert calls[0][-1] == safety.OBSERVER_SQL
    assert not any("DATABASE_URL" in arg for arg in calls[0])


def test_engine_probe_is_offline_and_unlimited_pools_are_refused(guard, monkeypatch):
    calls = []

    def output(*args):
        calls.append(args)
        if args[1] == "compose":
            return {"name": "yfc", "services": {}}
        return {"size": 10, "overflow": -1}

    monkeypatch.setattr(guard, "json", output)
    with pytest.raises(safety.SafetyError, match="pool_ceiling_unknown"):
        guard.configure(("sha256:" + "a" * 64,))
    assert calls[1][1:6] == ("run", "--rm", "--network", "none", "--env-file")
