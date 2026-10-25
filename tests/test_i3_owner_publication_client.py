"""Offline tests for the I3 Root publication one-shot command.

Network calls are always mocked; no production POST from CI.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import publish_i3_owner_article as client  # noqa: E402


class PublishI3OwnerArticleTests(unittest.TestCase):
    def test_fixture_keeps_pending_science(self) -> None:
        article, digest = client.load_article()
        self.assertEqual(article["slug"], client.EXPECTED_SLUG)
        self.assertEqual(article["evidence_level"], "limited")
        self.assertTrue(
            all(row["review_status"] == "pending" for row in article["claim_source_matrix"])
        )
        self.assertEqual(len(digest), 64)

    def test_origin_allowlist_rejects_token_exfiltration(self) -> None:
        allowed = (
            "https://app.your-fitness-coach.ru",
            "https://your-fitness-coach.ru/",
        )
        for value in allowed:
            self.assertTrue(client.require_yfc_url(value).startswith("https://"))
        for value in (
            "https://your-fitness-coach.ru.evil.example",
            "https://evil.example",
            "http://app.your-fitness-coach.ru",
            "https://app.your-fitness-coach.ru:444",
            "https://user:pass@app.your-fitness-coach.ru",
            "https://app.your-fitness-coach.ru/unexpected",
        ):
            with self.subTest(url=value), self.assertRaises(client.PublicationError):
                client.require_yfc_url(value)

    def test_dry_run_never_calls_live_api(self) -> None:
        with patch.object(client, "post_article") as post:
            self.assertEqual(client.main([]), 0)
            post.assert_not_called()

    def test_publish_without_token_fails_closed(self) -> None:
        with (
            patch.dict(os.environ, {client.TOKEN_ENV: ""}),
            patch.object(sys.stdin, "isatty", return_value=False),
            patch.object(client, "post_article") as post,
        ):
            self.assertEqual(client.main(["--publish"]), 2)
            post.assert_not_called()

    def test_publish_saves_secret_free_receipt(self) -> None:
        article, digest = client.load_article()
        del article
        response = {
            "article_id": "a" * 32,
            "slug": client.EXPECTED_SLUG,
            "article_status": "published",
            "content_version": 1,
            "canonical_url": (f"https://your-fitness-coach.ru/articles/{client.EXPECTED_SLUG}"),
            "editorial_decision": "root_owner_publication",
            "scientific_verification": "not_attested",
        }
        with tempfile.TemporaryDirectory() as folder:
            receipt = Path(folder) / "receipt.json"
            with (
                patch.dict(os.environ, {client.TOKEN_ENV: "synthetic-test-token-DO-NOT-LOG"}),
                patch.object(client, "post_article", return_value=response) as post,
                patch.object(client, "verify_public_api", return_value=True) as verify,
            ):
                self.assertEqual(
                    client.main(["--publish", "--receipt", str(receipt)]),
                    0,
                )
                self.assertTrue(post.called)
                verify.assert_called_once()
            saved = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(saved["article_sha256"], digest)
            self.assertEqual(saved["article_status"], "published")
            self.assertTrue(saved["public_api_verified"])
            self.assertNotIn("synthetic-test-token", receipt.read_text(encoding="utf-8"))

    def test_invalid_server_claim_cannot_be_reported_published(self) -> None:
        invalid = {
            "article_id": "a" * 32,
            "slug": client.EXPECTED_SLUG,
            "article_status": "draft",
            "content_version": 1,
            "canonical_url": (f"https://your-fitness-coach.ru/articles/{client.EXPECTED_SLUG}"),
            "editorial_decision": "root_owner_publication",
            "scientific_verification": "not_attested",
        }
        with self.assertRaises(client.PublicationError):
            client.validate_receipt(invalid, client.EXPECTED_SLUG)

    def test_public_probe_failure_does_not_create_false_verification(self) -> None:
        response = {
            "article_id": "a" * 32,
            "slug": client.EXPECTED_SLUG,
            "article_status": "published",
            "content_version": 1,
            "canonical_url": (f"https://your-fitness-coach.ru/articles/{client.EXPECTED_SLUG}"),
            "editorial_decision": "root_owner_publication",
            "scientific_verification": "not_attested",
        }
        with tempfile.TemporaryDirectory() as folder:
            receipt = Path(folder) / "receipt.json"
            with (
                patch.dict(os.environ, {client.TOKEN_ENV: "synthetic-test-token"}),
                patch.object(client, "post_article", return_value=response),
                patch.object(client, "verify_public_api", return_value=False),
            ):
                self.assertEqual(client.main(["--publish", "--receipt", str(receipt)]), 4)
            saved = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertFalse(saved["public_api_verified"])
            self.assertEqual(saved["article_status"], "published")


if __name__ == "__main__":
    unittest.main()
