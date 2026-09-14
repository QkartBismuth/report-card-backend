import re
import unicodedata

DAY_ABBR_FULL = {
    1: "Пн",
    2: "Вт",
    3: "Ср",
    4: "Чт",
    5: "Пт",
    6: "Сб",
    7: "Вс",
}


def normalize_text(value: str | None) -> str:
    """Нормализация для сравнения названий: нижний регистр, без пунктуации/пробелов."""
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE)


def surname_key(value: str | None) -> str:
    """Первый токен строки (фамилия), нормализованный."""
    if not value:
        return ""
    first = (value or "").strip().split()[0] if value.strip() else ""
    return normalize_text(first)


def match_subject_by_name(name: str, subjects) -> object | None:
    """Находит существующий предмет по нормализованному имени."""
    key = normalize_text(name)
    if not key:
        return None
    for s in subjects:
        if normalize_text(s.name) == key:
            return s
    return None


def match_teacher_by_surname(short_name: str, teachers) -> object | None:
    """Ищет аккаунт преподавателя рапортички по фамилии (первый токен full_name)."""
    key = surname_key(short_name)
    if not key:
        return None
    for t in teachers:
        if surname_key(t.full_name) == key:
            return t
    return None


def ktc_teacher_surname(full_name: str) -> str:
    """Из ФИО преподавателя КТК возвращает фамилию (первый токен)."""
    return (full_name or "").strip().split()[0] if (full_name or "").strip() else ""