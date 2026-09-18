from __future__ import annotations

import io
from datetime import date
from html import escape
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_ACCENT = colors.HexColor("#78A800")
_TEXT = colors.HexColor("#151713")
_MUTED = colors.HexColor("#62675D")
_LINE = colors.HexColor("#D9DED2")
_SURFACE = colors.HexColor("#F1F3ED")


def _font_paths() -> tuple[str, str] | None:
    candidates = (
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
        (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
    )
    for regular, bold in candidates:
        if regular.exists() and bold.exists():
            return str(regular), str(bold)
    return None


def _register_fonts() -> tuple[str, str]:
    paths = _font_paths()
    if paths is None:
        return "Helvetica", "Helvetica-Bold"
    regular, bold = paths
    if "YFCReport" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("YFCReport", regular))
        pdfmetrics.registerFont(TTFont("YFCReport-Bold", bold))
    return "YFCReport", "YFCReport-Bold"


def _number(value: Any, suffix: str = "") -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
        rendered = (
            f"{number:,.1f}".rstrip("0")
            .rstrip(".")
            .replace(",", "\N{NO-BREAK SPACE}")
            .replace(".", ",")
        )
    except TypeError, ValueError:
        rendered = str(value)
    return f"{rendered}{suffix}"


def _date(value: Any) -> str:
    try:
        return date.fromisoformat(str(value)).strftime("%d.%m.%Y")
    except ValueError:
        return str(value)


def _label(value: Any) -> str:
    return {
        "muscle_gain": "Набор мышечной массы",
        "weight_loss": "Снижение массы",
        "maintenance": "Поддержание формы",
        "strength": "Развитие силы",
        "endurance": "Развитие выносливости",
        "active": "активна",
        "scheduled": "запланирована",
        "completed": "завершена",
        "archived": "в архиве",
        "skipped": "пропущен",
        "sufficient": "достаточно данных",
        "limited": "данные ограничены",
        "insufficient": "недостаточно данных",
        "improving": "заметно выше в конце периода",
        "declining": "заметно ниже в конце периода",
        "stable": "без заметной разницы",
        "insufficient_data": "недостаточно точек",
    }.get(str(value), str(value))


def _safe(value: Any) -> str:
    return escape(str(value), quote=False)


def _body_metric(metric: str, *, label: Any = None, unit: Any = None) -> tuple[str, str]:
    fallback_label, fallback_suffix = {
        "weight_kg": ("Масса", " кг"),
        "chest_cm": ("Грудь", " см"),
        "waist_cm": ("Талия", " см"),
        "hips_cm": ("Бёдра", " см"),
        "biceps_cm": ("Бицепс", " см"),
        "thigh_cm": ("Бедро", " см"),
    }.get(
        metric,
        ("Пользовательский показатель" if metric.startswith("custom:") else "Замер", " см"),
    )
    display_label = label.strip() if isinstance(label, str) and label.strip() else fallback_label
    display_unit = unit.strip() if isinstance(unit, str) and unit.strip() else None
    suffix = (
        {"kg": " кг", "cm": " см"}.get(display_unit, fallback_suffix)
        if display_unit is not None
        else fallback_suffix
    )
    return display_label, suffix


def _wellbeing_value(value: int, metric: str) -> str:
    labels = {
        "sleep": {
            1: "Очень плохо",
            2: "Плохо",
            3: "Обычно",
            4: "Хорошо",
            5: "Отлично",
        },
        "mood": {
            1: "Очень тяжело",
            2: "Тяжеловато",
            3: "Обычно",
            4: "Хорошо",
            5: "Отлично",
        },
    }
    return labels.get(metric, {}).get(value, str(value))


def build_progress_report_pdf(report: dict[str, Any]) -> bytes:
    regular, bold = _register_fonts()
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "YFCTitle",
        parent=styles["Title"],
        fontName=bold,
        fontSize=21,
        leading=25,
        textColor=_TEXT,
        spaceAfter=4 * mm,
    )
    heading = ParagraphStyle(
        "YFCHeading",
        parent=styles["Heading2"],
        fontName=bold,
        fontSize=13,
        leading=16,
        textColor=_TEXT,
        spaceBefore=3 * mm,
        spaceAfter=1.5 * mm,
    )
    body = ParagraphStyle(
        "YFCBody",
        parent=styles["BodyText"],
        fontName=regular,
        fontSize=9,
        leading=12,
        textColor=_TEXT,
    )
    muted = ParagraphStyle("YFCMuted", parent=body, textColor=_MUTED, fontSize=8, leading=10)
    label = ParagraphStyle("YFCLabel", parent=muted, fontName=bold, textTransform="uppercase")

    stream = io.BytesIO()
    doc = SimpleDocTemplate(
        stream,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Отчёт о прогрессе — {report['subject']['name']}",
        author="Your Fitness Coach",
    )
    story: list[Any] = [
        Paragraph("ОТЧЁТ О ПРОГРЕССЕ", label),
        Paragraph(_safe(report["subject"]["name"]), title),
        Paragraph(
            f"Период: {_date(report['period_start'])} — {_date(report['period_end'])} · Часовой пояс: {_safe(report['timezone'])}",
            body,
        ),
    ]
    if report["subject"].get("goal"):
        story.append(Paragraph(f"Цель: {_safe(_label(report['subject']['goal']))}", muted))

    def metric_table(items: list[tuple[str, str]]) -> Table:
        cells = [
            Table(
                [[Paragraph(name, muted)], [Paragraph(value, heading)]],
                colWidths=[(A4[0] - 30 * mm) / max(1, len(items))],
            )
            for name, value in items
        ]
        table = Table([cells], colWidths=[(A4[0] - 30 * mm) / max(1, len(cells))] * len(cells))
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _SURFACE),
                    ("BOX", (0, 0), (-1, -1), 0.5, _LINE),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, _LINE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        return table

    training = report["training"]
    story.extend(
        [
            Paragraph("Ключевые факты", heading),
            metric_table(
                [
                    (
                        "Тренировки",
                        f"{training['completed_workouts']} / {training['planned_workouts']}",
                    ),
                    ("Рабочие подходы", _number(training["completed_working_sets"])),
                    ("Кардио", _number(report["cardio"]["completed_sessions"])),
                    (
                        "Средняя калорийность",
                        _number(report["nutrition"]["summary"]["calories"].get("average"), " ккал"),
                    ),
                ]
            ),
            Paragraph("Тренировки", heading),
            Paragraph(
                " · ".join(
                    (
                        f"Завершено: {training['completed_workouts']}",
                        f"Пропущено: {training['skipped_workouts']}",
                        f"Частота: {_number(training['frequency_per_week'])} в неделю",
                        f"Объём с внешней нагрузкой: {_number(training.get('external_load_volume_kg'), ' кг')}",
                    )
                ),
                body,
            ),
        ]
    )
    exercises = training.get("exercises", [])
    if exercises:
        rows = [
            [
                Paragraph("Упражнение", label),
                Paragraph("Сессии", label),
                Paragraph("Макс. вес", label),
                Paragraph("Объём", label),
            ]
        ]
        rows.extend(
            [
                Paragraph(_safe(item["exercise_title"]), body),
                Paragraph(str(item["performed_session_count"]), body),
                Paragraph(_number(item.get("max_external_load_kg"), " кг"), body),
                Paragraph(_number(item.get("external_load_volume_kg"), " кг"), body),
            ]
            for item in exercises
        )
        exercise_table = LongTable(
            rows, colWidths=[82 * mm, 24 * mm, 28 * mm, 30 * mm], repeatRows=1
        )
        exercise_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, _LINE),
                    ("BACKGROUND", (0, 0), (-1, 0), _SURFACE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("PADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.extend([Spacer(1, 2 * mm), exercise_table])

    cardio = report["cardio"]
    body_report = report["body"]
    nutrition = report["nutrition"]
    story.extend(
        [
            Paragraph("Кардио и антропометрия", heading),
            metric_table(
                [
                    ("Кардио-сессии", _number(cardio["completed_sessions"])),
                    ("Минуты кардио", _number(cardio["duration_minutes"])),
                    ("Метрики тела", _number(len(body_report["trends"]))),
                    ("Дни питания", _number(nutrition["summary"].get("logged_days"))),
                ]
            ),
            Paragraph("Питание", heading),
            Paragraph(
                " · ".join(
                    (
                        f"Среднее: {_number(nutrition['summary']['calories'].get('average'), ' ккал')}",
                        f"Белок: {_number(nutrition['summary']['protein_g'].get('average'), ' г')}",
                        f"Жиры: {_number(nutrition['summary']['fat_g'].get('average'), ' г')}",
                        f"Углеводы: {_number(nutrition['summary']['carbs_g'].get('average'), ' г')}",
                    )
                ),
                body,
            ),
        ]
    )
    trends = body_report.get("trends", [])
    if trends:
        trend_rows = [
            [
                Paragraph("Метрика", label),
                Paragraph("Начало", label),
                Paragraph("Сейчас", label),
                Paragraph("Изменение", label),
            ]
        ]
        for trend in trends:
            metric_name, unit = _body_metric(
                str(trend["metric"]),
                label=trend.get("label"),
                unit=trend.get("unit"),
            )
            trend_rows.append(
                [
                    Paragraph(_safe(metric_name), body),
                    Paragraph(
                        f"{_number(trend['first_value'], unit)}<br/><font size=7>{_date(trend['first_measured_on'])}</font>",
                        body,
                    ),
                    Paragraph(
                        f"{_number(trend['latest_value'], unit)}<br/><font size=7>{_date(trend['latest_measured_on'])}</font>",
                        body,
                    ),
                    Paragraph(_number(trend.get("change"), unit), body),
                ]
            )
        trend_table = Table(trend_rows, colWidths=[48 * mm, 38 * mm, 38 * mm, 40 * mm])
        trend_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, _LINE),
                    ("BACKGROUND", (0, 0), (-1, 0), _SURFACE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("PADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.extend([Spacer(1, 2 * mm), trend_table])

    wellbeing = report.get("wellbeing")
    if wellbeing:
        story.extend(
            [
                Paragraph("Сон и настроение", heading),
                Paragraph(
                    f"Заполнено: {wellbeing['recorded_days']} из {wellbeing['eligible_days']} дней "
                    f"({_number(wellbeing['coverage_percent'], '%')}). "
                    "Показываются только фактические отметки; заметки в этот отчёт не входят.",
                    body,
                ),
            ]
        )
        for key, title_text in (("sleep", "Качество сна"), ("mood", "Настроение")):
            metric = wellbeing[key]
            distribution = (
                ", ".join(
                    f"{_wellbeing_value(item['value'], key)}: {item['count']}"
                    for item in metric["distribution"]
                    if item["count"]
                )
                or "Нет отдельных отметок"
            )
            story.append(
                Paragraph(
                    f"<b>{_safe(title_text)}</b>: {distribution}. "
                    f"Тренд: {_safe(_label(metric['trend']))}.",
                    body,
                )
            )

    adherence = report["adherence"]
    story.extend(
        [
            Paragraph("Соблюдение плана и полнота данных", heading),
            Paragraph(
                f"Общий показатель: {_number(adherence.get('overall_percent'), '%')}. "
                "Он рассчитывается только по доступным компонентам и не является медицинским выводом.",
                body,
            ),
        ]
    )
    sufficiency = report["data_sufficiency"]
    sufficiency_labels = {
        "workout_logging": "Тренировки",
        "working_sets": "Рабочие подходы",
        "rir_coverage": "RIR",
        "nutrition_coverage": "Питание",
        "weight_trend": "Динамика массы",
        "anthropometry": "Антропометрия",
        "schedule_adherence": "План тренировок",
    }
    story.append(
        Paragraph(
            " · ".join(
                f"{name}: {_safe(_label(sufficiency[key]['status']))}"
                for key, name in sufficiency_labels.items()
                if key in sufficiency
            ),
            muted,
        )
    )
    program = report.get("program")
    if program:
        story.extend(
            [
                Paragraph("Программа", heading),
                Paragraph(
                    f"{_safe(program['title'])} · статус: {_safe(_label(program['status']))} · старт: {_date(program['start_date'])} · {program['duration_weeks']} нед.",
                    body,
                ),
            ]
        )
    check_ins = report.get("check_ins", [])
    if check_ins:
        story.extend([Paragraph("Еженедельные отчёты", heading)])
        for item in check_ins:
            story.append(
                Paragraph(
                    f"{_date(item['week_start'])} — {_date(item['week_end'])}: {_safe(_label(item['status']))}"
                    + (f" · {_safe(item['note'])}" if item.get("note") else ""),
                    body,
                )
            )
    story.extend(
        [
            Spacer(1, 5 * mm),
            Paragraph("Как читать отчёт", heading),
            Paragraph(
                "Отчёт показывает только зафиксированные в Your Fitness Coach данные. Пропуски не заменяются предположениями; недостаточная полнота данных ограничивает выводы.",
                muted,
            ),
        ]
    )

    def footer(canvas, document) -> None:
        canvas.saveState()
        canvas.setStrokeColor(_ACCENT)
        canvas.setLineWidth(1.5)
        canvas.line(15 * mm, 10 * mm, 195 * mm, 10 * mm)
        canvas.setFont(regular, 7.5)
        canvas.setFillColor(_MUTED)
        canvas.drawString(15 * mm, 6 * mm, "Your Fitness Coach")
        canvas.setFont(regular, 7.5)
        canvas.drawRightString(195 * mm, 6 * mm, f"Страница {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
