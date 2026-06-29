from __future__ import annotations

import tempfile
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, Message

from ats_bot.config import Settings
from ats_bot.parsers import SUPPORTED_EXTENSIONS, extract_resume_text
from ats_bot.reports import build_report
from ats_bot.scoring import evaluate_resume
from ats_bot.storage import Storage


class VacancyStates(StatesGroup):
    waiting_title = State()
    waiting_description = State()


class ResumeStates(StatesGroup):
    waiting_resume = State()


def build_dispatcher(settings: Settings, storage: Storage) -> Dispatcher:
    router = Router()

    def is_admin(message: Message) -> bool:
        return not settings.admin_ids or (message.from_user and message.from_user.id in settings.admin_ids)

    @router.message(Command("start"))
    async def start(message: Message) -> None:
        await message.answer(
            "Привет! Я ATS-бот.\n\n"
            "Команды:\n"
            "/add_vacancy - добавить вакансию\n"
            "/vacancies - список вакансий\n"
            "/delete_vacancy ID - удалить вакансию\n"
            "/analyze - проверить резюме"
        )

    @router.message(Command("add_vacancy"))
    async def add_vacancy(message: Message, state: FSMContext) -> None:
        if not is_admin(message):
            await message.answer("Добавлять вакансии может только администратор.")
            return
        await state.set_state(VacancyStates.waiting_title)
        await message.answer("Пришлите название вакансии.")

    @router.message(VacancyStates.waiting_title)
    async def vacancy_title(message: Message, state: FSMContext) -> None:
        await state.update_data(title=message.text or "Без названия")
        await state.set_state(VacancyStates.waiting_description)
        await message.answer("Теперь пришлите полный текст вакансии с требованиями.")

    @router.message(VacancyStates.waiting_description)
    async def vacancy_description(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        vacancy_id = storage.add_vacancy(data["title"], message.text or "")
        await state.clear()
        await message.answer(f"Вакансия сохранена. ID: {vacancy_id}")

    @router.message(Command("vacancies"))
    async def vacancies(message: Message) -> None:
        items = storage.list_vacancies()
        if not items:
            await message.answer("Пока нет сохраненных вакансий.")
            return
        await message.answer("\n".join(f"{item.id}. {item.title}" for item in items))

    @router.message(Command("delete_vacancy"))
    async def delete_vacancy(message: Message) -> None:
        if not is_admin(message):
            await message.answer("Удалять вакансии может только администратор.")
            return
        parts = (message.text or "").split()
        if len(parts) != 2 or not parts[1].isdigit():
            await message.answer("Используйте формат: /delete_vacancy 12")
            return
        deleted = storage.delete_vacancy(int(parts[1]))
        await message.answer("Вакансия удалена." if deleted else "Вакансия не найдена.")

    @router.message(Command("analyze"))
    async def analyze(message: Message, state: FSMContext) -> None:
        parts = (message.text or "").split()
        if len(parts) < 2 or not parts[1].isdigit():
            await message.answer("Используйте: /analyze ID [short|full]\nНапример: /analyze 3 full")
            return
        vacancy = storage.get_vacancy(int(parts[1]))
        if not vacancy:
            await message.answer("Вакансия не найдена.")
            return
        report_type = parts[2].lower() if len(parts) > 2 else "short"
        if report_type not in {"short", "full"}:
            report_type = "short"
        await state.set_state(ResumeStates.waiting_resume)
        await state.update_data(vacancy_id=vacancy.id, report_type=report_type)
        await message.answer("Пришлите резюме файлом: PDF, DOC, DOCX или RTF.")

    @router.message(ResumeStates.waiting_resume, F.document)
    async def resume_document(message: Message, state: FSMContext, bot: Bot) -> None:
        document = message.document
        filename = document.file_name or "resume"
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            await message.answer("Поддерживаются только PDF, DOC, DOCX и RTF.")
            return

        data = await state.get_data()
        vacancy = storage.get_vacancy(int(data["vacancy_id"]))
        if not vacancy:
            await state.clear()
            await message.answer("Вакансия не найдена. Начните заново.")
            return

        await message.answer("Принял резюме. Извлекаю текст и готовлю отчет.")
        with tempfile.TemporaryDirectory() as tmp:
            resume_path = Path(tmp) / filename
            await bot.download(document, destination=resume_path)
            try:
                resume_text = extract_resume_text(resume_path)
                if len(resume_text) < 80:
                    await message.answer("В резюме слишком мало распознанного текста для оценки.")
                    return
                result = evaluate_resume(
                    resume_text=resume_text,
                    vacancy=vacancy,
                    report_type=data["report_type"],
                    api_key=settings.openai_api_key,
                    model=settings.openai_model,
                )
                report_path = build_report(result, data["report_type"], settings.reports_dir)
            except Exception as exc:
                await message.answer(f"Не удалось обработать резюме: {exc}")
                return

        await state.clear()
        await message.answer_document(
            FSInputFile(report_path),
            caption=f"Готово: {data['report_type']} отчет, оценка {result.score}/100.",
        )

    @router.message(ResumeStates.waiting_resume)
    async def resume_expected(message: Message) -> None:
        await message.answer("Нужно прислать резюме именно файлом.")

    dp = Dispatcher()
    dp.include_router(router)
    return dp
