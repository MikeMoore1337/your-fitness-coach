from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.news import WebArticle
from fitminiapp_api.schemas.articles import WebArticleCard, WebArticleResponse
from fitminiapp_api.schemas.public import (
    PublicExerciseDetail,
    PublicExerciseSummary,
    PublicProgramResponse,
)
from fitminiapp_api.seo import NOINDEX_ROBOTS
from fitminiapp_api.services.public_exercises import public_exercise, public_exercises
from fitminiapp_api.services.public_programs import public_program
from fitminiapp_api.services.web_articles import (
    article_card,
    article_public_response,
    published_articles,
)

router = APIRouter()


@router.get("/public/config")
def public_config() -> dict[str, str | bool | list[str]]:
    return {
        "app_env": settings.app_env,
        "enable_dev_auth": settings.enable_dev_auth,
        "enable_web_auth": settings.enable_web_auth,
        "enable_email_auth": settings.enable_email_auth,
        "telegram_bot_username": settings.telegram_bot_username,
        "oauth_providers": settings.oauth_provider_names if settings.enable_web_auth else [],
    }


@router.get("/public/exercises", response_model=list[PublicExerciseSummary])
def get_public_exercises() -> tuple[dict[str, object], ...]:
    return public_exercises()


@router.get("/public/exercises/{slug}", response_model=PublicExerciseDetail)
def get_public_exercise(slug: str) -> dict[str, object]:
    exercise = public_exercise(slug)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Упражнение не опубликовано")
    return exercise


@router.get("/public/programs/{slug}", response_model=PublicProgramResponse)
def get_public_program(slug: str) -> dict[str, object]:
    program = public_program(slug)
    if program is None:
        raise HTTPException(
            status_code=404,
            detail="Программа не опубликована",
            headers={"X-Robots-Tag": NOINDEX_ROBOTS},
        )
    return program


@router.get("/public/articles", response_model=list[WebArticleCard])
def get_public_articles(db: Session = Depends(get_db)) -> list[WebArticleCard]:
    return [article_card(article) for article in published_articles(db)]


@router.get("/public/articles/{slug}", response_model=WebArticleResponse)
def get_public_article(slug: str, db: Session = Depends(get_db)) -> WebArticleResponse:
    article = db.query(WebArticle).filter(WebArticle.slug == slug).one_or_none()
    if article is None:
        raise HTTPException(
            status_code=404,
            detail="Статья не опубликована",
            headers={"X-Robots-Tag": NOINDEX_ROBOTS},
        )
    if article.status in {"archived", "retracted"}:
        raise HTTPException(
            status_code=410,
            detail="Статья снята с публикации",
            headers={"X-Robots-Tag": NOINDEX_ROBOTS},
        )
    if article.status != "published":
        raise HTTPException(
            status_code=404,
            detail="Статья не опубликована",
            headers={"X-Robots-Tag": NOINDEX_ROBOTS},
        )
    return article_public_response(article)
