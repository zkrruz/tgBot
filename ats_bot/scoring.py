from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass

import requests

from ats_bot.storage import Vacancy


DEFAULT_SYSTEM_ANALYST_MARKET = """
Системный аналитик: REST API, SOAP, OpenAPI, Swagger, Postman, SQL, PostgreSQL,
Kafka, RabbitMQ, BPMN, UML, ERD, sequence diagram, activity diagram, JSON, XML,
интеграции, микросервисы, требования, user story, use case, acceptance criteria,
Confluence, Jira, бизнес-процессы, документация, нефункциональные требования,
финтех, банки, платежи, высоконагруженные системы, Agile, Scrum.
"""

QWEN_DEFAULT_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"


@dataclass(frozen=True)
class SkillMatch:
    name: str
    status: str


@dataclass(frozen=True)
class MarketMatch:
    strong: int
    medium: int
    low: int
    sample_size: int


@dataclass(frozen=True)
class ScoreBlock:
    structure: int
    content: int
    standards: int
    rules: int
    first_impression: int
    skills_coverage: int
    hard_skills: int
    domain_fit: int
    ats_score: int


@dataclass(frozen=True)
class AtsResult:
    candidate_name: str
    role: str
    score: int
    grade: str
    level: str
    primary_domain: str
    recommendation: str
    summary: str
    market_match: MarketMatch
    score_block: ScoreBlock
    avg_keyword_matches: float
    strengths: list[str]
    risks: list[str]
    missing_requirements: list[str]
    quick_actions: list[str]
    deep_actions: list[str]
    employer_view: list[tuple[str, str]]
    interview_questions: list[str]
    skill_matches: list[SkillMatch]


HARD_SKILLS = [
    "REST", "REST API", "SOAP", "OpenAPI", "Swagger", "Postman", "SQL", "PostgreSQL",
    "Kafka", "RabbitMQ", "BPMN", "UML", "ERD", "JSON", "XML", "Confluence", "Jira",
    "микросервис", "интеграц", "API", "sequence", "activity", "use case", "user story",
]

DOMAIN_TERMS = {
    "Финансовые технологии (FinTech)": ["банк", "fintech", "платеж", "кредит", "скоринг", "эквайринг", "fraud", "транзакц"],
    "E-commerce": ["e-commerce", "маркетплейс", "заказ", "каталог", "retail", "доставка", "корзина"],
    "Enterprise / B2B": ["b2b", "enterprise", "erp", "crm", "корпоратив", "документооборот"],
    "GovTech": ["гос", "государ", "мфц", "реестр", "ведомств"],
}


def evaluate_resume_against_market(
    resume_text: str,
    vacancies: list[Vacancy],
    report_type: str,
    qwen_api_key: str | None,
    qwen_model: str,
    qwen_base_url: str = QWEN_DEFAULT_BASE_URL,
) -> AtsResult:
    if qwen_api_key:
        try:
            return _evaluate_with_qwen(
                resume_text,
                vacancies,
                report_type,
                qwen_api_key,
                qwen_model,
                qwen_base_url,
            )
        except Exception:
            return _evaluate_locally(resume_text, vacancies)
    return _evaluate_locally(resume_text, vacancies)


# Backward-compatible wrapper for the first prototype.
def evaluate_resume(
    resume_text: str,
    vacancy: Vacancy,
    report_type: str,
    qwen_api_key: str | None,
    qwen_model: str,
    qwen_base_url: str = QWEN_DEFAULT_BASE_URL,
) -> AtsResult:
    return evaluate_resume_against_market(
        resume_text,
        [vacancy],
        report_type,
        qwen_api_key,
        qwen_model,
        qwen_base_url,
    )


def _evaluate_with_qwen(
    resume_text: str,
    vacancies: list[Vacancy],
    report_type: str,
    api_key: str,
    model: str,
    base_url: str,
) -> AtsResult:
    local = _evaluate_locally(resume_text, vacancies)
    market_text = "\n\n".join(f"{v.title}\n{v.description}" for v in vacancies[:80])
    if not market_text:
        market_text = DEFAULT_SYSTEM_ANALYST_MARKET

    response = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json={
            "model": model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Ты senior ATS analyst для кандидатов на роль системного аналитика. "
                        "Верни только валидный JSON на русском без markdown. Ключи: "
                        "candidate_name, summary, recommendation, level, primary_domain, "
                        "strengths, risks, missing_requirements, quick_actions, deep_actions, "
                        "interview_questions, employer_view. employer_view - массив объектов "
                        "с keys name,value. Не выдумывай факты, опирайся на резюме и рынок."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "resume_text": resume_text[:26000],
                            "market_dataset_sample": market_text[:28000],
                            "report_type": report_type,
                            "local_metrics": {
                                "score": local.score,
                                "grade": local.grade,
                                "level": local.level,
                                "domain": local.primary_domain,
                                "sample_size": local.market_match.sample_size,
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        },
        timeout=60,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    payload = _json_from_model_content(content)
    return AtsResult(
        candidate_name=str(payload.get("candidate_name") or local.candidate_name),
        role=local.role,
        score=local.score,
        grade=local.grade,
        level=str(payload.get("level") or local.level),
        primary_domain=str(payload.get("primary_domain") or local.primary_domain),
        recommendation=str(payload.get("recommendation") or local.recommendation),
        summary=str(payload.get("summary") or local.summary),
        market_match=local.market_match,
        score_block=local.score_block,
        avg_keyword_matches=local.avg_keyword_matches,
        strengths=_as_list(payload.get("strengths")) or local.strengths,
        risks=_as_list(payload.get("risks")) or local.risks,
        missing_requirements=_as_list(payload.get("missing_requirements")) or local.missing_requirements,
        quick_actions=_as_list(payload.get("quick_actions")) or local.quick_actions,
        deep_actions=_as_list(payload.get("deep_actions")) or local.deep_actions,
        employer_view=_employer_view(payload.get("employer_view")) or local.employer_view,
        interview_questions=_as_list(payload.get("interview_questions")) or local.interview_questions,
        skill_matches=local.skill_matches,
    )


def _json_from_model_content(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _evaluate_locally(resume_text: str, vacancies: list[Vacancy]) -> AtsResult:
    market_texts = [v.description for v in vacancies if v.description.strip()]
    if not market_texts:
        market_texts = [DEFAULT_SYSTEM_ANALYST_MARKET]

    resume_lower = resume_text.lower()
    resume_terms = set(_keywords(resume_text, limit=500))
    market_terms = _market_keywords(market_texts)
    required_terms = [term for term, _ in market_terms[:80]]
    matched = [term for term in required_terms if term in resume_terms or term.lower() in resume_lower]
    missing = [term for term in required_terms if term not in matched]

    per_vacancy = [_vacancy_match_score(resume_terms, text) for text in market_texts]
    strong = sum(1 for score in per_vacancy if score >= 70)
    medium = sum(1 for score in per_vacancy if 40 <= score < 70)
    low = sum(1 for score in per_vacancy if score < 40)
    sample_size = len(per_vacancy)

    structure = _structure_score(resume_text)
    standards = _standards_score(resume_text)
    rules = _rules_score(resume_text)
    hard_skills = round(_coverage(_skill_hits(resume_text, HARD_SKILLS), HARD_SKILLS) * 100)
    skills_coverage = round(len(matched) / max(len(required_terms[:45]), 1) * 100)
    skills_coverage = _clamp_score(skills_coverage)
    domain, domain_fit = _domain_fit(resume_text)
    content = _content_score(resume_text, hard_skills, domain_fit)
    ats_score = round(skills_coverage * 0.38 + hard_skills * 0.24 + structure * 0.18 + standards * 0.1 + rules * 0.1)
    first_impression = _first_impression_score(resume_text, structure, content)
    score = _clamp_score(round(ats_score * 0.55 + content * 0.2 + first_impression * 0.15 + domain_fit * 0.1))

    level = _level(resume_text)
    grade = _grade(score)
    avg_matches = round(sum(len(set(_keywords(text, limit=80)) & resume_terms) for text in market_texts) / sample_size, 2)

    recommendation = _recommendation(score)
    summary = (
        f"Резюме похоже на профиль {level} системного аналитика. "
        f"По рыночной выборке найдено {strong} сильных и {medium} средних совпадений из {sample_size}. "
        f"Главная зона роста: {', '.join(missing[:3]) if missing else 'усилить измеримые достижения'}."
    )

    skill_matches = [
        SkillMatch(name=skill, status="найдено" if _contains_skill(resume_text, skill) else "не найдено")
        for skill in HARD_SKILLS
    ]

    return AtsResult(
        candidate_name=_guess_candidate_name(resume_text),
        role="Системный аналитик",
        score=score,
        grade=grade,
        level=level,
        primary_domain=domain,
        recommendation=recommendation,
        summary=summary,
        market_match=MarketMatch(strong=strong, medium=medium, low=low, sample_size=sample_size),
        score_block=ScoreBlock(
            structure=structure,
            content=content,
            standards=standards,
            rules=rules,
            first_impression=first_impression,
            skills_coverage=skills_coverage,
            hard_skills=hard_skills,
            domain_fit=domain_fit,
            ats_score=ats_score,
        ),
        avg_keyword_matches=avg_matches,
        strengths=_strengths(matched, hard_skills, domain),
        risks=_risks(missing, structure, first_impression),
        missing_requirements=missing[:16],
        quick_actions=[
            "Добавить 5-7 ключевых навыков системного аналитика на первую страницу резюме.",
            "Переписать 2-3 достижения по формуле: действие - метрика - бизнес-эффект.",
            "Добавить стек в каждый релевантный опыт: API, SQL, брокеры, нотации, инструменты.",
        ],
        deep_actions=[
            "Пересобрать блок 'О себе' под целевую роль системного аналитика и домен рынка.",
            "Обновить 6-8 буллетов опыта так, чтобы было видно масштаб, сложность и результат.",
            "Добавить отдельный блок проектов: продукт, роль, интеграции, артефакты, эффект.",
        ],
        employer_view=[
            ("Оценка уровня", level),
            ("Лучший домен", domain),
            ("Стиль резюме", _writing_style(resume_text)),
            ("Первое впечатление рекрутера", f"{first_impression} / 100"),
            ("ATS Score", f"{ats_score} / 100"),
            ("Совпадение навыков", f"{hard_skills} / 100"),
        ],
        interview_questions=[f"Расскажите подробнее про опыт с {term}." for term in matched[:6]]
        or ["Какие системные артефакты вы готовили на последних проектах?"],
        skill_matches=skill_matches,
    )


def _vacancy_match_score(resume_terms: set[str], vacancy_text: str) -> int:
    terms = _keywords(vacancy_text, limit=80)
    if not terms:
        return 0
    matched = sum(1 for term in terms if term in resume_terms)
    return _clamp_score(round(matched / len(terms) * 100))


def _market_keywords(texts: list[str]) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for text in texts:
        counter.update(_keywords(text, limit=120))
    for skill in HARD_SKILLS:
        if any(_contains_skill(text, skill) for text in texts):
            counter[skill.lower()] += 5
    return counter.most_common(120)


def _keywords(text: str, limit: int = 80) -> list[str]:
    words = re.findall(r"[A-Za-zА-Яа-я0-9+#.]{3,}", text.lower())
    stop = {
        "для", "или", "and", "the", "with", "без", "как", "что", "это", "опыт", "работы",
        "years", "year", "команда", "проект", "работа", "будет", "умение", "знание", "задачи",
        "требования", "участие", "разработка", "системный", "аналитик", "анализа",
    }
    seen: set[str] = set()
    result: list[str] = []
    for word in words:
        if word in stop or word.isdigit() or word in seen:
            continue
        seen.add(word)
        result.append(word)
    return result[:limit]


def _structure_score(text: str) -> int:
    lower = text.lower()
    score = 35
    if re.search(r"\+?\d[\d\s()\-]{8,}", text):
        score += 15
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text):
        score += 15
    for marker in ("опыт", "навыки", "образование", "о себе", "проекты"):
        if marker in lower:
            score += 8
    return _clamp_score(score)


def _standards_score(text: str) -> int:
    lower = text.lower()
    score = 100
    for bad in ("семейное положение", "паспорт", "адрес регистрации", "отчество"):
        if bad in lower:
            score -= 12
    if len(text) < 1200:
        score -= 18
    if len(text) > 18000:
        score -= 10
    return _clamp_score(score)


def _rules_score(text: str) -> int:
    lower = text.lower()
    action_verbs = ["спроект", "опис", "внедр", "интегр", "модел", "декомпоз", "оптимиз", "автоматиз"]
    score = 45 + min(35, sum(7 for verb in action_verbs if verb in lower))
    if re.search(r"\d+\s*(%|процент|млн|тыс|k\+|час|дн)", lower):
        score += 20
    return _clamp_score(score)


def _content_score(text: str, hard_skills: int, domain_fit: int) -> int:
    has_metrics = bool(re.search(r"\d+\s*(%|процент|млн|тыс|k\+|час|дн)", text.lower()))
    base = round(hard_skills * 0.55 + domain_fit * 0.25 + (100 if has_metrics else 45) * 0.2)
    return _clamp_score(base)


def _first_impression_score(text: str, structure: int, content: int) -> int:
    first_page = text[:2500].lower()
    first_page_hits = sum(1 for skill in HARD_SKILLS if skill.lower() in first_page)
    score = round(structure * 0.35 + content * 0.45 + min(first_page_hits * 6, 20))
    return _clamp_score(score)


def _skill_hits(text: str, skills: list[str]) -> list[str]:
    return [skill for skill in skills if _contains_skill(text, skill)]


def _contains_skill(text: str, skill: str) -> bool:
    return skill.lower() in text.lower()


def _coverage(hits: list[str], required: list[str]) -> float:
    return min(1.0, len(hits) / max(len(required), 1))


def _domain_fit(text: str) -> tuple[str, int]:
    lower = text.lower()
    scores = {domain: sum(1 for term in terms if term in lower) for domain, terms in DOMAIN_TERMS.items()}
    domain, hits = max(scores.items(), key=lambda item: item[1])
    if hits == 0:
        return "Домен не выражен явно", 45
    return domain, _clamp_score(45 + hits * 14)


def _level(text: str) -> str:
    lower = text.lower()
    years = [float(x.replace(",", ".")) for x in re.findall(r"(\d+[,.]?\d*)\s*(?:лет|года|год|years)", lower)]
    max_years = max(years) if years else 0
    if "senior" in lower or "ведущ" in lower or max_years >= 5:
        return "Senior"
    if "middle" in lower or max_years >= 2:
        return "Middle"
    return "Junior"


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 85:
        return "B+"
    if score >= 75:
        return "C+"
    if score >= 65:
        return "C"
    if score >= 50:
        return "D"
    return "E"


def _recommendation(score: int) -> str:
    if score >= 85:
        return "Высокая готовность к откликам"
    if score >= 70:
        return "Можно откликаться, но стоит усилить резюме"
    if score >= 55:
        return "Перед активными откликами лучше доработать резюме"
    return "Резюме требует переработки перед откликами"


def _strengths(matched: list[str], hard_skills: int, domain: str) -> list[str]:
    items = []
    if hard_skills >= 70:
        items.append("Хорошо читается технический стек системного аналитика.")
    if domain != "Домен не выражен явно":
        items.append(f"Есть выраженный доменный фокус: {domain}.")
    items.extend(f"Рынок часто ищет: {term}" for term in matched[:5])
    return items[:8] or ["Есть базовая релевантность роли системного аналитика."]


def _risks(missing: list[str], structure: int, first_impression: int) -> list[str]:
    items = []
    if structure < 70:
        items.append("Структура резюме может мешать ATS корректно разобрать профиль.")
    if first_impression < 70:
        items.append("На первом экране мало сильных сигналов для рекрутера.")
    items.extend(f"Не хватает рыночного ключевого слова: {term}" for term in missing[:5])
    return items[:8] or ["Критичных рисков по автоматической проверке не найдено."]


def _writing_style(text: str) -> str:
    lower = text.lower()
    if re.search(r"\d+\s*(%|процент|млн|тыс|k\+)", lower):
        return "продающий, с метриками"
    if any(word in lower for word in ("отвечал", "участвовал", "занимался")):
        return "описательный, стоит усилить результатами"
    return "нейтральный"


def _guess_candidate_name(text: str) -> str:
    for line in text.splitlines()[:12]:
        line = line.strip()
        if 2 <= len(line.split()) <= 4 and not any(ch.isdigit() for ch in line):
            if not any(x in line.lower() for x in ("резюме", "телефон", "email", "опыт")):
                return line[:80]
    return "Кандидат"


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _employer_view(value: object) -> list[tuple[str, str]]:
    if not isinstance(value, list):
        return []
    result: list[tuple[str, str]] = []
    for item in value:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("key") or "").strip()
            val = str(item.get("value") or "").strip()
            if name and val:
                result.append((name, val))
    return result


def _clamp_score(value: int) -> int:
    return max(0, min(int(value), 100))



