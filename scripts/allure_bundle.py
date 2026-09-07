"""Encrypt and safely unpack scheduled Allure result bundles."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

if __package__:
    from scripts.scheduled_regression import MAX_BUNDLE_BYTES
else:
    from scheduled_regression import MAX_BUNDLE_BYTES

BUNDLE_SCHEMA_VERSION = 1
DEFAULT_KEY_ENV = "ALLURE_REPORT_ENCRYPTION_KEY"
BUNDLE_MAGIC = b"YFC-ALLURE-BUNDLE-v1\n"
_SAFE_TEXT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class AllureBundleError(RuntimeError):
    """A result bundle could not be created or opened safely."""


def _require_key(key_env: str) -> str:
    key = os.environ.get(key_env, "")
    if len(key) < 32:
        raise AllureBundleError(f"{key_env} must contain at least 32 characters")
    return key


def _safe_text(value: str, *, field: str) -> str:
    if not _SAFE_TEXT.fullmatch(value):
        raise AllureBundleError(f"unsafe {field}: {value!r}")
    return value


def _source_files(source: Path) -> tuple[tuple[Path, str, int], ...]:
    if not source.is_dir():
        raise AllureBundleError(f"result directory does not exist: {source}")
    files: list[tuple[Path, str, int]] = []
    total_bytes = 0
    for candidate in sorted(source.rglob("*")):
        if candidate.is_symlink():
            raise AllureBundleError(f"symlink is not allowed in result bundle: {candidate}")
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(source).as_posix()
        if not relative or relative.startswith("../"):
            raise AllureBundleError(f"unsafe result path: {relative!r}")
        if relative == "manifest.json":
            raise AllureBundleError("source result directory must not contain manifest.json")
        size = candidate.stat().st_size
        total_bytes += size
        if total_bytes > MAX_BUNDLE_BYTES:
            raise AllureBundleError(f"result bundle exceeds {MAX_BUNDLE_BYTES} uncompressed bytes")
        files.append((candidate, relative, size))
    return tuple(files)


def _bundle_tag(ciphertext: bytes, *, key_env: str) -> bytes:
    key = _require_key(key_env).encode("utf-8")
    return hmac.new(key, BUNDLE_MAGIC + ciphertext, hashlib.sha256).digest()


def _run_openssl(*, decrypt: bool, input_path: Path, output_path: Path, key_env: str) -> None:
    _require_key(key_env)
    command = [
        "openssl",
        "enc",
        "-d" if decrypt else "-e",
        "-aes-256-cbc",
        "-pbkdf2",
        "-iter",
        "100000",
        "-salt",
        "-in",
        str(input_path),
        "-out",
        str(output_path),
        "-pass",
        f"env:{key_env}",
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=dict(os.environ),
    )
    if completed.returncode != 0:
        raise AllureBundleError("openssl could not process the Allure bundle")


def encrypt_bundle(
    *,
    source: Path,
    output: Path,
    suite: str,
    browser: str,
    key_env: str = DEFAULT_KEY_ENV,
) -> dict[str, object]:
    """Create one encrypted bundle with a non-sensitive manifest."""

    normalized_suite = _safe_text(suite, field="suite")
    normalized_browser = _safe_text(browser, field="browser")
    files = _source_files(source)
    source_bytes = sum(size for _, _, size in files)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise AllureBundleError(f"refusing to overwrite existing bundle: {output}")

    manifest: dict[str, object] = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "suite": normalized_suite,
        "browser": normalized_browser,
        "file_count": len(files),
        "source_bytes": source_bytes,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    archive_path: Path | None = None
    encrypted_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="allure-bundle-", suffix=".tar.gz", dir=output.parent, delete=False
        ) as stream:
            archive_path = Path(stream.name)
        with tarfile.open(archive_path, mode="w:gz") as archive:
            manifest_info = tarfile.TarInfo("manifest.json")
            manifest_info.size = len(manifest_bytes)
            manifest_info.mode = 0o600
            archive.addfile(manifest_info, io.BytesIO(manifest_bytes))
            for path, relative, _ in files:
                info = archive.gettarinfo(str(path), arcname=relative)
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                with path.open("rb") as source_stream:
                    archive.addfile(info, source_stream)
        with tempfile.NamedTemporaryFile(
            prefix="allure-bundle-", suffix=".enc", dir=output.parent, delete=False
        ) as stream:
            encrypted_path = Path(stream.name)
        _run_openssl(
            decrypt=False,
            input_path=archive_path,
            output_path=encrypted_path,
            key_env=key_env,
        )
        ciphertext = encrypted_path.read_bytes()
        payload = BUNDLE_MAGIC + _bundle_tag(ciphertext, key_env=key_env) + ciphertext
        encrypted_bytes = len(payload)
        if encrypted_bytes > MAX_BUNDLE_BYTES:
            raise AllureBundleError(f"encrypted bundle exceeds {MAX_BUNDLE_BYTES} bytes")
        output.write_bytes(payload)
        return {
            **manifest,
            "encrypted_bytes": encrypted_bytes,
            "output": output.as_posix(),
        }
    finally:
        for path in (archive_path, encrypted_path):
            if path is not None:
                path.unlink(missing_ok=True)


def _member_target(root: Path, name: str) -> Path:
    pure = PurePosixPath(name)
    if pure.is_absolute() or not pure.parts or ".." in pure.parts:
        raise AllureBundleError(f"unsafe archive member: {name!r}")
    target = (root / Path(*pure.parts)).resolve()
    if not target.is_relative_to(root.resolve()):
        raise AllureBundleError(f"archive member escapes output directory: {name!r}")
    return target


def _read_manifest(archive: tarfile.TarFile) -> dict[str, object]:
    try:
        member = archive.getmember("manifest.json")
    except KeyError as error:
        raise AllureBundleError("bundle manifest is missing") from error
    if not member.isfile() or member.size > 64 * 1024:
        raise AllureBundleError("bundle manifest is invalid")
    stream = archive.extractfile(member)
    if stream is None:
        raise AllureBundleError("bundle manifest cannot be read")
    try:
        payload = json.load(stream)
    except (json.JSONDecodeError, OSError) as error:
        raise AllureBundleError("bundle manifest is not valid JSON") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise AllureBundleError("unsupported bundle manifest schema")
    for field in ("file_count", "source_bytes"):
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise AllureBundleError(f"bundle manifest field {field!r} is invalid")
        if value > MAX_BUNDLE_BYTES:
            raise AllureBundleError(f"bundle manifest field {field!r} exceeds bundle size limit")
    for field in ("suite", "browser"):
        value = payload.get(field)
        if not isinstance(value, str):
            raise AllureBundleError(f"bundle manifest field {field!r} is invalid")
        _safe_text(value, field=field)
    return payload


def decrypt_bundle(
    *,
    source: Path,
    output: Path,
    key_env: str = DEFAULT_KEY_ENV,
) -> dict[str, object]:
    """Decrypt and extract one bundle while refusing traversal and special files."""

    source = source.resolve()
    output = output.resolve()
    if not source.is_file():
        raise AllureBundleError(f"encrypted bundle does not exist: {source}")
    if source.stat().st_size > MAX_BUNDLE_BYTES:
        raise AllureBundleError(f"encrypted bundle exceeds {MAX_BUNDLE_BYTES} bytes")
    if output.exists() and any(output.iterdir()):
        raise AllureBundleError(f"refusing to mix into non-empty output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging_output = Path(tempfile.mkdtemp(prefix="allure-decrypt-", dir=output.parent))
    archive_path: Path | None = None
    ciphertext_path: Path | None = None
    try:
        payload = source.read_bytes()
        tag_start = len(BUNDLE_MAGIC)
        tag_end = tag_start + hashlib.sha256().digest_size
        if not payload.startswith(BUNDLE_MAGIC) or len(payload) <= tag_end:
            raise AllureBundleError("encrypted bundle header is invalid")
        ciphertext = payload[tag_end:]
        expected_tag = _bundle_tag(ciphertext, key_env=key_env)
        if not hmac.compare_digest(payload[tag_start:tag_end], expected_tag):
            raise AllureBundleError("encrypted bundle authentication failed")
        with tempfile.NamedTemporaryFile(
            prefix="allure-bundle-", suffix=".ciphertext", dir=output.parent, delete=False
        ) as stream:
            ciphertext_path = Path(stream.name)
            stream.write(ciphertext)
        with tempfile.NamedTemporaryFile(
            prefix="allure-bundle-", suffix=".tar.gz", dir=output.parent, delete=False
        ) as stream:
            archive_path = Path(stream.name)
        _run_openssl(
            decrypt=True,
            input_path=ciphertext_path,
            output_path=archive_path,
            key_env=key_env,
        )
        with tarfile.open(archive_path, mode="r:gz") as archive:
            members = archive.getmembers()
            if len(members) > 100_000:
                raise AllureBundleError("bundle contains too many files")
            names = [member.name for member in members]
            if len(names) != len(set(names)):
                raise AllureBundleError("bundle contains duplicate archive members")
            if sum(member.name == "manifest.json" for member in members) != 1:
                raise AllureBundleError("bundle must contain exactly one manifest")
            manifest = _read_manifest(archive)
            total_bytes = 0
            file_count = 0
            for member in members:
                if member.name == "manifest.json":
                    continue
                if not member.isfile():
                    raise AllureBundleError(f"special archive member is not allowed: {member.name}")
                if member.size > MAX_BUNDLE_BYTES:
                    raise AllureBundleError("archive member exceeds bundle size limit")
                total_bytes += member.size
                if total_bytes > MAX_BUNDLE_BYTES:
                    raise AllureBundleError("expanded bundle exceeds size limit")
                file_count += 1
                target = _member_target(staging_output, member.name)
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = archive.extractfile(member)
                if stream is None:
                    raise AllureBundleError(f"archive member cannot be read: {member.name}")
                with target.open("wb") as destination:
                    shutil.copyfileobj(stream, destination)
            if manifest["file_count"] != file_count or manifest["source_bytes"] != total_bytes:
                raise AllureBundleError("bundle manifest does not match archive contents")
        if output.exists():
            output.rmdir()
        staging_output.replace(output)
        return manifest
    except (OSError, tarfile.TarError) as error:
        raise AllureBundleError("encrypted bundle is invalid") from error
    finally:
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)
        if ciphertext_path is not None:
            ciphertext_path.unlink(missing_ok=True)
        if staging_output.exists():
            shutil.rmtree(staging_output, ignore_errors=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    encrypt = subparsers.add_parser("encrypt")
    encrypt.add_argument("--source", type=Path, required=True)
    encrypt.add_argument("--output", type=Path, required=True)
    encrypt.add_argument("--suite", required=True)
    encrypt.add_argument("--browser", required=True)
    encrypt.add_argument("--key-env", default=DEFAULT_KEY_ENV)
    decrypt = subparsers.add_parser("decrypt")
    decrypt.add_argument("--source", type=Path, required=True)
    decrypt.add_argument("--output", type=Path, required=True)
    decrypt.add_argument("--key-env", default=DEFAULT_KEY_ENV)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "encrypt":
            payload = encrypt_bundle(
                source=args.source,
                output=args.output,
                suite=args.suite,
                browser=args.browser,
                key_env=args.key_env,
            )
        elif args.command == "decrypt":
            payload = decrypt_bundle(source=args.source, output=args.output, key_env=args.key_env)
        else:
            raise AssertionError(f"Unhandled command: {args.command}")
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    except (AllureBundleError, OSError) as error:
        print(f"allure bundle error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
