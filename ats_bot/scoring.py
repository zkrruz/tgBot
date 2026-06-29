from __future__ import annotations

import json
import re
from dataclasses import dataclass

from openai import OpenAI

from ats_bot.storage import Vacancy


@dataclass(frozen=True)
class SkillMatch:
    name: str
    status: str


@dataclass(frozen=True)
class AtsResult:
    candidate_name: str
    vacancy_title: str
    score: int
    recommendation: str
    summary: str
    strengths: list[str]
    risks: list[str]
    missing_requirements: list[str]
    interview_questions: list[str]
    skill_matches: list[SkillMatch]


def evaluate_resume(
    resume_text: str,
    vacancy: Vacancy,
    report_type: str,
    api_key: str | None,
    model: str,
) -> AtsResult:
    if api_key:
        try:
            return _evaluate_with_openai(resume_text, vacancy, report_type, api_key, model)
        except Exception:
            return _evaluate_locally(resume_text, vacancy)
    return _evaluate_locally(resume_text, vacancy)


def _evaluate_with_openai(
    resume_text: str,
    vacancy: Vacancy,
    report_type: str,
    api_key: str,
    model: str,
) -> AtsResult:
    client = OpenAI(api_key=api_key)
    prompt = {
        "vacancy_title": vacancy.title,
        "vacancy_description": vacancy.description,
        "resume_text": resume_text[:24000],
        "report_type": report_type,
    }
    response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a senior recruiter and ATS analyst. Return strict JSON with keys: "
                    "candidate_name, score, recommendation, summary, strengths, risks, "
                    "missing_requirements, interview_questions, skill_matches. score is 0-100. "
                    "skill_matches is an array of objects with name and status. Use Russian."
                ),
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    )
    payload = json.loads(response.choices[0].message.content or "{}")
    return AtsResult(
        candidate_name=str(payload.get("candidate_name") or "Кандидат не определен"),
        vacancy_title=vacancy.title,
        score=_clamp_score(payload.get("score", 0)),
        recommendation=str(payload.get("recommendation") or "Требуется ручная проверка"),
        summary=str(payload.get("summary") or ""),
        strengths=_as_list(payload.get("strengths")),
        risks=_as_list(payload.get("risks")),
        missing_requirements=_as_list(payload.get("missing_requirements")),
        interview_questions=_as_list(payload.get("interview_questions")),
        skill_matches=[
            SkillMatch(name=str(item.get("name", "")), status=str(item.get("status", "")))
            for item in payload.get("skill_matches", [])
            if isinstance(item, dict)
        ],
    )


def _evaluate_locally(resume_text: str, vacancy: Vacancy) -> AtsResult:
    vacancy_terms = _keywords(vacancy.description)
    resume_terms = set(_keywords(resume_text))
    matched = [term for term in vacancy_terms if term in resume_terms]
    missing = [term for term in vacancy_terms if term not in resume_terms]
    score = round((len(matched) / max(len(vacancy_terms), 1)) * 100)

    if score >= 75:
        recommendation = "Рекомендован к интервью"
    elif score >= 50:
        recommendation = "Подходит частично, нужна уточняющая проверка"
    else:
        recommendation = "Низкое совпадение с вакансией"

    return AtsResult(
        candidate_name=_guess_candidate_name(resume_text),
        vacancy_title=vacancy.title,
        score=score,
        recommendation=recommendation,
        summary=f"Автоматическая оценка нашла {len(matched)} совпадений из {len(vacancy_terms)} ключевых требований вакансии.",
        strengths=[f"Совпадает требование: {term}" for term in matched[:8]] or ["Явных совпадений мало"],
        risks=[f"Не найдено в резюме: {term}" for term in missing[:8]],
        missing_requirements=missing[:12],
        interview_questions=[f"Расскажите подробнее про опыт с {term}." for term in matched[:5]] or ["Какие задачи из вакансии кандидат выполнял в последних проектах?"],
        skill_matches=[SkillMatch(term, "найдено" if term in resume_terms else "не найдено") for term in vacancy_terms[:20]],
    )


def _keywords(text: str) -> list[str]:
    words = re.findall(r"[A-Za-zА-Яа-я0-9+#.]{3,}", text.lower())
    stop = {"для", "или", "and", "the", "with", "без", "как", "что", "это", "опыт", "работы", "years", "year", "команда", "проект"}
    seen: set[str] = set()
    result: list[str] = []
    for word in words:
        if word in stop or word.isdigit() or word in seen:
            continue
        seen.add(word)
        result.append(word)
    return result[:80]


def _guess_candidate_name(text: str) -> str:
    for line in text.splitlines()[:10]:
        line = line.strip()
        if 2 <= len(line.split()) <= 4 and not any(ch.isdigit() for ch in line):
            return line[:80]
    return "Кандидат не определен"


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _clamp_score(value: object) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(score, 100))
