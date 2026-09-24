from __future__ import annotations

import base64
import hashlib
import io
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import cast

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.models.news import NewsCluster, NewsDraftRevision, NewsImageRevision
from fitminiapp_api.services.news_content import editorial_content_from_metadata
from fitminiapp_api.services.news_state import transition_news_cluster

logger = logging.getLogger(__name__)

CANVAS_SIZE = (1200, 800)
BRAND_CIRCLE_BOUNDS = (760, -40, 1185, 385)
BRAND_MARK_SIZE = (220, 220)
BRAND_MARK_POSITION = (
    (BRAND_CIRCLE_BOUNDS[0] + BRAND_CIRCLE_BOUNDS[2] - BRAND_MARK_SIZE[0] + 1) // 2,
    (BRAND_CIRCLE_BOUNDS[1] + BRAND_CIRCLE_BOUNDS[3] - BRAND_MARK_SIZE[1] + 1) // 2,
)
MAX_DECODED_PIXELS = 20_000_000
MAX_PROVIDER_RESPONSE_BYTES = 13_000_000
CLOUDFLARE_IMAGES_ENDPOINT = (
    "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/"
    "@cf/black-forest-labs/flux-1-schnell"
)
PROVIDER_POLICY_CHECKED_AT = "2026-08-26"
BRAND_LABEL_POSITION = (90, 84)
RUBRIC_POSITION = (90, 155)
HEADLINE_X = 86
HEADLINE_MAX_WIDTH = 980
HEADLINE_INITIAL_FONT_SIZE = 55
HEADLINE_MIN_FONT_SIZE = 18
REVIEW_LABEL_POSITION = (90, 685)
HEADLINE_SPACING = 10


class NewsImageError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class NormalizedImage:
    data: bytes
    content_type: str
    width: int
    height: int
    sha256: str


@dataclass(frozen=True)
class GeneratedImage:
    image: NormalizedImage
    kind: str
    provider: str
    model: str
    prompt_digest: str
    safety_status: str
    latency_ms: int
    warnings: tuple[str, ...] = ()
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_microunits: int | None = None


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _brand_mark_path() -> Path | None:
    project_root = Path(__file__).resolve().parents[3]
    candidates = (
        project_root / "frontend/public/assets/brand/apple-touch-icon.png",
        Path("/app/frontend-dist/assets/brand/apple-touch-icon.png"),
    )
    return next((path for path in candidates if path.is_file()), None)


def _transparent_brand_mark(source: Image.Image) -> Image.Image:
    mark = source.convert("RGBA")
    background = cast(tuple[int, int, int, int], mark.getpixel((0, 0)))[:3]
    pixels = mark.load()
    if pixels is None:
        raise NewsImageError("brand_mark_decode_invalid")
    for y in range(mark.height):
        for x in range(mark.width):
            red, green, blue, alpha = cast(tuple[int, int, int, int], pixels[x, y])
            distance = max(
                abs(red - background[0]),
                abs(green - background[1]),
                abs(blue - background[2]),
            )
            if distance <= 3:
                converted_alpha = 0
            elif distance < 96:
                converted_alpha = round((distance - 3) * 255 / 93)
            else:
                converted_alpha = alpha
            pixels[x, y] = (red, green, blue, min(alpha, converted_alpha))
    return mark


def _headline(draft: NewsDraftRevision) -> str:
    content = editorial_content_from_metadata(
        draft.evidence_metadata,
        fallback_text=draft.draft_text,
    )
    if content is not None:
        return content.headline
    lines = draft.draft_text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("Заголовок:"):
            value = line.removeprefix("Заголовок:").strip()
            if value:
                return value[:180]
        if line.strip() == "ЗАГОЛОВОК" and index + 1 < len(lines):
            value = lines[index + 1].strip()
            if value:
                return value[:180]
    return "Редакционный материал Your Fitness Coach"


def _rubric(draft: NewsDraftRevision) -> str:
    for line in draft.draft_text.splitlines():
        if line.startswith("Рубрика:"):
            value = line.removeprefix("Рубрика:").strip()
            if value:
                return value[:48]
    return {
        "fitness_training": "Фитнес и тренировки",
        "bodybuilding": "Бодибилдинг",
        "sports_bodybuilding_pharmacology": "Спортивная фармакология",
        "peptides": "Пептиды",
        "nutrition": "Питание",
        "sports_nutrition": "Спортивное питание",
        "dietary_supplements": "БАДы и добавки",
        "healthy_lifestyle": "ЗОЖ и восстановление",
        # Historical topics remain readable for already-created immutable revisions.
        "fitness": "Фитнес и тренировки",
        "medicine_pharmacology": "Медицина и фармакология",
        "strength": "Силовые тренировки",
        "cardio_recovery": "Кардио и восстановление",
        "research": "Исследования",
        "industry_product": "Индустрия и продукты",
    }.get(str(draft.evidence_metadata.get("topic", "")), "Редакционный разбор")


def _what_happened(draft: NewsDraftRevision) -> str:
    content = editorial_content_from_metadata(
        draft.evidence_metadata,
        fallback_text=draft.draft_text,
    )
    if content is not None:
        return content.summary[:500]
    lines = draft.draft_text.splitlines()
    collected: list[str] = []
    capture = False
    for line in lines:
        stripped = line.strip()
        if stripped in {"Что произошло", "Что произошло:", "КРАТКО"} or stripped.startswith(
            "Что произошло:"
        ):
            capture = True
            remainder = stripped.removeprefix("Что произошло:").strip()
            if remainder:
                collected.append(remainder)
            continue
        if capture and (
            stripped.endswith(":") or stripped in {"ПОЧЕМУ ЭТО ВАЖНО", "ИСТОЧНИК", "──────────"}
        ):
            break
        if capture and stripped:
            collected.append(stripped)
    summary = " ".join(collected)
    return " ".join(summary.split())[:500] or _headline(draft)


def _centered_headline_y(
    draw: ImageDraw.ImageDraw,
    headline: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    *,
    rubric_bounds: tuple[float, float, float, float],
    review_label_bounds: tuple[float, float, float, float],
) -> int:
    headline_bounds = draw.multiline_textbbox(
        (0, 0),
        headline,
        font=font,
        spacing=HEADLINE_SPACING,
    )
    available_top = rubric_bounds[3]
    available_bottom = review_label_bounds[1]
    headline_height = headline_bounds[3] - headline_bounds[1]
    centered_top = available_top + (available_bottom - available_top - headline_height) / 2
    return round(centered_top - headline_bounds[1])


def _wrap_headline(
    draw: ImageDraw.ImageDraw,
    headline: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    *,
    max_width: int,
) -> tuple[str, ...]:
    normalized = " ".join(headline.split())
    if not normalized:
        return ()

    lines: list[str] = []
    current = ""
    for word in normalized.split(" "):
        candidate = word if not current else f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
            continue

        if current:
            lines.append(current)
            current = ""

        remaining = word
        while draw.textlength(remaining, font=font) > max_width:
            split_at = next(
                (
                    index
                    for index in range(len(remaining), 0, -1)
                    if draw.textlength(remaining[:index], font=font) <= max_width
                ),
                1,
            )
            lines.append(remaining[:split_at])
            remaining = remaining[split_at:]
        current = remaining

    if current:
        lines.append(current)
    return tuple(lines)


def _fit_headline_layout(
    draw: ImageDraw.ImageDraw,
    headline: str,
    *,
    rubric_bounds: tuple[float, float, float, float],
    review_label_bounds: tuple[float, float, float, float],
) -> tuple[str, ImageFont.FreeTypeFont | ImageFont.ImageFont, int]:
    available_height = review_label_bounds[1] - rubric_bounds[3]
    for font_size in range(HEADLINE_INITIAL_FONT_SIZE, HEADLINE_MIN_FONT_SIZE - 1, -1):
        headline_font = _font(font_size, bold=True)
        headline_lines = _wrap_headline(
            draw,
            headline,
            headline_font,
            max_width=HEADLINE_MAX_WIDTH,
        )
        if not headline_lines:
            raise NewsImageError("headline_layout_invalid")
        headline_text = "\n".join(headline_lines)
        headline_bounds = draw.multiline_textbbox(
            (0, 0),
            headline_text,
            font=headline_font,
            spacing=HEADLINE_SPACING,
        )
        headline_height = headline_bounds[3] - headline_bounds[1]
        max_line_width = max(draw.textlength(line, font=headline_font) for line in headline_lines)
        if max_line_width <= HEADLINE_MAX_WIDTH and headline_height <= available_height:
            return (
                headline_text,
                headline_font,
                _centered_headline_y(
                    draw,
                    headline_text,
                    headline_font,
                    rubric_bounds=rubric_bounds,
                    review_label_bounds=review_label_bounds,
                ),
            )
    raise NewsImageError("headline_layout_invalid")


def _draw_brand_overlay(image: Image.Image, draft: NewsDraftRevision) -> Image.Image:
    canvas = ImageOps.fit(image.convert("RGB"), CANVAS_SIZE, method=Image.Resampling.LANCZOS)
    overlay = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 0, 1200, 800), fill=(7, 12, 8, 92))
    draw.polygon(((0, 0), (690, 0), (455, 800), (0, 800)), fill=(10, 16, 11, 220))
    draw.line((691, 0, 455, 800), fill=(158, 224, 43, 150), width=3)
    draw.rounded_rectangle((54, 50, 1146, 750), radius=32, outline=(158, 224, 43, 110), width=2)
    draw.text(BRAND_LABEL_POSITION, "YOUR FITNESS COACH", font=_font(30, bold=True), fill="#9EE02B")
    rubric_font = _font(24, bold=True)
    rubric_text = _rubric(draft).upper()
    draw.text(RUBRIC_POSITION, rubric_text, font=rubric_font, fill="#EEF0EA")
    review_label_font = _font(22)
    review_label_text = "Проверено редактором • Источник — в публикации"
    draw.text(
        REVIEW_LABEL_POSITION,
        review_label_text,
        font=review_label_font,
        fill="#EEF0EA",
    )
    rubric_bounds = draw.textbbox(RUBRIC_POSITION, rubric_text, font=rubric_font)
    review_label_bounds = draw.textbbox(
        REVIEW_LABEL_POSITION,
        review_label_text,
        font=review_label_font,
    )
    headline_text, headline_font, headline_y = _fit_headline_layout(
        draw,
        _headline(draft),
        rubric_bounds=rubric_bounds,
        review_label_bounds=review_label_bounds,
    )
    draw.multiline_text(
        (HEADLINE_X, headline_y),
        headline_text,
        font=headline_font,
        fill="#FFFFFF",
        spacing=HEADLINE_SPACING,
    )
    mark_path = _brand_mark_path()
    if mark_path is not None:
        with Image.open(mark_path) as mark_source:
            mark = _transparent_brand_mark(mark_source).resize(
                BRAND_MARK_SIZE, Image.Resampling.LANCZOS
            )
        overlay.alpha_composite(mark, BRAND_MARK_POSITION)
    return Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")


def _encode_jpeg(image: Image.Image, *, maximum_bytes: int) -> NormalizedImage:
    for quality in (90, 86, 80, 74):
        output = io.BytesIO()
        image.save(
            output,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=True,
            exif=b"",
        )
        data = output.getvalue()
        if len(data) <= maximum_bytes:
            return NormalizedImage(
                data=data,
                content_type="image/jpeg",
                width=image.width,
                height=image.height,
                sha256=hashlib.sha256(data).hexdigest(),
            )
    raise NewsImageError("normalized_image_too_large")


def normalize_image_bytes(
    data: bytes,
    *,
    maximum_input_bytes: int,
    apply_brand_overlay: bool,
    draft: NewsDraftRevision,
) -> NormalizedImage:
    if not data or len(data) > maximum_input_bytes:
        raise NewsImageError("image_size_invalid")
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in {"JPEG", "PNG"} or getattr(source, "is_animated", False):
                raise NewsImageError("image_format_invalid")
            width, height = source.size
            if (
                width < 600
                or height < 400
                or width > 6000
                or height > 6000
                or width * height > MAX_DECODED_PIXELS
                or max(width / height, height / width) > 3
            ):
                raise NewsImageError("image_dimensions_invalid")
            source.verify()
        with Image.open(io.BytesIO(data)) as verified:
            normalized = ImageOps.exif_transpose(verified).convert("RGB")
            normalized = (
                _draw_brand_overlay(normalized, draft)
                if apply_brand_overlay
                else ImageOps.fit(
                    normalized,
                    CANVAS_SIZE,
                    method=Image.Resampling.LANCZOS,
                )
            )
    except NewsImageError:
        raise
    except (Image.DecompressionBombError, OSError, UnidentifiedImageError) as exc:
        raise NewsImageError("image_decode_invalid") from exc
    return _encode_jpeg(normalized, maximum_bytes=settings.news_image_max_bytes)


def render_template_image(draft: NewsDraftRevision) -> NormalizedImage:
    base = Image.new("RGB", CANVAS_SIZE, "#101310")
    draw = ImageDraw.Draw(base)
    draw.ellipse((675, -140, 1285, 470), fill="#172018")
    draw.ellipse(BRAND_CIRCLE_BOUNDS, outline="#9EE02B", width=5)
    draw.line((760, 0, 520, 800), fill="#2F4315", width=4)
    return _encode_jpeg(
        _draw_brand_overlay(base, draft), maximum_bytes=settings.news_image_max_bytes
    )


def _safe_prompt(draft: NewsDraftRevision) -> str:
    topic = str(draft.evidence_metadata.get("topic", "fitness"))[:48]
    rubric = _rubric(draft)
    context_headline = str(draft.evidence_metadata.get("image_context_headline", _headline(draft)))[
        :180
    ]
    return (
        "Create an original editorial cover illustration for a Russian fitness news post. "
        f"Topic category: {topic}. Editorial rubric: {rubric}. "
        f"News headline: {context_headline}. What happened: {_what_happened(draft)}. "
        "Abstract sport-tech still life, calm precise composition, dark neutral background, "
        "subtle lime accent, generous safe crop area. No people or likenesses, no bodies, "
        "no before/after, no medical imagery, no pills or syringes, no logos or trademarks, "
        "no source screenshot, no chart, no numbers, no labels, no embedded text. "
        "The application will add all branding and text deterministically."
    )


async def _generate_cloudflare_image(
    client: httpx.AsyncClient, draft: NewsDraftRevision
) -> GeneratedImage:
    prompt = _safe_prompt(draft)
    prompt_digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    started = monotonic()
    try:
        response = await client.post(
            CLOUDFLARE_IMAGES_ENDPOINT.format(account_id=settings.news_image_cloudflare_account_id),
            headers={
                "Authorization": f"Bearer {settings.news_image_cloudflare_api_token}",
                "Content-Type": "application/json",
            },
            json={
                "prompt": prompt,
                "steps": settings.news_image_steps,
            },
            timeout=settings.news_image_timeout_seconds,
        )
    except httpx.TimeoutException as exc:
        raise NewsImageError("image_provider_timeout") from exc
    except httpx.RequestError as exc:
        raise NewsImageError("image_provider_network_error") from exc
    if response.status_code == 429:
        raise NewsImageError("image_provider_rate_limited")
    if response.status_code in {401, 403}:
        raise NewsImageError("image_provider_misconfigured")
    if response.status_code >= 500:
        raise NewsImageError("image_provider_unavailable")
    if not response.is_success:
        raise NewsImageError("image_provider_rejected")
    if len(response.content) > MAX_PROVIDER_RESPONSE_BYTES:
        raise NewsImageError("image_provider_response_too_large")
    try:
        payload = response.json()
        if payload.get("success") is not True:
            raise TypeError
        encoded = payload["result"]["image"]
        if not isinstance(encoded, str):
            raise TypeError
        raw = base64.b64decode(encoded, validate=True)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise NewsImageError("image_provider_malformed_response") from exc
    normalized = normalize_image_bytes(
        raw,
        maximum_input_bytes=settings.news_image_max_bytes,
        apply_brand_overlay=True,
        draft=draft,
    )
    return GeneratedImage(
        image=normalized,
        kind="generated",
        provider="cloudflare_workers_ai_free",
        model=settings.news_image_model,
        prompt_digest=prompt_digest,
        safety_status="generated_pending_review",
        latency_ms=round((monotonic() - started) * 1000),
        cost_microunits=0,
    )


def _template_result(draft: NewsDraftRevision, warning: str | None = None) -> GeneratedImage:
    prompt_digest = hashlib.sha256(_safe_prompt(draft).encode("utf-8")).hexdigest()
    warnings = (warning,) if warning else ()
    return GeneratedImage(
        image=render_template_image(draft),
        kind="template",
        provider="deterministic",
        model="yfc-editorial-cover-v1",
        prompt_digest=prompt_digest,
        safety_status="template",
        latency_ms=0,
        warnings=warnings,
    )


async def create_image_revision(
    db: Session,
    cluster: NewsCluster,
    draft: NewsDraftRevision,
    *,
    client: httpx.AsyncClient | None,
) -> NewsImageRevision:
    generated: GeneratedImage
    day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    today_count = (
        db.query(NewsImageRevision.id).filter(NewsImageRevision.created_at >= day_start).count()
    )
    if (
        settings.news_image_provider == "cloudflare_workers_ai"
        and client is not None
        and today_count < settings.news_image_daily_request_limit
    ):
        try:
            generated = await _generate_cloudflare_image(client, draft)
        except NewsImageError as exc:
            generated = _template_result(draft, exc.code)
    elif settings.news_image_provider == "cloudflare_workers_ai" and (
        today_count >= settings.news_image_daily_request_limit
    ):
        generated = _template_result(draft, "free_daily_request_limit_reached")
    else:
        generated = _template_result(draft)
    revision = cluster.latest_image_revision + 1
    row = NewsImageRevision(
        id=secrets.token_hex(16),
        cluster_id=cluster.id,
        text_revision_id=draft.id,
        revision=revision,
        kind=generated.kind,
        provider=generated.provider,
        model=generated.model,
        prompt_version=settings.news_image_prompt_version,
        prompt_digest=generated.prompt_digest,
        provenance={
            "provider_policy_checked_at": PROVIDER_POLICY_CHECKED_AT,
            "source": "safe_editorial_summary",
            "branding": "deterministic_yfc_overlay",
            "metadata_stripped": True,
        },
        content_type=generated.image.content_type,
        byte_size=len(generated.image.data),
        width=generated.image.width,
        height=generated.image.height,
        sha256=generated.image.sha256,
        image_data=generated.image.data,
        safety_status=generated.safety_status,
        warnings=list(generated.warnings),
        generation_latency_ms=generated.latency_ms,
        generation_input_tokens=generated.input_tokens,
        generation_output_tokens=generated.output_tokens,
        generation_cost_microunits=generated.cost_microunits,
    )
    db.add(row)
    cluster.latest_image_revision = revision
    cluster.current_image_revision = revision
    transition_news_cluster(db, cluster, "draft_ready", reason_code="image_revision_created")
    db.flush()
    logger.info(
        "news_image_generation_completed",
        extra={
            "pipeline_stage": "image_generation",
            "provider": row.provider,
            "outcome": row.kind,
            "latency_ms": row.generation_latency_ms,
            "image_bytes": row.byte_size,
            "warning_count": len(row.warnings),
            "generation_cost_microunits": row.generation_cost_microunits,
        },
    )
    return row


def create_uploaded_image_revision(
    db: Session,
    cluster: NewsCluster,
    draft: NewsDraftRevision,
    data: bytes,
) -> NewsImageRevision:
    normalized = normalize_image_bytes(
        data,
        maximum_input_bytes=settings.news_image_upload_max_bytes,
        apply_brand_overlay=False,
        draft=draft,
    )
    revision = cluster.latest_image_revision + 1
    row = NewsImageRevision(
        id=secrets.token_hex(16),
        cluster_id=cluster.id,
        text_revision_id=draft.id,
        revision=revision,
        kind="uploaded",
        provider="owner_upload",
        model="none",
        prompt_version="none",
        prompt_digest=hashlib.sha256(b"owner-upload").hexdigest(),
        provenance={
            "source": "owner_private_bot_upload",
            "metadata_stripped": True,
            "normalized": True,
        },
        content_type=normalized.content_type,
        byte_size=len(normalized.data),
        width=normalized.width,
        height=normalized.height,
        sha256=normalized.sha256,
        image_data=normalized.data,
        safety_status="owner_uploaded",
        warnings=[],
        generation_latency_ms=0,
    )
    db.add(row)
    cluster.latest_image_revision = revision
    cluster.current_image_revision = revision
    transition_news_cluster(db, cluster, "draft_ready", reason_code="owner_image_replaced")
    db.flush()
    return row


def current_image(db: Session, cluster: NewsCluster) -> NewsImageRevision | None:
    if cluster.current_image_revision < 1:
        return None
    return (
        db.query(NewsImageRevision)
        .filter(
            NewsImageRevision.cluster_id == cluster.id,
            NewsImageRevision.revision == cluster.current_image_revision,
        )
        .first()
    )