from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ats_bot.scoring import AtsResult


def build_report(result: AtsResult, report_type: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(ch for ch in result.candidate_name if ch.isalnum() or ch in (" ", "_")).strip()
    filename = f"ats_{report_type}_{safe_name or 'candidate'}_{datetime.now():%Y%m%d_%H%M%S}.pdf"
    path = output_dir / filename

    font = _register_font()
    styles = _styles(font)
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="ATS resume report",
    )

    story = _cover_page(result, styles)
    story.extend(_metrics_page(result, styles))
    story.extend(_improvement_plan(result, styles))
    story.extend(_employer_view(result, styles))

    if report_type == "full":
        story.extend(_full_sections(result, styles))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return path


def _cover_page(result: AtsResult, styles: dict[str, ParagraphStyle]) -> list:
    match = result.market_match
    return [
        Paragraph("Отчет по резюме", styles["Kicker"]),
        Paragraph("ОБЩИЙ БАЛЛ", styles["SectionCenter"]),
        Paragraph(f"{result.score} / 100", styles["Score"]),
        Paragraph(f"Оценка: {result.grade}", styles["Grade"]),
        Spacer(1, 8),
        _match_table(result, styles),
        Spacer(1, 8),
        Paragraph(f"До отличного результата: +{max(0, 100 - result.score)} баллов", styles["Body"]),
        Paragraph(
            f"Отчет создан {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. "
            f"На основе {match.sample_size} вакансий. Роль: {escape(result.role)}.",
            styles["Small"],
        ),
        Spacer(1, 12),
        Paragraph("Общая информация", styles["Section"]),
        _info_table(
            [
                ("Кандидат", result.candidate_name),
                ("Уровень по резюме", result.level),
                ("Основной домен", result.primary_domain),
                ("Совпадение слов", f"{result.avg_keyword_matches} на вакансию"),
                ("Вывод", result.summary),
            ],
            styles,
        ),
        Spacer(1, 8),
        Paragraph("Пройдет ли резюме фильтры", styles["Section"]),
        _filters_table(result, styles),
        PageBreak(),
    ]


def _metrics_page(result: AtsResult, styles: dict[str, ParagraphStyle]) -> list:
    block = result.score_block
    return [
        Paragraph("КЛЮЧЕВЫЕ ПОКАЗАТЕЛИ", styles["SectionCenter"]),
        _score_cards(
            [
                ("СТРУКТУРА", block.structure),
                ("СОДЕРЖАНИЕ", block.content),
                ("СТАНДАРТЫ", block.standards),
                ("ПРАВИЛА", block.rules),
                ("ПЕРВОЕ ВПЕЧАТЛЕНИЕ", block.first_impression),
            ],
            styles,
        ),
        Spacer(1, 10),
        Paragraph("ДЕТАЛЬНЫЕ МЕТРИКИ", styles["Section"]),
        _info_table(
            [
                ("Skills Coverage", f"{block.skills_coverage}%"),
                ("Hard Skills", f"{block.hard_skills}%"),
                ("Domain Fit", f"{block.domain_fit}%"),
                ("ATS Score", f"{block.ats_score}%"),
            ],
            styles,
        ),
        Spacer(1, 8),
        Paragraph("ЦЕЛЕВЫЕ ПОКАЗАТЕЛИ", styles["Section"]),
        *_bullets(
            [
                "Skills Coverage: покрытие ключевых навыков. Цель - 85% или выше.",
                "Hard Skills: покрытие технических навыков. Цель - 88% или выше.",
                "Domain Fit: соответствие предметной области. Цель - 60% или выше.",
                "ATS Score: вероятность прохождения автоматического фильтра. Цель - 80% или выше.",
            ],
            styles,
        ),
        Spacer(1, 8),
        Paragraph("Рекомендация", styles["Section"]),
        Paragraph(_p(result.recommendation), styles["Body"]),
        PageBreak(),
    ]


def _improvement_plan(result: AtsResult, styles: dict[str, ParagraphStyle]) -> list:
    return [
        Paragraph("1. План улучшения резюме", styles["Section"]),
        Paragraph("Карьерный профиль - как себя позиционировать", styles["Subsection"]),
        _info_table(
            [
                ("Уровень", result.level),
                ("Фокус", f"{result.role}, {result.primary_domain}, интеграции, требования и системные артефакты"),
                ("Релевантные роли", "системный аналитик, бизнес-аналитик, аналитик интеграционных решений"),
                ("Следующие шаги", "усилить ключевые слова, метрики достижений и описание проектного масштаба"),
            ],
            styles,
        ),
        Spacer(1, 8),
        Paragraph("Задачи на фокус", styles["Subsection"]),
        _actions_table(result, styles),
        Spacer(1, 6),
        Paragraph("Рекомендованные действия помогают повысить конверсию резюме в приглашения на собеседования.", styles["Small"]),
        PageBreak(),
    ]


def _employer_view(result: AtsResult, styles: dict[str, ParagraphStyle]) -> list:
    return [
        Paragraph("2. Как вас видят работодатели", styles["Section"]),
        Paragraph(_p(result.summary), styles["Body"]),
        Spacer(1, 8),
        _info_table(result.employer_view, styles),
        Spacer(1, 8),
        Paragraph("Сильные стороны", styles["Subsection"]),
        *_bullets(result.strengths, styles),
        Spacer(1, 8),
        Paragraph("Риски и пробелы", styles["Subsection"]),
        *_bullets(result.risks, styles),
    ]


def _full_sections(result: AtsResult, styles: dict[str, ParagraphStyle]) -> list:
    return [
        PageBreak(),
        Paragraph("3. Соответствие ключевым словам", styles["Section"]),
        _skills_table(result, styles),
        Spacer(1, 8),
        Paragraph("Недостающие требования", styles["Subsection"]),
        *_bullets(result.missing_requirements, styles),
        PageBreak(),
        Paragraph("4. Как ваше резюме видят ATS и ИИ", styles["Section"]),
        *_bullets(
            [
                f"Автоматический ATS-балл: {result.score_block.ats_score} / 100.",
                f"Первое впечатление рекрутера: {result.score_block.first_impression} / 100.",
                "Сильнее всего влияют навыки на первой странице, измеримые достижения и явный доменный фокус.",
                "Для ИИ-скрининга важно, чтобы роль, артефакты, стек и бизнес-эффект были написаны явно, а не подразумевались.",
            ],
            styles,
        ),
        Spacer(1, 8),
        Paragraph("Вопросы для подготовки к интервью", styles["Subsection"]),
        *_bullets(result.interview_questions, styles),
        PageBreak(),
        Paragraph("5. Методология оценки", styles["Section"]),
        *_bullets(
            [
                "Резюме сравнивается с рыночной выборкой вакансий системного аналитика.",
                "Считаются совпадения ключевых навыков, доменных терминов, инструментов и системных артефактов.",
                "Отдельно оцениваются структура, соответствие стандартам резюме, наличие метрик и первое впечатление.",
                "Итоговый балл показывает готовность резюме к откликам и прохождению ATS-фильтров.",
            ],
            styles,
        ),
    ]


def _register_font() -> str:
    candidates = [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            pdfmetrics.registerFont(TTFont("AtsFont", str(path)))
            return "AtsFont"
    return "Helvetica"


def _styles(font: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "Kicker": ParagraphStyle("Kicker", parent=base["BodyText"], fontName=font, fontSize=12, leading=15, textColor=colors.HexColor("#475569"), alignment=TA_CENTER),
        "Score": ParagraphStyle("Score", parent=base["Title"], fontName=font, fontSize=34, leading=40, textColor=colors.HexColor("#111827"), alignment=TA_CENTER, spaceAfter=2),
        "Grade": ParagraphStyle("Grade", parent=base["Heading2"], fontName=font, fontSize=14, leading=18, textColor=colors.HexColor("#334155"), alignment=TA_CENTER),
        "SectionCenter": ParagraphStyle("SectionCenter", parent=base["Heading2"], fontName=font, fontSize=13, leading=16, textColor=colors.HexColor("#111827"), alignment=TA_CENTER, spaceBefore=4, spaceAfter=6),
        "Section": ParagraphStyle("Section", parent=base["Heading2"], fontName=font, fontSize=13, leading=16, textColor=colors.HexColor("#111827"), spaceBefore=4, spaceAfter=6),
        "Subsection": ParagraphStyle("Subsection", parent=base["Heading3"], fontName=font, fontSize=10.5, leading=14, textColor=colors.HexColor("#1F2937"), spaceBefore=4, spaceAfter=4),
        "Body": ParagraphStyle("Body", parent=base["BodyText"], fontName=font, fontSize=9.2, leading=12.5, textColor=colors.HexColor("#374151")),
        "Small": ParagraphStyle("Small", parent=base["BodyText"], fontName=font, fontSize=8, leading=10.5, textColor=colors.HexColor("#64748B")),
    }


def _match_table(result: AtsResult, styles: dict[str, ParagraphStyle]) -> Table:
    match = result.market_match
    sample = max(match.sample_size, 1)
    rows = [
        ["Соответствие вакансиям", "Количество", "Доля выборки"],
        ["Сильное", str(match.strong), f"{match.strong / sample:.1%}"],
        ["Среднее", str(match.medium), f"{match.medium / sample:.1%}"],
        ["Низкое", str(match.low), f"{match.low / sample:.1%}"],
    ]
    return _table(rows, styles, [72 * mm, 35 * mm, 42 * mm], header=True)


def _filters_table(result: AtsResult, styles: dict[str, ParagraphStyle]) -> Table:
    score = result.score
    levels = ["Junior", "Middle", "Senior"]
    rows = [["Уровень позиции", "Автофильтр", "Рекрутер", "Нанимающий менеджер"]]
    for level in levels:
        if level == result.level:
            auto = "да" if score >= 72 else "?"
            recruiter = "да" if score >= 55 else "?"
            manager = "да" if score >= 82 else "?"
        else:
            auto = "нет" if score < 90 else "?"
            recruiter = "да" if score >= 70 else "?"
            manager = "нет" if score < 85 else "?"
        rows.append([level, auto, recruiter, manager])
    return _table(rows, styles, [42 * mm, 36 * mm, 36 * mm, 44 * mm], header=True)


def _score_cards(items: list[tuple[str, int]], styles: dict[str, ParagraphStyle]) -> Table:
    rows = [[Paragraph(_p(name), styles["Small"]) for name, _ in items], [Paragraph(f"<b>{score}</b><br/>/ 100", styles["SectionCenter"]) for _, score in items]]
    table = Table(rows, colWidths=[31 * mm] * len(items))
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2FF")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _info_table(items: list[tuple[str, str]], styles: dict[str, ParagraphStyle]) -> Table:
    rows = [[Paragraph(_p(k), styles["Body"]), Paragraph(_p(v), styles["Body"])] for k, v in items]
    return _table(rows, styles, [45 * mm, 110 * mm], header=False)


def _actions_table(result: AtsResult, styles: dict[str, ParagraphStyle]) -> Table:
    rows = [
        [Paragraph("20 минут", styles["Body"]), Paragraph(_p("\n".join(result.quick_actions)), styles["Body"])],
        [Paragraph("2 часа", styles["Body"]), Paragraph(_p("\n".join(result.deep_actions)), styles["Body"])],
    ]
    return _table(rows, styles, [28 * mm, 127 * mm], header=False)


def _skills_table(result: AtsResult, styles: dict[str, ParagraphStyle]) -> Table:
    rows = [["Навык / требование", "Статус"]]
    rows.extend([[item.name, item.status] for item in result.skill_matches[:32]])
    return _table(rows, styles, [112 * mm, 43 * mm], header=True)


def _table(rows, styles: dict[str, ParagraphStyle], col_widths, header: bool) -> Table:
    table = Table(rows, colWidths=col_widths, repeatRows=1 if header else 0)
    commands = [
        ("FONTNAME", (0, 0), (-1, -1), styles["Body"].fontName),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        commands.extend([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ])
    else:
        commands.extend([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#334155")),
        ])
    table.setStyle(TableStyle(commands))
    return table


def _bullets(items: list[str], styles: dict[str, ParagraphStyle]) -> list[Paragraph]:
    if not items:
        items = ["Нет данных."]
    return [Paragraph(f"- {_p(item)}", styles["Body"]) for item in items]


def _p(value: object) -> str:
    return escape(str(value)).replace("\n", "<br/>")


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#94A3B8"))
    canvas.drawRightString(A4[0] - 16 * mm, 8 * mm, f"{doc.page}")
    canvas.restoreState()
