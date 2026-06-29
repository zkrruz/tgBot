from __future__ import annotations

import tempfile
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ats_bot.config import Settings
from ats_bot.parsers import SUPPORTED_EXTENSIONS, extract_resume_text
from ats_bot.reports import build_report
from ats_bot.scoring import evaluate_resume_against_market
from ats_bot.storage import Storage


class VacancyStates(StatesGroup):
    waiting_title = State()
    waiting_description = State()


class ResumeStates(StatesGroup):
    waiting_report_type = State()


def build_dispatcher(settings: Settings, storage: Storage) -> Dispatcher:
    router = Router()

    def is_admin(message: Message) -> bool:
        return not settings.admin_ids or (message.from_user and message.from_user.id in settings.admin_ids)

    @router.message(Command("start"))
    async def start(message: Message) -> None:
        await message.answer(
            "Привет! Я помогу оценить резюме как ATS-система.\n\n"
            "Загрузите резюме файлом: PDF, DOC, DOCX или RTF. "
            "Я сравню его с рыночной базой вакансий системного аналитика и подготовлю PDF-отчет.\n\n"
            "Доступны два формата: краткий отчет и полный отчет."
        )

    @router.message(Command("help"))
    async def help_message(message: Message) -> None:
        await message.answer(
            "Для кандидата: просто отправьте файл резюме.\n\n"
            "Для администратора датасета:\n"
            "/add_market_vacancy - добавить вакансию в рыночную базу\n"
            "/dataset - размер базы вакансий\n"
            "/vacancies - список вакансий\n"
            "/delete_vacancy ID - удалить вакансию"
        )

    @router.message(Command("add_market_vacancy", "add_vacancy"))
    async def add_vacancy(message: Message, state: FSMContext) -> None:
        if not is_admin(message):
            await message.answer("Пополнять рыночный датасет может только администратор.")
            return
        await state.set_state(VacancyStates.waiting_title)
        await message.answer("Пришлите название вакансии, например: Системный аналитик - банк.")

    @router.message(VacancyStates.waiting_title)
    async def vacancy_title(message: Message, state: FSMContext) -> None:
        await state.update_data(title=message.text or "Системный аналитик")
        await state.set_state(VacancyStates.waiting_description)
        await message.answer("Теперь пришлите полный текст вакансии с требованиями, задачами и стеком.")

    @router.message(VacancyStates.waiting_description)
    async def vacancy_description(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        vacancy_id = storage.add_vacancy(data["title"], message.text or "")
        await state.clear()
        await message.answer(f"Вакансия добавлена в рыночный датасет. ID: {vacancy_id}")

    @router.message(Command("dataset"))
    async def dataset(message: Message) -> None:
        count = len(storage.list_vacancies())
        if count:
            await message.answer(f"В рыночном датасете сейчас {count} вакансий.")
        else:
            await message.answer(
                "Рыночный датасет пока пуст. Бот использует базовый профиль системного аналитика. "
                "Добавьте вакансии командой /add_market_vacancy."
            )

    @router.message(Command("vacancies"))
    async def vacancies(message: Message) -> None:
        items = storage.list_vacancies()
        if not items:
            await message.answer("Пока нет сохраненных вакансий в рыночном датасете.")
            return
        text = "\n".join(f"{item.id}. {item.title}" for item in items[:40])
        if len(items) > 40:
            text += f"\n...и еще {len(items) - 40}"
        await message.answer(text)

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

    @router.message(F.document)
    async def resume_document(message: Message, state: FSMContext, bot: Bot) -> None:
        document = message.document
        filename = document.file_name or "resume"
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            await message.answer("Поддерживаются только PDF, DOC, DOCX и RTF.")
            return

        await message.answer("Принял резюме. Извлекаю текст и готовлю оценку рынка.")
        with tempfile.TemporaryDirectory() as tmp:
            resume_path = Path(tmp) / filename
            await bot.download(document, destination=resume_path)
            try:
                resume_text = extract_resume_text(resume_path)
            except Exception as exc:
                await message.answer(f"Не удалось прочитать резюме: {exc}")
                return

        if len(resume_text) < 80:
            await message.answer("В резюме слишком мало распознанного текста для оценки.")
            return

        await state.set_state(ResumeStates.waiting_report_type)
        await state.update_data(resume_text=resume_text)
        await message.answer(
            "Текст резюме распознан. Какой отчет подготовить?",
            reply_markup=_report_keyboard(),
        )

    @router.callback_query(ResumeStates.waiting_report_type, F.data.startswith("report:"))
    async def choose_report(callback: CallbackQuery, state: FSMContext) -> None:
        report_type = (callback.data or "report:short").split(":", 1)[1]
        if report_type not in {"short", "full"}:
            report_type = "short"

        data = await state.get_data()
        resume_text = data.get("resume_text")
        if not resume_text:
            await state.clear()
            await callback.message.answer("Резюме не найдено в сессии. Пришлите файл еще раз.")
            await callback.answer()
            return

        await callback.message.answer("Сравниваю резюме с рыночным датасетом и собираю PDF-отчет.")
        vacancies = storage.list_vacancies()
        try:
            result = evaluate_resume_against_market(
                resume_text=resume_text,
                vacancies=vacancies,
                report_type=report_type,
                qwen_api_key=settings.qwen_api_key,
                qwen_model=settings.qwen_model,
                qwen_base_url=settings.qwen_base_url,
            )
            report_path = build_report(result, report_type, settings.reports_dir)
        except Exception as exc:
            await callback.message.answer(f"Не удалось подготовить отчет: {exc}")
            await callback.answer()
            return

        await state.clear()
        await callback.message.answer_document(
            FSInputFile(report_path),
            caption=(
                f"Готово: {'полный' if report_type == 'full' else 'краткий'} отчет. "
                f"Оценка {result.score}/100, уровень {result.level}."
            ),
        )
        await callback.answer()

    @router.message(ResumeStates.waiting_report_type)
    async def report_choice_expected(message: Message) -> None:
        await message.answer("Выберите тип отчета кнопкой под предыдущим сообщением.")

    dp = Dispatcher()
    dp.include_router(router)
    return dp


def _report_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Краткий отчет", callback_data="report:short"),
                InlineKeyboardButton(text="Полный отчет", callback_data="report:full"),
            ]
        ]
    )




