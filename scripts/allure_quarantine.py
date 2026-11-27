"""Bind a human Allure attachment review to immutable encrypted CI inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

if __package__:
    from scripts.scheduled_regression import (
        CROSS_BROWSER_PROJECTS,
        CROSS_BROWSER_SHARD_COUNT,
        FRONTEND_E2E_SHARD_COUNT,
        PYTHON_TEST_SHARD_COUNT,
    )
else:
    from scheduled_regression import (
        CROSS_BROWSER_PROJECTS,
        CROSS_BROWSER_SHARD_COUNT,
        FRONTEND_E2E_SHARD_COUNT,
        PYTHON_TEST_SHARD_COUNT,
    )

ENVIRONMENT = "allure-review"


class QuarantineError(ValueError):
    """Review evidence is missing, inconsistent, or not trusted."""


def expected_bundles(kind: str) -> set[str]:
    if kind not in {"daily", "weekly"}:
        raise QuarantineError("unsupported run kind")
    names = {
        "frontend-checks.enc",
        "frontend-mobile-regression.enc",
        "migrated-stack.enc",
        *(f"frontend-e2e-shard-{n}.enc" for n in range(1, FRONTEND_E2E_SHARD_COUNT + 1)),
        *(f"python-tests-shard-{n}.enc" for n in range(1, PYTHON_TEST_SHARD_COUNT + 1)),
    }
    if kind == "weekly":
        names.add("frontend-mobile-regression-extended.enc")
        names.update(
            f"frontend-cross-browser-{browser}-shard-{shard}.enc"
            for browser in CROSS_BROWSER_PROJECTS
            for shard in range(1, CROSS_BROWSER_SHARD_COUNT + 1)
        )
    return names


def digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise QuarantineError("bundle is missing or is a symlink")
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def make_manifest(root: Path, *, kind: str, run_id: str, attempt: str, sha: str) -> bytes:
    if not re.fullmatch(r"[1-9][0-9]*", run_id) or not re.fullmatch(r"[1-9][0-9]*", attempt):
        raise QuarantineError("invalid run identity")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise QuarantineError("invalid commit SHA")
    expected = expected_bundles(kind)
    actual = {p.name for p in root.glob("*.enc")}
    if actual != expected:
        raise QuarantineError("encrypted bundle set is incomplete or unexpected")
    payload = {
        "schema": 1,
        "kind": kind,
        "run_id": run_id,
        "attempt": attempt,
        "sha": sha,
        "bundles": {name: digest(root / name) for name in sorted(expected)},
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def verify_environment(environment: object, owner: str) -> int:
    if not isinstance(environment, dict) or environment.get("name") != ENVIRONMENT:
        raise QuarantineError("review environment is missing")
    if environment.get("can_admins_bypass") is not False:
        raise QuarantineError("review environment must disallow administrator bypass")
    rules = environment.get("protection_rules")
    if not isinstance(rules, list):
        raise QuarantineError("review protection rules are missing")
    reviewers = [r for r in rules if isinstance(r, dict) and r.get("type") == "required_reviewers"]
    if len(reviewers) != 1 or not any(
        isinstance(r, dict)
        and r.get("type") == "User"
        and isinstance(r.get("reviewer"), dict)
        and r["reviewer"].get("login") == owner
        for r in reviewers[0].get("reviewers", [])
    ):
        raise QuarantineError("repository owner is not a required reviewer")
    policy = environment.get("deployment_branch_policy")
    if (
        not isinstance(policy, dict)
        or policy.get("custom_branch_policies") is not True
        or policy.get("protected_branches") is not False
    ):
        raise QuarantineError("review environment must use explicit branch policies")
    env_id = environment.get("id")
    if isinstance(env_id, bool) or not isinstance(env_id, int) or env_id <= 0:
        raise QuarantineError("review environment identity is invalid")
    return env_id


def verify_branch_policies(policies: object) -> None:
    if (
        not isinstance(policies, dict)
        or type(policies.get("total_count")) is not int
        or policies["total_count"] != 1
    ):
        raise QuarantineError("review environment must allow only the master branch")
    branches = policies.get("branch_policies")
    if (
        not isinstance(branches, list)
        or len(branches) != 1
        or not isinstance(branches[0], dict)
        or branches[0].get("name") != "master"
        or branches[0].get("type") != "branch"
    ):
        raise QuarantineError("review environment must allow only the master branch")


def verify_approval(
    reviews: object, *, env_id: int, owner: str, run_id: str, attempt: str, manifest_digest: str
) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", manifest_digest):
        raise QuarantineError("invalid manifest digest")
    if not isinstance(reviews, list):
        raise QuarantineError("review history is unavailable")
    comment = f"allure-review:{run_id}:{attempt}:{manifest_digest}"
    matches = [
        r
        for r in reviews
        if isinstance(r, dict)
        and any(isinstance(e, dict) and e.get("id") == env_id for e in r.get("environments", []))
    ]
    if not matches:
        raise QuarantineError("review approval is missing")
    review = matches[-1]
    if (
        review.get("state") != "approved"
        or review.get("comment") != comment
        or not isinstance(review.get("user"), dict)
        or review["user"].get("login") != owner
    ):
        raise QuarantineError("review does not approve this run, attempt and manifest")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("manifest", "verify", "environment", "approval"))
    parser.add_argument("--root", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--kind")
    parser.add_argument("--run-id")
    parser.add_argument("--attempt")
    parser.add_argument("--sha")
    parser.add_argument("--digest")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--branch-policies", type=Path)
    parser.add_argument("--owner")
    parser.add_argument("--environment-id", type=int)
    args = parser.parse_args()
    try:
        if args.mode in {"manifest", "verify"}:
            data = make_manifest(
                args.root, kind=args.kind, run_id=args.run_id, attempt=args.attempt, sha=args.sha
            )
            value = hashlib.sha256(data).hexdigest()
            if args.mode == "manifest":
                args.manifest.write_bytes(data)
                print(value)
            elif args.manifest.read_bytes() != data or value != args.digest:
                raise QuarantineError("quarantine manifest or bundle changed")
        elif args.mode == "environment":
            if args.branch_policies is None:
                raise QuarantineError("review branch policies are missing")
            verify_branch_policies(json.loads(args.branch_policies.read_text(encoding="utf-8")))
            print(verify_environment(json.loads(args.json.read_text(encoding="utf-8")), args.owner))
        else:
            verify_approval(
                json.loads(args.json.read_text(encoding="utf-8")),
                env_id=args.environment_id,
                owner=args.owner,
                run_id=args.run_id,
                attempt=args.attempt,
                manifest_digest=args.digest,
            )
    except (QuarantineError, OSError, ValueError, TypeError) as error:
        print(f"allure quarantine: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
