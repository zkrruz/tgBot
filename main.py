from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from ats_bot.bot import build_dispatcher
from ats_bot.config import load_settings
from ats_bot.storage import Storage


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    storage = Storage(settings.database_path)
    bot = Bot(settings.bot_token)
    dispatcher = build_dispatcher(settings, storage)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
