"""Reproducible local build and verification commands for Task 129."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

UPSTREAM_VERSION = "0.21.0"
UPSTREAM_TAG = "v2026.8.31"
UPSTREAM_COMMIT = "29112bef099274229cadff79cdff7bf7b99c4b77"
UPSTREAM_REPOSITORY = "https://github.com/NousResearch/hermes-agent.git"
BASE_IMAGE = "python:3.13-alpine"
BASE_DIGEST = "sha256:f3ebba2ace255c93267a0278da88c7f1044432991abc4e6ad20d22e34dd0f8ee"
TRIVY_IMAGE = (
    "aquasec/trivy:0.74.0@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969"
)
DOCKERFILE_SYNTAX_DIGEST = "sha256:ecfaec9ed6d810b56388c508f4121597bfbba70d41a6dfeee4d8cad5f295fc32"
LOCK_LINE = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[^\s;#]+)$")
LOCK_HASH = re.compile(r"^--hash=sha256:[0-9a-f]{64}$")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def worker_root() -> Path:
    return repo_root() / "deploy" / "hermes-editorial-worker"


def evidence_root() -> Path:
    return repo_root() / ".artifacts" / "tasks" / "129" / "evidence" / "hermes-worker-integration"


def image_ref() -> str:
    return os.environ.get("HERMES_WORKER_IMAGE", "task129-hermes-editorial-worker:repo-local")


def run(
    command: list[str], *, check: bool = True, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, check=False, text=True, capture_output=capture)
    if check and result.returncode != 0:
        if capture and result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        raise SystemExit(result.returncode)
    return result


def discovery_verification(command: str) -> None:
    """Run the companion discovery verification without importing its runtime."""
    result = subprocess.run(
        [sys.executable, str(repo_root() / "scripts" / "hermes_discovery.py"), command],
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def write_json(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def normalise(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).casefold()


def lock_packages() -> dict[str, str]:
    packages: dict[str, str] = {}
    previous_name: str | None = None
    previous_has_hash = False
    for raw_line in (worker_root() / "requirements.lock").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            line = line[:-1].rstrip()
        if line.startswith("--hash="):
            if previous_name is None or LOCK_HASH.fullmatch(line) is None:
                raise SystemExit(f"invalid dependency hash line: {raw_line!r}")
            previous_has_hash = True
            continue
        if previous_name is not None and not previous_has_hash:
            raise SystemExit(f"dependency without hash: {previous_name}")
        match = LOCK_LINE.fullmatch(line)
        if match is None:
            raise SystemExit(f"unpinned dependency line: {raw_line!r}")
        previous_name = normalise(match.group("name"))
        if previous_name in packages:
            raise SystemExit(f"duplicate dependency: {previous_name}")
        packages[previous_name] = match.group("version")
        previous_has_hash = False
    if previous_name is not None and not previous_has_hash:
        raise SystemExit(f"dependency without hash: {previous_name}")
    return packages


def provenance(source_dir: Path | None = None) -> None:
    root = worker_root()
    document = json.loads((root / "hermes-provenance.json").read_text(encoding="utf-8"))
    upstream = document["upstream"]
    base = document["base"]
    checks = {
        "upstream.version": upstream.get("version") == UPSTREAM_VERSION,
        "upstream.repository": upstream.get("repository") == UPSTREAM_REPOSITORY,
        "upstream.tag": upstream.get("tag") == UPSTREAM_TAG,
        "upstream.commit": upstream.get("commit") == UPSTREAM_COMMIT,
        "base.image": base.get("image") == BASE_IMAGE,
        "base.digest": base.get("digest") == BASE_DIGEST,
        "base.platform": base.get("platform") == "linux/amd64",
        "docker.base": f"FROM {BASE_IMAGE}@{BASE_DIGEST}"
        in (root / "Dockerfile").read_text(encoding="utf-8"),
        "docker.syntax_digest": f"# syntax=docker/dockerfile:1@{DOCKERFILE_SYNTAX_DIGEST}"
        in (root / "Dockerfile").read_text(encoding="utf-8"),
        "docker.upstream_tag": f"HERMES_RUNTIME_UPSTREAM_TAG={UPSTREAM_TAG}"
        in (root / "Dockerfile").read_text(encoding="utf-8"),
        "docker.upstream_commit": f"HERMES_RUNTIME_UPSTREAM_COMMIT={UPSTREAM_COMMIT}"
        in (root / "Dockerfile").read_text(encoding="utf-8"),
        "docker.no_latest": "latest"
        not in (root / "Dockerfile").read_text(encoding="utf-8").casefold(),
        "dependencies.floating": document["dependencies"].get("floatingVersions") is False,
    }
    locked = lock_packages()
    expected = json.loads(
        (root / "LICENSES" / "package-license-inventory.json").read_text(encoding="utf-8")
    )
    expected_packages = {
        normalise(str(item["name"])): str(item["version"]) for item in expected["pythonPackages"]
    }
    checks["dependencies.inventory_match"] = locked == expected_packages
    if source_dir is not None:
        source_dir = source_dir.resolve()

        def git(*args: str) -> str:
            result = run(["git", "-C", str(source_dir), *args], capture=True)
            return result.stdout.strip()

        def git_bytes(*args: str) -> bytes:
            result = subprocess.run(
                ["git", "-C", str(source_dir), *args],
                check=False,
                capture_output=True,
            )
            if result.returncode != 0:
                raise SystemExit(f"git command failed: {args!r}")
            return result.stdout

        pyproject = git_bytes("show", "HEAD:pyproject.toml").decode("utf-8")
        remote = git("remote", "get-url", "origin")
        checks["source.commit"] = git("rev-parse", "HEAD") == UPSTREAM_COMMIT
        checks["source.tag"] = git("describe", "--exact-match", "--tags", "HEAD") == UPSTREAM_TAG
        checks["source.repository"] = remote == UPSTREAM_REPOSITORY
        checks["source.version"] = (
            re.search(r'^version\s*=\s*["\']0\.21\.0["\']$', pyproject, re.MULTILINE) is not None
        )
        checks["source.license"] = (
            hashlib.sha256(git_bytes("show", "HEAD:LICENSE")).hexdigest()
            == upstream["licenseSha256"]
        )
    if not all(checks.values()):
        write_json(evidence_root() / "provenance-failed.json", {"checks": checks})
        raise SystemExit(f"provenance verification failed: {checks}")
    write_json(evidence_root() / "provenance.json", {"checks": checks, "document": document})
    print(json.dumps({"status": "passed", "checks": checks}, ensure_ascii=False, sort_keys=True))
    discovery_verification("provenance")


def ensure_evidence_path() -> None:
    path = evidence_root()
    if path.exists():
        return
    manager = repo_root() / "scripts" / "artifact_manager.py"
    run(
        [
            sys.executable,
            str(manager),
            "--root",
            str(repo_root() / ".artifacts"),
            "--repo-root",
            str(repo_root()),
            "allocate",
            "129",
            "evidence",
            "evidence/hermes-worker-integration",
            "--directory",
            "--purpose",
            "Task 129 local Hermes worker integration evidence",
            "--command",
            "scripts/hermes_worker.py verify",
        ]
    )


def build() -> None:
    ensure_evidence_path()
    provenance()
    run(
        [
            "docker",
            "build",
            "--platform",
            "linux/amd64",
            "--pull=false",
            "--file",
            str(worker_root() / "Dockerfile"),
            "--tag",
            image_ref(),
            str(worker_root()),
        ]
    )
    inspect()
    discovery_verification("build")


def inspect() -> dict[str, Any]:
    result = run(["docker", "image", "inspect", image_ref()], capture=True)
    document = json.loads(result.stdout)[0]
    metadata = {
        "image": image_ref(),
        "id": document.get("Id"),
        "repoDigests": document.get("RepoDigests", []),
        "sizeBytes": document.get("Size"),
        "architecture": document.get("Architecture"),
        "os": document.get("Os"),
        "config": {
            "user": document.get("Config", {}).get("User"),
            "entrypoint": document.get("Config", {}).get("Entrypoint"),
        },
        "upstream": {
            "version": UPSTREAM_VERSION,
            "tag": UPSTREAM_TAG,
            "commit": UPSTREAM_COMMIT,
        },
        "base": {"image": BASE_IMAGE, "digest": BASE_DIGEST},
    }
    write_json(evidence_root() / "image-metadata.json", metadata)
    return metadata


def save_image() -> Path:
    path = evidence_root() / "image.tar"
    run(["docker", "save", "--output", str(path), image_ref()])
    return path


def scanner_run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    image_tar = evidence_root() / "image.tar"
    # Always refresh the tarball so SBOM and vulnerability evidence belongs to
    # the image currently addressed by image_ref(), never to a prior build.
    save_image()
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--volume",
        f"{image_tar.parent}:/input:ro",
        "--volume",
        f"{evidence_root()}:/output",
        "--volume",
        "task129-trivy-cache:/root/.cache/trivy",
        TRIVY_IMAGE,
        "image",
        "--input",
        "/input/image.tar",
        *args,
    ]
    return run(command, check=check)


def sbom() -> None:
    ensure_evidence_path()
    inspect()
    save_image()
    scanner_run(["--format", "cyclonedx", "--output", "/output/sbom.cdx.json"])
    scanner_run(["--format", "spdx-json", "--output", "/output/sbom.spdx.json"])
    print(
        json.dumps(
            {"status": "passed", "files": ["sbom.cdx.json", "sbom.spdx.json"]}, sort_keys=True
        )
    )
    discovery_verification("sbom")


def security() -> None:
    ensure_evidence_path()
    inspect()
    save_image()
    result = scanner_run(
        [
            "--scanners",
            "vuln",
            "--severity",
            "CRITICAL,HIGH",
            "--exit-code",
            "1",
            "--format",
            "json",
            "--output",
            "/output/vulnerability-report.json",
        ],
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    print(json.dumps({"status": "passed", "critical": 0, "high": 0}, sort_keys=True))
    discovery_verification("security")


def hardening() -> None:
    ensure_evidence_path()
    script = (
        "import os,pathlib,re,sys; "
        "root=pathlib.Path('/'); data=pathlib.Path('/opt/data'); "
        "\ntry: (root/'task129-rootfs-probe').write_text('blocked')\nexcept OSError: print('rootfs=blocked')\nelse: raise SystemExit('rootfs_write_allowed'); "
        "\ntry: (data/'task129-data-probe').write_text('ok'); (data/'task129-data-probe').unlink(); print('data=writeable')\nexcept OSError as exc: raise SystemExit(f'data_write_failed:{type(exc).__name__}'); "
        "\nstatus=pathlib.Path('/proc/self/status').read_text(); "
        "caps=re.search(r'^CapEff:\\s+([0-9a-f]+)$',status,re.M); nnp=re.search(r'^NoNewPrivs:\\s+(\\d+)$',status,re.M); "
        "uid=os.getuid(); gid=os.getgid(); cap_value=caps.group(1).lower() if caps else ''; nnp_value=nnp.group(1) if nnp else ''; "
        "print('uid={} gid={}'.format(uid, gid)); print('CapEff: {}'.format(cap_value or 'missing')); print('NoNewPrivs: {}'.format(nnp_value or 'missing')); "
        "\nif uid != 10000 or gid != 10000: raise SystemExit('identity_not_non_root:{}:{}'.format(uid, gid)); "
        "\nif not cap_value or int(cap_value, 16) != 0: raise SystemExit('capabilities_not_dropped:' + (cap_value or 'missing')); "
        "\nif nnp_value != '1': raise SystemExit('no_new_privileges_missing:' + (nnp_value or 'missing')); "
        "\nblocked=['/bin/sh','/bin/ash','/bin/busybox','/usr/bin/busybox','/sbin/apk','/usr/sbin/apk','/usr/bin/apk','/usr/bin/curl','/usr/bin/ffmpeg','/usr/bin/perl','/usr/bin/chromium','/opt/hermes/license_bundle.py']; "
        "present=[item for item in blocked if pathlib.Path(item).exists()]; "
        "\nif present: raise SystemExit('forbidden_surfaces_present:'+','.join(present))\nprint('forbidden_surfaces=absent')"
    )
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=64m,uid=10000,gid=10000,mode=700",
        "--tmpfs",
        "/opt/data:rw,noexec,nosuid,nodev,size=64m,uid=10000,gid=10000,mode=700",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        "64",
        "--memory",
        "512m",
        "--cpus",
        "0.50",
        "--user",
        "10000:10000",
        "--entrypoint",
        "python",
        image_ref(),
        "-c",
        script,
    ]
    result = run(command, capture=True)
    (evidence_root() / "hardening-boundary.txt").write_text(result.stdout, encoding="utf-8")
    print(result.stdout, end="")
    discovery_verification("hardening")


def e2e() -> None:
    ensure_evidence_path()
    environment = os.environ.copy()
    environment["HERMES_WORKER_IMAGE"] = image_ref()
    environment["TASK129_ARTIFACT_ROOT"] = tempfile.mkdtemp(
        prefix="local-e2e-run-", dir=evidence_root()
    )
    test_script = (
        repo_root() / "tests" / "integration" / "hermes_editorial_worker" / "local_worker_e2e.py"
    )
    result = subprocess.run(
        [sys.executable, str(test_script)], env=environment, check=False, text=True
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    discovery_verification("e2e")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("provenance", "build", "hardening", "e2e", "sbom", "security", "verify")
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        help="Optional local Hermes checkout for exact tag/commit verification",
    )
    args = parser.parse_args()
    ensure_evidence_path()
    if args.command == "provenance":
        provenance(args.source_dir)
    elif args.command == "build":
        build()
    elif args.command == "hardening":
        hardening()
    elif args.command == "e2e":
        e2e()
    elif args.command == "sbom":
        sbom()
    elif args.command == "security":
        security()
    else:
        provenance(args.source_dir)
        build()
        hardening()
        e2e()
        sbom()
        security()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
