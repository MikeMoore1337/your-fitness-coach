"""Server-side selection of the smallest safe context for conversational AI Coach."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from fitminiapp_api.ai_coach.contracts import (
    AiCoachChatContextKind,
    AiCoachConversationTurn,
    AiCoachDataClass,
    AiCoachJob,
    AiCoachPersonalTool,
    ContextRef,
)
from fitminiapp_api.ai_coach.personal_tools import (
    PersonalToolResult,
    get_bench_history_tool,
    get_nutrition_summary_tool,
    get_workout_context_tool,
    run_period_report_tool,
    run_personal_tool,
)
from fitminiapp_api.ai_coach.retrieval import retrieve_context_for_message
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.ai_coach import AiCoachContextDescriptor
from fitminiapp_api.schemas.progress import NutritionReportPeriod

_PERSONAL_PATTERN = re.compile(
    r"(?:\b(?:мой|моя|мои|мою|моего|моей|моём|моем|моими|мне|у\s+меня|для\s+меня|по\s+моим)\b|"
    r"\b(?:сегодня|сейчас|завтра|вчера|последн\w*|эт\w*\s+недел\w*)\b|"
    r"\b(?:мо\w*\s+прогресс|мо\w*\s+трениров|мо\w*\s+питан)\b|"
    r"\b(?:my|me|mine|today|now|tomorrow|yesterday|latest|recent)\b|"
    r"\b(?:my|our)\s+(?:progress|workout|training|nutrition|diet|goal|bench)\b)",
    re.IGNORECASE,
)
_REPORT_PATTERN = re.compile(
    r"(?:отч[её]т|итог|сводк|за\s+\d+\s*(?:дн|недел)|за\s+период|"
    r"\breport\b|\bsummary\b|\blast\s+\d+\s+days?\b)",
    re.IGNORECASE,
)
_TODAY_PATTERN = re.compile(
    r"(?:сегодня|сейчас|завтра|расписан|последн\w*\s+трениров|"
    r"что\s+(?:мне\s+)?(?:делать|трениров)|какую\s+трениров|"
    r"\b(?:today|now|tomorrow|schedule|scheduled|what\s+should\s+i\s+do|"
    r"which\s+workout|latest\s+workout)\b)",
    re.IGNORECASE,
)
_NUTRITION_PATTERN = re.compile(
    r"(?:питан|дневник|ккал|калори|белк|жир|углевод|вод|гидратац|кбжу|"
    r"nutrition|diet|diary|calorie|protein|fat|carb|water|hydration|macro|kcal)",
    re.IGNORECASE,
)
_PROGRESS_PATTERN = re.compile(
    r"(?:прогресс|вес|замер|нагруз|жим|подход|повтор|не\s+раст|стоит|динамик|"
    r"progress|weight|measurement|load|bench|set|rep|stalls?|dynamics)",
    re.IGNORECASE,
)
_BENCH_PATTERN = re.compile(r"(?:\bжим\w*\b|\bbench(?:-?press)?\b)", re.IGNORECASE)
_PROGRAM_PATTERN = re.compile(r"(?:программ\w*|\bprogram\w*\b)", re.IGNORECASE)
_PROFILE_GOALS_PATTERN = re.compile(
    r"(?:цел\w*|профил\w*|goal|profile|weight|вес|рост|height|"
    r"(?:калори\w*|ккал|белк\w*|жир\w*|углевод\w*|calorie\w*|protein\w*|macro\w*)"
    r".{0,64}(?:мне|моя?\w*|мои|моего|для\s+меня|my|me)|"
    r"(?:мне|моя?\w*|мои|моего|для\s+меня|my|me).{0,64}"
    r"(?:калори\w*|ккал|белк\w*|жир\w*|углевод\w*|calorie\w*|protein\w*|macro\w*))",
    re.IGNORECASE,
)
_APP_HELP_PATTERN = re.compile(
    r"(?:\b(?:yfc|telegram|ai\s+coach)\b|\b(?:приложен\w*|экран\w*|раздел\w*)\b|"
    r"как\s+(?:открыть|добавить|записать|найти|сохранить|удалить|изменить|поменять|"
    r"посмотреть|пользоваться|использовать|работать\s+с)|"
    r"где\s+(?:посмотреть|найти|открыть)|"
    r"\b(?:app|application|screen|section|telegram)\b|"
    r"\b(?:how\s+do\s+i|where\s+can\s+i)\s+(?:open|add|record|find|save|delete|"
    r"change|view|use)\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ChatContextSelection:
    data_class: AiCoachDataClass
    job: AiCoachJob
    context_id: str
    context_refs: tuple[ContextRef, ...]
    context_kind: AiCoachChatContextKind = AiCoachChatContextKind.NONE
    tool_name: AiCoachPersonalTool | None = None
    fallback_path: str | None = None
    data_sufficiency: str | None = None


def _history_text(history: tuple[AiCoachConversationTurn, ...]) -> str:
    return " ".join(turn.content for turn in history[-8:] if turn.role == "user")


def message_requires_personal_context(
    message: str,
    history: tuple[AiCoachConversationTurn, ...] = (),
) -> bool:
    if _APP_HELP_PATTERN.search(message):
        return False
    if _PERSONAL_PATTERN.search(message):
        return True
    if any(pattern.search(message) for pattern in (_NUTRITION_PATTERN, _PROGRESS_PATTERN)):
        return False
    return len(message) <= 100 and bool(_PERSONAL_PATTERN.search(_history_text(history)))


def history_without_personal_context(
    history: tuple[AiCoachConversationTurn, ...],
) -> tuple[AiCoachConversationTurn, ...]:
    """Keep generic chat history free of prior personal turns and their answers."""

    safe_history: list[AiCoachConversationTurn] = []
    skip_until_next_user = False
    for turn in history:
        if turn.role == "user":
            skip_until_next_user = bool(_PERSONAL_PATTERN.search(turn.content))
        if not skip_until_next_user:
            safe_history.append(turn)
    return tuple(safe_history)


def _generic_job(message: str) -> AiCoachJob:
    if _APP_HELP_PATTERN.search(message):
        return AiCoachJob.APP_HELP
    if _NUTRITION_PATTERN.search(message):
        return AiCoachJob.NUTRITION_KNOWLEDGE
    if _PROGRESS_PATTERN.search(message):
        return AiCoachJob.PROGRESSION_EXPLANATION
    return AiCoachJob.FITNESS_KNOWLEDGE


def _personal_route_message(
    message: str,
    history: tuple[AiCoachConversationTurn, ...],
) -> str:
    if any(
        pattern.search(message)
        for pattern in (
            _REPORT_PATTERN,
            _TODAY_PATTERN,
            _BENCH_PATTERN,
            _PROGRAM_PATTERN,
            _PROFILE_GOALS_PATTERN,
            _NUTRITION_PATTERN,
            _PROGRESS_PATTERN,
        )
    ):
        return message
    return _history_text(history)


def _personal_result(
    db: Session,
    user: User,
    message: str,
    *,
    history: tuple[AiCoachConversationTurn, ...] = (),
) -> PersonalToolResult | None:
    route_message = _personal_route_message(message, history)
    if _REPORT_PATTERN.search(route_message):
        return run_period_report_tool(
            db,
            user,
            period=NutritionReportPeriod.DAYS_30,
        )
    if _TODAY_PATTERN.search(route_message):
        focus = (
            "today"
            if re.search(
                r"сегодня|сейчас|завтра|расписан|today|now|tomorrow|schedule",
                route_message,
                re.IGNORECASE,
            )
            else "recent"
        )
        return get_workout_context_tool(db, user, focus=focus)
    if _BENCH_PATTERN.search(route_message):
        return get_bench_history_tool(db, user, period_days=30)
    if _PROGRAM_PATTERN.search(route_message):
        return get_workout_context_tool(db, user, focus="program")
    if _PROFILE_GOALS_PATTERN.search(route_message):
        return get_nutrition_summary_tool(
            db,
            user,
            30,
            include_profile_goals=True,
        )
    if _NUTRITION_PATTERN.search(route_message):
        return get_nutrition_summary_tool(
            db,
            user,
            30,
            include_profile_goals=False,
        )
    if _PROGRESS_PATTERN.search(route_message):
        return run_personal_tool(
            db,
            user,
            AiCoachPersonalTool.GET_PROGRESS_SUMMARY,
            30,
        )
    return None


def _personal_context_kind(
    message: str,
    result: PersonalToolResult,
    *,
    history: tuple[AiCoachConversationTurn, ...] = (),
) -> AiCoachChatContextKind:
    route_message = _personal_route_message(message, history)
    if _TODAY_PATTERN.search(route_message):
        return (
            AiCoachChatContextKind.ACTIVE_PROGRAM
            if re.search(
                r"сегодня|сейчас|завтра|расписан|today|now|tomorrow|schedule",
                route_message,
                re.IGNORECASE,
            )
            else AiCoachChatContextKind.RECENT_WORKOUTS
        )
    if _BENCH_PATTERN.search(route_message):
        return AiCoachChatContextKind.BENCH_HISTORY
    if _PROGRAM_PATTERN.search(route_message):
        return AiCoachChatContextKind.ACTIVE_PROGRAM
    if result.tool == AiCoachPersonalTool.GET_NUTRITION_SUMMARY:
        if _PROFILE_GOALS_PATTERN.search(route_message):
            return AiCoachChatContextKind.PROFILE_GOALS
        return AiCoachChatContextKind.NUTRITION_SUMMARY
    return AiCoachChatContextKind.RECENT_WORKOUTS


def _personal_job(tool: AiCoachPersonalTool) -> AiCoachJob:
    if tool == AiCoachPersonalTool.GET_NUTRITION_SUMMARY:
        return AiCoachJob.NUTRITION_KNOWLEDGE
    if tool == AiCoachPersonalTool.GET_PROGRESS_SUMMARY:
        return AiCoachJob.PROGRESSION_EXPLANATION
    return AiCoachJob.METRIC_EXPLANATION


def _explicit_context_result(
    db: Session,
    user: User,
    context: AiCoachContextDescriptor,
) -> PersonalToolResult:
    if context.surface == "today":
        return get_workout_context_tool(db, user, focus="today")
    if context.surface == "workout":
        workout_id = context.resource_id
        if workout_id is None:
            raise ValueError("workout context requires a resource")
        return get_workout_context_tool(
            db,
            user,
            focus="workout",
            workout_id=workout_id,
        )
    if context.surface == "nutrition":
        period_days = context.period_days
        if period_days is None:
            raise ValueError("nutrition context requires a period")
        return get_nutrition_summary_tool(
            db,
            user,
            period_days,
            include_profile_goals=False,
        )
    if context.surface == "progress":
        period_days = context.period_days
        if period_days is None:
            raise ValueError("progress context requires a period")
        return run_personal_tool(
            db,
            user,
            AiCoachPersonalTool.GET_PROGRESS_SUMMARY,
            period_days,
        )
    return get_workout_context_tool(db, user, focus="program")


def _explicit_context_kind(context: AiCoachContextDescriptor) -> AiCoachChatContextKind:
    if context.surface == "nutrition":
        return AiCoachChatContextKind.NUTRITION_SUMMARY
    if context.surface == "program":
        return AiCoachChatContextKind.ACTIVE_PROGRAM
    if context.surface == "today":
        return AiCoachChatContextKind.ACTIVE_PROGRAM
    return AiCoachChatContextKind.RECENT_WORKOUTS


def select_chat_context(
    db: Session,
    user: User,
    *,
    message: str,
    history: tuple[AiCoachConversationTurn, ...] = (),
    context: AiCoachContextDescriptor | None = None,
) -> ChatContextSelection:
    """Choose public or current-user read-only context without exposing raw records."""

    if context is not None:
        result = _explicit_context_result(db, user, context)
        return ChatContextSelection(
            data_class=AiCoachDataClass.PERSONALIZED,
            job=_personal_job(result.tool),
            context_id=f"personal:context:{context.surface}",
            context_refs=result.context_refs,
            context_kind=_explicit_context_kind(context),
            tool_name=result.tool,
            fallback_path=result.fallback_path,
            data_sufficiency=result.data_sufficiency,
        )

    if message_requires_personal_context(message, history):
        personal_result = _personal_result(db, user, message, history=history)
        if personal_result is None:
            return ChatContextSelection(
                data_class=AiCoachDataClass.PERSONALIZED,
                job=AiCoachJob.METRIC_EXPLANATION,
                context_id="personal:none",
                context_refs=(),
                context_kind=AiCoachChatContextKind.NONE,
            )
        return ChatContextSelection(
            data_class=AiCoachDataClass.PERSONALIZED,
            job=_personal_job(personal_result.tool),
            context_id=f"personal:{personal_result.tool.value}",
            context_refs=personal_result.context_refs,
            context_kind=_personal_context_kind(message, personal_result, history=history),
            tool_name=personal_result.tool,
            fallback_path=personal_result.fallback_path,
            data_sufficiency=personal_result.data_sufficiency,
        )

    job = _generic_job(message)
    context_refs = retrieve_context_for_message(db, message=message, job=job)
    return ChatContextSelection(
        data_class=AiCoachDataClass.GENERIC,
        job=job,
        context_id="public:ranked",
        context_refs=context_refs,
        # Public material is an optional enhancement for general chat, not a new
        # personalization scope. Keep the explicit selector value NONE for that path.
        context_kind=(
            AiCoachChatContextKind.APP_CAPABILITIES
            if job == AiCoachJob.APP_HELP
            else AiCoachChatContextKind.NONE
        ),
    )


__all__ = [
    "ChatContextSelection",
    "history_without_personal_context",
    "message_requires_personal_context",
    "select_chat_context",
]
