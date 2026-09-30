"""Fail-closed Stage 4 AI proposals layered on the deterministic program engine."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from itsdangerous import BadSignature, BadTimeSignature, URLSafeTimedSerializer
from sqlalchemy.orm import Session, selectinload

from fitminiapp_api.ai_coach.contracts import (
    AI_COACH_ADAPTATION_POLICY_VERSION,
    AI_COACH_ADAPTATION_PROMPT_VERSION,
    AI_COACH_ADAPTATION_SCHEMA_VERSION,
    AdaptationContextRef,
    AdaptationLlmPort,
    AdaptationPatch,
    AdaptationProposal,
    AdaptationProviderRequest,
    AiCoachAdaptationProposalType,
    AiCoachDataClass,
    AiCoachDeterministicRelationship,
    AiCoachOutcome,
    AiCoachQuotaSnapshot,
    NormalizedProviderError,
    ProviderErrorCode,
)
from fitminiapp_api.ai_coach.providers import GroqDirectAdapter
from fitminiapp_api.ai_coach.quota import ai_coach_quota
from fitminiapp_api.ai_coach.safety import (
    SafetyCategory,
    classify_message,
    inspect_chat_output,
)
from fitminiapp_api.ai_coach.service import ProviderCooldown
from fitminiapp_api.core.config import settings
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.program import (
    ProgramRevision,
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.ai_coach import (
    AiCoachAdaptationGenerateRequest,
    AiCoachAdaptationProposalResponse,
    AiCoachAdaptationReviewRequest,
    AiCoachAdaptationReviewResponse,
)
from fitminiapp_api.schemas.program import CoachProgramExerciseCreate
from fitminiapp_api.services.ai_coach_consent import (
    get_ai_coach_consent,
    has_active_ai_coach_consent,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.exercise_catalog import (
    _effective_exercise_id,
    _load_visible_exercise_rows,
)
from fitminiapp_api.services.program_common import ProgramError
from fitminiapp_api.services.program_versioning import (
    get_program_for_actor,
    program_lifecycle_summary,
    upsert_future_program_exercise,
)
from fitminiapp_api.services.progression_guidance import build_progression_guidance
from fitminiapp_api.services.workout_metrics import workout_exercise_metric_type

logger = logging.getLogger("app.ai_coach")

_TOKEN_SALT = "ai-coach-adaptation-v1"
_TOKEN_MAX_AGE_SECONDS = 24 * 60 * 60
_UNAVAILABLE_LIMITATION = "AI Coach adaptation сейчас недоступен; детерминированные функции программы продолжают работать."
_SAFETY_LIMITATION = "Запрос не прошёл безопасную проверку и не был передан провайдеру."
_INVALID_LIMITATION = "Предложение не прошло проверку формата или допустимого изменения."
_STALE_LIMITATION = "Предложение устарело после изменения программы. Сформируйте его заново."


class AdaptationError(ProgramError):
    """A safe domain failure for proposal generation or review."""


@dataclass(frozen=True)
class _Target:
    actor_role: str
    owner: User
    program: UserProgram
    revision: ProgramRevision
    workout: UserWorkout
    exercise: UserWorkoutExercise
    block_id: int | None
    progression: dict[str, Any]
    context_refs: tuple[AdaptationContextRef, ...]
    evidence_ids: frozenset[str]
    candidate_ids: dict[str, int]


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=_TOKEN_SALT)


def _canonical_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _runtime_available() -> bool:
    return bool(
        settings.ai_coach_adaptation_enabled
        and not settings.ai_coach_adaptation_kill_switch
        and settings.ai_coach_enabled
        and not settings.ai_coach_kill_switch
        and settings.ai_coach_provider == "groq"
        and settings.groq_api_key.get_secret_value().strip()
        and settings.ai_coach_cost_policy == "free_only"
        and settings.ai_coach_cost_class == "free"
        and settings.ai_coach_data_policy == "verified_generic_only"
        and settings.ai_coach_structured_output
    )


def _quota_snapshot(db: Session, user_id: int) -> AiCoachQuotaSnapshot:
    snapshot = ai_coach_quota.snapshot(db, user_id=user_id)
    db.commit()
    return snapshot


def _response(
    *,
    outcome: AiCoachOutcome,
    request_id: str | None,
    limitations: tuple[str, ...] = (),
    safety_category: SafetyCategory = SafetyCategory.CLEAR,
    quota: AiCoachQuotaSnapshot | None = None,
    proposal: AdaptationProposal | None = None,
    proposal_token: str | None = None,
) -> AiCoachAdaptationProposalResponse:
    return AiCoachAdaptationProposalResponse(
        outcome=outcome,
        proposal=proposal,
        proposal_token=proposal_token,
        limitations=limitations,
        safety_category=safety_category.value,
        request_id=request_id,
        quota=quota,
    )


def _find_revision(db: Session, program: UserProgram) -> ProgramRevision:
    revision = (
        db.query(ProgramRevision)
        .filter(
            ProgramRevision.user_program_id == program.id,
            ProgramRevision.revision_number == program.current_revision_number,
        )
        .one_or_none()
    )
    if revision is None:
        raise AdaptationError("Program revision is unavailable")
    return revision


def _target_workout(
    db: Session,
    program: UserProgram,
    payload: AiCoachAdaptationGenerateRequest,
) -> UserWorkout:
    query = (
        db.query(UserWorkout)
        .options(
            selectinload(UserWorkout.exercises).joinedload(UserWorkoutExercise.exercise),
            selectinload(UserWorkout.exercises).selectinload(UserWorkoutExercise.sets),
        )
        .filter(UserWorkout.user_program_id == program.id)
    )
    if payload.target_workout_id is not None:
        workout = query.filter(UserWorkout.id == payload.target_workout_id).one_or_none()
    else:
        workout = (
            query.filter(UserWorkout.status == "planned")
            .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
            .first()
        )
    if workout is None or workout.status not in {"planned", "in_progress"}:
        raise AdaptationError("No upcoming planned workout for adaptation")
    return workout


def _target_exercise(
    workout: UserWorkout,
    target_exercise_id: int | None,
) -> UserWorkoutExercise:
    if not workout.exercises:
        raise AdaptationError("Target workout has no exercises")
    if target_exercise_id is None:
        return sorted(workout.exercises, key=lambda row: (row.sort_order, row.id))[0]
    exercise = next((row for row in workout.exercises if row.id == target_exercise_id), None)
    if exercise is None:
        exercise = next(
            (row for row in workout.exercises if row.exercise_id == target_exercise_id), None
        )
    if exercise is None:
        raise AdaptationError("Target exercise is not available")
    return exercise


def _progression_context(
    db: Session,
    owner: User,
    workout: UserWorkout,
    exercise: UserWorkoutExercise,
) -> dict[str, Any]:
    try:
        guidance = build_progression_guidance(db, owner, workout).get(exercise.id)
    except ProgramError, ValueError, TypeError:
        return {"outcome": "insufficient_data", "reason_keys": []}
    if not isinstance(guidance, dict):
        return {"outcome": "insufficient_data", "reason_keys": []}
    result = guidance.get("result") if isinstance(guidance.get("result"), dict) else guidance
    evidence = result.get("evidence") if isinstance(result, dict) else None
    return {
        "outcome": result.get("outcome", "insufficient_data")
        if isinstance(result, dict)
        else "insufficient_data",
        "eligibility_status": result.get("eligibility_status")
        if isinstance(result, dict)
        else None,
        "reason_keys": tuple(
            str(item)
            for item in (evidence.get("reason_keys", []) if isinstance(evidence, dict) else [])
            if isinstance(item, str)
        )[:8],
    }


def _context_for_target(
    db: Session,
    actor: User,
    program: UserProgram,
    actor_role: str,
    revision: ProgramRevision,
    workout: UserWorkout,
    exercise: UserWorkoutExercise,
) -> tuple[
    tuple[AdaptationContextRef, ...], frozenset[str], dict[str, int], int | None, dict[str, Any]
]:
    progression = _progression_context(
        db, db.query(User).filter(User.id == program.user_id).one(), workout, exercise
    )
    lifecycle = program_lifecycle_summary(db, actor, program.id)
    current_block = lifecycle.get("current_block")
    block_id = current_block.get("id") if isinstance(current_block, dict) else None
    visible = _load_visible_exercise_rows(
        db, db.query(User).filter(User.id == program.user_id).one()
    )
    if actor_role == "trainer":
        visible = [row for row in visible if row.created_by_user_id is None]
    candidate_ids: dict[str, int] = {}
    candidate_lines: list[str] = []
    current_metric = workout_exercise_metric_type(exercise)
    for row in visible:
        effective_id = _effective_exercise_id(row)
        if effective_id == exercise.exercise_id or row.metric_type != current_metric:
            continue
        ref_id = f"candidate:{len(candidate_ids)}"
        candidate_ids[ref_id] = effective_id
        candidate_lines.append(
            f"{ref_id}: title={row.title}; metric={row.metric_type}; equipment={row.equipment or 'none'}"
        )
        if len(candidate_ids) >= 8:
            break

    evidence_ids = frozenset({"evidence:progression", "evidence:revision"})
    prescription_mode = "structured" if exercise.prescription else "flat"
    context_refs = (
        AdaptationContextRef(
            ref_id="program:current",
            kind="program",
            content=(
                f"status={program.status}; active={program.is_active}; duration_weeks={program.duration_weeks}; "
                f"current_revision_number={program.current_revision_number}; actor_role={actor_role}"
            ),
        ),
        AdaptationContextRef(
            ref_id="revision:current",
            kind="revision",
            content=(
                f"revision_number={revision.revision_number}; change_kind={revision.change_kind}; "
                "only future planned workouts are mutable"
            ),
        ),
        AdaptationContextRef(
            ref_id="workout:target",
            kind="workout",
            content=(
                f"scheduled_date={workout.scheduled_date.isoformat()}; day_number={workout.day_number}; "
                f"week_number={workout.week_number}; status={workout.status}"
            ),
        ),
        AdaptationContextRef(
            ref_id="exercise:target",
            kind="exercise",
            content=(
                f"title={exercise.exercise.title if exercise.exercise else 'known exercise'}; "
                f"metric={current_metric}; sets={exercise.prescribed_sets}; reps={exercise.prescribed_reps}; "
                f"rest_seconds={exercise.rest_seconds}; prescription_mode={prescription_mode}"
            ),
        ),
        AdaptationContextRef(
            ref_id="evidence:progression",
            kind="evidence",
            content=(
                f"outcome={progression['outcome']}; eligibility={progression.get('eligibility_status')}; "
                f"reason_keys={','.join(progression['reason_keys']) or 'none'}"
            ),
        ),
        AdaptationContextRef(
            ref_id="evidence:revision",
            kind="evidence",
            content="current revision and target exercise were resolved by the server",
        ),
        AdaptationContextRef(
            ref_id="candidates:approved",
            kind="candidates",
            content="\n".join(candidate_lines)
            or "No approved substitution candidate is available.",
        ),
    )
    return context_refs, evidence_ids, candidate_ids, block_id, progression


def _validate_response(
    response,
    *,
    target: _Target,
) -> None:
    if not set(response.evidence_ids).issubset(target.evidence_ids):
        raise AdaptationError("AI proposal references unknown evidence")
    patch = response.suggested_change
    expected_operation = {
        AiCoachAdaptationProposalType.EXERCISE_SUBSTITUTION: "replace_exercise",
        AiCoachAdaptationProposalType.VOLUME_OR_FREQUENCY_ADJUSTMENT: "update_prescription",
    }.get(response.proposal_type, "explanation_only")
    if patch.operation != expected_operation:
        raise AdaptationError("AI proposal operation is not allowed for its proposal type")
    if patch.effective_scope != "next_workout":
        raise AdaptationError("AI proposal scope is not supported")
    if response.proposal_type == AiCoachAdaptationProposalType.EXERCISE_SUBSTITUTION:
        if response.target_exercise_ref != "exercise:target":
            raise AdaptationError("Exercise substitution requires a target exercise")
        if patch.replacement_candidate_ref not in target.candidate_ids:
            raise AdaptationError("AI proposal references an unknown exercise candidate")
        if target.exercise.source_template_exercise_id is None:
            raise AdaptationError("Exercise substitution target has no stable template identity")
    elif response.proposal_type == AiCoachAdaptationProposalType.VOLUME_OR_FREQUENCY_ADJUSTMENT:
        if response.target_exercise_ref != "exercise:target":
            raise AdaptationError("Prescription adjustment requires a target exercise")
        if (
            workout_exercise_metric_type(target.exercise) != "strength"
            or target.exercise.prescription
        ):
            raise AdaptationError("Only simple strength prescriptions can be adjusted")
        if target.progression.get("outcome") in {"insufficient_data", "review"}:
            raise AdaptationError("Prescription adjustment lacks sufficient deterministic evidence")
    elif (
        response.target_exercise_ref is not None
        and response.target_exercise_ref != "exercise:target"
    ):
        raise AdaptationError("AI proposal references an unknown target exercise")


def _proposal_token_payload(
    proposal: AdaptationProposal, target: _Target, candidate_id: int | None
) -> dict[str, object]:
    return {
        "version": 1,
        "proposal_id": proposal.proposal_id,
        "actor_user_id": target.owner.id
        if target.actor_role == "self"
        else target.program.assigned_by_user_id,
        "target_user_id": target.program.user_id,
        "program_id": target.program.id,
        "revision_id": proposal.target_revision_id,
        "revision_number": proposal.target_revision_number,
        "workout_id": target.workout.id,
        "exercise_row_id": target.exercise.id,
        "exercise_id": proposal.target_exercise_id,
        "proposal_type": proposal.proposal_type.value,
        "patch": proposal.suggested_change.model_dump(mode="json"),
        "candidate_id": candidate_id,
        "evidence_ids": list(proposal.evidence_ids),
        "relationship": proposal.deterministic_rule_relationship.value,
        "explanation": proposal.explanation,
        "limitations": list(proposal.limitations),
        "target_block_id": proposal.target_block_id,
    }


def _decode_token(token: str) -> dict[str, object]:
    try:
        payload = _serializer().loads(token, max_age=_TOKEN_MAX_AGE_SECONDS)
    except (BadSignature, BadTimeSignature) as exc:
        raise AdaptationError("AI proposal token is invalid or expired") from exc
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise AdaptationError("AI proposal token is invalid")
    return payload


class AiCoachAdaptationService:
    def __init__(self, *, provider: AdaptationLlmPort | None = None) -> None:
        self.provider = provider or GroqDirectAdapter()
        self.cooldown = ProviderCooldown()

    def generate(
        self,
        *,
        db: Session,
        actor: User,
        payload: AiCoachAdaptationGenerateRequest,
        request_id: str | None,
    ) -> AiCoachAdaptationProposalResponse:
        safety = classify_message(payload.message)
        if safety not in {
            SafetyCategory.CLEAR,
            SafetyCategory.ACTION_REQUEST,
            SafetyCategory.PERSONAL_DATA,
        }:
            return _response(
                outcome=AiCoachOutcome.SAFETY_REFUSAL,
                request_id=request_id,
                safety_category=safety,
                limitations=(_SAFETY_LIMITATION,),
            )
        try:
            program, actor_role = get_program_for_actor(db, actor, payload.program_id)
            if program.current_revision_number != payload.expected_revision_number:
                raise AdaptationError("Program revision conflict")
            if not program.is_active or program.status not in {"scheduled", "active"}:
                raise AdaptationError("Assigned program is not editable")
            if not _runtime_available():
                return _response(
                    outcome=AiCoachOutcome.UNAVAILABLE,
                    request_id=request_id,
                    limitations=(_UNAVAILABLE_LIMITATION,),
                )
            if actor_role == "self":
                if not has_active_ai_coach_consent(get_ai_coach_consent(db, actor.id)):
                    return _response(
                        outcome=AiCoachOutcome.CONSENT_REQUIRED,
                        request_id=request_id,
                        limitations=(
                            "Сначала включите отдельное согласие на персональный AI Coach.",
                        ),
                    )
                if not (
                    settings.ai_coach_personal_enabled
                    and settings.ai_coach_personal_data_policy == "verified_personal_user"
                ):
                    return _response(
                        outcome=AiCoachOutcome.UNAVAILABLE,
                        request_id=request_id,
                        limitations=(_UNAVAILABLE_LIMITATION,),
                    )
            revision = _find_revision(db, program)
            workout = _target_workout(db, program, payload)
            exercise = _target_exercise(workout, payload.target_exercise_id)
            context_refs, evidence_ids, candidate_ids, block_id, progression = _context_for_target(
                db, actor, program, actor_role, revision, workout, exercise
            )
            target = _Target(
                actor_role=actor_role,
                owner=db.query(User).filter(User.id == program.user_id).one(),
                program=program,
                revision=revision,
                workout=workout,
                exercise=exercise,
                block_id=block_id,
                progression=progression,
                context_refs=context_refs,
                evidence_ids=evidence_ids,
                candidate_ids=candidate_ids,
            )
        except ProgramError as exc:
            raise AdaptationError(str(exc)) from exc

        data_class = (
            AiCoachDataClass.PERSONALIZED if actor_role == "self" else AiCoachDataClass.GENERIC
        )
        if self.cooldown.active():
            return _response(
                outcome=AiCoachOutcome.UNAVAILABLE,
                request_id=request_id,
                limitations=(_UNAVAILABLE_LIMITATION,),
                quota=_quota_snapshot(db, actor.id),
            )
        quota_decision = ai_coach_quota.reserve(
            db,
            user_id=actor.id,
            account_key=str(actor.id),
            request_key=request_id,
        )
        if not quota_decision.granted:
            return _response(
                outcome=AiCoachOutcome.RATE_LIMITED,
                request_id=request_id,
                limitations=("Лимит AI Coach исчерпан. Попробуйте позже.",),
                quota=quota_decision.user_snapshot,
            )
        reservation_active = True
        started = time.monotonic()
        error_code: str | None = None
        try:
            provider_result = self.provider.generate_adaptation(
                AdaptationProviderRequest(
                    message=payload.message,
                    data_class=data_class,
                    locale=payload.locale,
                ),
                target.context_refs,
            )
            try:
                _validate_response(provider_result.response, target=target)
                inspection = inspect_chat_output(
                    provider_result.response.explanation,
                    data_class=data_class,
                    locale=payload.locale,
                )
                if inspection.reason is not None:
                    raise AdaptationError("AI proposal explanation failed safety validation")
            except AdaptationError:
                error_code = ProviderErrorCode.INVALID_OUTPUT.value
                if reservation_active:
                    ai_coach_quota.release(db, request_key=quota_decision.request_key)
                    reservation_active = False
                db.commit()
                return _response(
                    outcome=AiCoachOutcome.INVALID_OUTPUT,
                    request_id=request_id,
                    limitations=(_INVALID_LIMITATION,),
                    quota=_quota_snapshot(db, actor.id),
                )
            if not ai_coach_quota.consume(db, request_key=quota_decision.request_key):
                reservation_active = False
                return _response(
                    outcome=AiCoachOutcome.RATE_LIMITED,
                    request_id=request_id,
                    limitations=("Квота AI Coach истекла до завершения запроса.",),
                    quota=_quota_snapshot(db, actor.id),
                )
            reservation_active = False
            response = provider_result.response
            candidate_id = target.candidate_ids.get(
                response.suggested_change.replacement_candidate_ref or ""
            )
            proposal_payload = {
                "proposal_type": response.proposal_type.value,
                "target_program_id": target.program.id,
                "target_revision_id": target.revision.id,
                "target_revision_number": target.revision.revision_number,
                "target_block_id": target.block_id,
                "target_exercise_id": target.exercise.exercise_id
                if response.target_exercise_ref is not None
                else None,
                "explanation": response.explanation,
                "suggested_change": response.suggested_change.model_dump(mode="json"),
                "evidence_ids": list(response.evidence_ids),
                "deterministic_rule_relationship": response.deterministic_rule_relationship.value,
                "limitations": list(response.limitations),
                "requires_confirmation": True,
            }
            proposal_id = _canonical_hash(proposal_payload)
            proposal = AdaptationProposal.model_validate(
                {**proposal_payload, "proposal_id": proposal_id}
            )
            token = _serializer().dumps(_proposal_token_payload(proposal, target, candidate_id))
            record_audit_event(
                db,
                actor_user_id=actor.id,
                target_user_id=program.user_id,
                action="ai_coach.adaptation_proposal_generated",
                resource_type="ai_coach_adaptation",
                resource_id=proposal_id,
                details={
                    "proposal_type": proposal.proposal_type.value,
                    "context_kinds": [ref.kind for ref in target.context_refs],
                    "evidence_count": len(proposal.evidence_ids),
                    "candidate_available": candidate_id is not None,
                    "deterministic_rule_relationship": proposal.deterministic_rule_relationship.value,
                    "requires_confirmation": True,
                    "actor_role": actor_role,
                    "data_class": data_class.value,
                    "prompt_version": AI_COACH_ADAPTATION_PROMPT_VERSION,
                    "schema_version": AI_COACH_ADAPTATION_SCHEMA_VERSION,
                    "policy_version": AI_COACH_ADAPTATION_POLICY_VERSION,
                    "explanation_sha256": hashlib.sha256(
                        proposal.explanation.encode("utf-8")
                    ).hexdigest(),
                    "limitations_count": len(proposal.limitations),
                    "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
                },
            )
            db.commit()
            return _response(
                outcome=AiCoachOutcome.ANSWER,
                request_id=request_id,
                proposal=proposal,
                proposal_token=token,
                quota=_quota_snapshot(db, actor.id),
            )
        except NormalizedProviderError as exc:
            error_code = exc.code.value
            self.cooldown.mark(exc)
            if reservation_active:
                ai_coach_quota.release(db, request_key=quota_decision.request_key)
                reservation_active = False
            db.commit()
            outcome = (
                AiCoachOutcome.INVALID_OUTPUT
                if exc.code == ProviderErrorCode.INVALID_OUTPUT
                else AiCoachOutcome.RATE_LIMITED
                if exc.code == ProviderErrorCode.RATE_LIMITED
                else AiCoachOutcome.UNAVAILABLE
            )
            return _response(
                outcome=outcome,
                request_id=request_id,
                limitations=(
                    _INVALID_LIMITATION
                    if outcome == AiCoachOutcome.INVALID_OUTPUT
                    else _UNAVAILABLE_LIMITATION,
                ),
                quota=_quota_snapshot(db, actor.id),
            )
        finally:
            if reservation_active:
                ai_coach_quota.release(db, request_key=quota_decision.request_key)
            db.commit()
            logger.info(
                "ai_coach_adaptation_generation",
                extra={
                    "request_id": request_id,
                    "actor_role": target.actor_role,
                    "proposal_type": None,
                    "prompt_version": AI_COACH_ADAPTATION_PROMPT_VERSION,
                    "schema_version": AI_COACH_ADAPTATION_SCHEMA_VERSION,
                    "policy_version": AI_COACH_ADAPTATION_POLICY_VERSION,
                    "outcome": error_code or "answer",
                    "latency_ms": max(0, round((time.monotonic() - started) * 1000)),
                },
            )

    def review(
        self,
        *,
        db: Session,
        actor: User,
        program_id: int | None,
        payload: AiCoachAdaptationReviewRequest,
    ) -> AiCoachAdaptationReviewResponse:
        token_payload = _decode_token(payload.proposal_token)
        if token_payload.get("proposal_id") != payload.proposal_id:
            raise AdaptationError("AI proposal token does not match proposal")
        token_program_id = token_payload.get("program_id")
        if not isinstance(token_program_id, int) or (
            program_id is not None and token_program_id != program_id
        ):
            raise AdaptationError("AI proposal target mismatch")
        try:
            program, _actor_role = get_program_for_actor(db, actor, token_program_id, lock=True)
        except ProgramError as exc:
            raise AdaptationError(str(exc)) from exc
        if (
            token_payload.get("program_id") != program.id
            or token_payload.get("actor_user_id") != actor.id
        ):
            raise AdaptationError("AI proposal authorization mismatch")
        if token_payload.get("target_user_id") != program.user_id:
            raise AdaptationError("AI proposal target mismatch")
        if payload.expected_revision_number != token_payload.get("revision_number"):
            raise AdaptationError("Program revision conflict")
        prior_events = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.action.in_(
                    {"ai_coach.adaptation_proposal_confirm", "ai_coach.adaptation_proposal_reject"}
                ),
                AuditEvent.resource_type == "ai_coach_adaptation",
                AuditEvent.resource_id == payload.proposal_id,
                AuditEvent.target_user_id == program.user_id,
            )
            .order_by(AuditEvent.id.desc())
            .all()
        )
        prior = prior_events[0] if prior_events else None
        if prior is not None:
            if (
                prior.actor_user_id == actor.id
                and prior.details.get("decision") == payload.decision
            ):
                result = prior.details.get("result")
                if isinstance(result, dict):
                    return AiCoachAdaptationReviewResponse(
                        outcome=AiCoachOutcome.ANSWER,
                        proposal_id=payload.proposal_id,
                        decision=payload.decision,
                        applied=bool(result.get("applied")),
                        idempotent=True,
                        current_revision_number=program.current_revision_number,
                        limitations=tuple(result.get("limitations", ())),
                        quota=_quota_snapshot(db, actor.id),
                    )
            raise AdaptationError("AI adaptation proposal already reviewed")
        if program.current_revision_number != payload.expected_revision_number:
            raise AdaptationError("Program revision conflict")
        relationship = token_payload.get("relationship")
        if relationship == AiCoachDeterministicRelationship.CONFLICTS_WITH_DETERMINISTIC_RULE.value:
            raise AdaptationError("AI proposal conflicts with deterministic rule")

        proposal_type = token_payload.get("proposal_type")
        patch = AdaptationPatch.model_validate(token_payload.get("patch"))
        target_workout_id = token_payload.get("workout_id")
        target_exercise_row_id = token_payload.get("exercise_row_id")
        workout = (
            db.query(UserWorkout)
            .options(selectinload(UserWorkout.exercises).joinedload(UserWorkoutExercise.exercise))
            .filter(UserWorkout.id == target_workout_id, UserWorkout.user_program_id == program.id)
            .with_for_update()
            .one_or_none()
        )
        if workout is None or workout.status != "planned":
            raise AdaptationError("AI proposal target workout is no longer available")
        exercise = next(
            (row for row in workout.exercises if row.id == target_exercise_row_id), None
        )
        if exercise is None:
            raise AdaptationError("AI proposal target exercise is no longer available")

        applied = False
        if payload.decision == "confirm" and patch.operation != "explanation_only":
            candidate_id = token_payload.get("candidate_id")
            if proposal_type == AiCoachAdaptationProposalType.EXERCISE_SUBSTITUTION.value:
                if (
                    not isinstance(candidate_id, int)
                    or exercise.source_template_exercise_id is None
                ):
                    raise AdaptationError("AI substitution target is no longer stable")
                if exercise.prescription:
                    raise AdaptationError("AI substitution cannot change structured prescription")
                candidate = candidate_id
                request = CoachProgramExerciseCreate(
                    expected_revision_number=payload.expected_revision_number,
                    effective_scope="next_workout",
                    exercise_id=candidate,
                    prescribed_sets=exercise.prescribed_sets,
                    prescribed_reps=exercise.prescribed_reps,
                    prescribed_duration_minutes=exercise.prescribed_duration_minutes,
                    rest_seconds=patch.rest_seconds or exercise.rest_seconds,
                    notes=exercise.notes,
                    prescription=None,
                    target_template_exercise_id=exercise.source_template_exercise_id,
                    reason="AI Coach proposal confirmed",
                )
            elif (
                proposal_type == AiCoachAdaptationProposalType.VOLUME_OR_FREQUENCY_ADJUSTMENT.value
            ):
                if workout_exercise_metric_type(exercise) != "strength" or exercise.prescription:
                    raise AdaptationError("AI prescription target is no longer simple")
                request = CoachProgramExerciseCreate(
                    expected_revision_number=payload.expected_revision_number,
                    effective_scope="next_workout",
                    exercise_id=exercise.exercise_id,
                    prescribed_sets=patch.prescribed_sets or exercise.prescribed_sets,
                    prescribed_reps=patch.prescribed_reps or exercise.prescribed_reps,
                    rest_seconds=patch.rest_seconds or exercise.rest_seconds,
                    notes=exercise.notes,
                    reason="AI Coach proposal confirmed",
                )
            else:
                raise AdaptationError("AI proposal operation is not supported")
            try:
                upsert_future_program_exercise(db, actor, program.id, request)
            except ProgramError as exc:
                raise AdaptationError(str(exc)) from exc
            applied = True

        current_program = db.query(UserProgram).filter(UserProgram.id == program.id).one()
        result = {
            "applied": applied,
            "limitations": []
            if applied or payload.decision == "reject"
            else ["Это предложение содержит только объяснение и не меняет программу."],
            "current_revision_number": current_program.current_revision_number,
        }
        record_audit_event(
            db,
            actor_user_id=actor.id,
            target_user_id=program.user_id,
            action=(
                "ai_coach.adaptation_proposal_confirm"
                if payload.decision == "confirm"
                else "ai_coach.adaptation_proposal_reject"
            ),
            resource_type="ai_coach_adaptation",
            resource_id=payload.proposal_id,
            details={
                "decision": payload.decision,
                "applied": applied,
                "idempotent": False,
                "result": result,
            },
        )
        db.commit()
        return AiCoachAdaptationReviewResponse(
            outcome=AiCoachOutcome.ANSWER,
            proposal_id=payload.proposal_id,
            decision=payload.decision,
            applied=applied,
            current_revision_number=current_program.current_revision_number,
            limitations=tuple(result["limitations"]),
            quota=_quota_snapshot(db, actor.id),
        )


ai_coach_adaptation_service = AiCoachAdaptationService()


__all__ = [
    "AdaptationError",
    "AiCoachAdaptationService",
    "ai_coach_adaptation_service",
]
