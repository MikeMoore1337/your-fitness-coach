"""Publish the exact I3 article through YFC's existing authenticated Root API.

No Hermes HMAC, GitHub secrets, shell credentials, DB writes, or CI-based bypass.
The operation is OFF by default; --publish and a transient Root access token
are both required. A sanitized local receipt is saved for reconciliation.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error, parse, request

ROOT = Path(__file__).resolve().parents[1]
ARTICLE_PATH = ROOT / "backend/tests/fixtures/i3_plant_recovery_editorial_draft.json"
RECEIPT_PATH = ROOT / ".artifacts/operations/i3-plant-recovery-publication.json"
API_ORIGIN = "https://app.your-fitness-coach.ru"
ALLOWED_HOSTS = {"app.your-fitness-coach.ru", "your-fitness-coach.ru"}
EXPECTED_SLUG = "rastitelnye-produkty-i-boleznennost-posle-trenirovki"
TOKEN_ENV = "YFC_OWNER_ACCESS_TOKEN"


class PublicationError(RuntimeError):
    """A non-secret-bearing explanation for a failed operation."""


class NoRedirects(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


def require_yfc_url(value: str) -> str:
    """A fixed allowlist prevents accidental bearer forwarding to other hosts."""
    parsed = parse.urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise PublicationError("Production origin must be an approved HTTPS YFC host")
    return f"https://{parsed.hostname}"


def load_article(path: Path = ARTICLE_PATH) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    article = json.loads(raw)
    if not isinstance(article, dict) or article.get("slug") != EXPECTED_SLUG:
        raise PublicationError("Exact I3 article fixture is required")
    if (
        article.get("risk_level") != "moderate"
        or article.get("evidence_level") != "limited"
        or article.get("domain_reviewer") is not None
    ):
        raise PublicationError("I3 evidence and reviewer status unexpectedly changed")
    matrix = article.get("claim_source_matrix")
    claims = article.get("claims")
    sources = article.get("sources")
    if (
        not isinstance(matrix, list)
        or not isinstance(claims, list)
        or not isinstance(sources, list)
    ):
        raise PublicationError("I3 claim/source matrix is missing")
    if len(matrix) != 3 or len(claims) != 3 or len(sources) != 3:
        raise PublicationError("I3 expected three claims and three sources")
    if {row.get("claim_id") for row in matrix} != {item.get("claim_id") for item in claims}:
        raise PublicationError("I3 claim mapping changed")
    if any(
        row.get("review_status") != "pending"
        or row.get("support_level") not in {"supports", "partially_supports"}
        for row in matrix
    ):
        raise PublicationError("I3 review markers changed: inspect the file before publishing")
    return article, hashlib.sha256(raw).hexdigest()


def validate_receipt(data: Any, slug: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise PublicationError("Publisher response is not a JSON object")
    if (
        data.get("article_status") != "published"
        or data.get("editorial_decision") != "root_owner_publication"
        or data.get("scientific_verification") != "not_attested"
        or data.get("slug") != slug
        or not isinstance(data.get("article_id"), str)
        or not isinstance(data.get("content_version"), int)
    ):
        raise PublicationError("Publisher did not return the expected Root publication receipt")
    canonical = data.get("canonical_url")
    if not isinstance(canonical, str):
        raise PublicationError("Publisher omitted canonical URL")
    parsed = parse.urlparse(canonical)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_HOSTS
        or parsed.path != f"/articles/{slug}"
        or parsed.query
        or parsed.fragment
    ):
        raise PublicationError("Publisher returned an unexpected canonical URL")
    return data


def post_article(origin: str, token: str, article: dict[str, Any]) -> dict[str, Any]:
    endpoint = f"{origin}/api/v1/admin/articles/publish"
    body = json.dumps(
        {
            "article": article,
            "acknowledge_unverified_evidence": True,
            "generated_with_ai": True,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    req = request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    opener = request.build_opener(NoRedirects)
    try:
        with opener.open(req, timeout=20) as response:
            return json.load(response)
    except error.HTTPError as exc:
        # Never emit server response bodies or auth headers to a terminal/Issue.
        raise PublicationError(f"YFC rejected Root publication (HTTP {exc.code})") from None
    except (error.URLError, OSError, ValueError) as exc:
        raise PublicationError(f"YFC publication transport failed: {type(exc).__name__}") from None


def verify_public_api(origin: str, slug: str) -> bool:
    endpoint = f"{origin}/api/v1/public/articles/{slug}"
    req = request.Request(endpoint, method="GET", headers={"Accept": "application/json"})
    try:
        with request.build_opener(NoRedirects).open(req, timeout=15) as response:
            published = json.load(response)
        return (
            isinstance(published, dict)
            and published.get("slug") == slug
            and published.get("evidence_level") == "limited"
            and isinstance(published.get("published_at"), str)
            and len(published.get("claim_source_matrix", [])) == 3
            and all(
                item.get("review_status") == "pending"
                for item in published.get("claim_source_matrix", [])
            )
        )
    except error.HTTPError, error.URLError, OSError, ValueError, TypeError:
        return False


def save_receipt(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    data = (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--publish", action="store_true", help="POST with authenticated Root access"
    )
    parser.add_argument("--origin", default=API_ORIGIN, help="Approved YFC HTTPS origin")
    parser.add_argument("--receipt", type=Path, default=RECEIPT_PATH)
    args = parser.parse_args(argv)
    try:
        origin = require_yfc_url(args.origin)
        article, digest = load_article()
        if not args.publish:
            print(
                json.dumps(
                    {
                        "mode": "DRY_RUN",
                        "slug": EXPECTED_SLUG,
                        "evidence": "limited",
                        "science_reviews": "pending",
                        "article_sha256": digest,
                        "target": f"{origin}/api/v1/admin/articles/publish",
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        token = os.environ.get(TOKEN_ENV, "").strip()
        if not token and sys.stdin.isatty():
            token = getpass.getpass("YFC Root token (input hidden): ").strip()
        if not token:
            raise PublicationError(
                f"Authenticated Root token missing: enter it on TTY or set {TOKEN_ENV}"
            )
        published = validate_receipt(post_article(origin, token, article), EXPECTED_SLUG)
        public_verified = verify_public_api(origin, EXPECTED_SLUG)
        record = {
            "published_at_observed_utc": datetime.now(UTC).isoformat(),
            "article_sha256": digest,
            "article_id": published["article_id"],
            "content_version": published["content_version"],
            "slug": published["slug"],
            "canonical_url": published["canonical_url"],
            "article_status": "published",
            "editorial_decision": "root_owner_publication",
            "scientific_verification": "not_attested",
            "public_api_verified": public_verified,
        }
        save_receipt(args.receipt, record)
        print(json.dumps(record, ensure_ascii=False))
        return 0 if public_verified else 4
    except (PublicationError, OSError, ValueError) as exc:
        print(f"Publication not confirmed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
