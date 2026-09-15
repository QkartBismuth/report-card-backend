"""Миграция: роль «Завотделения», назначение групп, комментарий НН, отметка «о».

Применяется идемпотентно к рабочей БД (PostgreSQL 12+).
Запуск: DATABASE_URL=postgresql://raport@localhost:5432/raport python tools/migrate_2026_09.py
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from database import engine


def _has_column(conn, table: str, column: str) -> bool:
    return (
        conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        ).first()
        is not None
    )


def _enum_has_value(conn, enum_name: str, value: str) -> bool:
    return (
        conn.execute(
            text(
                "SELECT 1 FROM pg_enum e "
                "JOIN pg_type t ON e.enumtypid = t.oid "
                "WHERE t.typname = :e AND e.enumlabel = :v"
            ),
            {"e": enum_name, "v": value},
        ).first()
        is not None
    )


def main():
    with engine.begin() as conn:
        if not _has_column(conn, "groups", "department_head_id"):
            conn.execute(
                text(
                    "ALTER TABLE groups "
                    "ADD COLUMN department_head_id INTEGER "
                    "REFERENCES users(id)"
                )
            )
            print("groups.department_head_id добавлен")
        else:
            print("groups.department_head_id уже есть")

        if not _has_column(conn, "attendance_records", "comment"):
            conn.execute(text("ALTER TABLE attendance_records ADD COLUMN comment TEXT"))
            print("attendance_records.comment добавлен")
        else:
            print("attendance_records.comment уже есть")

    # ALTER TYPE ... ADD VALUE выполняем вне явной транзакции.
    conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        for enum_name, value in (
            ("mark_value", "o"),
            ("user_role", "department_head"),
        ):
            if _enum_has_value(conn, enum_name, value):
                print(f"enum {enum_name}.'{value}' уже есть")
                continue
            conn.execute(
                text(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{value}'")
            )
            print(f"enum {enum_name}.'{value}' добавлен")
    finally:
        conn.close()

    print("Готово.")


if __name__ == "__main__":
    main()