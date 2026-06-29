from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    openai_api_key: str | None
    openai_model: str
    admin_ids: set[int]
    database_path: Path
    reports_dir: Path


def _parse_admin_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for item in raw.split(","):
        item = item.strip()
        if item:
            ids.add(int(item))
    return ids


def load_settings() -> Settings:
    load_dotenv(encoding="utf-8-sig")
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required. Put it in .env or environment variables.")
    return Settings(
        bot_token=bot_token,
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS", "")),
        database_path=Path(os.getenv("DATABASE_PATH", "data/ats_bot.sqlite3")),
        reports_dir=Path(os.getenv("REPORTS_DIR", "reports")),
    )

