# Telegram ATS Bot

Бот принимает резюме в форматах PDF, DOC, DOCX, RTF, сравнивает его с сохраненной вакансией и возвращает PDF-отчет: короткий или полный.

## Возможности

- хранение вакансий в SQLite;
- прием резюме через Telegram;
- извлечение текста из PDF, DOCX, RTF и DOC;
- оценка совпадения резюме с вакансией;
- LLM-оценка через OpenAI при наличии `OPENAI_API_KEY`;
- локальный keyword-scoring fallback без LLM;
- PDF-отчеты `short` и `full`.

## Установка

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Заполните `.env`:

```env
BOT_TOKEN=...
OPENAI_API_KEY=...
ADMIN_IDS=123456789
```

`OPENAI_API_KEY` можно не указывать, но тогда оценка будет простой keyword-based.

## Запуск

```bash
python main.py
```

## Команды

- `/add_vacancy` - добавить вакансию;
- `/vacancies` - показать список вакансий;
- `/delete_vacancy ID` - удалить вакансию;
- `/analyze ID short` - короткий отчет;
- `/analyze ID full` - полный отчет.

## Примечания по DOC

Старый `.doc` является бинарным форматом. Для его чтения на сервере нужен один из инструментов: `antiword`, `catdoc` или LibreOffice (`soffice`). Форматы PDF, DOCX и RTF читаются Python-библиотеками из `requirements.txt`.
