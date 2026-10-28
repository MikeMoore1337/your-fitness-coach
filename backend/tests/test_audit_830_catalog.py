from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "audit_830_catalog", Path(__file__).resolve().parents[2] / "scripts/audit_830_catalog.py"
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    records = [
        {"id": "0002", "variantOf": "0001"},
        {"id": "0001", "name": "SHARED", "textSource": "opengym", "femaleVariant": "0002"},
        {"id": "0003", "name": "Other"},
    ]
    blobs = {row["id"]: row["id"] * 10 for row in records}
    catalog = [("a", "A"), ("b", "B")]
    metadata = {"a": {"aliases": ("shared",)}, "b": {"aliases": ("shared", "other")}}
    manifest = {
        "exercises": {
            "a": {
                "media": [
                    {"asset_id": "gymvisual:0001:asset"},
                    {"asset_id": "gymvisual:0003:asset"},
                ]
            },
            "b": {"media": [{"asset_id": "gymvisual:0001:asset"}]},
        }
    }
    return records, blobs, catalog, metadata, {}, manifest


def test_candidates_remain_review_and_order_is_stable():
    args = fixture()
    before = copy.deepcopy(args)
    rows, canonical, _, dimensions = module.compare(*args)
    assert [row["source_id"] for row in rows] == ["0001", "0002", "0003"]
    assert [row["reason"] for row in rows] == [
        "AMBIGUOUS_CANDIDATES",
        "UPSTREAM_VARIANT_IDENTITY_UNVERIFIED",
        "NAME_MEDIA_CONFLICT",
    ]
    assert rows[1]["source_relation"] == "VARIANT"
    assert rows[1]["source_relation_evidence"] == "variantOf+reciprocal_femaleVariant"
    assert rows[0]["media_id_candidates"] == "a|b"
    assert all(row["status"] == "REVIEW" for row in rows)
    assert canonical == ["a", "b"]
    assert dimensions["textSource"]["UNKNOWN"] == 2
    assert args == before
    assert module.compare(*args)[0] == rows


def test_duplicate_ids_and_missing_variant_fail_closed():
    args = fixture()
    args[0].append(copy.deepcopy(args[0][0]))
    with pytest.raises(ValueError, match="duplicate IDs"):
        module.compare(*args)
    args = fixture()
    args[0][0]["variantOf"] = "missing"
    with pytest.raises(ValueError, match="unresolved variantOf"):
        module.compare(*args)


def test_manifest_must_cover_exact_canonical_set():
    args = fixture()
    del args[-1]["exercises"]["b"]
    with pytest.raises(ValueError, match="canonical and manifest entries differ"):
        module.compare(*args)


def test_unreciprocated_source_variant_is_review():
    args = fixture()
    del args[0][1]["femaleVariant"]
    rows, *_ = module.compare(*args)
    assert rows[1]["source_relation"] == "REVIEW"
    assert rows[1]["source_relation_evidence"] == "variantOf_without_reciprocal"
