"""Render the Hermes discovery allowlist from the canonical YFC source registry.

The generated document is a deployment input, not a second source of truth.  It
contains the SHA-256 of ``backend/fitminiapp_api/resources/news_sources.json`` so
the VM bundle can be tied back to the exact YFC definitions that produced it.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SCHEMA_VERSION = "hermes-source-definitions-v1"
GENERATOR_VERSION = "task403-yfc-source-registry-renderer-v1"
SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
HOST_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$")
FETCH_KINDS = frozenset({"rss", "json_feed", "html_metadata"})
SUPPORTED_TOPICS = (
    "fitness_training",
    "bodybuilding",
    "sports_bodybuilding_pharmacology",
    "peptides",
    "nutrition",
    "sports_nutrition",
    "dietary_supplements",
    "healthy_lifestyle",
)


class RegistryError(ValueError):
    """Raised when the canonical registry cannot produce a safe deployment file."""


def _read_lf_only_registry(source_registry_path: Path) -> bytes:
    """Read registry bytes only when their provenance line endings are unambiguous."""
    raw_bytes = source_registry_path.read_bytes()
    if b"\r\n" in raw_bytes:
        raise RegistryError("source_registry_crlf_not_allowed")
    if b"\r" in raw_bytes:
        raise RegistryError("source_registry_bare_cr_not_allowed")
    return raw_bytes


def _normalise_host(value: object) -> str:
    if not isinstance(value, str):
        raise RegistryError("source_host_must_be_string")
    host = value.strip().casefold().rstrip(".")
    if not host or not HOST_PATTERN.fullmatch(host) or ".." in host or "*" in host:
        raise RegistryError("source_host_invalid")
    return host


def _validate_url(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegistryError("source_url_invalid")
    parsed = urlsplit(value.strip())
    try:
        port = parsed.port
    except ValueError as exc:
        raise RegistryError("source_url_invalid") from exc
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or port not in {None, 443}
    ):
        raise RegistryError("source_url_invalid")
    _normalise_host(parsed.hostname)
    try:
        ipaddress.ip_address(parsed.hostname)
    except ValueError:
        pass
    else:
        raise RegistryError("source_url_must_use_hostname")
    if any(ord(char) < 32 for char in value):
        raise RegistryError("source_url_invalid")
    return value.strip()


def _validate_host_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 12:
        raise RegistryError("source_host_list_invalid")
    result = [_normalise_host(item) for item in value]
    if len(set(result)) != len(result):
        raise RegistryError("source_host_list_duplicate")
    return sorted(result)


def _validate_source(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RegistryError("source_definition_invalid")
    required = {"id", "name", "type", "fetch_kind", "url", "language", "enabled", "topics"}
    if not required.issubset(raw):
        raise RegistryError("source_definition_missing_field")
    source_id = raw["id"]
    if not isinstance(source_id, str) or SOURCE_ID_PATTERN.fullmatch(source_id) is None:
        raise RegistryError("source_id_invalid")
    name = raw["name"]
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 160:
        raise RegistryError("source_name_invalid")
    fetch_kind = raw["fetch_kind"]
    if fetch_kind not in FETCH_KINDS:
        raise RegistryError("source_fetch_kind_invalid")
    adapter = raw.get("adapter")
    if adapter is not None and (adapter != "pubmed_eutils" or fetch_kind != "json_feed"):
        raise RegistryError("source_adapter_invalid")
    language = raw["language"]
    if not isinstance(language, str) or not re.fullmatch(r"[a-z]{2,8}(?:-[A-Z]{2})?", language):
        raise RegistryError("source_language_invalid")
    if not isinstance(raw["enabled"], bool):
        raise RegistryError("source_enabled_invalid")
    topics = raw["topics"]
    if (
        not isinstance(topics, list)
        or not 1 <= len(topics) <= 20
        or any(
            not isinstance(topic, str) or not re.fullmatch(r"[a-z0-9_]{2,64}", topic)
            for topic in topics
        )
        or len(set(topics)) != len(topics)
    ):
        raise RegistryError("source_topics_invalid")
    if any(topic not in SUPPORTED_TOPICS for topic in topics):
        raise RegistryError("source_topic_not_supported")
    url = _validate_url(raw["url"])
    allowed_redirect_hosts = _validate_host_list(raw.get("allowed_redirect_hosts"))
    allowed_item_hosts = _validate_host_list(raw.get("allowed_item_hosts"))
    result: dict[str, Any] = {
        "id": source_id,
        "name": name.strip(),
        "type": raw["type"],
        "fetch_kind": fetch_kind,
        "url": url,
        "language": language,
        "enabled": raw["enabled"],
        "topics": list(topics),
        "authoritative": bool(raw.get("authoritative", False)),
        "allowed_redirect_hosts": allowed_redirect_hosts,
        "allowed_item_hosts": allowed_item_hosts,
    }
    if adapter is not None:
        result["adapter"] = adapter
    for key in (
        "fetch_interval_minutes",
        "freshness_policy",
        "jurisdiction",
        "trust_notes",
        "licensing_notes",
        "health_claim_limitations",
    ):
        if key in raw:
            result[key] = raw[key]
    return result


def render_registry(source_registry_path: Path) -> dict[str, Any]:
    raw_bytes = _read_lf_only_registry(source_registry_path)
    try:
        document = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegistryError("source_registry_json_invalid") from exc
    if not isinstance(document, list) or not 1 <= len(document) <= 50:
        raise RegistryError("source_registry_shape_invalid")
    sources = [_validate_source(item) for item in document]
    source_ids = [source["id"] for source in sources]
    if len(set(source_ids)) != len(source_ids):
        raise RegistryError("source_id_duplicate")
    source_hash = hashlib.sha256(raw_bytes).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": GENERATOR_VERSION,
        "source_registry": "backend/fitminiapp_api/resources/news_sources.json",
        "source_registry_sha256": source_hash,
        "definitions_version": f"yfc-news-sources:{source_hash}",
        "supported_topics": list(SUPPORTED_TOPICS),
        "sources": sources,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--source-registry",
        type=Path,
        default=root / "backend" / "fitminiapp_api" / "resources" / "news_sources.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rendered = render_registry(args.source_registry.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(rendered, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "status": "passed",
                "definitions_version": rendered["definitions_version"],
                "source_count": len(rendered["sources"]),
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())