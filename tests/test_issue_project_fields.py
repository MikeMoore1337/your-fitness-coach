"""Регрессии read-only проверки Project: схема, пагинация и ложный Done."""

from __future__ import annotations

import io
import json
import subprocess
import unittest
from unittest.mock import patch

from scripts import issue_project_fields as audit


def item(
    number: int = 123,
    *,
    kind: str = "Issue",
    status: str | None = "Backlog",
    priority: str | None = "P2",
    area: str | None = "Nutrition",
    effort: str | None = None,
    release: str | None = None,
    state: str = "OPEN",
    reason: str | None = None,
    title: str = "Задача",
    archived: bool = False,
    labels: list[str] | None = None,
    children: int = 0,
    repo: str = audit.REPOSITORY,
) -> dict:
    values = {"Status": status, "Priority": priority, "Area": area, "Effort": effort}
    fields = [
        {"name": value, "field": {"name": name}}
        for name, value in values.items()
        if value is not None
    ]
    if release is not None:
        fields.append({"text": release, "field": {"name": "Release"}})
    return {
        "isArchived": archived,
        "content": {
            "__typename": kind,
            "number": number,
            "state": state,
            "stateReason": reason,
            "title": title,
            "repository": {"nameWithOwner": repo},
            "subIssues": {"totalCount": children},
            "labels": {"nodes": [{"name": label} for label in labels or []]},
        },
        "fieldValues": {"nodes": fields},
    }


def project_page(nodes: list, *, more: bool = False, cursor: str | None = None) -> dict:
    return {
        "data": {
            "node": {
                "id": audit.PROJECT_ID,
                "title": "Your Fitness Coach - Delivery Board",
                "owner": {"login": "MikeMoore1337"},
                "items": {
                    "nodes": nodes,
                    "pageInfo": {"hasNextPage": more, "endCursor": cursor},
                },
            }
        }
    }


class DeliveryProjectTests(unittest.TestCase):
    def test_new_schema_needs_no_effort_or_duplicate_area_label(self) -> None:
        self.assertEqual(audit.inspect_items([item()], strict=True), ([], 1))

    def test_empty_release_is_allowed(self) -> None:
        self.assertEqual(audit.inspect_items([item(release="")], strict=True), ([], 1))

    def test_missing_priority_area_warn_and_strict_fails(self) -> None:
        target = item(priority=None, area=None)
        findings, _ = audit.inspect_items([target])
        self.assertEqual(len(findings), 2)
        self.assertEqual({finding.severity for finding in findings}, {"warning"})
        strict, _ = audit.inspect_items([target], strict=True)
        self.assertEqual({finding.severity for finding in strict}, {"error"})

    def test_ready_requires_area(self) -> None:
        findings, _ = audit.inspect_items([item(status="Ready", area=None)])
        self.assertEqual(
            findings, [audit.Finding(123, "error", "Не заполнено обязательное поле/метка Area.")]
        )

    def test_legacy_names_do_not_silently_pass_delivery_audit(self) -> None:
        findings, _ = audit.inspect_items(
            [item(status="Review", priority="P2 Medium")], strict=True
        )
        self.assertEqual(len(findings), 2)
        self.assertTrue(all(finding.severity == "error" for finding in findings))

    def test_legacy_mode_is_explicit_and_preserves_old_effort_contract(self) -> None:
        valid = item(priority="P2 Medium", effort="S", labels=["area:nutrition"])
        self.assertEqual(audit.inspect_items([valid], strict=True, schema="legacy"), ([], 1))
        missing = item(priority="P2 Medium", labels=["area:nutrition"])
        findings, _ = audit.inspect_items([missing], strict=True, schema="legacy")
        self.assertEqual(
            findings, [audit.Finding(123, "error", "Не заполнено обязательное поле/метка Effort.")]
        )
        epic = item(priority="P2 Medium", children=2, labels=["area:nutrition"])
        self.assertEqual(audit.inspect_items([epic], strict=True, schema="legacy"), ([], 1))

    def test_open_done_is_error_for_issue_and_pr(self) -> None:
        for kind in ("Issue", "PullRequest"):
            with self.subTest(kind=kind):
                findings, _ = audit.inspect_items([item(kind=kind, status="Done")])
                self.assertEqual(
                    findings,
                    [audit.Finding(123, "error", "Открытый Issue/PR имеет ложный статус Done.")],
                )

    def test_closed_issue_without_acceptance_stays_review_warning(self) -> None:
        findings, _ = audit.inspect_items([item(state="CLOSED", status="In review")])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "warning")

    def test_closed_done_preserves_historical_incomplete_metadata(self) -> None:
        self.assertEqual(
            audit.inspect_items(
                [item(state="CLOSED", status="Done", priority=None, area=None)], strict=True
            ),
            ([], 1),
        )

    def test_not_planned_is_not_successful_done(self) -> None:
        findings, _ = audit.inspect_items(
            [item(state="CLOSED", reason="NOT_PLANNED", status="Done")]
        )
        self.assertEqual(len(findings), 1)
        self.assertIn("без выполнения", findings[0].reason)
        self.assertEqual(findings[0].severity, "error")

    def test_closed_unmerged_pr_is_not_successful_done(self) -> None:
        findings, _ = audit.inspect_items([item(kind="PullRequest", state="CLOSED", status="Done")])
        self.assertEqual(len(findings), 1)
        self.assertIn("без выполнения", findings[0].reason)
        self.assertEqual(findings[0].severity, "error")

    def test_false_done_causes_nonzero_cli_exit(self) -> None:
        for kind in ("Issue", "PullRequest"):
            target = item(kind=kind, state="CLOSED", reason="NOT_PLANNED", status="Done")
            with (
                patch.object(audit, "load_project_items", return_value=[target]),
                patch.object(audit, "load_open_repository_items", return_value={}),
                patch("sys.argv", ["audit", "--strict", "--format", "json"]),
                patch("sys.stdout", new_callable=io.StringIO) as output,
            ):
                self.assertEqual(audit.main(), 1)
                self.assertGreater(json.loads(output.getvalue())["errors"], 0)

    def test_merged_pr_does_not_complete_open_parent(self) -> None:
        pr = item(number=124, kind="PullRequest", state="MERGED", status="Done")
        parent = item(status="In review")
        self.assertEqual(audit.inspect_items([parent, pr], strict=True), ([], 2))
        self.assertEqual(parent["content"]["state"], "OPEN")
        self.assertEqual(audit._selected_fields(parent)["Status"], "In review")

    def test_merged_pr_without_done_is_reported(self) -> None:
        findings, _ = audit.inspect_items(
            [item(kind="PullRequest", state="MERGED", status="In review")]
        )
        self.assertEqual(
            findings, [audit.Finding(123, "warning", "PR объединён, но статус не Done.")]
        )

    def test_hold_cannot_be_in_review(self) -> None:
        for kind in ("Issue", "PullRequest"):
            findings, _ = audit.inspect_items(
                [item(kind=kind, title="[Backlog][HOLD] Media", status="In review")]
            )
            self.assertEqual(
                findings, [audit.Finding(123, "error", "HOLD должен оставаться в Blocked.")]
            )
        pr_selection = audit.PROJECT_QUERY.split("... on PullRequest {", 1)[1].split("}", 1)[0]
        self.assertIn("title", pr_selection)

    def test_invalid_api_state_cannot_pass(self) -> None:
        for state in (None, "INVALID", "MERGED"):
            findings, _ = audit.inspect_items([item(state=state)], strict=True)
            self.assertTrue(any(finding.severity == "error" for finding in findings))

    def test_reopened_item_and_type_mismatch_require_fresh_read(self) -> None:
        for target, expected in (
            (item(state="CLOSED", status="Done"), "Issue"),
            (item(), "PullRequest"),
        ):
            findings, _ = audit.inspect_items([target], open_items={123: expected}, strict=True)
            self.assertTrue(any("повторите чтение" in finding.reason for finding in findings))

    def test_unapproved_versions_cannot_be_ready(self) -> None:
        for release in ("V13", "V14"):
            with self.subTest(release=release):
                findings, _ = audit.inspect_items([item(release=release, status="Ready")])
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0].severity, "error")

    def test_unapproved_versions_can_remain_backlog_or_blocked(self) -> None:
        for status in ("Backlog", "Blocked"):
            self.assertEqual(audit.inspect_items([item(release="V14", status=status)]), ([], 1))

    def test_archived_open_object_is_not_visible_coverage(self) -> None:
        findings, _ = audit.inspect_items([item(archived=True)])
        self.assertEqual(
            findings, [audit.Finding(123, "error", "Открытый объект скрыт в архиве Project.")]
        )

    def test_full_inventory_distinguishes_missing_issue_and_pr(self) -> None:
        findings, count = audit.inspect_items(
            [item()], open_items={123: "Issue", 124: "Issue", 125: "PullRequest"}, strict=True
        )
        self.assertEqual(count, 1)
        self.assertEqual([finding.number for finding in findings], [124, 125])
        self.assertIn("PR", findings[1].reason)
        self.assertTrue(all(finding.severity == "error" for finding in findings))

    def test_single_pr_can_be_audited(self) -> None:
        self.assertEqual(
            audit.inspect_items(
                [item(kind="PullRequest", status="In review")], number=123, strict=True
            ),
            ([], 1),
        )

    def test_missing_single_item_fails(self) -> None:
        findings, count = audit.inspect_items([item()], number=456)
        self.assertEqual(count, 0)
        self.assertEqual(findings[0].severity, "error")

    def test_duplicates_are_errors_and_repeated_audit_does_not_mutate_data(self) -> None:
        targets = [item(), item()]
        original = json.dumps(targets, sort_keys=True)
        first = audit.inspect_items(targets, strict=True)
        self.assertEqual(first, audit.inspect_items(targets, strict=True))
        self.assertEqual(
            first[0], [audit.Finding(123, "error", "Один объект присутствует в Project дважды.")]
        )
        self.assertEqual(original, json.dumps(targets, sort_keys=True))

    def test_foreign_repository_and_drafts_are_not_yfc_coverage(self) -> None:
        targets = [item(repo="other/repo"), item(kind="DraftIssue")]
        findings, count = audit.inspect_items(targets, open_items={123: "Issue"}, strict=True)
        self.assertEqual(count, 0)
        self.assertEqual(len(findings), 1)

    def test_graphql_pagination_reads_all_pages(self) -> None:
        responses = [
            project_page([item(1)], more=True, cursor="next"),
            project_page([item(2)]),
        ]
        with patch.object(audit, "_gh_json", side_effect=responses) as api:
            self.assertEqual(len(audit.load_project_items()), 2)
        self.assertEqual(
            [call.kwargs["payload"]["variables"]["after"] for call in api.call_args_list],
            [None, "next"],
        )

    def test_repeated_cursor_fails_instead_of_looping(self) -> None:
        response = project_page([item()], more=True, cursor="repeat")
        with (
            patch.object(audit, "_gh_json", return_value=response),
            self.assertRaisesRegex(RuntimeError, "пагинация"),
        ):
            audit.load_project_items()

    def test_access_error_never_becomes_pass(self) -> None:
        for response in ({"errors": [{"message": "Denied"}]}, {"data": {"node": None}}):
            with (
                self.subTest(response=response),
                patch.object(audit, "_gh_json", return_value=response),
                self.assertRaises(RuntimeError),
            ):
                audit.load_project_items()

    def test_same_id_is_accepted_after_rename_but_wrong_owner_is_rejected(self) -> None:
        for title in audit.PROJECT_TITLES:
            response = project_page([])
            response["data"]["node"]["title"] = title
            with patch.object(audit, "_gh_json", return_value=response):
                self.assertEqual(audit.load_project_items(), [])
        response["data"]["node"]["owner"]["login"] = "other"
        with (
            patch.object(audit, "_gh_json", return_value=response),
            self.assertRaises(RuntimeError),
        ):
            audit.load_project_items()

    def test_rest_inventory_paginates_both_types(self) -> None:
        first = [{"number": number} for number in range(1, 101)]
        second = [{"number": 101, "pull_request": {"url": "https://github.com/example"}}]
        with patch.object(audit, "_gh_json", side_effect=[first, second]) as api:
            inventory = audit.load_open_repository_items()
        self.assertEqual(len(inventory), 101)
        self.assertEqual(inventory[101], "PullRequest")
        self.assertIn("page=2", api.call_args_list[1].args[0])

    def test_legacy_inventory_wrapper_excludes_prs(self) -> None:
        with patch.object(
            audit, "_gh_json", return_value=[{"number": 7}, {"number": 8, "pull_request": {}}]
        ):
            self.assertEqual(audit.load_open_repository_issues(), {7})

    def test_gh_is_read_only_and_token_errors_are_not_printed(self) -> None:
        fake = subprocess.CompletedProcess([], 1, b"", b"private diagnostic")
        with (
            patch.object(audit.subprocess, "run", return_value=fake) as run,
            self.assertRaises(RuntimeError) as error,
        ):
            audit._gh_json("graphql", payload={"query": audit.PROJECT_QUERY})
        self.assertNotIn("private diagnostic", str(error.exception))
        self.assertEqual(run.call_args.args[0], ["gh", "api", "graphql", "--input", "-"])
        self.assertNotIn("mutation", audit.PROJECT_QUERY)


if __name__ == "__main__":
    unittest.main()
