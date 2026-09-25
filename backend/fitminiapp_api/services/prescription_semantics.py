from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from fitminiapp_api.schemas.program import (
    ExercisePrescriptionPlan,
    PrescriptionDurationTarget,
    PrescriptionRepTarget,
    PrescriptionSegment,
)
from fitminiapp_api.services.program_common import ProgramError

_REP_RANGE_RE = re.compile(r"^(\d+)\s*-\s*(\d+)$")
_REP_EXACT_RE = re.compile(r"^(\d+)$")
_REP_AMRAP_RE = re.compile(r"^(?:amrap|as many as possible)(?:\s*(\d+)\s*\+?)?$", re.I)


@dataclass(frozen=True)
class PrescriptionProjection:
    prescribed_sets: int
    prescribed_reps: str
    prescribed_duration_minutes: int | None
    rest_seconds: int


def parse_prescription_plan(
    value: object | None,
    *,
    metric_type: str | None = None,
) -> ExercisePrescriptionPlan | None:
    if value is None:
        return None
    plan = (
        value
        if isinstance(value, ExercisePrescriptionPlan)
        else ExercisePrescriptionPlan.model_validate(value)
    )
    if metric_type is not None and plan.metric_type != metric_type:
        raise ProgramError("Prescription metric type does not match the exercise")
    return plan


def prescription_json(
    value: object | None,
) -> dict | None:
    plan = parse_prescription_plan(value)
    return plan.model_dump(mode="json") if plan is not None else None


def _rep_target(text: str) -> PrescriptionRepTarget:
    normalized = text.strip()
    exact = _REP_EXACT_RE.fullmatch(normalized)
    if exact:
        return PrescriptionRepTarget(kind="exact", value=int(exact.group(1)))
    ranged = _REP_RANGE_RE.fullmatch(normalized)
    if ranged:
        return PrescriptionRepTarget(
            kind="range",
            min_reps=int(ranged.group(1)),
            max_reps=int(ranged.group(2)),
        )
    amrap = _REP_AMRAP_RE.fullmatch(normalized)
    if amrap:
        return PrescriptionRepTarget(
            kind="amrap",
            cap_reps=int(amrap.group(1)) if amrap.group(1) else None,
        )
    # The legacy flat value remains authoritative; an opaque string is represented
    # as an uncapped AMRAP without inventing a numeric target.
    return PrescriptionRepTarget(kind="amrap")


def legacy_prescription_plan(
    *,
    metric_type: str,
    prescribed_sets: int | None,
    prescribed_reps: str | None,
    prescribed_duration_minutes: int | None,
    rest_seconds: int,
) -> ExercisePrescriptionPlan:
    if metric_type == "cardio":
        if prescribed_duration_minutes is None:
            raise ProgramError("Cardio duration is required")
        return ExercisePrescriptionPlan(
            metric_type="cardio",
            segments=[
                PrescriptionSegment(
                    position=1,
                    role="working",
                    duration_target=PrescriptionDurationTarget(
                        kind="exact", value_minutes=prescribed_duration_minutes
                    ),
                    rest_after_seconds=0,
                )
            ],
        )
    if prescribed_sets is None or not prescribed_reps:
        raise ProgramError("Strength sets and repetitions are required")
    return ExercisePrescriptionPlan(
        metric_type="strength",
        segments=[
            PrescriptionSegment(
                position=position,
                role="working",
                rep_target=_rep_target(prescribed_reps),
                rest_after_seconds=rest_seconds,
            )
            for position in range(1, prescribed_sets + 1)
        ],
    )


def _rep_text(target: PrescriptionRepTarget) -> str:
    if target.kind == "exact":
        return str(target.value)
    if target.kind == "range":
        return f"{target.min_reps}-{target.max_reps}"
    return f"AMRAP до {target.cap_reps}" if target.cap_reps else "AMRAP"


def project_prescription(
    plan: ExercisePrescriptionPlan,
    *,
    fallback_sets: int | None = None,
    fallback_reps: str | None = None,
    fallback_duration_minutes: int | None = None,
    fallback_rest_seconds: int | None = None,
) -> PrescriptionProjection:
    if plan.metric_type == "cardio":
        duration_first = plan.segments[0].duration_target
        duration = (
            duration_first.value_minutes
            if duration_first is not None and duration_first.kind == "exact"
            else fallback_duration_minutes
        )
        if duration is None:
            raise ProgramError("Cardio prescription requires a duration projection")
        return PrescriptionProjection(
            prescribed_sets=1,
            prescribed_reps="",
            prescribed_duration_minutes=duration,
            rest_seconds=0,
        )
    rep_first = plan.segments[0].rep_target
    reps = fallback_reps or (_rep_text(rep_first) if rep_first is not None else None)
    if not reps:
        raise ProgramError("Strength prescription requires a repetition projection")
    return PrescriptionProjection(
        prescribed_sets=fallback_sets or len(plan.segments),
        prescribed_reps=reps,
        prescribed_duration_minutes=None,
        rest_seconds=(
            fallback_rest_seconds
            if fallback_rest_seconds is not None
            else plan.segments[0].rest_after_seconds
        ),
    )


def ensure_plan(
    plan: object | None,
    *,
    metric_type: str,
    prescribed_sets: int | None,
    prescribed_reps: str | None,
    prescribed_duration_minutes: int | None,
    rest_seconds: int,
) -> tuple[ExercisePrescriptionPlan, PrescriptionProjection]:
    parsed = parse_prescription_plan(plan, metric_type=metric_type)
    provided = parsed is not None
    if parsed is None:
        parsed = legacy_prescription_plan(
            metric_type=metric_type,
            prescribed_sets=prescribed_sets,
            prescribed_reps=prescribed_reps,
            prescribed_duration_minutes=prescribed_duration_minutes,
            rest_seconds=rest_seconds,
        )
    projection = project_prescription(
        parsed,
        fallback_sets=None if provided else prescribed_sets,
        fallback_reps=None if provided else prescribed_reps,
        fallback_duration_minutes=None if provided else prescribed_duration_minutes,
        fallback_rest_seconds=None if provided else rest_seconds,
    )
    return parsed, projection


def planned_segments(
    plan: ExercisePrescriptionPlan | Mapping[str, object] | None,
    *,
    metric_type: str,
    prescribed_sets: int,
    prescribed_reps: str,
    prescribed_duration_minutes: int | None,
    rest_seconds: int,
) -> list[dict]:
    parsed, _projection = ensure_plan(
        plan,
        metric_type=metric_type,
        prescribed_sets=prescribed_sets,
        prescribed_reps=prescribed_reps,
        prescribed_duration_minutes=prescribed_duration_minutes,
        rest_seconds=rest_seconds,
    )
    return [segment.model_dump(mode="json") for segment in parsed.segments]


def is_working_role(role: str | None) -> bool:
    return role in {None, "working", "top", "backoff", "activation"}


def is_pr_record_role(role: str | None) -> bool:
    return role in {None, "working", "top", "backoff"}


def compatible_for_substitution(
    source: ExercisePrescriptionPlan | Mapping[str, object] | None,
    target: ExercisePrescriptionPlan | Mapping[str, object] | None,
    *,
    source_metric: str,
    target_metric: str,
) -> tuple[bool, list[str]]:
    if source_metric != target_metric:
        return False, ["metric_type_mismatch"]
    source_plan = parse_prescription_plan(source, metric_type=source_metric)
    target_plan = parse_prescription_plan(target, metric_type=target_metric)
    if source_plan is None or target_plan is None:
        return True, ["legacy_flat_prescription"]
    if len(source_plan.segments) != len(target_plan.segments):
        return True, ["segment_count_adapted"]
    if any(segment.role == "cluster_member" for segment in source_plan.segments):
        return True, ["cluster_prescription_requires_load_reset"]
    return True, ["metric_and_segment_shape_match"]
