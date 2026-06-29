from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

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
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="ATS report",
    )

    story = [
        Paragraph("ATS ОТЧЕТ ПО КАНДИДАТУ", styles["Title"]),
        Spacer(1, 8),
        _score_table(result, styles),
        Spacer(1, 12),
        Paragraph("Краткое резюме", styles["Section"]),
        Paragraph(result.summary or "Нет данных для краткого резюме.", styles["Body"]),
        Spacer(1, 8),
        Paragraph("Сильные стороны", styles["Section"]),
        *_bullets(result.strengths, styles),
        Spacer(1, 8),
        Paragraph("Риски и пробелы", styles["Section"]),
        *_bullets(result.risks or result.missing_requirements, styles),
    ]

    if report_type == "full":
        story.extend(
            [
                Spacer(1, 8),
                Paragraph("Матрица требований", styles["Section"]),
                _skills_table(result, styles),
                Spacer(1, 8),
                Paragraph("Вопросы для интервью", styles["Section"]),
                *_bullets(result.interview_questions, styles),
                Spacer(1, 8),
                Paragraph("Отсутствующие требования", styles["Section"]),
                *_bullets(result.missing_requirements, styles),
            ]
        )

    doc.build(story)
    return path


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
        "Title": ParagraphStyle("AtsTitle", parent=base["Title"], fontName=font, fontSize=18, leading=22, textColor=colors.HexColor("#1F2937"), alignment=TA_CENTER, spaceAfter=8),
        "Section": ParagraphStyle("AtsSection", parent=base["Heading2"], fontName=font, fontSize=12, leading=15, textColor=colors.HexColor("#111827"), spaceBefore=4, spaceAfter=4),
        "Body": ParagraphStyle("AtsBody", parent=base["BodyText"], fontName=font, fontSize=9.5, leading=13, textColor=colors.HexColor("#374151")),
    }


def _score_table(result: AtsResult, styles: dict[str, ParagraphStyle]) -> Table:
    data = [
        ["Кандидат", result.candidate_name],
        ["Вакансия", result.vacancy_title],
        ["Оценка", f"{result.score}/100"],
        ["Рекомендация", result.recommendation],
    ]
    table = Table(data, colWidths=[38 * mm, 118 * mm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), styles["Body"].fontName),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EEF2FF")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#3730A3")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _skills_table(result: AtsResult, styles: dict[str, ParagraphStyle]) -> Table:
    rows = [["Навык / требование", "Статус"]]
    rows.extend([[item.name, item.status] for item in result.skill_matches[:24]])
    table = Table(rows, colWidths=[112 * mm, 44 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), styles["Body"].fontName),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _bullets(items: list[str], styles: dict[str, ParagraphStyle]) -> list[Paragraph]:
    if not items:
        items = ["Нет данных."]
    return [Paragraph(f"- {item}", styles["Body"]) for item in items]
