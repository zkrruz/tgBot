from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class Vacancy:
    id: int
    title: str
    description: str
    created_at: str


class Storage:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vacancies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def add_vacancy(self, title: str, description: str) -> int:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO vacancies(title, description, created_at) VALUES (?, ?, ?)",
                (title.strip(), description.strip(), now),
            )
            return int(cur.lastrowid)

    def list_vacancies(self) -> list[Vacancy]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, title, description, created_at FROM vacancies ORDER BY id DESC"
            ).fetchall()
        return [Vacancy(**dict(row)) for row in rows]

    def get_vacancy(self, vacancy_id: int) -> Vacancy | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, title, description, created_at FROM vacancies WHERE id = ?",
                (vacancy_id,),
            ).fetchone()
        return Vacancy(**dict(row)) if row else None

    def delete_vacancy(self, vacancy_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM vacancies WHERE id = ?", (vacancy_id,))
            return cur.rowcount > 0
