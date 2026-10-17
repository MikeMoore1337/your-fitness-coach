"""Deterministic, offline import of semantically verified HD exercise posters.

The command is intentionally dry-run by default.  It consumes the checked-in
semantic mapping and a locally checked-out source repository pinned to the
recorded revision; it never downloads media or guesses a mapping.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "backend/assets/exercise-guides"
MANIFEST_PATH = ASSETS / "manifest.json"
MAPPING_PATH = ROOT / "docs/exercises/catalog-v2/986_HD_MAPPING.csv"
INVENTORY_PATH = ROOT / "docs/exercises/catalog-v2/986_SOURCE_INVENTORY.csv"
OLD_MATRIX_PATH = ROOT / "docs/exercises/catalog-v2/986_COVERAGE_MATRIX.csv"
FULL_MATRIX_PATH = ROOT / "docs/exercises/catalog-v2/986_FULL_HD_COVERAGE.csv"
REPORT_PATH = ROOT / "docs/exercises/catalog-v2/986_FULL_HD_COVERAGE_REPORT.md"
DEFAULT_SOURCE_ROOT = ROOT / ".artifacts/runtime/986-full-hd-audit/source"
SOURCE_URL = "https://github.com/akajdid-mostafa/exercises-media"
SOURCE_REVISION = "18742da40b0627c85925c5dd4441dc3eac0594d0"
RIGHTS_BASIS = "owner_confirmed_hq_media_usage_and_derivatives_2026-10-16"
BASELINE_ASSET_COUNT = 334
BASELINE_TOTAL_BYTES = 18_352_704
SIZES = (640, 1280, 1920)
SAFE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _safe_relative(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    if not candidate.is_relative_to(root_resolved):
        raise ValueError(f"Path escapes root: {relative}")
    return candidate


def _encode_derivatives(source: bytes) -> dict[int, dict[str, bytes]]:
    with Image.open(io.BytesIO(source)) as opened:
        if opened.format != "JPEG":
            raise ValueError("HD source is not JPEG")
        image = ImageOps.exif_transpose(opened).convert("RGB")
        if image.size != (1920, 1080):
            raise ValueError(f"HD source dimensions are {image.size}, expected 1920x1080")
        result: dict[int, dict[str, bytes]] = {}
        for width in SIZES:
            height = width * 1080 // 1920
            resized = (
                image if width == 1920 else image.resize((width, height), Image.Resampling.LANCZOS)
            )
            jpeg = io.BytesIO()
            resized.save(
                jpeg, format="JPEG", quality=88, optimize=True, progressive=True, subsampling=0
            )
            webp = io.BytesIO()
            resized.save(webp, format="WEBP", quality=88, method=6)
            result[width] = {"jpg": jpeg.getvalue(), "webp": webp.getvalue()}
        return result


def _descriptor(path: str, payload: bytes, width: int) -> dict[str, Any]:
    suffix = Path(path).suffix.lower()
    mime = "image/webp" if suffix == ".webp" else "image/jpeg"
    return {
        "path": path,
        "mime_type": mime,
        "width": width,
        "height": width * 1080 // 1920,
        "byte_size": len(payload),
        "sha256": sha256(payload),
    }


def _source_provenance(row: dict[str, str], source_bytes: bytes, canonical: str) -> dict[str, Any]:
    return {
        "name": "Exercises Media",
        "url": SOURCE_URL,
        "source_revision": SOURCE_REVISION,
        "source_path": row["path"],
        "source_gender": row["gender"],
        "source_slug": row["slug"],
        "git_blob_sha1": row["git_blob_sha1"],
        "source_sha256": sha256(source_bytes),
        "source_byte_size": len(source_bytes),
        "source_dimensions": {"width": 1920, "height": 1080},
        "canonical_slug": canonical,
        "rights_basis": RIGHTS_BASIS,
        "transformation": "pillow-exif-transpose-rgb-resize-jpeg-q88-webp-q88-no-metadata",
    }


def _all_referenced_paths(manifest: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for item in manifest.get("exercises", {}).values():
        for media in item.get("media", []):
            for key in ("path", "poster_path"):
                if media.get(key):
                    paths.add(str(media[key]))
            for key in ("sources", "poster_sources", "video_sources"):
                paths.update(
                    str(source["path"]) for source in media.get(key, []) if source.get("path")
                )
    return paths


def _manifest_asset_counts(
    manifest: dict[str, Any], generated: dict[str, bytes]
) -> tuple[int, int]:
    paths = _all_referenced_paths(manifest)
    total = 0
    for relative in paths:
        path = _safe_relative(ASSETS, relative)
        if relative in generated:
            total += len(generated[relative])
            continue
        if not path.is_file():
            raise ValueError(f"Manifest references missing asset: {relative}")
        total += path.stat().st_size
    return len(paths), total


def _canonical_titles() -> dict[str, tuple[str, dict[str, Any]]]:
    from fitminiapp_api.services.exercise_catalog_metadata import (
        CANONICAL_EXERCISE_REDIRECTS,
        structured_catalog_metadata,
    )
    from fitminiapp_api.services.program_seed_data import EXERCISE_CATALOG

    metadata = structured_catalog_metadata()
    result: dict[str, tuple[str, dict[str, Any]]] = {}
    for slug, title, _primary_muscle, _equipment in EXERCISE_CATALOG:
        canonical = CANONICAL_EXERCISE_REDIRECTS.get(slug, slug)
        result.setdefault(canonical, (title, metadata[canonical]))
    return result


def _baseline_rows() -> dict[str, dict[str, str]]:
    """Read the pre-import ledger; the importer never rewrites this file."""
    rows = _read_csv(OLD_MATRIX_PATH)
    required = {"canonical_slug", "current_status", "current_media_source"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("Immutable coverage baseline is missing current status fields")
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        canonical = row["canonical_slug"]
        if canonical in result:
            raise ValueError(f"Duplicate canonical in immutable coverage baseline: {canonical}")
        result[canonical] = row
    return result


def _mapping_rows() -> list[dict[str, str]]:
    rows = _read_csv(MAPPING_PATH)
    seen: set[str] = set()
    for row in rows:
        canonical = row["canonical_slug"]
        if not SAFE_SLUG.fullmatch(canonical) or canonical in seen:
            raise ValueError(f"Unsafe or duplicate canonical mapping: {canonical}")
        if row["semantic_status"] != "VERIFIED_SEMANTIC" or row["confidence"] != "high":
            raise ValueError(f"Only high-confidence verified mappings may be imported: {canonical}")
        if row["import_action"] not in {"replace_hd", "add_static"}:
            raise ValueError(f"Unsupported import action: {canonical}")
        if row["source_gender"] not in {"male", "female"} or not SAFE_SLUG.fullmatch(
            row["source_slug"]
        ):
            raise ValueError(f"Unsafe source mapping: {canonical}")
        seen.add(canonical)
    return rows


def _plan(source_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, bytes]]:
    if not source_root.is_dir():
        raise FileNotFoundError(f"Pinned source checkout is missing: {source_root}")
    git_dir = source_root / ".git"
    if not git_dir.exists():
        raise ValueError("Pinned source checkout must retain .git for revision verification")
    revision = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if revision != SOURCE_REVISION:
        raise ValueError(f"Pinned source revision mismatch: {revision}")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 3:
        raise ValueError("Unexpected active media manifest schema")
    inventory = {
        (row["gender"], row["slug"], row["asset_type"]): row for row in _read_csv(INVENTORY_PATH)
    }
    titles = _canonical_titles()
    old_status = _baseline_rows()
    mappings = _mapping_rows()
    canonical_slugs = set(titles)
    if set(manifest.get("exercises", {})) != canonical_slugs:
        raise ValueError("Manifest/catalog canonical set mismatch")
    if set(old_status) != canonical_slugs:
        raise ValueError("Immutable coverage baseline/catalog canonical set mismatch")
    new_manifest = copy.deepcopy(manifest)
    new_manifest.setdefault("hd_baseline_asset_count", BASELINE_ASSET_COUNT)
    new_manifest.setdefault("hd_baseline_total_bytes", BASELINE_TOTAL_BYTES)
    payloads: dict[str, bytes] = {}
    planned_by_slug: dict[str, dict[str, Any]] = {}
    for mapping in mappings:
        canonical = mapping["canonical_slug"]
        record = inventory.get((mapping["source_gender"], mapping["source_slug"], "poster"))
        if record is None or record["path"] != (
            f"public/thumbnails/{mapping['source_gender']}/{mapping['source_slug']}.jpg"
        ):
            raise ValueError(f"Pinned source inventory poster missing: {canonical}")
        source_path = _safe_relative(source_root, record["path"])
        source_bytes = source_path.read_bytes()
        if (
            len(source_bytes) != int(record["bytes"])
            or git_blob_sha1(source_bytes) != record["git_blob_sha1"]
        ):
            raise ValueError(f"Pinned source SHA-1/size mismatch: {canonical}")
        derivatives = _encode_derivatives(source_bytes)
        poster_sources: list[dict[str, Any]] = []
        for width in SIZES:
            for ext in ("webp", "jpg"):
                relative = f"exercises-media/{canonical}/poster-{width}.{ext}"
                payload = derivatives[width][ext]
                payloads[relative] = payload
                poster_sources.append(_descriptor(relative, payload, width))
        poster_sources.sort(key=lambda value: (value["width"], value["mime_type"]))
        fallback = next(
            source
            for source in poster_sources
            if source["width"] == 1280 and source["mime_type"] == "image/jpeg"
        )
        provenance = _source_provenance(record, source_bytes, canonical)
        item = new_manifest["exercises"][canonical]
        if mapping["import_action"] == "add_static":
            title = titles[canonical][0]
            item["status"] = "approved"
            item.pop("blocked_reason", None)
            item["source"] = {
                "name": "Exercises Media",
                "url": SOURCE_URL,
                "license": "Owner-authorized source media and derivatives",
                "license_url": SOURCE_URL,
                "source_revision": SOURCE_REVISION,
                "rights_basis": RIGHTS_BASIS,
            }
            item["media"] = [
                {
                    "type": "image",
                    "path": fallback["path"],
                    "poster_path": fallback["path"],
                    "phase_id": "movement",
                    "phase": "Движение",
                    "alt": f"{title}: изображение упражнения",
                    "asset_id": f"exercises-media:{canonical}:{mapping['source_slug']}",
                    "asset_version": f"exercises-media-{SOURCE_REVISION[:12]}",
                    "variant_key": "canonical-exercises-media-static",
                    "width": fallback["width"],
                    "height": fallback["height"],
                    "byte_size": fallback["byte_size"],
                    "poster_byte_size": fallback["byte_size"],
                    "sort_order": 0,
                    "asset_sha256": fallback["sha256"],
                    "poster_sha256": fallback["sha256"],
                    "poster_dimensions": {"width": fallback["width"], "height": fallback["height"]},
                    "frame_count": 1,
                    "duration_ms": 0,
                    "animated": False,
                    "poster_preferred": True,
                    "poster_source": provenance,
                    "sources": poster_sources,
                    "poster_sources": poster_sources,
                }
            ]
        else:
            if item.get("status") != "approved" or not item.get("media"):
                raise ValueError(f"replace_hd requires approved existing animation: {canonical}")
            media = item["media"][0]
            media["poster_path"] = fallback["path"]
            media["poster_byte_size"] = fallback["byte_size"]
            media["poster_sha256"] = fallback["sha256"]
            media["poster_dimensions"] = {"width": fallback["width"], "height": fallback["height"]}
            media["poster_preferred"] = True
            media["poster_source"] = provenance
            media["poster_sources"] = poster_sources
        planned_by_slug[canonical] = {
            "mapping": mapping,
            "record": record,
            "provenance": provenance,
            "poster_sources": poster_sources,
            "fallback": fallback,
            "old_item": manifest["exercises"][canonical],
        }
    approved_animated = sum(
        item.get("status") == "approved"
        and any(media.get("type") == "animation" for media in item.get("media", []))
        for item in new_manifest["exercises"].values()
    )
    approved_static = sum(
        item.get("status") == "approved"
        and any(media.get("type") == "image" for media in item.get("media", []))
        for item in new_manifest["exercises"].values()
    )
    mapped_count = len(planned_by_slug)
    new_manifest["hd_source"] = {
        "name": "Exercises Media",
        "url": SOURCE_URL,
        "source_revision": SOURCE_REVISION,
        "rights_basis": RIGHTS_BASIS,
    }
    new_manifest["hd_source_repository"] = SOURCE_URL
    new_manifest["hd_source_revision"] = SOURCE_REVISION
    new_manifest["hd_rights_basis"] = RIGHTS_BASIS
    new_manifest["counts"] = {
        **new_manifest.get("counts", {}),
        "canonical_exercises": len(canonical_slugs),
        "approved_animated": approved_animated,
        "approved_static": approved_static,
        "blocked": len(canonical_slugs) - approved_animated - approved_static,
        "approved_coverage_percent": round(
            (approved_animated + approved_static) / len(canonical_slugs) * 100, 2
        ),
        "hd_coverage_percent": round(mapped_count / len(canonical_slugs) * 100, 2),
        "static_only": approved_static,
        "remote_runtime_assets": 0,
    }
    new_manifest["hq_poster_count"] = mapped_count
    new_manifest["derivative_count"] = mapped_count
    new_manifest["poster_variant_count"] = len(payloads)
    new_manifest["asset_count"], new_manifest["total_bytes"] = _manifest_asset_counts(
        new_manifest, payloads
    )
    matrix = _build_matrix(titles, old_status, manifest, new_manifest, planned_by_slug)
    return new_manifest, matrix, payloads


def _build_matrix(
    titles: dict[str, tuple[str, dict[str, Any]]],
    old_status: dict[str, dict[str, str]],
    old_manifest: dict[str, Any],
    new_manifest: dict[str, Any],
    planned: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    fields = [
        "canonical_slug",
        "russian_title",
        "english_title",
        "aliases",
        "primary_muscle",
        "movement_pattern",
        "equipment",
        "previous_status",
        "previous_media_source",
        "current_status",
        "current_media_source",
        "new_hd_source",
        "source_gender",
        "source_slug",
        "source_path",
        "exact_correspondence",
        "semantic_status",
        "confidence",
        "media_type",
        "resolution",
        "file_size",
        "sha256",
        "import_status",
        "skip_reason",
        "source_revision",
        "source_git_blob_sha1",
        "source_sha256",
    ]
    result: list[dict[str, str]] = []
    for canonical, (title, metadata) in titles.items():
        old_item = old_manifest["exercises"][canonical]
        new_item = new_manifest["exercises"][canonical]
        new_media = (new_item.get("media") or [None])[0] or {}
        old_row = old_status[canonical]
        plan = planned.get(canonical)
        mapping = plan["mapping"] if plan else {}
        fallback = plan["fallback"] if plan else {}
        provenance = plan["provenance"] if plan else {}
        reason = (
            ""
            if plan
            else (
                "Источник не подтверждён семантически; оставить текущий media/fallback"
                if old_item.get("status") == "approved"
                else "Подходящий HD-источник не подтверждён; blocked не снимать"
            )
        )
        result.append(
            {
                "canonical_slug": canonical,
                "russian_title": title,
                "english_title": canonical.replace("-", " ").title(),
                "aliases": " | ".join(metadata["aliases"]),
                "primary_muscle": metadata["primary_muscle"],
                "movement_pattern": metadata["movement_pattern"],
                "equipment": metadata["equipment"],
                "previous_status": old_row["current_status"],
                "previous_media_source": old_row["current_media_source"],
                "current_status": new_item.get("status", ""),
                "current_media_source": new_media.get("path", "")
                or ("blocked/no media" if new_item.get("status") == "blocked" else ""),
                "new_hd_source": provenance.get("url", "") if plan else "",
                "source_gender": mapping.get("source_gender", ""),
                "source_slug": mapping.get("source_slug", ""),
                "source_path": provenance.get("source_path", "") if plan else "",
                "exact_correspondence": mapping.get("review_note", "") if plan else "",
                "semantic_status": mapping.get(
                    "semantic_status", old_row.get("status", "NO_MATCH")
                ),
                "confidence": mapping.get("confidence", ""),
                "media_type": new_media.get("type", ""),
                "resolution": f"{fallback.get('width')}x{fallback.get('height')}" if plan else "",
                "file_size": str(fallback.get("byte_size", "")) if plan else "",
                "sha256": fallback.get("sha256", "") if plan else "",
                "import_status": "planned" if plan else "skipped",
                "skip_reason": reason,
                "source_revision": provenance.get("source_revision", "") if plan else "",
                "source_git_blob_sha1": provenance.get("git_blob_sha1", "") if plan else "",
                "source_sha256": provenance.get("source_sha256", "") if plan else "",
            }
        )
    _ = fields
    return result


def _write_matrix(rows: list[dict[str, str]], path: Path) -> None:
    if not rows:
        raise ValueError("Coverage matrix is empty")
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temp, path)


def _write_report(
    rows: list[dict[str, str]], old_manifest: dict[str, Any], new_manifest: dict[str, Any]
) -> None:
    imported = [
        row
        for row in rows
        if row["import_status"] in {"planned", "imported_added", "imported_replaced"}
    ]
    skipped = [row for row in rows if row["import_status"] == "skipped"]
    static = [row for row in imported if row["media_type"] == "image"]
    replaced = [row for row in imported if row["media_type"] == "animation"]
    review = [row for row in skipped if row["semantic_status"] == "REVIEW"]
    no_match = [row for row in skipped if row["semantic_status"] == "NO_MATCH"]
    before_count = int(new_manifest.get("hd_baseline_asset_count", BASELINE_ASSET_COUNT))
    before = int(new_manifest.get("hd_baseline_total_bytes", BASELINE_TOTAL_BYTES))
    after = int(new_manifest.get("total_bytes", 0))
    report = (
        f"""# Issue #986 — полное HD-покрытие каталога

Отчёт построен универсальным импортёром из закреплённой матрицы `986_HD_MAPPING.csv`.
Импорт выполняется без сетевых запросов и принимает только `VERIFIED_SEMANTIC` / `high` сопоставления.

## Итог

- Canonical exercises: **{len(rows)}**.
- HD-покрытие по подтверждённой матрице: **{len(imported)}/{len(rows)} ({len(imported) / len(rows) * 100:.2f}%)**.
- Подтверждённых HD-постеров для существующего media: **{len(replaced)}**.
- Новых статических изображений для ранее пустых записей: **{len(static)}**.
- Осталось без подтверждённого HD: **{len(skipped)}**.
- Из них `REVIEW`: **{len(review)}**, `NO_MATCH`: **{len(no_match)}**.
- После импорта approved animated: **{new_manifest["counts"]["approved_animated"]}**.
- После импорта approved static: **{new_manifest["counts"]["approved_static"]}**.
- После импорта blocked: **{new_manifest["counts"]["blocked"]}**.
- Runtime assets: **{new_manifest["asset_count"]} файлов / {new_manifest["total_bytes"]:,} байт** (origin/master до импорта: {before_count} файлов / {before:,} байт; изменение: {after - before:+,} байт).

## Контракт обработки

- Источник: `{SOURCE_URL}` at `{SOURCE_REVISION}`.
- `previous_*` берутся из неизменяемой исходной матрицы до импорта; `current_*` — из текущего результата.
- Проверены source path, размер, Git blob SHA-1, JPEG 1920×1080 и контрольная сумма SHA-256.
- Производные: 640/1280/1920 px, WebP и JPEG fallback, RGB, без EXIF/GPS; пропорция 16:9 сохранена.
- Для существующих GIF/H.264 сохранён текущий animated/video путь; HD-постер становится предпочтительным статическим fallback.
- Для новых записей используется `type=image`; MP4 не записывается в image-поля API.

## Ограничения и риски

`REVIEW` и `NO_MATCH` из полной исторической матрицы не были повышены автоматически. Наличие изображения в источнике само по себе не считается доказательством техники. Проверка физического iPhone/TMA, production smoke и визуальная приёмка владельца остаются post-release gates.

## Пропущенные записи

"""
        + "\n".join(f"- `{row['canonical_slug']}` — {row['skip_reason']}" for row in skipped)
        + "\n"
    )
    temp = REPORT_PATH.with_suffix(REPORT_PATH.suffix + ".tmp")
    temp.write_text(report, encoding="utf-8", newline="\n")
    os.replace(temp, REPORT_PATH)


def _apply(
    new_manifest: dict[str, Any],
    rows: list[dict[str, str]],
    payloads: dict[str, bytes],
    old_manifest: dict[str, Any],
) -> None:
    applied_rows = [
        {
            **row,
            "import_status": (
                "imported_added" if row["media_type"] == "image" else "imported_replaced"
            )
            if row["import_status"] == "planned"
            else row["import_status"],
        }
        for row in rows
    ]
    previous = {
        relative: (
            _safe_relative(ASSETS, relative).read_bytes()
            if _safe_relative(ASSETS, relative).is_file()
            else None
        )
        for relative in payloads
    }
    old_manifest_text = MANIFEST_PATH.read_text(encoding="utf-8")
    previous_matrix = FULL_MATRIX_PATH.read_bytes() if FULL_MATRIX_PATH.is_file() else None
    previous_report = REPORT_PATH.read_bytes() if REPORT_PATH.is_file() else None
    staging = Path(tempfile.mkdtemp(prefix=".986-hd-import-", dir=ASSETS))
    try:
        for relative, payload in payloads.items():
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        for relative in payloads:
            destination = _safe_relative(ASSETS, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging / relative, destination)
        manifest_temp = MANIFEST_PATH.with_suffix(".json.tmp")
        manifest_temp.write_text(
            json.dumps(new_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(manifest_temp, MANIFEST_PATH)
        _write_matrix(applied_rows, FULL_MATRIX_PATH)
        _write_report(applied_rows, old_manifest, new_manifest)
    except Exception:
        for relative, data in previous.items():
            destination = _safe_relative(ASSETS, relative)
            if data is None:
                destination.unlink(missing_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
        MANIFEST_PATH.write_text(old_manifest_text, encoding="utf-8", newline="\n")
        for path, data in ((FULL_MATRIX_PATH, previous_matrix), (REPORT_PATH, previous_report)):
            if data is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(data)
        FULL_MATRIX_PATH.with_suffix(FULL_MATRIX_PATH.suffix + ".tmp").unlink(missing_ok=True)
        REPORT_PATH.with_suffix(REPORT_PATH.suffix + ".tmp").unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plan or apply the full verified HD exercise media mapping"
    )
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument(
        "--apply", action="store_true", help="Write managed assets, manifest and reports"
    )
    options = parser.parse_args()
    new_manifest, rows, payloads = _plan(options.source_root)
    mapped = sum(row["import_status"] == "planned" for row in rows)
    print(
        f"HD_MAPPING={mapped}/{len(rows)} HD_COVERAGE={new_manifest['counts']['hd_coverage_percent']:.2f}% "
        f"APPROVED={new_manifest['counts']['approved_animated'] + new_manifest['counts']['approved_static']} "
        f"STATIC_ONLY={new_manifest['counts']['approved_static']} FILES={len(payloads)} APPLY={options.apply}"
    )
    if options.apply:
        old_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        _apply(new_manifest, rows, payloads, old_manifest)
        print(f"WROTE={FULL_MATRIX_PATH.relative_to(ROOT)}")
        print(f"WROTE={REPORT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
