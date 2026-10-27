"""Live barriers for the existing single-slot maintenance path; no resumable state.

Docker/PG are authoritative. Every check obtains new observations. A killed helper
leaves restart disabled; a subsequent invocation must verify reality from scratch.
"""

from __future__ import annotations

import ipaddress
import json
import os
import pwd
import stat
import time
from pathlib import Path

try:
    from scripts.trusted_runtime_collector import CollectorPolicy, _run_bounded
except ModuleNotFoundError:
    from trusted_runtime_collector import CollectorPolicy, _run_bounded

CONSUMERS = frozenset(
    {
        "setup",
        *(
            f"{kind}{suffix}"
            for kind in ("backend", "worker", "bot")
            for suffix in ("", "-blue", "-green")
        ),
    }
)
DB_CONSUMERS = CONSUMERS - {"bot", "bot-blue", "bot-green"}
OBSERVER_DIRECTORY = Path("/etc/yfc/observer")
DEPLOY_ACCOUNT = "yfc-deploy"

# Raw tuples stay in memory. Never emit query text, usernames or client addresses.
OBSERVER_SQL = """
SELECT json_build_object(
 'version', current_setting('server_version_num')::int / 10000,
 'maximum', current_setting('max_connections')::int,
 'reserved', current_setting('superuser_reserved_connections')::int
   + coalesce(nullif(current_setting('reserved_connections', true), '')::int, 0),
 'superuser', current_setting('is_superuser')::boolean,
 'stats', pg_has_role(current_user, 'pg_read_all_stats', 'member'),
 'connection_limit', (SELECT rolconnlimit FROM pg_roles WHERE rolname = current_user),
 'readonly', current_setting('transaction_read_only')::boolean,
 'application_access', EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE c.relkind IN ('r','p','v','m','f') AND n.nspname !~ '^pg_'
     AND n.nspname <> 'information_schema'
     AND has_table_privilege(current_user, c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER')),
 'dangerous', (SELECT bool_or(pg_has_role(current_user, oid, 'member')) FROM pg_roles
   WHERE rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls
      OR rolname IN ('pg_monitor', 'pg_read_all_data', 'pg_write_all_data',
       'pg_signal_backend', 'pg_read_server_files', 'pg_write_server_files',
       'pg_execute_server_program', 'pg_use_reserved_connections')),
 'server', host(inet_server_addr()), 'port', inet_server_port(),
 'database', current_database(), 'observer', pg_backend_pid(),
 'unsupported', (SELECT count(*) FROM pg_stat_activity WHERE backend_type IS NULL OR backend_type NOT IN (
   'client backend', 'autovacuum launcher', 'autovacuum worker', 'background writer',
   'checkpointer', 'archiver', 'walwriter', 'logical replication launcher', 'parallel worker')),
 'clients', (SELECT coalesce(json_agg(json_build_object(
   'pid', pid, 'start', backend_start, 'address', host(client_addr),
   'port', client_port, 'state', state, 'transaction', xact_start)), '[]'::json)
   FROM pg_stat_activity WHERE backend_type = 'client backend'))
"""

# Run only in inspected application containers. Match established socket inode to
# an owning process, not application_name (which any client can forge).
# Keep these two signatures aligned with the backend and worker ``healthcheck.test``
# commands in docker-compose.yml; other inline Python remains an application process.
SOCKET_PROBE_HEALTHCHECK_COMMANDS = (
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=4)",
    "import os,time; from fitminiapp_api.core.config import settings; age=time.time()-os.path.getmtime('/tmp/fitminiapp-worker-heartbeat'); assert age < max(120, settings.worker_poll_seconds * 3 + 30)",
)

# Docker healthchecks also run ``python -c`` inside these containers. Ignore only
# the two known short-lived helpers when they own no PostgreSQL socket; an extra
# process with a DB socket remains a hard topology failure.
SOCKET_PROBE_PROCESS_RULE = (
    r"""
KNOWN_HEALTHCHECK_COMMANDS = """
    + repr(SOCKET_PROBE_HEALTHCHECK_COMMANDS)
    + r"""
def is_known_healthcheck(arguments):
    if len(arguments) < 3 or arguments[1] != b'-c':
        return False
    if any(arguments[3:]):
        return False
    try:
        return arguments[2].decode('utf-8') in KNOWN_HEALTHCHECK_COMMANDS
    except UnicodeDecodeError:
        return False

def application_process_count(processes, db_socket_inodes):
    return sum(
        not known_healthcheck or bool(process_sockets & db_socket_inodes)
        for known_healthcheck, process_sockets in processes
    )
"""
)

SOCKET_PROBE = (
    r"""
import ipaddress, json, os, pathlib
"""
    + SOCKET_PROBE_PROCESS_RULE
    + r"""
root = pathlib.Path('/proc')
owners = set()
matching_processes = []
for process in root.iterdir():
    if not process.name.isdigit() or int(process.name) == os.getpid():
        continue
    try:
        command = (process / 'comm').read_text().strip()
        process_sockets = set()
        for fd in (process / 'fd').iterdir():
            try:
                link = os.readlink(fd)
                if link.startswith('socket:['):
                    inode = link[8:-1]
                    owners.add(inode)
                    process_sockets.add(inode)
            except FileNotFoundError:
                pass
        if command.startswith(('python', 'uvicorn')):
            try:
                arguments = (process / 'cmdline').read_bytes().split(b'\0')
                known_healthcheck = command.startswith('python') and is_known_healthcheck(arguments)
            except (FileNotFoundError, PermissionError):
                known_healthcheck = False
            matching_processes.append((known_healthcheck, process_sockets))
    except FileNotFoundError:
        pass
def endpoint(value, ipv6):
    address, port = value.split(':')
    raw = bytes.fromhex(address)
    raw = b''.join(raw[i:i+4][::-1] for i in range(0, len(raw), 4))
    ip = ipaddress.ip_address(raw)
    if getattr(ip, 'ipv4_mapped', None):
        ip = ip.ipv4_mapped
    return str(ip), int(port, 16)
rows = []
db_socket_inodes = set()
for filename in ('tcp', 'tcp6'):
    for line in (root / 'net' / filename).read_text().splitlines()[1:]:
        fields = line.split()
        if fields[3] == '01' and fields[9] in owners:
            local = endpoint(fields[1], filename == 'tcp6')
            remote = endpoint(fields[2], filename == 'tcp6')
            if remote[1] == 5432:
                db_socket_inodes.add(fields[9])
            rows.append([*local, *remote])
"""
    + r"""
print(json.dumps({'processes': application_process_count(matching_processes, db_socket_inodes),
                  'sockets': rows}))
"""
)

ENGINE_PROBE = """
import json
from sqlalchemy.pool import QueuePool
from fitminiapp_api.core.config import settings
from fitminiapp_api.db.session import engine
assert settings.app_env == 'prod'
assert isinstance(engine.pool, QueuePool)
assert engine.url.get_backend_name() == 'postgresql'
assert engine.url.host == 'db' and (engine.url.port or 5432) == 5432
print(json.dumps({'size': engine.pool.size(), 'overflow': engine.pool._max_overflow}))
"""


class SafetyError(RuntimeError):
    """Sanitized fail-closed maintenance barrier failure."""


def _protected_observer_files() -> None:
    """Verify libpq files are readable by the unprivileged SSH deploy identity.

    pgpass must be owned by the effective user and mode 0600: libpq ignores
    any password file exposing group or other permissions on Unix.
    """
    try:
        account = pwd.getpwnam(DEPLOY_ACCOUNT)
    except KeyError:
        raise SafetyError("observer_deploy_identity_missing") from None
    if account.pw_uid == 0 or os.geteuid() != account.pw_uid or os.getegid() != account.pw_gid:
        raise SafetyError("observer_deploy_identity_invalid")

    try:
        for parent in OBSERVER_DIRECTORY.parents:
            info = parent.lstat()
            if info.st_uid != 0 or not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022:
                raise SafetyError("observer_parent_unprotected")

        directory = OBSERVER_DIRECTORY.lstat()
        if (
            not stat.S_ISDIR(directory.st_mode)
            or directory.st_uid != 0
            or directory.st_gid != account.pw_gid
            or stat.S_IMODE(directory.st_mode) != 0o750
        ):
            raise SafetyError("observer_directory_unprotected")

        for name, expected_uid, mode in (
            ("pg_service.conf", 0, 0o640),
            ("pgpass", account.pw_uid, 0o600),
        ):
            path = OBSERVER_DIRECTORY / name
            metadata = path.lstat()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or metadata.st_uid != expected_uid
                or metadata.st_gid != account.pw_gid
                or stat.S_IMODE(metadata.st_mode) != mode
            ):
                raise SafetyError("observer_files_unprotected")

            # An actual open with the deployment identity detects inaccessible
            # files and O_NOFOLLOW protects against a file replacement symlink.
            descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            try:
                opened = os.fstat(descriptor)
                if (
                    opened.st_dev != metadata.st_dev
                    or opened.st_ino != metadata.st_ino
                    or opened.st_uid != metadata.st_uid
                    or opened.st_gid != metadata.st_gid
                    or opened.st_mode != metadata.st_mode
                    or opened.st_nlink != metadata.st_nlink
                ):
                    raise SafetyError("observer_files_changed_during_access")
            finally:
                os.close(descriptor)
    except OSError, ValueError:
        raise SafetyError("observer_files_unreadable") from None


def validate_snapshot(snapshot: dict, *, addresses: set[str], database: str) -> list[dict]:
    if (
        snapshot["version"] != 16
        or snapshot["superuser"] is not False
        or snapshot["stats"] is not True
        or snapshot["connection_limit"] != 1
        or snapshot["readonly"] is not True
        or snapshot["application_access"] is not False
        or snapshot["dangerous"] is not False
        or snapshot["unsupported"] != 0
        or snapshot["server"] not in addresses
        or snapshot["port"] != 5432
        or snapshot["database"] != database
    ):
        raise SafetyError("observer_identity_or_visibility_invalid")
    clients = snapshot["clients"]
    identities = {(row["pid"], row["start"]) for row in clients}
    if (
        len(identities) != len(clients)
        or sum(row["pid"] == snapshot["observer"] for row in clients) != 1
    ):
        raise SafetyError("observer_clients_inconsistent")
    return [row for row in clients if row["pid"] != snapshot["observer"]]


def phase_budget(snapshot: dict, caps: dict[str, int], margin: int) -> dict[str, int]:
    """All reachable phases; forbidden overlaps are separately denied by inventory."""
    if (
        type(margin) is not int
        or margin <= 0
        or any(type(value) is not int or value <= 0 for value in caps.values())
    ):
        raise SafetyError("capacity_policy_unknown")
    backend, worker, setup = (caps[key] for key in ("backend", "worker", "setup"))
    phases = {
        "steady": backend + worker,
        "backup": backend + worker + 1,
        "drained": 0,
        "migration": 1,
        "setup_readiness": setup,
        "setup_seed": setup,
        "backend_start": backend,
        "worker_readiness": backend + max(15, worker),
        "worker_start": backend + worker,
        "bot_start": backend + worker,
        "rollback_stop": backend + worker,
        "rollback_backend": backend,
        "rollback_worker": backend + max(15, worker),
        "rollback_bot": backend + worker,
    }
    usable = snapshot["maximum"] - snapshot["reserved"]
    if (
        type(usable) is not int
        or usable <= 0
        or snapshot["reserved"] < 0
        or max(phases.values()) + 1 + margin > usable
        or len(snapshot["clients"]) + margin > usable
    ):
        raise SafetyError("insufficient_connection_budget")
    return {name: demand + 1 + margin for name, demand in phases.items()}


class SequentialSafety:
    def __init__(self, root: Path, margin: int):
        self.root = root
        self.margin = margin
        self.caps: dict[str, int] = {}
        self.project = ""
        self.last_report: dict[str, int] = {}

    def run(self, *args: str) -> bytes:
        try:
            return _run_bounded(args, cwd=self.root, policy=CollectorPolicy())
        except Exception:
            raise SafetyError("maintenance_observation_unavailable") from None

    def json(self, *args: str):
        try:
            return json.loads(self.run(*args))
        except ValueError, TypeError:
            raise SafetyError("maintenance_observation_invalid") from None

    def inventory(self) -> list[dict]:
        ids = self.run("docker", "ps", "-aq").decode().split()
        if not ids:
            raise SafetyError("runtime_inventory_empty")
        # Never inspect Config.Env wholesale into logs/artifacts.
        return [
            self.json(
                "docker",
                "inspect",
                "--format",
                '{"id":{{json .Id}},"state":{{json .State}},'
                '"labels":{{json .Config.Labels}},"restart":{{json .HostConfig.RestartPolicy.Name}},'
                '"networks":{{json .NetworkSettings.Networks}}}',
                item,
            )
            for item in ids
        ]

    def observe(self, inventory: list[dict]) -> tuple[dict, list[dict], set[str]]:
        _protected_observer_files()
        dbs = [
            item
            for item in inventory
            if item["state"]["Running"]
            and item["labels"].get("com.docker.compose.service") == "db"
            and item["labels"].get("com.docker.compose.project") == self.project
        ]
        if len(dbs) != 1:
            raise SafetyError("database_inventory_ambiguous")
        db = dbs[0]
        addresses = {net["IPAddress"] for net in db["networks"].values() if net["IPAddress"]}
        database = self.run("docker", "exec", db["id"], "printenv", "POSTGRES_DB").decode().strip()
        snapshot = self.json(
            "/usr/bin/env",
            "-i",
            "PATH=/usr/bin:/bin",
            f"PGSERVICEFILE={OBSERVER_DIRECTORY}/pg_service.conf",
            f"PGPASSFILE={OBSERVER_DIRECTORY}/pgpass",
            "PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000",
            "/usr/bin/psql",
            "-X",
            "-w",
            "-A",
            "-t",
            "-v",
            "ON_ERROR_STOP=1",
            "--dbname=service=yfc_observer connect_timeout=5 application_name=yfc-maintenance-observer options='-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000'",
            "-c",
            OBSERVER_SQL,
        )
        clients = validate_snapshot(snapshot, addresses=addresses, database=database)
        return snapshot, clients, addresses

    def configure(self, images: tuple[str, ...]) -> None:
        rendered = self.json(
            "docker", "compose", "--profile", "production-slots", "config", "--format", "json"
        )
        self.project = rendered["name"]
        # Probe each immutable old/new image with its real .env, with no network.
        caps = []
        for image in images:
            result = self.json(
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--env-file",
                ".env",
                "--entrypoint",
                "python",
                image,
                "-c",
                ENGINE_PROBE,
            )
            if any(type(result[key]) is not int or result[key] < 0 for key in ("size", "overflow")):
                raise SafetyError("pool_ceiling_unknown")
            caps.append(result["size"] + result["overflow"])
        ceiling = max(caps)
        # Rendered per-service overrides must match the image/.env probe.
        for name, service in rendered["services"].items():
            if name in DB_CONSUMERS:
                env = service.get("environment", {})
                if (
                    any(key in env for key in ("DB_POOL_SIZE", "DB_MAX_OVERFLOW"))
                    and int(env["DB_POOL_SIZE"]) + int(env["DB_MAX_OVERFLOW"]) != ceiling
                ):
                    raise SafetyError("rendered_pool_override_unverified")
        self.caps = {"backend": ceiling, "worker": ceiling, "setup": max(15, ceiling)}

    def disarm(self) -> None:
        for item in self.inventory():
            if (
                item["labels"].get("com.docker.compose.project") == self.project
                and item["labels"].get("com.docker.compose.service") in CONSUMERS
            ):
                self.run("docker", "update", "--restart=no", item["id"])

    def check(self, expected: frozenset[str], *, disarmed: bool = True) -> None:
        try:
            # A connection can disappear between the PostgreSQL snapshot and
            # the /proc socket probe. Retry only this attribution race, with
            # two complete, consecutive clean checks before proceeding.
            clean_checks = 0
            for attempt in range(5):
                try:
                    self._check(expected, disarmed=disarmed)
                except SafetyError as error:
                    if str(error) != "unknown_or_unreleased_database_client" or attempt == 4:
                        raise
                    clean_checks = 0
                else:
                    clean_checks += 1
                    if attempt == 0 or clean_checks == 2:
                        return
                time.sleep(0.15)
            raise SafetyError("unknown_or_unreleased_database_client")
        except SafetyError:
            raise
        except Exception:
            raise SafetyError("maintenance_evidence_invalid") from None

    def _check(self, expected: frozenset[str], *, disarmed: bool) -> None:
        before = self.inventory()
        active = {}
        for item in before:
            labels = item["labels"] or {}
            if item["state"]["Running"]:
                has_db = (
                    self.run(
                        "docker",
                        "inspect",
                        "--format",
                        '{{range .Config.Env}}{{if eq (index (split . "=") 0) "DATABASE_URL"}}true{{end}}{{end}}',
                        item["id"],
                    ).strip()
                    == b"true"
                )
                if has_db and (
                    labels.get("com.docker.compose.project") != self.project
                    or labels.get("com.docker.compose.service") not in DB_CONSUMERS
                ):
                    raise SafetyError("unknown_configured_database_consumer")
            if labels.get("com.docker.compose.project") != self.project:
                continue
            name = labels.get("com.docker.compose.service")
            if name not in CONSUMERS:
                continue
            if disarmed and item["restart"] != "no":
                raise SafetyError("consumer_restart_not_fenced")
            if (
                not expected
                and name in {"backend", "worker", "bot"}
                and not item["state"]["Running"]
                and item["state"]["ExitCode"] != 0
            ):
                raise SafetyError("consumer_drain_unproven")
            if item["state"]["Running"]:
                if name in active or name not in expected or item["state"].get("Paused"):
                    raise SafetyError("unexpected_active_consumer")
                active[name] = item
        if set(active) != set(expected):
            raise SafetyError("consumer_missing_or_interrupted")
        snapshot, clients, addresses = self.observe(before)
        sockets = {}
        for name in expected & DB_CONSUMERS:
            engine = self.json("docker", "exec", active[name]["id"], "python", "-c", ENGINE_PROBE)
            if (
                type(engine["size"]) is not int
                or type(engine["overflow"]) is not int
                or engine["size"] < 0
                or engine["overflow"] < 0
                or engine["size"] + engine["overflow"] > self.caps[name]
            ):
                raise SafetyError("running_pool_ceiling_unverified")
            probe = self.json("docker", "exec", active[name]["id"], "python", "-c", SOCKET_PROBE)
            if probe["processes"] != 1:
                raise SafetyError("consumer_process_topology_unknown")
            for address, port, remote, remote_port in probe["sockets"]:
                if remote in addresses and remote_port == 5432:
                    key = (str(ipaddress.ip_address(address)), port)
                    if key in sockets:
                        raise SafetyError("socket_owner_ambiguous")
                    sockets[key] = name
        if any((row["address"], row["port"]) not in sockets for row in clients):
            raise SafetyError("unknown_or_unreleased_database_client")
        if len(clients) > sum(self.caps[name] for name in expected & {"backend", "worker"}):
            raise SafetyError("observed_clients_exceed_pool_ceiling")
        self.last_report = phase_budget(snapshot, self.caps, self.margin)
        _, second_clients, _ = self.observe(before)

        def client_identity(rows):
            return {(row["pid"], row["start"], row["address"], row["port"]) for row in rows}

        if client_identity(clients) != client_identity(second_clients):
            raise SafetyError("database_clients_changed_during_observation")
        after = self.inventory()

        def identity(items):
            return {
                (item["id"], item["state"]["Running"], item["state"]["StartedAt"], item["restart"])
                for item in items
            }

        if identity(before) != identity(after):
            raise SafetyError("runtime_changed_during_observation")

    def released(self) -> None:
        # Two independent observations; no accepted cached/pre-stop snapshot.
        self.check(frozenset())
        time.sleep(0.1)
        self.check(frozenset())
