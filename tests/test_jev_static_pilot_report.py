"""Deterministic acceptance and negative cases for optional upstream static pilot."""
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "jev_static_pilot_report.py"
spec = importlib.util.spec_from_file_location("jev_static_pilot_report_1212", SCRIPT)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def sample(full=False, selected=2, discovered=10, changed=1, requests=0):
    return {"fullSuite": full, "selected": [{"path": f"x{i}.test.ts"} for i in range(selected)],
            "testsDiscovered": discovered, "changedFiles": changed,
            "jevRequests": requests, "selectionMs": 1.5}


class StaticPilotTests(unittest.TestCase):
    def test_positive_only_static_discovery_plausible(self):
        cases = {name: sample(full=full, selected=10 if full else 2)
                 for name, full in report.CASES.items()}
        out = report.evaluate(cases)
        self.assertEqual(out["verdict"], "STATIC_DISCOVERY_PLAUSIBLE_NOT_ADOPTED")
        self.assertEqual(out["runtime_test_recall"], "NOT_MEASURED")

    def test_missing_source_tests_is_no_go(self):
        cases = {name: sample(full=full, selected=10 if full else 0)
                 for name, full in report.CASES.items()}
        self.assertEqual(report.evaluate(cases)["verdict"], "NO_GO")

    def test_shared_config_without_full_fallback_is_no_go(self):
        cases = {name: sample(full=False, selected=2)
                 for name in report.CASES}
        result = report.evaluate(cases)
        self.assertIn("tsconfig: MISSED_FULL_SUITE_FALLBACK", result["findings"])

    def test_missing_case_invalid_diff_and_api_are_no_go(self):
        cases = {"shared-module": sample(changed=0, requests=1)}
        result = report.evaluate(cases)
        self.assertEqual(result["verdict"], "NO_GO")
        self.assertIn("shared-module: INVALID_DIFF_SCOPE", result["findings"])
        self.assertIn("shared-module: API_MODE_NOT_ALLOWED", result["findings"])
        self.assertIn("workout-ui: MISSING_RESULT", result["findings"])


if __name__ == "__main__":
    unittest.main()
