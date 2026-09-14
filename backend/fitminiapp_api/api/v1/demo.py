import re
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from fitminiapp_api.core.rate_limit import limiter
from fitminiapp_api.schemas.demo import (
    DemoActionRequest,
    DemoSessionCreated,
    DemoSessionCreateRequest,
    DemoSessionSnapshot,
)
from fitminiapp_api.services.demo_sessions import (
    DemoActionForbiddenError,
    DemoSessionCapacityError,
    DemoSessionExpiredError,
    DemoTransitionError,
    demo_session_store,
)

router = APIRouter()
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _demo_token(x_demo_session: Annotated[str | None, Header()] = None) -> str:
    token = (x_demo_session or "").strip()
    if not _TOKEN_PATTERN.fullmatch(token):
        raise HTTPException(status_code=401, detail="Демо-сессия недействительна")
    return token


def _snapshot_or_error(operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return operation()
    except DemoSessionExpiredError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Демо-сессия истекла. Начните новый сценарий.",
        )
    except DemoActionForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Это действие недоступно в демо-режиме.",
        )
    except DemoTransitionError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Состояние демо изменилось. Обновите сценарий и повторите действие.",
        )


@router.post("/sessions", response_model=DemoSessionCreated, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
def create_demo_session(
    request: Request,
    response: Response,
    payload: DemoSessionCreateRequest,
) -> DemoSessionCreated:
    del request
    _no_store(response)
    try:
        token, snapshot = demo_session_store.create(payload.scenario)
    except DemoSessionCapacityError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сейчас нельзя начать новую демо-сессию. Попробуйте позже.",
        )
    return DemoSessionCreated(session_token=token, **snapshot)


@router.get("/sessions/current", response_model=DemoSessionSnapshot)
@limiter.limit("120/minute")
def get_demo_session(
    request: Request,
    response: Response,
    token: str = Depends(_demo_token),
) -> DemoSessionSnapshot:
    del request
    _no_store(response)
    return DemoSessionSnapshot(**_snapshot_or_error(lambda: demo_session_store.get(token)))


@router.post("/sessions/current/actions", response_model=DemoSessionSnapshot)
@limiter.limit("120/minute")
def apply_demo_action(
    request: Request,
    response: Response,
    payload: DemoActionRequest,
    token: str = Depends(_demo_token),
) -> DemoSessionSnapshot:
    del request
    _no_store(response)
    snapshot = _snapshot_or_error(
        lambda: demo_session_store.apply_action(
            token,
            payload.action,
            payload.comment,
            payload.client_id,
        )
    )
    return DemoSessionSnapshot(**snapshot)


@router.post("/sessions/current/reset", response_model=DemoSessionSnapshot)
@limiter.limit("30/minute")
def reset_demo_session(
    request: Request,
    response: Response,
    token: str = Depends(_demo_token),
) -> DemoSessionSnapshot:
    del request
    _no_store(response)
    return DemoSessionSnapshot(**_snapshot_or_error(lambda: demo_session_store.reset(token)))
