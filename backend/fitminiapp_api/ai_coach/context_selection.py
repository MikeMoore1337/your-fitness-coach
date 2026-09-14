"""Server-side selection of the smallest safe context for conversational AI Coach."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from fitminiapp_api.ai_coach.contracts import (
    AiCoachConversationTurn,
    AiCoachDataClass,
    AiCoachJob,
    AiCoachPersonalTool,
    ContextRef,
)
from fitminiapp_api.ai_coach.personal_tools import (
    PersonalToolResult,
    get_workout_context_tool,
    run_period_report_tool,
    run_personal_tool,
)
from fitminiapp_api.ai_coach.retrieval import retrieve_context_for_message
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.progress import NutritionReportPeriod

_PERSONAL_PATTERN = re.compile(
    r"(?:\b(?:мой|моя|мои|мне|у\s+меня|для\s+меня|по\s+моим)\b|"
    r"\b(?:сегодня|сейчас|завтра|вчера|последн\w*|эт\w*\s+недел\w*)\b|"
    r"\b(?:мо\w*\s+прогресс|мо\w*\s+трениров|мо\w*\s+питан)\b)",
    re.IGNORECASE,
)
_REPORT_PATTERN = re.compile(
    r"(?:отч[её]т|итог|сводк|за\s+\d+\s*(?:дн|недел)|за\s+период)",
    re.IGNORECASE,
)
_TODAY_PATTERN = re.compile(
    r"(?:сегодня|сейчас|завтра|расписан|последн\w*\s+трениров|"
    r"что\s+(?:мне\s+)?(?:делать|трениров)|какую\s+трениров)",
    re.IGNORECASE,
)
_NUTRITION_PATTERN = re.compile(
    r"(?:питан|дневник|ккал|калори|белк|жир|углевод|вод|гидратац|кбжу)",
    re.IGNORECASE,
)
_PROGRESS_PATTERN = re.compile(
    r"(?:прогресс|вес|замер|нагруз|жим|подход|повтор|не\s+раст|стоит|динамик)",
    re.IGNORECASE,
)
_APP_HELP_PATTERN = re.compile(
    r"(?:yfc|приложен|экран|раздел|дневник|программ|расписан|telegram|"
    r"как\s+(?:открыть|добавить|записать|найти|сохранить))",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ChatContextSelection:
    data_class: AiCoachDataClass
    job: AiCoachJob
    context_id: str
    context_refs: tuple[ContextRef, ...]
    tool_name: AiCoachPersonalTool | None = None
    fallback_path: str | None = None
    data_sufficiency: str | None = None


def _history_text(history: tuple[AiCoachConversationTurn, ...]) -> str:
    return " ".join(turn.content for turn in history[-8:] if turn.role == "user")


def message_requires_personal_context(
    message: str,
    history: tuple[AiCoachConversationTurn, ...] = (),
) -> bool:
    if _PERSONAL_PATTERN.search(message):
        return True
    return len(message) <= 100 and bool(_PERSONAL_PATTERN.search(_history_text(history)))


def _generic_job(message: str) -> AiCoachJob:
    if _APP_HELP_PATTERN.search(message):
        return AiCoachJob.APP_HELP
    if _NUTRITION_PATTERN.search(message):
        return AiCoachJob.NUTRITION_KNOWLEDGE
    if _PROGRESS_PATTERN.search(message):
        return AiCoachJob.PROGRESSION_EXPLANATION
    return AiCoachJob.FITNESS_KNOWLEDGE


def _personal_result(db: Session, user: User, message: str) -> PersonalToolResult:
    if _REPORT_PATTERN.search(message):
        return run_period_report_tool(
            db,
            user,
            period=NutritionReportPeriod.DAYS_30,
        )
    if _TODAY_PATTERN.search(message):
        focus = (
            "today"
            if re.search(r"сегодня|сейчас|завтра|расписан", message, re.IGNORECASE)
            else "recent"
        )
        return get_workout_context_tool(db, user, focus=focus)
    if _NUTRITION_PATTERN.search(message):
        return run_personal_tool(
            db,
            user,
            AiCoachPersonalTool.GET_NUTRITION_SUMMARY,
            30,
        )
    if _PROGRESS_PATTERN.search(message):
        return run_personal_tool(
            db,
            user,
            AiCoachPersonalTool.GET_PROGRESS_SUMMARY,
            30,
        )
    return run_personal_tool(
        db,
        user,
        AiCoachPersonalTool.GET_RECENT_TRAINING_SUMMARY,
        30,
    )


def _personal_job(tool: AiCoachPersonalTool) -> AiCoachJob:
    if tool == AiCoachPersonalTool.GET_NUTRITION_SUMMARY:
        return AiCoachJob.NUTRITION_KNOWLEDGE
    if tool == AiCoachPersonalTool.GET_PROGRESS_SUMMARY:
        return AiCoachJob.PROGRESSION_EXPLANATION
    return AiCoachJob.METRIC_EXPLANATION


def select_chat_context(
    db: Session,
    user: User,
    *,
    message: str,
    history: tuple[AiCoachConversationTurn, ...] = (),
) -> ChatContextSelection:
    """Choose public or current-user read-only context without exposing raw records."""

    if message_requires_personal_context(message, history):
        result = _personal_result(db, user, message)
        return ChatContextSelection(
            data_class=AiCoachDataClass.PERSONALIZED,
            job=_personal_job(result.tool),
            context_id=f"personal:{result.tool.value}",
            context_refs=result.context_refs,
            tool_name=result.tool,
            fallback_path=result.fallback_path,
            data_sufficiency=result.data_sufficiency,
        )

    job = _generic_job(message)
    context_refs = retrieve_context_for_message(db, message=message, job=job)
    return ChatContextSelection(
        data_class=AiCoachDataClass.GENERIC,
        job=job,
        context_id="public:ranked",
        context_refs=context_refs,
    )


__all__ = [
    "ChatContextSelection",
    "message_requires_personal_context",
    "select_chat_context",
]
