from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import psycopg
from psycopg.rows import dict_row


class Database:
    def __init__(self, url: str) -> None:
        if not url:
            raise ValueError("SUPABASE_DB_URL is required for database operations")
        self.url = url

    def execute(self, sql: str, params: Mapping[str, Any] | None = None) -> None:
        with psycopg.connect(self.url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params or {})
            conn.commit()

    def fetch_all(self, sql: str, params: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        with psycopg.connect(self.url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute(sql, params or {})
            return list(cur.fetchall())

    def upsert_rows(self, table: str, rows: Iterable[Mapping[str, Any]], conflict: str) -> None:
        materialized = list(rows)
        if not materialized:
            return
        columns = list(materialized[0].keys())
        placeholders = ", ".join(f"%({column})s" for column in columns)
        assignments = ", ".join(f"{column}=excluded.{column}" for column in columns)
        quoted_columns = ", ".join(columns)
        sql = (
            f"insert into {table} ({quoted_columns}) values ({placeholders}) "
            f"on conflict ({conflict}) do update set {assignments}"
        )
        with psycopg.connect(self.url) as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, materialized)
            conn.commit()
