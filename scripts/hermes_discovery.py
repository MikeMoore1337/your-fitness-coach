"""Reproducible local build and verification commands for Task 129 discovery."""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

BASE_IMAGE = "python:3.13-alpine"
BASE_DIGEST = "sha256:f3ebba2ace255c93267a0278da88c7f1044432991abc4e6ad20d22e34dd0f8ee"
DOCKERFILE_SYNTAX_DIGEST = "sha256:ecfaec9ed6d810b56388c508f4121597bfbba70d41a6dfeee4d8cad5f295fc32"
TRIVY_IMAGE = (
    "aquasec/trivy:0.74.0@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969"
)
SOURCE_SCHEMA_VERSION = "hermes-source-definitions-v1"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def discovery_root() -> Path:
    return repo_root() / "deploy" / "hermes-discovery"


def evidence_root() -> Path:
    return repo_root() / ".artifacts" / "tasks" / "403" / "evidence" / "discovery-scheduler"


def image_ref() -> str:
    return os.environ.get("HERMES_DISCOVERY_IMAGE", "task403-hermes-discovery:repo-local")


def run(
    command: list[str], *, check: bool = True, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, check=False, text=True, capture_output=capture)
    if check and result.returncode != 0:
        if capture and result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        raise SystemExit(result.returncode)
    return result


def write_json(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def provenance() -> None:
    root = discovery_root()
    document = json.loads((root / "hermes-discovery-provenance.json").read_text(encoding="utf-8"))
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    runner_path = root / "discovery_runner.py"
    discovery_unit = (root / "systemd" / "hermes-discovery.service.template").read_text(
        encoding="utf-8"
    )
    drain_unit = (root / "systemd" / "hermes-worker-drain.service.template").read_text(
        encoding="utf-8"
    )
    drain_path = root / "hermes_worker_drain.py"
    drain_source = drain_path.read_text(encoding="utf-8")
    health_path = root / "hermes_health.py"
    health_source = health_path.read_text(encoding="utf-8")
    guard_path = root / "hermes_resource_guard.py"
    guard_source = guard_path.read_text(encoding="utf-8")
    egress_path = root / "hermes_egress.py"
    egress_source = egress_path.read_text(encoding="utf-8")
    timer_unit = (root / "systemd" / "hermes-discovery.timer").read_text(encoding="utf-8")
    tree = ast.parse(runner_path.read_text(encoding="utf-8"), filename=str(runner_path))
    imports = {
        node.names[0].name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import) and node.names
    }
    imports.update(
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    forbidden_imports = {"subprocess", "httpx", "playwright", "selenium", "requests"}
    checks = {
        "schema": document.get("schemaVersion") == "task403-hermes-discovery-provenance-v2",
        "base.image": document.get("base", {}).get("image") == BASE_IMAGE,
        "base.digest": document.get("base", {}).get("digest") == BASE_DIGEST,
        "base.platform": document.get("base", {}).get("platform") == "linux/amd64",
        "docker.base": f"FROM {BASE_IMAGE}@{BASE_DIGEST}" in dockerfile,
        "docker.syntax_digest": f"# syntax=docker/dockerfile:1@{DOCKERFILE_SYNTAX_DIGEST}"
        in dockerfile,
        "docker.no_latest": "latest" not in dockerfile.casefold(),
        "dependencies.none": document.get("dependencies", {}).get("thirdPartyPython") == [],
        "dependencies.floating": document.get("dependencies", {}).get("floatingVersions") is False,
        "source.schema": (root / "source-definitions.schema.json").is_file(),
        "runtime.health": "hermes-pipeline-health-v1" in health_source,
        "runtime.syntax": all(
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path)) is not None
            for path in (runner_path, drain_path, guard_path, egress_path, health_path)
        ),
        "systemd.definitions_digest": all(
            "HERMES_DISCOVERY_DEFINITIONS_SHA256=@SOURCE_DEFINITIONS_SHA256@" in unit
            for unit in (discovery_unit, drain_unit)
        ),
        "systemd.resource_guard": all(
            "hermes_resource_guard.py check" in unit
            and "hermes_resource_guard.py run" in unit
            and "HERMES_YFC_DEPLOYMENT_LOCK" in unit
            for unit in (discovery_unit, drain_unit)
        ),
        "systemd.discovery_once": "@DISCOVERY_IMAGE@ --once" in discovery_unit,
        "systemd.discovery_network": (
            "Environment=HERMES_DOCKER_NETWORK=hermes-net" in discovery_unit
            and "--network=${HERMES_DOCKER_NETWORK}" in discovery_unit
        ),
        "systemd.scoped_egress": "hermes_egress.py refresh" in discovery_unit,
        "systemd.egress_mode_explicit": "--mode ${HERMES_DEPLOYMENT_MODE}" in discovery_unit,
        "egress.host_runtime": all(
            token in egress_source
            for token in (
                'TABLE_NAME = "hermes_egress"',
                "hook forward",
                "shell=False",
                "DEPLOYMENT_MODES",
                "ip daddr !=",
                "SEPARATE_VM_MODE",
                "COLOCATED_ISOLATED_MODE",
            )
        ),
        "systemd.drain_network": "Environment=HERMES_DOCKER_NETWORK=hermes-net" in drain_unit,
        "systemd.shared_host_root_launchers": all(
            "User=root" in unit
            and "Group=root" in unit
            and "User=hermes" not in unit
            and "docker.sock" not in unit
            for unit in (discovery_unit, drain_unit)
        ),
        "systemd.discovery_container_hardening": all(
            token in discovery_unit
            for token in (
                "--read-only",
                "--cap-drop ALL",
                "--security-opt no-new-privileges:true",
                "--pids-limit 32",
                "--memory 256m",
                "--cpus 0.25",
                "--user 10000:10000",
            )
        ),
        "systemd.discovery_no_floating_image": ":latest" not in discovery_unit,
        "systemd.discovery_no_bridge": "--network bridge" not in discovery_unit,
        "systemd.drain_service_resources": all(
            token in drain_unit
            for token in ("TasksMax=32", "MemoryMax=512M", "CPUQuota=50%", "OOMScoreAdjust=500")
        ),
        "systemd.discovery_oom_priority": "--oom-score-adj 500" in discovery_unit,
        "systemd.timer_worker": "Unit=hermes-worker-drain.service" in timer_unit,
        "resource_guard.thresholds": all(
            token in guard_source
            for token in (
                "MIN_MEMORY_AVAILABLE_MIB = 768",
                "MAX_SWAP_USED_MIB = 512",
                "MAX_LOAD1 = 1.50",
                "MIN_DISK_FREE_MIB = 5 * 1024",
            )
        ),
        "resource_guard.no_shell": "shell=True" not in guard_source,
        "worker.docker_network_validation": all(
            token in drain_source
            for token in (
                "HERMES_DOCKER_NETWORK",
                "_validate_docker_network",
                '"--network",',
                '"--user",\n        "10000:10000"',
            )
        ),
        "worker.no_hardcoded_bridge": '"--network",\n        "bridge"' not in drain_source,
        "worker.resources": all(
            token in drain_source
            for token in (
                '"--pids-limit",\n        "32"',
                '"--memory",\n        "512m"',
                '"--cpus",\n        "0.50"',
            )
        ),
        "systemd.no_missed_run_replay": "Persistent=false" in timer_unit,
        "source.runner_imports": not imports.intersection(forbidden_imports),
        "source.runner_no_secrets": not any(
            value in runner_path.read_text(encoding="utf-8")
            for value in (
                "HERMES_PROVIDER_API_KEY",
                "YFC_HERMES_SHARED_SECRET",
                "TELEGRAM_BOT_TOKEN",
            )
        ),
    }
    definitions_output = evidence_root() / "source-definitions.json"
    generator = repo_root() / "scripts" / "generate_hermes_source_definitions.py"
    generated = run(
        [sys.executable, str(generator), "--output", str(definitions_output)],
        check=True,
        capture=True,
    )
    generated_document = json.loads(definitions_output.read_text(encoding="utf-8"))
    checks["source.generated"] = (
        generated_document.get("schema_version") == SOURCE_SCHEMA_VERSION
        and len(generated_document.get("sources", [])) > 0
    )
    if not all(checks.values()):
        write_json(evidence_root() / "provenance-failed.json", {"checks": checks})
        raise SystemExit(f"discovery provenance verification failed: {checks}")
    write_json(
        evidence_root() / "provenance.json",
        {"checks": checks, "document": document, "generator_output": generated.stdout.strip()},
    )
    print(json.dumps({"status": "passed", "checks": checks}, sort_keys=True))


def build() -> None:
    root = discovery_root()
    run(
        [
            "docker",
            "build",
            "--platform",
            "linux/amd64",
            "--pull=false",
            "--file",
            str(root / "Dockerfile"),
            "--tag",
            image_ref(),
            str(root),
        ]
    )
    inspect()


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
        "base": {"image": BASE_IMAGE, "digest": BASE_DIGEST},
    }
    write_json(evidence_root() / "image-metadata.json", metadata)
    return metadata


def save_image() -> Path:
    path = evidence_root() / "discovery-image.tar"
    run(["docker", "save", "--output", str(path), image_ref()])
    return path


def scanner_run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    image_tar = evidence_root() / "discovery-image.tar"
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
        "/input/discovery-image.tar",
        *args,
    ]
    return run(command, check=check)


def sbom() -> None:
    inspect()
    save_image()
    scanner_run(["--format", "cyclonedx", "--output", "/output/discovery-sbom.cdx.json"])
    scanner_run(["--format", "spdx-json", "--output", "/output/discovery-sbom.spdx.json"])
    print(
        json.dumps(
            {"status": "passed", "files": ["discovery-sbom.cdx.json", "discovery-sbom.spdx.json"]},
            sort_keys=True,
        )
    )


def security() -> None:
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
            "/output/discovery-vulnerability-report.json",
        ],
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    print(json.dumps({"status": "passed", "critical": 0, "high": 0}, sort_keys=True))


def hardening() -> None:
    script = (
        "import os,pathlib,re; root=pathlib.Path('/'); data=pathlib.Path('/opt/data'); "
        "\ntry: (root/'task129-rootfs-probe').write_text('blocked')\nexcept OSError: print('rootfs=blocked')\nelse: raise SystemExit('rootfs_write_allowed'); "
        "\ntry: (data/'task129-data-probe').write_text('ok'); (data/'task129-data-probe').unlink(); print('data=writeable')\nexcept OSError as exc: raise SystemExit(f'data_write_failed:{type(exc).__name__}'); "
        "\nstatus=pathlib.Path('/proc/self/status').read_text(); caps=re.search(r'^CapEff:\\s+([0-9a-f]+)$',status,re.M); nnp=re.search(r'^NoNewPrivs:\\s+(\\d+)$',status,re.M); "
        "uid=os.getuid(); gid=os.getgid(); cap_value=caps.group(1).lower() if caps else ''; nnp_value=nnp.group(1) if nnp else ''; "
        "print('uid={} gid={}'.format(uid,gid)); print('CapEff: {}'.format(cap_value or 'missing')); print('NoNewPrivs: {}'.format(nnp_value or 'missing')); "
        "\nif uid != 10000 or gid != 10000: raise SystemExit('identity_not_non_root'); "
        "\nif not cap_value or int(cap_value,16) != 0: raise SystemExit('capabilities_not_dropped'); "
        "\nif nnp_value != '1': raise SystemExit('no_new_privileges_missing'); "
        "\nblocked=['/bin/sh','/bin/ash','/bin/busybox','/usr/bin/busybox','/sbin/apk','/usr/sbin/apk','/usr/bin/apk','/usr/bin/curl','/usr/bin/ffmpeg','/usr/bin/perl','/usr/bin/chromium','/usr/local/bin/pip','/opt/hermes/license_bundle.py','/opt/hermes/hermes_worker_drain.py','/opt/hermes/editorial_worker.py']; "
        "present=[item for item in blocked if pathlib.Path(item).exists()]; "
        "\nif present: raise SystemExit('forbidden_surfaces_present:'+','.join(present)); print('forbidden_surfaces=absent')"
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
    (evidence_root() / "discovery-hardening-boundary.txt").write_text(
        result.stdout, encoding="utf-8"
    )
    print(result.stdout, end="")


def e2e() -> None:
    test_script = (
        repo_root() / "tests" / "integration" / "hermes_editorial_worker" / "local_discovery_e2e.py"
    )
    environment = os.environ.copy()
    environment["HERMES_DISCOVERY_IMAGE"] = image_ref()
    environment["HERMES_WORKER_IMAGE"] = os.environ.get(
        "HERMES_WORKER_IMAGE", "task403-hermes-editorial-worker:repo-local"
    )
    environment["TASK129_DISCOVERY_ARTIFACT_ROOT"] = tempfile.mkdtemp(
        prefix="local-e2e-run-", dir=evidence_root()
    )
    result = subprocess.run(
        [sys.executable, str(test_script)], env=environment, check=False, text=True
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("provenance", "build", "hardening", "e2e", "sbom", "security", "verify")
    )
    args = parser.parse_args()
    evidence_root().mkdir(parents=True, exist_ok=True)
    if args.command == "provenance":
        provenance()
    elif args.command == "build":
        provenance()
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
        provenance()
        build()
        hardening()
        e2e()
        sbom()
        security()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
