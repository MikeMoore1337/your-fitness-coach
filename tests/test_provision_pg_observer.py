"""Offline-only tests for Issue #848 one-time host provisioning."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import stat
from types import SimpleNamespace

import pytest
from scripts import provision_pg_observer as p


def test_scram_has_correct_stored_and_server_keys():
    salt = bytes(range(16))
    secret = "deadbeef" * 8
    result = p.scram(secret, salt)
    salted = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, 4096)
    stored = hashlib.sha256(hmac.new(salted, b"Client Key", hashlib.sha256).digest()).digest()
    server = hmac.new(salted, b"Server Key", hashlib.sha256).digest()

    def b64(x: bytes) -> str:
        return base64.b64encode(x).decode()

    assert result == f"SCRAM-SHA-256$4096:{b64(salt)}${b64(stored)}:{b64(server)}"
    assert secret not in result


def test_unprivileged_process_fails_before_any_changes(monkeypatch):
    monkeypatch.setattr(p.os, "geteuid", lambda: 1000)
    with pytest.raises(p.Blocked, match="root_shell_required"):
        p.deploy_account()


def test_database_rejects_ambiguous_and_non_loopback_container(monkeypatch):
    monkeypatch.setattr(p, "execute", lambda *_: "abc\ndef")
    with pytest.raises(p.Blocked, match="db_container_ambiguous"):
        p.database()
    cid = "a" * 64
    monkeypatch.setattr(p, "execute", lambda argv, **kw: cid if argv[1] == "ps" else "0.0.0.0:5432")
    with pytest.raises(p.Blocked, match="db_not_bound_to_loopback_only"):
        p.database()


def test_admin_sql_not_in_arguments(monkeypatch):
    calls = []

    def fake(argv, stdin=None):
        calls.append((argv, stdin))
        return "t"

    monkeypatch.setattr(p, "execute", fake)
    assert p.db_sql("a" * 64, "test_db", "postgres", "SELECT 1") == "t"
    assert "SELECT 1" not in " ".join(calls[0][0])
    assert calls[0][1] == "SELECT 1"
    assert calls[0][0][:6] == ["docker", "exec", "-i", "-u", "postgres", "a" * 64]


def test_verify_runs_as_deploy_user_and_requires_positive_result(monkeypatch):
    calls = []

    def fake(argv, stdin=None):
        calls.append(argv)
        return "PASS"

    monkeypatch.setattr(p, "execute", fake)
    p.verify()
    assert calls[0][:5] == ["runuser", "-u", "yfc-deploy", "--", "/usr/bin/env"]
    assert "-i" in calls[0]
    assert any(s == "PGPASSFILE=/etc/yfc/observer/pgpass" for s in calls[0])
    assert not any("secret" in token.lower() for token in calls[0])
    monkeypatch.setattr(p, "execute", lambda *_: "FAIL")
    with pytest.raises(p.Blocked, match="permissions_invalid"):
        p.verify()


def test_secret_files_are_never_put_in_db_sql(tmp_path, monkeypatch):
    observer = tmp_path / "observer"
    monkeypatch.setattr(p, "ROOT", observer)
    account = SimpleNamespace(pw_uid=1500, pw_gid=os.getgid())
    monkeypatch.setattr(p, "prerequisites", lambda: (account, "a" * 64, "test_db", "postgres"))
    monkeypatch.setattr(p, "secure_parents", lambda: None)
    monkeypatch.setattr(p.os, "chown", lambda *_: None)
    monkeypatch.setattr(p.os, "fchown", lambda *_: None)
    monkeypatch.setattr(p, "verify", lambda: None)
    sql = []
    monkeypatch.setattr(p, "db_sql", lambda *args: sql.append(args[3]) or "")
    p.provision()
    cfg = (observer / "pg_service.conf").read_text()
    row = (observer / "pgpass").read_text()
    secret = row.split(":")[-1].strip()
    assert len(secret) == 64
    assert secret not in sql[0]
    assert "SCRAM-SHA-256$4096:" in sql[0]
    assert "GRANT pg_read_all_stats" in sql[0]
    assert "CONNECTION LIMIT 1" in sql[0]
    assert "default_transaction_read_only=on" in sql[0]
    assert "host=127.0.0.1" in cfg
    assert "passfile=" in cfg
    assert stat.S_IMODE((observer / "pgpass").stat().st_mode) == 0o600
    assert stat.S_IMODE((observer / "pg_service.conf").stat().st_mode) == 0o640


def test_existing_password_file_cannot_be_overwritten(tmp_path):
    filename = tmp_path / "pgpass"
    filename.write_text("do-not-touch")
    with pytest.raises(FileExistsError):
        p.write_stage(filename, "secret", 0, 0, 0o600)
    assert filename.read_text() == "do-not-touch"


def test_failed_role_transaction_leaves_no_password_files(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "ROOT", tmp_path / "observer")
    account = SimpleNamespace(pw_uid=1500, pw_gid=os.getgid())
    monkeypatch.setattr(p, "prerequisites", lambda: (account, "a" * 64, "test_db", "postgres"))
    monkeypatch.setattr(p, "secure_parents", lambda: None)
    monkeypatch.setattr(p.os, "chown", lambda *_: None)
    monkeypatch.setattr(p.os, "fchown", lambda *_: None)
    monkeypatch.setattr(p, "db_sql", lambda *_: (_ for _ in ()).throw(p.Blocked("command_failed")))
    with pytest.raises(p.Blocked):
        p.provision()
    assert not (p.ROOT / "pgpass").exists()
    assert not (p.ROOT / "pg_service.conf").exists()
    assert list(p.ROOT.iterdir()) == []


def test_stdout_stderr_remain_sanitized_on_command_failure(monkeypatch):
    def fake(*a, **kw):
        return SimpleNamespace(returncode=1, stdout="secret", stderr="PASSWORD secret")

    monkeypatch.setattr(p.subprocess, "run", fake)
    with pytest.raises(p.Blocked) as caught:
        p.execute(["missing"], stdin="secret")
    assert str(caught.value) == "command_failed"
