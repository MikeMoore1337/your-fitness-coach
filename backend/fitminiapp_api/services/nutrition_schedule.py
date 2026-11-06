from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import and_
from sqlalchemy.orm import Session

from fitminiapp_api.models.nutrition import (
    NutritionScheduleBinding,
    NutritionTarget,
    NutritionTargetScheduleRule,
)
from fitminiapp_api.models.program import ProgramRevision, UserProgram
from fitminiapp_api.services.nutrition_program import program_cycle_identity, program_nutrition_day


def load_scheduled_nutrition_targets(
    db: Session,
    user_ids: set[int],
    start: date,
    end: date,
    *,
    preview_binding: tuple[int, UserProgram, ProgramRevision, date] | None = None,
    preview_rule: tuple[NutritionTargetScheduleRule, NutritionTarget] | None = None,
) -> dict[tuple[int, date], NutritionTarget]:
    if not user_ids or end < start:
        return {}
    bindings = (
        db.query(NutritionScheduleBinding, ProgramRevision, UserProgram)
        .join(ProgramRevision, ProgramRevision.id == NutritionScheduleBinding.program_revision_id)
        .join(
            UserProgram,
            and_(
                UserProgram.id == ProgramRevision.user_program_id,
                UserProgram.user_id == NutritionScheduleBinding.user_id,
            ),
        )
        .filter(
            NutritionScheduleBinding.user_id.in_(user_ids),
            NutritionScheduleBinding.effective_from <= end,
        )
        .order_by(
            NutritionScheduleBinding.effective_from.desc(), NutritionScheduleBinding.id.desc()
        )
        .all()
    )
    if not bindings and preview_binding is None:
        return {}
    rules = (
        db.query(NutritionTargetScheduleRule, NutritionTarget)
        .join(
            NutritionTarget,
            and_(
                NutritionTarget.id == NutritionTargetScheduleRule.target_id,
                NutritionTarget.user_id == NutritionTargetScheduleRule.user_id,
            ),
        )
        .filter(
            NutritionTargetScheduleRule.user_id.in_(user_ids),
            NutritionTargetScheduleRule.effective_from <= end,
        )
        .order_by(
            NutritionTargetScheduleRule.effective_from.desc(), NutritionTargetScheduleRule.id.desc()
        )
        .all()
    )
    program_ids = {program.id for _, _, program in bindings}
    if preview_binding is not None:
        program_ids.add(preview_binding[1].id)
    revisions_by_program: dict[int, list[ProgramRevision]] = defaultdict(list)
    for revision in (
        db.query(ProgramRevision)
        .filter(ProgramRevision.user_program_id.in_(program_ids))
        .order_by(ProgramRevision.revision_number)
    ):
        revisions_by_program[revision.user_program_id].append(revision)
    bindings_by_user: dict[int, list[tuple[date, int, ProgramRevision, UserProgram]]] = defaultdict(
        list
    )
    for binding, revision, program in bindings:
        bindings_by_user[binding.user_id].append(
            (binding.effective_from, binding.id, revision, program)
        )
    if preview_binding is not None:
        preview_user_id, program, revision, effective_from = preview_binding
        bindings_by_user[preview_user_id].append((effective_from, 2**63 - 1, revision, program))
    for items in bindings_by_user.values():
        items.sort(key=lambda row: (row[0], row[1]), reverse=True)
    rules_by_user: dict[int, list[tuple[NutritionTargetScheduleRule, NutritionTarget]]] = (
        defaultdict(list)
    )
    for rule, target in rules:
        rules_by_user[rule.user_id].append((rule, target))
    if preview_rule is not None:
        rule, target = preview_rule
        rules_by_user[rule.user_id].append((rule, target))

    result: dict[tuple[int, date], NutritionTarget] = {}
    for user_id in user_ids:
        for offset in range((end - start).days + 1):
            day = start + timedelta(days=offset)
            binding_row = next((row for row in bindings_by_user[user_id] if row[0] <= day), None)
            if binding_row is None:
                continue
            _, _, revision, program = binding_row
            revisions = revisions_by_program[program.id]
            day_type, week_type = program_nutrition_day(
                db, program, revisions, revision.revision_number, day
            )
            if day_type is None:
                continue
            source_week, boundary = program_cycle_identity(
                db, program, revisions, revision.revision_number, day
            )
            recovery = [
                (rule, target)
                for rule, target in rules_by_user[user_id]
                if rule.scope == "recovery"
                and rule.effective_from <= day
                and day_type == "rest"
                and rule.program_id == program.id
                and rule.week_type == week_type
                and rule.source_cycle_week == source_week
                and rule.cycle_boundary == boundary
                and rule.weekday == day.weekday()
            ]
            candidates = []
            resolved_day_type: str = day_type
            if recovery:
                resolved_day_type = "recovery"
                rule, target = max(recovery, key=lambda row: (row[0].effective_from, row[0].id))
                candidates.append((0, rule.effective_from, rule.id, target))
            for rule, target in rules_by_user[user_id]:
                if rule.effective_from > day:
                    continue
                if rule.scope == "future":
                    matches_day = (
                        rule.day_type == resolved_day_type
                        and (rule.day_type != "recovery" or rule.weekday == day.weekday())
                    ) or (
                        rule.day_type == "recovery"
                        and resolved_day_type == "rest"
                        and rule.weekday == day.weekday()
                    )
                    if not (
                        matches_day
                        and rule.program_id == program.id
                        and rule.week_type == week_type
                        and rule.source_cycle_week == source_week
                        and rule.cycle_boundary == boundary
                    ):
                        continue
                    candidates.append((2, rule.effective_from, rule.id, target))
                elif (
                    rule.scope == "template"
                    and rule.day_type == resolved_day_type
                    and (rule.week_type is None or rule.week_type == week_type)
                ):
                    candidates.append(
                        (
                            1 if rule.week_type is not None else 0,
                            rule.effective_from,
                            rule.id,
                            target,
                        )
                    )
            if candidates:
                result[(user_id, day)] = max(candidates, key=lambda row: row[:3])[3]
    return result
