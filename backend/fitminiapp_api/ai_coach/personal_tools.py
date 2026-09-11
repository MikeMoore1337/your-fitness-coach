"""Allowlisted, current-user-only read models for the personal AI Coach route."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from fitminiapp_api.ai_coach.contracts import (
    AI_COACH_PERIOD_REPORT_INPUT_VERSION,
    AI_COACH_PERIOD_REPORT_OUTPUT_VERSION,
    AiCoachPersonalTool,
    AiCoachResponseMetadata,
    ContextCitation,
    ContextRef,
)
from fitminiapp_api.ai_coach.safety import SafetyCategory, classify_message
from fitminiapp_api.core.config import settings
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.progress import NutritionReportPeriod
from fitminiapp_api.seo import public_origin
from fitminiapp_api.services.analytics import build_training_analytics
from fitminiapp_api.services.nutrition_reports import build_nutrition_report
from fitminiapp_api.services.period_bounds import (
    PeriodBoundsError,
    progress_period_for_days,
    resolve_report_bounds,
)
from fitminiapp_api.services.progress import build_progress_summary
from fitminiapp_api.services.progress_reports import build_progress_report
from fitminiapp_api.services.report_handoffs import REPORT_HANDOFF_CONTRACT_VERSION

PERSONAL_TOOL_VERSION = "ai-coach-personal-tools-v1"
PERIOD_REPORT_TOOL_VERSION = "ai-coach-period-report-tool-v1"


class PersonalToolUnavailable(ValueError):
    """The canonical source could not produce a safe bounded result."""


class PersonalToolUnsafe(ValueError):
    """A user-controlled label contained instruction-like content."""


def _as_mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


@dataclass(frozen=True)
class PersonalToolResult:
    tool: AiCoachPersonalTool
    purpose: str
    period_start: date
    period_end: date
    data_sufficiency: str
    facts: dict[str, object]
    limitations: tuple[str, ...]
    fallback_path: str
    context_refs: tuple[ContextRef, ...]
    response_metadata: AiCoachResponseMetadata | None = None
    evidence_ids: tuple[str, ...] = ()
    reason_keys: tuple[str, ...] = ()


def _status_from_signals(value: object) -> str:
    statuses: list[str] = []
    if isinstance(value, dict):
        for child in value.values():
            if isinstance(child, dict) and child.get("status") in {
                "sufficient",
                "limited",
                "insufficient",
            }:
                statuses.append(str(child["status"]))
    if not statuses or all(status == "insufficient" for status in statuses):
        return "insufficient"
    if any(status == "insufficient" for status in statuses):
        return "limited"
    if any(status == "limited" for status in statuses):
        return "limited"
    return "sufficient"


def _compact_body(body: object) -> dict[str, object] | None:
    if not isinstance(body, dict):
        return None
    latest = body.get("latest_measurement")
    latest_compact = None
    if isinstance(latest, dict):
        latest_compact = {
            key: latest.get(key)
            for key in (
                "measured_on",
                "weight_kg",
                "chest_cm",
                "waist_cm",
                "hips_cm",
                "biceps_cm",
                "thigh_cm",
            )
        }
    trends = []
    for trend in body.get("trends", ()) if isinstance(body.get("trends"), list) else ():
        if not isinstance(trend, dict):
            continue
        trends.append(
            {
                key: trend.get(key)
                for key in (
                    "metric",
                    "first_value",
                    "latest_value",
                    "change",
                    "first_measured_on",
                    "latest_measured_on",
                    "point_count",
                    "span_days",
                    "interpretation_status",
                )
            }
        )
    return {"latest_measurement": latest_compact, "trends": trends[:6]}


def _progress_facts(summary: dict) -> tuple[dict[str, object], str]:
    training = _as_mapping(summary.get("training"))
    cardio = _as_mapping(summary.get("cardio"))
    nutrition = _as_mapping(summary.get("nutrition"))
    facts = {
        "period_days": summary.get("period_days"),
        "period_start": summary.get("period_start"),
        "period_end": summary.get("period_end"),
        "training": {
            key: training.get(key)
            for key in (
                "planned_workouts",
                "completed_workouts",
                "skipped_workouts",
                "frequency_per_week",
                "volume_kg",
                "new_personal_records",
                "last_completed_workout_on",
            )
        },
        "cardio": {
            key: cardio.get(key)
            for key in (
                "completed_sessions",
                "planned_sessions",
                "frequency_per_week",
                "duration_minutes",
                "distance_km",
                "zone_duration",
            )
        },
        "nutrition": {
            key: nutrition.get(key)
            for key in (
                "visible",
                "logged_days",
                "complete_days",
                "incomplete_days",
                "fasted_days",
                "unlogged_days",
                "adherence_evaluated_days",
                "average_calories",
                "target_calories",
                "average_protein_g",
                "target_protein_g",
                "target_effective_on",
            )
        },
        "body": _compact_body(summary.get("body")),
        "adherence": {
            key: _as_mapping(summary.get("adherence")).get(key)
            for key in ("formula_version", "overall_percent", "included_components")
        }
        if isinstance(summary.get("adherence"), dict)
        else None,
        "data_sufficiency": summary.get("data_sufficiency", {}),
    }
    return facts, _status_from_signals(summary.get("data_sufficiency"))


def _training_facts(analytics: dict) -> tuple[dict[str, object], str]:
    exercises = []
    for exercise in analytics.get("exercises", [])[:10]:
        if not isinstance(exercise, dict):
            continue
        exercises.append(
            {
                key: exercise.get(key)
                for key in (
                    "exercise_title",
                    "performed_session_count",
                    "completed_set_count",
                    "first_performed_on",
                    "last_performed_on",
                    "reps_total",
                    "reps_recorded_sets",
                    "max_external_load_kg",
                    "best_set_volume_kg",
                    "external_load_volume_kg",
                    "volume_recorded_sets",
                    "history_truncated",
                )
            }
        )

    def compact_exposure(value: object) -> list[dict[str, object]]:
        if not isinstance(value, list):
            return []
        return [
            {
                "muscle_name": item.get("muscle_name"),
                "completed_set_count": item.get("completed_set_count"),
            }
            for item in value[:20]
            if isinstance(item, dict)
        ]

    facts = {
        "period_days": analytics.get("period_days"),
        "period_start": analytics.get("period_start"),
        "period_end": analytics.get("period_end"),
        "completed_set_count": analytics.get("completed_set_count"),
        "reps_total": analytics.get("reps_total"),
        "reps_recorded_sets": analytics.get("reps_recorded_sets"),
        "external_load_volume_kg": analytics.get("external_load_volume_kg"),
        "volume_recorded_sets": analytics.get("volume_recorded_sets"),
        "exercises": exercises,
        "rir": analytics.get("rir"),
        "primary_muscle_exposure": compact_exposure(analytics.get("primary_muscle_exposure")),
        "secondary_muscle_exposure": compact_exposure(analytics.get("secondary_muscle_exposure")),
        "completed_sets_without_muscle_metadata": analytics.get(
            "completed_sets_without_muscle_metadata"
        ),
        "data_sufficiency": analytics.get("data_sufficiency", {}),
    }
    return facts, _status_from_signals(analytics.get("data_sufficiency"))


def _nutrition_facts(report: dict) -> tuple[dict[str, object], str]:
    summary = _as_mapping(report.get("summary"))
    target_changes = [
        {
            key: change.get(key)
            for key in ("effective_from", "calories", "protein_g", "fat_g", "carbs_g")
        }
        for change in report.get("target_changes", [])[:12]
        if isinstance(change, dict)
    ]
    facts = {
        "period": report.get("period"),
        "period_start": report.get("period_start"),
        "period_end": report.get("period_end"),
        "timezone": report.get("timezone"),
        "summary": summary,
        "target_changes": target_changes,
        "hydration": report.get("hydration"),
    }
    logged_value = summary.get("logged_days")
    eligible_value = summary.get("eligible_days")
    logged_days = int(logged_value) if isinstance(logged_value, (int, float)) else 0
    eligible_days = int(eligible_value) if isinstance(eligible_value, (int, float)) else 0
    if logged_days == 0:
        sufficiency = "insufficient"
    elif eligible_days and logged_days * 2 < eligible_days:
        sufficiency = "limited"
    else:
        sufficiency = "sufficient"
    return facts, sufficiency


def _context_ref(
    *,
    tool: AiCoachPersonalTool,
    title: str,
    path: str,
    period_end: date,
    facts: dict[str, object],
    limitations: tuple[str, ...],
    context_version: str = PERSONAL_TOOL_VERSION,
) -> ContextRef:
    origin = public_origin().rstrip("/")
    canonical_url = f"{origin}{path}"
    content = json.dumps(
        {
            "tool": tool.value,
            "version": context_version,
            "facts": facts,
            "limitations": limitations,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    if len(content) > settings.ai_coach_max_context_chars:
        raise PersonalToolUnavailable("personal_context_too_large")
    if classify_message(content) == SafetyCategory.PROMPT_INJECTION:
        raise PersonalToolUnsafe("personal_context_instruction_like")
    citation = ContextCitation(
        title=title,
        publisher="Your Fitness Coach",
        url=canonical_url,
        source_type="personal_tool_screen",
    )
    return ContextRef(
        ref_id=f"personal-tool:{tool.value}",
        title=title,
        category="personal_tool",
        updated_at=period_end.isoformat(),
        reviewer="Your Fitness Coach",
        canonical_url=canonical_url,
        content=content,
        citations=(citation,),
    )


def _result(
    *,
    tool: AiCoachPersonalTool,
    purpose: str,
    facts: dict[str, object],
    period_start: date,
    period_end: date,
    sufficiency: str,
    limitations: tuple[str, ...],
    fallback_path: str,
    title: str,
    screen_path: str,
    context_version: str = PERSONAL_TOOL_VERSION,
    response_metadata: AiCoachResponseMetadata | None = None,
    evidence_ids: tuple[str, ...] = (),
    reason_keys: tuple[str, ...] = (),
) -> PersonalToolResult:
    ref = _context_ref(
        tool=tool,
        title=title,
        path=screen_path,
        period_end=period_end,
        facts=facts,
        limitations=limitations,
        context_version=context_version,
    )
    return PersonalToolResult(
        tool=tool,
        purpose=purpose,
        period_start=period_start,
        period_end=period_end,
        data_sufficiency=sufficiency,
        facts=facts,
        limitations=limitations,
        fallback_path=fallback_path,
        context_refs=(ref,),
        response_metadata=response_metadata,
        evidence_ids=evidence_ids,
        reason_keys=reason_keys,
    )


def _compact_sufficiency(value: object) -> dict[str, dict[str, object]]:
    if not isinstance(value, dict):
        return {}
    compact: dict[str, dict[str, object]] = {}
    for section, signal in value.items():
        if not isinstance(signal, dict) or "status" not in signal:
            continue
        counters = signal.get("counters")
        compact[section] = {
            "status": signal.get("status"),
            "counters": counters if isinstance(counters, dict) else {},
            "reason_keys": list(_as_string_tuple(signal.get("reason_keys"))),
        }
    return compact


def _as_string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _as_mapping_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_number(value: object) -> int | float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _sufficiency_status(value: object) -> str:
    statuses = [
        signal.get("status")
        for signal in _compact_sufficiency(value).values()
        if isinstance(signal, dict)
        and signal.get("status") in {"sufficient", "limited", "insufficient"}
    ]
    if not statuses or all(status == "insufficient" for status in statuses):
        return "insufficient"
    if any(status != "sufficient" for status in statuses):
        return "limited"
    return "sufficient"


def _append_fact(
    facts: list[dict[str, object]],
    *,
    evidence_id: str,
    value: object,
    unit: str,
    source_section: str,
) -> None:
    if value is None:
        return
    facts.append(
        {
            "evidence_id": evidence_id,
            "value": value,
            "unit": unit,
            "source_section": source_section,
        }
    )


def _period_report_evidence(
    report: dict,
) -> tuple[dict[str, object], tuple[str, ...], tuple[str, ...], str]:
    period_start = str(report["period_start"])
    period_end = str(report["period_end"])
    training = _as_mapping(report.get("training"))
    cardio = _as_mapping(report.get("cardio"))
    nutrition = _as_mapping(report.get("nutrition"))
    nutrition_summary = _as_mapping(nutrition.get("summary"))
    body = _as_mapping(report.get("body"))
    adherence = _as_mapping(report.get("adherence"))
    hydration = nutrition.get("hydration")
    facts: list[dict[str, object]] = []
    _append_fact(
        facts,
        evidence_id="report.period_days",
        value=(date.fromisoformat(period_end) - date.fromisoformat(period_start)).days + 1,
        unit="days",
        source_section="report",
    )
    for key, unit in (
        ("planned_workouts", "workouts"),
        ("completed_workouts", "workouts"),
        ("skipped_workouts", "workouts"),
        ("frequency_per_week", "workouts_per_week"),
        ("completed_working_sets", "sets"),
        ("external_load_volume_kg", "kg"),
        ("volume_recorded_sets", "sets"),
        ("new_personal_records", "records"),
    ):
        _append_fact(
            facts,
            evidence_id=f"training.{key}",
            value=training.get(key),
            unit=unit,
            source_section="training",
        )
    for key, unit in (
        ("completed_sessions", "sessions"),
        ("planned_sessions", "sessions"),
        ("frequency_per_week", "sessions_per_week"),
        ("duration_minutes", "minutes"),
        ("distance_km", "km"),
    ):
        _append_fact(
            facts,
            evidence_id=f"cardio.{key}",
            value=cardio.get(key),
            unit=unit,
            source_section="cardio",
        )
    for key, unit in (
        ("logged_days", "days"),
        ("eligible_days", "days"),
        ("coverage_percent", "percent"),
        ("complete_days", "days"),
        ("incomplete_days", "days"),
        ("fasted_days", "days"),
        ("missing_days", "days"),
    ):
        _append_fact(
            facts,
            evidence_id=f"nutrition.{key}",
            value=nutrition_summary.get(key),
            unit=unit,
            source_section="nutrition",
        )
    for summary_key, evidence_key, unit in (
        ("calories", "average_calories", "kcal_per_logged_day"),
        ("protein_g", "average_protein_g", "g_per_logged_day"),
    ):
        metric = _as_mapping(nutrition_summary.get(summary_key))
        _append_fact(
            facts,
            evidence_id=f"nutrition.{evidence_key}",
            value=metric.get("average"),
            unit=unit,
            source_section="nutrition",
        )
    for key, unit in (("overall_percent", "percent"), ("formula_version", "version")):
        _append_fact(
            facts,
            evidence_id=f"adherence.{key}",
            value=adherence.get(key),
            unit=unit,
            source_section="adherence",
        )
    if isinstance(hydration, dict) and (_as_number(hydration.get("logged_days")) or 0) > 0:
        for key, unit in (
            ("average_ml", "ml_per_logged_day"),
            ("logged_days", "days"),
            ("coverage_percent", "percent"),
            ("days_meeting_goal", "days"),
            ("goal_evaluated_days", "days"),
        ):
            _append_fact(
                facts,
                evidence_id=f"hydration.{key}",
                value=hydration.get(key),
                unit=unit,
                source_section="nutrition.hydration",
            )
    latest_measurement = _as_mapping(body.get("latest_measurement"))
    for key, unit in (
        ("weight_kg", "kg"),
        ("chest_cm", "cm"),
        ("waist_cm", "cm"),
        ("hips_cm", "cm"),
        ("biceps_cm", "cm"),
        ("thigh_cm", "cm"),
    ):
        _append_fact(
            facts,
            evidence_id=f"body.latest.{key}",
            value=latest_measurement.get(key),
            unit=unit,
            source_section="body",
        )
    body_trends: list[dict[str, object]] = []
    for trend in _as_mapping_list(body.get("trends")):
        compact_trend = {
            key: trend.get(key)
            for key in (
                "metric",
                "first_value",
                "latest_value",
                "change",
                "point_count",
                "span_days",
                "interpretation_status",
            )
        }
        body_trends.append(compact_trend)
        _append_fact(
            facts,
            evidence_id=f"body.trend.{trend.get('metric', 'unknown')}",
            value=compact_trend,
            unit="measurement_trend",
            source_section="body",
        )

    sufficiency = _compact_sufficiency(report.get("data_sufficiency"))
    reason_keys = {
        reason
        for signal in sufficiency.values()
        for reason in _as_string_tuple(signal.get("reason_keys"))
    }
    missing_days = _as_number(nutrition_summary.get("missing_days"))
    incomplete_days = _as_number(nutrition_summary.get("incomplete_days"))
    if missing_days is not None and missing_days > 0:
        reason_keys.add("nutrition_missing_days")
    target_changes = [
        {
            key: change.get(key)
            for key in ("effective_from", "source", "calories", "protein_g", "fat_g", "carbs_g")
        }
        for change in _as_mapping_list(nutrition.get("target_changes"))
    ]
    if target_changes:
        reason_keys.add("nutrition_target_changed")
    if not isinstance(hydration, dict):
        reason_keys.add("hydration_unavailable")
    elif (_as_number(hydration.get("logged_days")) or 0) == 0:
        reason_keys.add("hydration_no_logged_days")
    if any(
        trend.get("interpretation_status") != "available"
        for trend in body_trends
        if isinstance(trend, dict)
    ):
        reason_keys.add("body_trend_limited")
    if not body_trends:
        reason_keys.add("body_trend_unavailable")
    reason_keys.add(f"report_version:{REPORT_HANDOFF_CONTRACT_VERSION}")

    limitations: list[str] = []
    if (missing_days or 0) or (incomplete_days or 0):
        limitations.append(
            "Пропущенные и неполные дни питания не считаются нулевыми значениями и не используются как полноценные наблюдения."
        )
    if target_changes:
        limitations.append(
            "Цели питания менялись в периоде; сравнение учитывает исторические версии целей."
        )
    if not isinstance(hydration, dict):
        limitations.append(
            "Гидратация не включена в эту сводку или не имеет доступной записи за период."
        )
    elif (_as_number(hydration.get("logged_days")) or 0) == 0:
        limitations.append("За период нет записанных значений гидратации.")
    if (
        any(
            trend.get("interpretation_status") != "available"
            for trend in body_trends
            if isinstance(trend, dict)
        )
        or not body_trends
    ):
        limitations.append("Редкие замеры тела не доказывают изменение состава тела.")
    limitations.append(
        "Сон и настроение не включены: для этой категории требуется отдельное согласие."
    )
    if not report.get("program"):
        limitations.append("За период нет доступного контекста текущей программы или блока.")
    limitations.extend(
        f"{section}: данных недостаточно для устойчивого вывода ({', '.join(_as_string_tuple(signal.get('reason_keys')))})."
        for section, signal in sufficiency.items()
        if signal.get("status") != "sufficient" and _as_string_tuple(signal.get("reason_keys"))
    )
    limitations = list(dict.fromkeys(limitations))[:8]
    evidence: dict[str, object] = {
        "report_version": REPORT_HANDOFF_CONTRACT_VERSION,
        "input_version": AI_COACH_PERIOD_REPORT_INPUT_VERSION,
        "output_version": AI_COACH_PERIOD_REPORT_OUTPUT_VERSION,
        "period": {
            "start": period_start,
            "end": period_end,
            "timezone": report.get("timezone"),
        },
        "facts": facts,
        "coverage": sufficiency,
        "historical_target_versions": target_changes,
        "canonical_reason_keys": sorted(reason_keys),
        "limitations": limitations,
        "contradictions": [],
    }
    revision_payload = {key: value for key, value in evidence.items() if key != "output_version"}
    revision = hashlib.sha256(
        json.dumps(
            revision_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    return (
        evidence,
        tuple(str(item["evidence_id"]) for item in facts),
        tuple(sorted(reason_keys)),
        revision,
    )


def run_period_report_tool(
    db: Session,
    user: User,
    *,
    period: NutritionReportPeriod,
    date_from: date | None = None,
    date_to: date | None = None,
) -> PersonalToolResult:
    allowed_periods = {
        NutritionReportPeriod.DAYS_7,
        NutritionReportPeriod.DAYS_30,
        NutritionReportPeriod.DAYS_90,
        NutritionReportPeriod.CUSTOM,
    }
    if period not in allowed_periods:
        raise PersonalToolUnavailable("period_not_allowed")
    try:
        bounds = resolve_report_bounds(user, period, date_from=date_from, date_to=date_to)
        report = build_progress_report(
            db,
            user,
            period,
            date_from=date_from,
            date_to=date_to,
        )
        evidence, evidence_ids, reason_keys, revision = _period_report_evidence(report)
        metadata = AiCoachResponseMetadata(
            report_version=REPORT_HANDOFF_CONTRACT_VERSION,
            input_version=AI_COACH_PERIOD_REPORT_INPUT_VERSION,
            output_version=AI_COACH_PERIOD_REPORT_OUTPUT_VERSION,
            report_revision=revision,
            period_start=bounds.start,
            period_end=bounds.end,
            timezone=str(report["timezone"]),
        )
        result = _result(
            tool=AiCoachPersonalTool.GET_PERIOD_REPORT_INSIGHTS,
            purpose="Объяснить фактический канонический отчёт за выбранный период.",
            facts=evidence,
            period_start=bounds.start,
            period_end=bounds.end,
            sufficiency=_sufficiency_status(report.get("data_sufficiency")),
            limitations=_as_string_tuple(evidence.get("limitations")),
            fallback_path="/progress",
            title="Канонический отчёт за период",
            screen_path="/progress",
            context_version=PERIOD_REPORT_TOOL_VERSION,
            response_metadata=metadata,
            evidence_ids=evidence_ids,
            reason_keys=reason_keys,
        )
        return result
    except PersonalToolUnavailable:
        raise
    except PeriodBoundsError:
        raise
    except (ValueError, KeyError, TypeError, AttributeError, SQLAlchemyError) as exc:
        raise PersonalToolUnavailable("canonical_report_unavailable") from exc


def get_progress_summary_tool(db: Session, user: User, period_days: int) -> PersonalToolResult:
    summary = build_progress_summary(db, user, period_days)
    facts, sufficiency = _progress_facts(summary)
    return _result(
        tool=AiCoachPersonalTool.GET_PROGRESS_SUMMARY,
        purpose="Объяснить фактическую сводку прогресса за выбранный период.",
        facts=facts,
        period_start=summary["period_start"],
        period_end=summary["period_end"],
        sufficiency=sufficiency,
        limitations=(
            "Показаны только записанные данные; пропущенный день не считается нулевым.",
            "Тренд окружностей тела интерпретируется только при достаточном числе и интервале замеров.",
        ),
        fallback_path="/progress",
        title="Сводка прогресса",
        screen_path="/progress",
    )


def get_recent_training_summary_tool(
    db: Session, user: User, period_days: int
) -> PersonalToolResult:
    analytics = build_training_analytics(
        db,
        user,
        period_days,
        exercise_history_limit=10,
    )
    facts, sufficiency = _training_facts(analytics)
    return _result(
        tool=AiCoachPersonalTool.GET_RECENT_TRAINING_SUMMARY,
        purpose="Объяснить фактический объём и наблюдения по последним тренировкам.",
        facts=facts,
        period_start=analytics["period_start"],
        period_end=analytics["period_end"],
        sufficiency=sufficiency,
        limitations=(
            "Учитываются только завершённые рабочие подходы, которые были записаны.",
            "Отсутствующие веса, повторы, RIR и мышечная разметка не восстанавливаются предположением.",
        ),
        fallback_path="/progress",
        title="Сводка тренировок",
        screen_path="/progress",
    )


def get_nutrition_summary_tool(db: Session, user: User, period_days: int) -> PersonalToolResult:
    period = progress_period_for_days(period_days)
    report = build_nutrition_report(db, user, NutritionReportPeriod(period))
    facts, sufficiency = _nutrition_facts(report)
    return _result(
        tool=AiCoachPersonalTool.GET_NUTRITION_SUMMARY,
        purpose="Объяснить фактическую сводку питания, целей и гидратации.",
        facts=facts,
        period_start=report["period_start"],
        period_end=report["period_end"],
        sufficiency=sufficiency,
        limitations=(
            "Пропущенные, неполные и fasting-дни сохраняют свой фактический статус и не превращаются в нули.",
            "Цели показаны с историей изменений; AI Coach не пересчитывает их и не назначает новые.",
        ),
        fallback_path="/nutrition",
        title="Сводка питания",
        screen_path="/nutrition",
    )


_PERSONAL_TOOL_REGISTRY: dict[
    AiCoachPersonalTool, Callable[[Session, User, int], PersonalToolResult]
] = {
    AiCoachPersonalTool.GET_PROGRESS_SUMMARY: get_progress_summary_tool,
    AiCoachPersonalTool.GET_RECENT_TRAINING_SUMMARY: get_recent_training_summary_tool,
    AiCoachPersonalTool.GET_NUTRITION_SUMMARY: get_nutrition_summary_tool,
}


def run_personal_tool(
    db: Session,
    user: User,
    tool: AiCoachPersonalTool,
    period_days: int,
) -> PersonalToolResult:
    if period_days not in {7, 30, 90}:
        raise PersonalToolUnavailable("period_not_allowed")
    handler = _PERSONAL_TOOL_REGISTRY.get(tool)
    if handler is None:
        raise PersonalToolUnavailable("tool_not_allowed")
    try:
        return handler(db, user, period_days)
    except PersonalToolUnsafe:
        raise
    except (ValueError, KeyError, TypeError, AttributeError, SQLAlchemyError) as exc:
        raise PersonalToolUnavailable("canonical_source_unavailable") from exc


__all__ = [
    "PERIOD_REPORT_TOOL_VERSION",
    "PERSONAL_TOOL_VERSION",
    "PersonalToolResult",
    "PersonalToolUnavailable",
    "PersonalToolUnsafe",
    "get_nutrition_summary_tool",
    "get_progress_summary_tool",
    "get_recent_training_summary_tool",
    "run_period_report_tool",
    "run_personal_tool",
]
