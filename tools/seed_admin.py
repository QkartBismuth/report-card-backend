"""Создание администратора в пустой базе данных.

Запуск в контейнере (из каталога с docker-compose.yml):

    docker compose exec -e ADMIN_PASSWORD=... api python tools/seed_admin.py

Логин задаётся переменной ADMIN_LOGIN (по умолчанию "admin"),
пароль — ADMIN_PASSWORD (обязательно). Учётка не создаётся повторно.
"""

import os
import sys

sys.path.insert(0, ".")

from auth import hash_password
from database import SessionLocal
from models import User, UserRole


def main() -> None:
    login = os.environ.get("ADMIN_LOGIN", "admin")
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        sys.exit("Задайте ADMIN_PASSWORD (и опционально ADMIN_LOGIN)")

    db = SessionLocal()
    try:
        if db.query(User).filter(User.login == login).first() is not None:
            print(f"Пользователь '{login}' уже существует")
            return
        db.add(
            User(
                login=login,
                password_hash=hash_password(password),
                full_name="Администратор системы",
                role=UserRole.admin,
            )
        )
        db.commit()
        print(f"Администратор '{login}' создан")
    finally:
        db.close()


if __name__ == "__main__":
    main()
