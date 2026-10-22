#!/usr/bin/env python3
"""Issue #848: one-time, fail-closed production PostgreSQL observer bootstrap.

Run as root on the REAL production host, never in a sandbox. No application
deploy, container restart, migration, PostgreSQL configuration or pool changes.
Requires /usr/bin/psql (postgresql-client-16), installed separately.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import os
import pwd
import re
import secrets
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path("/etc/yfc/observer")
USER = "yfc-deploy"
ROLE = "yfc_observer"
PROJECT = "fit-mini-app"


class Blocked(Exception):
    """Sanitized error code, never a credential or SQL text."""


def execute(argv: list[str], stdin: str | None = None) -> str:
    try:
        proc = subprocess.run(
            argv, input=stdin, capture_output=True, text=True,
            timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise Blocked("command_unavailable_or_timed_out") from None
    if proc.returncode:
        # Server errors may include SQL, so do not forward stderr.
        raise Blocked("command_failed")
    return proc.stdout.strip()


def scram(password: str, salt: bytes | None = None) -> str:
    """PG16 SCRAM verifier: plaintext secret never appears in SQL or argv."""
    salt = secrets.token_bytes(16) if salt is None else salt
    salted = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 4096)
    client = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored = hashlib.sha256(client).digest()
    server = hmac.new(salted, b"Server Key", hashlib.sha256).digest()
    b64 = lambda data: base64.b64encode(data).decode("ascii")
    return "SCRAM-SHA-256$4096:" + b64(salt) + "$" + b64(stored) + ":" + b64(server)


def deploy_account() -> pwd.struct_passwd:
    if os.geteuid() != 0:
        raise Blocked("root_shell_required")
    try:
        info = pwd.getpwnam(USER)
    except KeyError:
        raise Blocked("deploy_account_missing") from None
    if info.pw_uid == 0 or info.pw_gid == 0:
        raise Blocked("privileged_deploy_account")
    return info


def database() -> tuple[str, str, str]:
    ids = execute([
        "docker", "ps", "-q",
        "--filter", f"label=com.docker.compose.project={PROJECT}",
        "--filter", "label=com.docker.compose.service=db",
        "--filter", "status=running",
    ]).splitlines()
    if len(ids) != 1 or not re.fullmatch(r"[a-f0-9]{12,64}", ids[0]):
        raise Blocked("db_container_ambiguous")
    cid = ids[0]
    if execute(["docker", "port", cid, "5432/tcp"]).splitlines() != ["127.0.0.1:5432"]:
        raise Blocked("db_not_bound_to_loopback_only")
    name = execute(["docker", "exec", cid, "printenv", "POSTGRES_DB"])
    admin = execute(["docker", "exec", cid, "printenv", "POSTGRES_USER"])
    if not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", x) for x in (name, admin)):
        raise Blocked("database_identifier_unexpected")
    return cid, name, admin


def db_sql(cid: str, name: str, admin: str, sql: str) -> str:
    # Never pass even a SCRAM verifier as an argv argument.
    return execute([
        "docker", "exec", "-i", "-u", "postgres", cid,
        "psql", "-X", "-qAt", "-w", "-v", "ON_ERROR_STOP=1",
        "-U", admin, "-d", name,
    ], stdin=sql)


def secure_parents() -> None:
    for path in (Path("/"), Path("/etc"), ROOT.parent):
        if path.exists() or path.is_symlink():
            data = path.lstat()
            if data.st_uid or not stat.S_ISDIR(data.st_mode) or data.st_mode & 0o022:
                raise Blocked("observer_parent_unprotected")


def prerequisites() -> tuple[pwd.struct_passwd, str, str, str]:
    account = deploy_account()
    if not Path("/usr/bin/psql").exists():
        raise Blocked("psql_missing_install_postgresql_client_16")
    secure_parents()
    if ROOT.exists() or ROOT.is_symlink():
        raise Blocked("observer_directory_exists_do_not_overwrite")
    cid, dbname, admin = database()
    if db_sql(
        cid, dbname, admin,
        "SELECT current_setting('server_version_num')::int >= 160000 "
        "AND current_setting('is_superuser') = 'on';\n",
    ) != "t":
        raise Blocked("postgres_admin_or_version_invalid")
    if db_sql(
        cid, dbname, admin,
        "SELECT count(*) FROM pg_roles WHERE rolname='yfc_observer';\n",
    ) != "0":
        raise Blocked("observer_role_exists_do_not_rotate")
    return account, cid, dbname, admin


def write_stage(path: Path, data: str, uid: int, gid: int, mode: int) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.fchown(fd, uid, gid)
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def verify() -> None:
    query = (
        "SELECT CASE WHEN current_setting('transaction_read_only') = 'on' "
        "AND current_setting('is_superuser') = 'off' "
        "AND pg_has_role(current_user,'pg_read_all_stats','member') "
        "AND (SELECT rolconnlimit = 1 AND NOT rolsuper "
        "AND NOT rolcreatedb AND NOT rolcreaterole "
        "AND NOT rolreplication AND NOT rolbypassrls "
        "FROM pg_roles WHERE rolname = current_user) "
        "THEN 'PASS' ELSE 'FAIL' END;"
    )
    result = execute([
        "runuser", "-u", USER, "--", "/usr/bin/env", "-i",
        "PATH=/usr/bin:/bin",
        f"PGSERVICEFILE={ROOT}/pg_service.conf",
        f"PGPASSFILE={ROOT}/pgpass",
        "PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=5000",
        "/usr/bin/psql", "-X", "-w", "-A", "-t", "-v", "ON_ERROR_STOP=1",
        "--dbname=service=yfc_observer connect_timeout=5",
        "-c", query,
    ])
    if result != "PASS":
        raise Blocked("observer_readonly_or_permissions_invalid")


def provision() -> None:
    account, cid, dbname, admin = prerequisites()
    password = secrets.token_hex(32)
    verifier = scram(password)
    ROOT.parent.mkdir(mode=0o755, exist_ok=True)
    secure_parents()
    ROOT.mkdir(mode=0o700)
    os.chown(ROOT, 0, account.pw_gid)
    ROOT.chmod(0o750)
    nonce = secrets.token_hex(8)
    cfg_tmp = ROOT / f".service-{nonce}.tmp"
    pwd_tmp = ROOT / f".pass-{nonce}.tmp"
    try:
        service = (
            "[yfc_observer]\nhost=127.0.0.1\nport=5432\n"
            f"dbname={dbname}\nuser={ROLE}\nconnect_timeout=5\n"
            f"passfile={ROOT}/pgpass\n"
        )
        password_row = f"127.0.0.1:5432:{dbname}:{ROLE}:{password}\n"
        write_stage(cfg_tmp, service, 0, account.pw_gid, 0o640)
        write_stage(pwd_tmp, password_row, account.pw_uid, account.pw_gid, 0o600)
        sql = (
            "BEGIN;\n"
            f"CREATE ROLE {ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            f"INHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 1 "
            f"PASSWORD '{verifier}';\n"
            f'GRANT CONNECT ON DATABASE "{dbname}" TO {ROLE};\n'
            f"GRANT pg_read_all_stats TO {ROLE};\n"
            f"ALTER ROLE {ROLE} SET default_transaction_read_only=on;\n"
            "COMMIT;\n"
        )
        db_sql(cid, dbname, admin, sql)
        os.replace(cfg_tmp, ROOT / "pg_service.conf")
        os.replace(pwd_tmp, ROOT / "pgpass")
        # A failed validation leaves a stopped, reviewable state: do not
        # blindly rotate or drop a role on retry. No app services are touched.
        verify()
        print("OBSERVER_PROVISIONED_AND_READONLY_VALIDATED")
    finally:
        for path in (cfg_tmp, pwd_tmp):
            path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="YFC Issue #848 observer provisioning")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        if args.check:
            prerequisites()
            print("OBSERVER_PREREQUISITES_PASS")
        else:
            provision()
        return 0
    except Blocked as exc:
        print(f"OBSERVER_BLOCKED:{exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print("OBSERVER_BLOCKED:host_operation_failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
