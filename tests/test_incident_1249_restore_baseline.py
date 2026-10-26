"""Synthetic fail-closed tests for incident #1249 baseline recovery."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import incident_1249_restore_baseline as recovery


class RestoreBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        release = self.root / "releases" / recovery.BASELINE
        release.mkdir(parents=True)
        deployment_state = self.root / ".artifacts" / "operations" / "deployments"
        deployment_state.mkdir(parents=True)
        (deployment_state / "last-successful-revision").write_text(recovery.BASELINE)
        (release / ".deployment-sha").write_text(recovery.BASELINE)
        (self.root / "current").symlink_to(release, target_is_directory=True)
        for env_path in (self.root / ".env", release / ".env"):
            env_path.write_bytes(b"TEST_ONLY=true\n")
            env_path.chmod(0o600)
        self.root_patch = mock.patch.object(recovery, "ROOT", self.root)
        self.hash_patch = mock.patch.object(
            recovery, "ORIGINAL_ENV_SHA", hashlib.sha256(b"TEST_ONLY=true\n").hexdigest()
        )
        self.root_patch.start()
        self.hash_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.addCleanup(self.hash_patch.stop)

    @staticmethod
    def service_state(service: str) -> dict[str, object]:
        if service in recovery.RESTORE_SERVICES:
            return {"status": "exited", "revision": recovery.FAILED, "project": "yfc"}
        if service == "db":
            return {"status": "running", "health": "healthy", "project": "yfc"}
        return {"status": "running", "health": "unhealthy", "project": "yfc"}

    def test_preflight_rejects_env_drift_without_docker_mutation(self) -> None:
        (self.root / ".env").write_bytes(b"DRIFT=true\n")
        with (
            mock.patch.object(recovery, "call") as runner,
            self.assertRaises(recovery.RecoveryBlocked),
        ):
            recovery.preflight()
        runner.assert_not_called()

    def test_preflight_accepts_exact_synthetic_metadata(self) -> None:
        with (
            mock.patch.object(recovery, "check_image", return_value=True),
            mock.patch.object(recovery, "service", side_effect=self.service_state),
            mock.patch.object(recovery, "call", return_value="") as runner,
        ):
            env, report = recovery.preflight()
        self.assertEqual(report["preflight"], "PASS")
        self.assertEqual(report["application_mutation"], False)
        self.assertEqual(env["COMPOSE_PROJECT_NAME"], "yfc")
        self.assertEqual(env["YFC_CONSUMER_RESTART_POLICY"], "no")
        self.assertEqual(runner.call_count, 1)

    def test_restore_order_and_no_image_pull(self) -> None:
        environment = {"COMPOSE_PROJECT_NAME": "yfc"}
        report = {"preflight": "PASS", "application_mutation": False}
        with (
            mock.patch.object(recovery, "preflight", return_value=(environment, report)),
            mock.patch.object(recovery, "call", return_value="") as runner,
            mock.patch.object(recovery, "service") as state,
        ):
            state.side_effect = lambda name: {
                "status": "running",
                "health": "healthy",
                "revision": recovery.BASELINE,
            }
            restored = recovery.restore()
        self.assertEqual(restored["started_services"], ["backend", "worker", "bot"])
        self.assertTrue(restored["application_mutation"])
        self.assertFalse(restored["owner_and_public_smoke_verified"])
        self.assertEqual(runner.call_count, 3)
        for call in runner.call_args_list:
            command = call.args[0]
            self.assertIn("--pull", command)
            self.assertIn("never", command)
            self.assertIn("--no-deps", command)
            self.assertIn("--no-build", command)

    def test_restore_never_starts_when_preflight_fails(self) -> None:
        with (
            mock.patch.object(recovery, "preflight", side_effect=recovery.RecoveryBlocked("NO")),
            mock.patch.object(recovery, "call") as runner,
            self.assertRaises(recovery.RecoveryBlocked),
        ):
            recovery.restore()
        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
