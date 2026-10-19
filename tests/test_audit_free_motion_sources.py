"""Deterministic protections for the free-motion review queue."""

import unittest

from scripts.audit_free_motion_sources import build_matrix, name_similarity


class FreeMotionAuditTests(unittest.TestCase):
    def test_similarity_is_symmetric(self):
        self.assertEqual(
            name_similarity("dumbbell-bench-press", "db-bench-press"),
            name_similarity("db-bench-press", "dumbbell-bench-press"),
        )

    def test_unverified_same_name_must_stay_review(self):
        yfc = [
            {
                "canonical_slug": f"exercise-{i}",
                "english_title": "Example",
                "equipment": "Barbell",
                "current_status": "approved",
                "semantic_status": "NO_MATCH",
                "source_slug": "",
            }
            for i in range(206)
        ]
        videos = [
            {
                "slug": f"exercise-{i}",
                "gender": "male",
                "asset_type": "video",
                "path": f"public/videos/male/exercise-{i}.mp4",
            }
            for i in range(206)
        ]
        videos += [
            {
                "slug": f"other-{i}",
                "gender": "female",
                "asset_type": "video",
                "path": f"public/videos/female/other-{i}.mp4",
            }
            for i in range(387)
        ]
        for i in range(77):
            yfc[i]["semantic_status"] = "VERIFIED_SEMANTIC"
            yfc[i]["source_slug"] = yfc[i]["canonical_slug"]
        rows, summary = build_matrix(yfc, videos)
        self.assertEqual(len(rows), 206)
        self.assertEqual(summary["source_mp4"], 593)
        self.assertEqual(summary["additional_verified_for_release"], 0)
        self.assertEqual(rows[77]["decision"], "EXACT_FILENAME_REVIEW")
        self.assertEqual(rows[77]["production_approved"], "NO")
        self.assertEqual(rows[0]["production_approved"], "YES")

    def test_wrong_source_inventory_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "206"):
            build_matrix([], [])


if __name__ == "__main__":
    unittest.main()
