"""Fail closed when a release contains migrations unsafe for an online slot switch."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from pathlib import Path

MIGRATION_ROOT = Path("backend/alembic/versions")
ALLOWED_PHASES = {"expand", "backfill", "constraint_swap"}
DESTRUCTIVE_CALLS = {
    "alter_column",
    "drop_column",
    "drop_constraint",
    "drop_index",
    "drop_table",
    "rename_table",
}
FORBIDDEN_ONLINE_CALLS = {
    "create_check_constraint",
    "create_exclude_constraint",
    "create_foreign_key",
    "create_primary_key",
    "create_unique_constraint",
}
SAFE_TABLE_CONSTRUCTORS = {
    "CheckConstraint",
    "Column",
    "ForeignKey",
    "PrimaryKeyConstraint",
    "UniqueConstraint",
}
SAFE_COLUMN_TYPES = {
    "BigInteger",
    "Boolean",
    "Date",
    "DateTime",
    "Float",
    "Integer",
    "JSON",
    "LargeBinary",
    "Numeric",
    "SmallInteger",
    "String",
    "Text",
    "Time",
}


class OnlineMigrationError(RuntimeError):
    """The release cannot coexist with the currently active revision."""


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def changed_migrations(active_revision: str, target_revision: str) -> list[tuple[str, Path]]:
    try:
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", active_revision, target_revision],
            check=False,
        )
    except OSError as exc:
        raise OnlineMigrationError(f"cannot execute Git: {exc}") from exc
    if ancestor.returncode != 0:
        raise OnlineMigrationError(
            f"active revision {active_revision} is not an ancestor of {target_revision}"
        )

    rows = _git(
        "diff",
        "--name-status",
        active_revision,
        target_revision,
        "--",
        MIGRATION_ROOT.as_posix(),
    ).splitlines()
    changes: list[tuple[str, Path]] = []
    for row in rows:
        fields = row.split("\t")
        status = fields[0]
        path = Path(fields[-1])
        if path.suffix == ".py" and path.name != "__init__.py":
            changes.append((status, path))
    return changes


def changed_migrations_from_manifest(
    active_revision: str, target_revision: str, manifest: Path
) -> list[tuple[str, Path]]:
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OnlineMigrationError(
            f"cannot read immutable migration manifest {manifest}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise OnlineMigrationError("immutable migration manifest must be an object")
    if payload.get("schema_version") != 1:
        raise OnlineMigrationError("unsupported immutable migration manifest version")
    if (
        payload.get("active_revision") != active_revision
        or payload.get("target_revision") != target_revision
    ):
        raise OnlineMigrationError(
            "immutable migration manifest revision range does not match deployment"
        )
    changes: list[tuple[str, Path]] = []
    raw_changes = payload.get("changes")
    if not isinstance(raw_changes, list):
        raise OnlineMigrationError("immutable migration manifest changes must be a list")
    for item in raw_changes:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("status"), str)
            or not isinstance(item.get("path"), str)
        ):
            raise OnlineMigrationError("immutable migration manifest contains an invalid change")
        path = Path(item["path"])
        if (
            path.is_absolute()
            or ".." in path.parts
            or path.parts[: len(MIGRATION_ROOT.parts)] != MIGRATION_ROOT.parts
        ):
            raise OnlineMigrationError(
                f"immutable migration manifest path is outside {MIGRATION_ROOT}: {path}"
            )
        if path.suffix == ".py" and path.name != "__init__.py":
            changes.append((item["status"], path))
    return changes


def _assignment(tree: ast.Module, name: str) -> object | None:
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == name for target in targets):
            continue
        value = node.value
        if value is None:
            return None
        try:
            return ast.literal_eval(value)
        except ValueError:
            return None
        except TypeError:
            return None
    return None


def _upgrade_body(tree: ast.Module, path: Path) -> ast.FunctionDef | ast.AsyncFunctionDef:
    upgrades = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "upgrade"
    ]
    if len(upgrades) != 1:
        raise OnlineMigrationError(f"{path} must define exactly one upgrade() function")
    return upgrades[0]


def _op_calls(upgrade: ast.AST) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(upgrade)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "op"
    ]


def _parent_links(root: ast.AST) -> dict[ast.AST, tuple[ast.AST, str]]:
    links: dict[ast.AST, tuple[ast.AST, str]] = {}
    for parent in ast.walk(root):
        for field_name, value in ast.iter_fields(parent):
            if isinstance(value, ast.AST):
                links[value] = (parent, field_name)
            elif isinstance(value, list):
                for child in value:
                    if isinstance(child, ast.AST):
                        links[child] = (parent, field_name)
    return links


def _is_direct_op_call(call: ast.Call, attribute: str) -> bool:
    return (
        isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "op"
        and call.func.attr == attribute
    )


def _has_true_keyword(call: ast.Call, name: str) -> bool:
    return any(
        keyword.arg == name
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is True
        for keyword in call.keywords
    )


def _is_autocommit_block_call(call: ast.Call) -> bool:
    return (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "autocommit_block"
        and isinstance(call.func.value, ast.Call)
        and _is_direct_op_call(call.func.value, "get_context")
    )


def _is_postgresql_dialect_name(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "name"
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "dialect"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "bind"
    )


def _is_postgresql_dialect_check(node: ast.AST) -> bool:
    if (
        not isinstance(node, ast.Compare)
        or len(node.ops) != 1
        or not isinstance(node.ops[0], ast.Eq)
    ):
        return False
    if len(node.comparators) != 1:
        return False
    left, right = node.left, node.comparators[0]
    return (
        _is_postgresql_dialect_name(left)
        and isinstance(right, ast.Constant)
        and right.value == "postgresql"
    ) or (
        _is_postgresql_dialect_name(right)
        and isinstance(left, ast.Constant)
        and left.value == "postgresql"
    )


def _is_within_autocommit_block(call: ast.Call, links: dict[ast.AST, tuple[ast.AST, str]]) -> bool:
    current: ast.AST = call
    while current in links:
        parent, _field_name = links[current]
        if isinstance(parent, ast.With) and any(
            _is_autocommit_block_call(item.context_expr) for item in parent.items
        ):
            return True
        current = parent
    return False


def _is_in_non_postgresql_branch(call: ast.Call, links: dict[ast.AST, tuple[ast.AST, str]]) -> bool:
    current: ast.AST = call
    while current in links:
        parent, field_name = links[current]
        if (
            isinstance(parent, ast.If)
            and field_name == "orelse"
            and _is_postgresql_dialect_check(parent.test)
        ):
            return True
        current = parent
    return False


def _is_in_postgresql_branch(call: ast.Call, links: dict[ast.AST, tuple[ast.AST, str]]) -> bool:
    current: ast.AST = call
    while current in links:
        parent, field_name = links[current]
        if (
            isinstance(parent, ast.If)
            and field_name == "body"
            and _is_postgresql_dialect_check(parent.test)
        ):
            return True
        current = parent
    return False


def _validate_upgrade_call_allowlist(path: Path, upgrade: ast.AST, phase: object) -> None:
    links = _parent_links(upgrade)
    created_tables = {
        call.args[0].value
        for call in _op_calls(upgrade)
        if call.func.attr == "create_table"
        and call.args
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
    }
    for call in (node for node in ast.walk(upgrade) if isinstance(node, ast.Call)):
        function = call.func
        allowed = False
        if isinstance(function, ast.Attribute) and isinstance(function.value, ast.Name):
            owner = function.value.id
            if phase == "expand":
                allowed = (
                    owner == "op"
                    and function.attr
                    in {"add_column", "create_table", "create_index", "get_bind", "get_context"}
                ) or (
                    owner == "sa"
                    and (
                        function.attr in SAFE_TABLE_CONSTRUCTORS
                        or function.attr in SAFE_COLUMN_TYPES
                        or function.attr == "text"
                    )
                )
            elif phase == "backfill":
                allowed = owner == "op" and function.attr == "execute"
            elif phase == "constraint_swap":
                allowed = owner == "op" and function.attr in {"execute", "get_bind"}
        if _is_autocommit_block_call(call):
            allowed = True
        if not allowed:
            raise OnlineMigrationError(
                f"{path} calls a helper or operation outside the {phase!r} online allowlist"
            )
        if (
            phase == "expand"
            and isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id == "op"
            and function.attr == "create_index"
        ):
            table_name = (
                call.args[1].value
                if len(call.args) > 1 and isinstance(call.args[1], ast.Constant)
                else None
            )
            if table_name not in created_tables and not (
                _has_true_keyword(call, "postgresql_concurrently")
                and _has_true_keyword(call, "if_not_exists")
                and (
                    _is_within_autocommit_block(call, links)
                    or _is_in_non_postgresql_branch(call, links)
                )
            ):
                raise OnlineMigrationError(
                    f"{path} contains lock-prone operations: create_index is allowed only for "
                    "a new empty table in the same migration or a PostgreSQL-concurrent "
                    "index in an autocommit block"
                )


def _validate_constraint_swap_sql(
    path: Path,
    statements: list[str],
    *,
    table_name: str,
    constraint_name: str,
    lock_timeout_seconds: int,
    statement_timeout_seconds: int,
) -> None:
    expected_lock = f"SET LOCAL lock_timeout = '{lock_timeout_seconds}s'"
    expected_statement = f"SET LOCAL statement_timeout = '{statement_timeout_seconds}s'"
    expected_validate = f"ALTER TABLE {table_name} VALIDATE CONSTRAINT {constraint_name}"
    if len(statements) != 4:
        raise OnlineMigrationError(
            f"{path} constraint_swap must contain exactly four static op.execute statements"
        )
    if statements[0].strip() != expected_lock:
        raise OnlineMigrationError(
            f"{path} constraint_swap must set the declared LOCAL lock_timeout first"
        )
    if statements[1].strip() != expected_statement:
        raise OnlineMigrationError(
            f"{path} constraint_swap must set the declared LOCAL statement_timeout second"
        )

    swap = re.sub(r"\s+", " ", statements[2]).strip()
    prefix = (
        f"ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS {constraint_name}, "
        f"ADD CONSTRAINT {constraint_name} CHECK ("
    )
    if (
        not swap.startswith(prefix)
        or not swap.endswith(") NOT VALID")
        or ";" in swap
        or re.search(r"\b(REFERENCES|UNIQUE|PRIMARY KEY|FOREIGN KEY)\b", swap, re.IGNORECASE)
    ):
        raise OnlineMigrationError(
            f"{path} constraint_swap must replace only the declared CHECK constraint using NOT VALID"
        )
    if statements[3].strip() != expected_validate:
        raise OnlineMigrationError(
            f"{path} constraint_swap must validate the declared constraint after replacement"
        )


def _validate_nullable_add_column(path: Path, call: ast.Call) -> None:
    if len(call.args) < 2 or not isinstance(call.args[1], ast.Call):
        raise OnlineMigrationError(
            f"{path} add_column must contain a statically verifiable nullable Column"
        )
    column = call.args[1]
    if not isinstance(column.func, ast.Attribute) or column.func.attr != "Column":
        raise OnlineMigrationError(
            f"{path} add_column must contain a statically verifiable nullable Column"
        )
    if len(column.args) != 2:
        raise OnlineMigrationError(
            f"{path} add_column cannot contain positional constraints or generated values"
        )
    column_type = column.args[1]
    if (
        not isinstance(column_type, ast.Call)
        or not isinstance(column_type.func, ast.Attribute)
        or not isinstance(column_type.func.value, ast.Name)
        or column_type.func.value.id != "sa"
        or column_type.func.attr not in SAFE_COLUMN_TYPES
        or any(not isinstance(argument, ast.Constant) for argument in column_type.args)
        or any(
            keyword.arg is None or not isinstance(keyword.value, ast.Constant)
            for keyword in column_type.keywords
        )
    ):
        raise OnlineMigrationError(
            f"{path} add_column must use an allowlisted static SQLAlchemy scalar type"
        )
    keywords = {keyword.arg: keyword.value for keyword in column.keywords if keyword.arg}
    nullable = keywords.get("nullable")
    if not isinstance(nullable, ast.Constant) or nullable.value is not True:
        raise OnlineMigrationError(
            f"{path} add_column must explicitly use nullable=True during expand"
        )
    for unsafe_keyword in ("server_default", "unique", "index"):
        value = keywords.get(unsafe_keyword)
        if unsafe_keyword == "server_default":
            safe = value is None or _is_constant_false_server_default(value)
        else:
            safe = value is None or (
                isinstance(value, ast.Constant) and value.value in {None, False}
            )
        if not safe:
            raise OnlineMigrationError(
                f"{path} add_column cannot use {unsafe_keyword} during an online expand"
            )


def _is_constant_false_server_default(value: ast.AST | None) -> bool:
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and isinstance(value.func.value, ast.Name)
        and value.func.value.id == "sa"
        and value.func.attr == "text"
        and len(value.args) == 1
        and not value.keywords
        and isinstance(value.args[0], ast.Constant)
        and isinstance(value.args[0].value, str)
        and value.args[0].value.strip().upper() == "FALSE"
    )


def validate_added_migration(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    upgrade = _upgrade_body(tree, path)
    phase = _assignment(tree, "online_rollout_phase")
    if phase not in ALLOWED_PHASES:
        raise OnlineMigrationError(
            f"{path} must declare online_rollout_phase as one of {sorted(ALLOWED_PHASES)}"
        )

    notes = _assignment(tree, "online_rollout_notes")
    if not isinstance(notes, str) or not notes.strip():
        raise OnlineMigrationError(
            f"{path} must declare non-empty online_rollout_notes with lock/data bounds"
        )

    if phase == "backfill":
        batch_size = _assignment(tree, "online_rollout_batch_size")
        idempotent = _assignment(tree, "online_rollout_idempotent")
        if (
            not isinstance(batch_size, int)
            or isinstance(batch_size, bool)
            or not 1 <= batch_size <= 10_000
        ):
            raise OnlineMigrationError(
                f"{path} backfill must declare online_rollout_batch_size between 1 and 10000"
            )
        if idempotent is not True:
            raise OnlineMigrationError(
                f"{path} backfill must declare online_rollout_idempotent = True"
            )

    constraint_swap_config: tuple[str, str, int, int] | None = None
    if phase == "constraint_swap":
        table_name = _assignment(tree, "online_rollout_constraint_table")
        constraint_name = _assignment(tree, "online_rollout_constraint_name")
        lock_timeout_seconds = _assignment(tree, "online_rollout_lock_timeout_seconds")
        statement_timeout_seconds = _assignment(tree, "online_rollout_statement_timeout_seconds")
        if not isinstance(table_name, str) or not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*", table_name
        ):
            raise OnlineMigrationError(
                f"{path} constraint_swap must declare a static table identifier"
            )
        if not isinstance(constraint_name, str) or not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*", constraint_name
        ):
            raise OnlineMigrationError(
                f"{path} constraint_swap must declare a static constraint identifier"
            )
        if (
            not isinstance(lock_timeout_seconds, int)
            or isinstance(lock_timeout_seconds, bool)
            or not 1 <= lock_timeout_seconds <= 5
        ):
            raise OnlineMigrationError(
                f"{path} constraint_swap lock timeout must be between 1 and 5 seconds"
            )
        if (
            not isinstance(statement_timeout_seconds, int)
            or isinstance(statement_timeout_seconds, bool)
            or not 1 <= statement_timeout_seconds <= 60
        ):
            raise OnlineMigrationError(
                f"{path} constraint_swap statement timeout must be between 1 and 60 seconds"
            )
        constraint_swap_config = (
            table_name,
            constraint_name,
            lock_timeout_seconds,
            statement_timeout_seconds,
        )

    destructive = sorted(
        {
            node.func.attr
            for node in _op_calls(upgrade)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in DESTRUCTIVE_CALLS
        }
    )
    if destructive:
        raise OnlineMigrationError(
            f"{path} contains destructive operations forbidden during an online rollout: "
            + ", ".join(destructive)
        )

    links = _parent_links(upgrade)
    for node in ast.walk(upgrade):
        if (
            not isinstance(node, ast.Call)
            or not isinstance(node.func, ast.Attribute)
            or node.func.attr not in {"execute", "exec_driver_sql"}
        ):
            continue
        if not (
            node.func.attr == "execute"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "op"
        ):
            raise OnlineMigrationError(
                f"{path} uses SQL execution outside the verified op.execute online contract"
            )
        if phase == "constraint_swap" and not _is_in_postgresql_branch(node, links):
            raise OnlineMigrationError(
                f"{path} constraint_swap SQL must be gated to the PostgreSQL branch"
            )

    forbidden = sorted(
        {
            node.func.attr
            for node in _op_calls(upgrade)
            if isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_ONLINE_CALLS
        }
    )
    if forbidden:
        raise OnlineMigrationError(
            f"{path} contains lock-prone operations forbidden during an online rollout: "
            + ", ".join(forbidden)
        )

    for call in _op_calls(upgrade):
        operation = call.func.attr if isinstance(call.func, ast.Attribute) else ""
        if phase == "expand" and operation == "add_column":
            _validate_nullable_add_column(path, call)
        elif phase == "expand" and operation not in {
            "add_column",
            "create_table",
            "create_index",
            "get_bind",
            "get_context",
        }:
            raise OnlineMigrationError(
                f"{path} uses op.{operation}, which is not allowlisted for online expand"
            )
        elif phase == "backfill" and operation != "execute":
            raise OnlineMigrationError(
                f"{path} uses op.{operation}, which is not allowlisted for online backfill"
            )
        elif phase == "constraint_swap" and operation not in {"execute", "get_bind"}:
            raise OnlineMigrationError(
                f"{path} uses op.{operation}, which is not allowlisted for online constraint_swap"
            )

    execute_statements: list[str] = []
    for node in _op_calls(upgrade):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
        ):
            if (
                not node.args
                or not isinstance(node.args[0], ast.Constant)
                or not isinstance(node.args[0].value, str)
            ):
                raise OnlineMigrationError(
                    f"{path} uses dynamic op.execute; online safety cannot be verified"
                )
            raw_sql = node.args[0].value
            if phase == "constraint_swap":
                execute_statements.append(raw_sql)
                continue
            sql = re.sub(r"\s+", " ", raw_sql).strip().upper()
            if re.search(r"\b(DROP|ALTER|TRUNCATE|DELETE)\b", sql):
                raise OnlineMigrationError(
                    f"{path} contains destructive SQL forbidden during an online rollout"
                )
            if phase != "backfill":
                raise OnlineMigrationError(
                    f"{path} uses op.execute but online_rollout_phase is not 'backfill'"
                )
            if not sql.startswith("UPDATE ") or " WHERE " not in sql or ";" in sql:
                raise OnlineMigrationError(
                    f"{path} backfill SQL must be one bounded UPDATE with an explicit WHERE"
                )

    if phase == "constraint_swap":
        assert constraint_swap_config is not None
        _validate_constraint_swap_sql(
            path,
            execute_statements,
            table_name=constraint_swap_config[0],
            constraint_name=constraint_swap_config[1],
            lock_timeout_seconds=constraint_swap_config[2],
            statement_timeout_seconds=constraint_swap_config[3],
        )

    if phase == "backfill" and not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute"
        for node in _op_calls(upgrade)
    ):
        raise OnlineMigrationError(
            f"{path} declares backfill without an explicit bounded op.execute"
        )

    _validate_upgrade_call_allowlist(path, upgrade, phase)


def check_online_migrations(
    active_revision: str, target_revision: str, *, manifest: Path | None = None
) -> list[Path]:
    changes = (
        changed_migrations_from_manifest(active_revision, target_revision, manifest)
        if manifest is not None
        else changed_migrations(active_revision, target_revision)
    )
    unsafe_history = [(status, path) for status, path in changes if status != "A"]
    if unsafe_history:
        details = ", ".join(f"{status}:{path}" for status, path in unsafe_history)
        raise OnlineMigrationError(
            "applied migration history is immutable during an online rollout: " + details
        )
    added = [path for _status, path in changes]
    for path in added:
        validate_added_migration(path)
    return added


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("active_revision", nargs="?")
    parser.add_argument("target_revision", nargs="?")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if not args.active_revision or not args.target_revision:
            raise OnlineMigrationError("active and target revisions are required")
        if args.write_manifest:
            if args.manifest is not None or args.output is None:
                raise OnlineMigrationError("--write-manifest requires only --output")
            changes = changed_migrations(args.active_revision, args.target_revision)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "active_revision": args.active_revision,
                        "target_revision": args.target_revision,
                        "changes": [
                            {"status": status, "path": path.as_posix()} for status, path in changes
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            print(f"Migration manifest written: {args.output}")
            return 0
        if args.output is not None:
            raise OnlineMigrationError("--output is valid only with --write-manifest")
        migrations = check_online_migrations(
            args.active_revision, args.target_revision, manifest=args.manifest
        )
    except (OSError, SyntaxError, subprocess.CalledProcessError, OnlineMigrationError) as exc:
        print(f"Online migration gate failed: {exc}")
        return 1
    print(f"Online migration gate passed: {len(migrations)} added migration(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
