import json
import urllib.error
import urllib.request

BASE_URL = "http://mob.kansk-tc.ru/ktc-api"

DAY_TO_NUM = {
    "Пн": 1,
    "Вт": 2,
    "Ср": 3,
    "Чт": 4,
    "Пт": 5,
    "Сб": 6,
    "Вс": 7,
    "Пнд": 1,
    "Вторник": 2,
}


class KtcError(Exception):
    pass


def _fetch(path: str, timeout: int = 10) -> dict | list:
    url = BASE_URL.rstrip("/") + "/" + path.lstrip("/")
    req = urllib.request.Request(url, headers={"User-Agent": "raporticka/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
        raise KtcError(f"KTK API недоступен ({url}): {e}") from e


def fetch_branches():
    data = _fetch("branches")
    return [{"id": b.get("id"), "title": b.get("title", "")} for b in data if b.get("id")]


def fetch_courses(branch_id: int):
    data = _fetch(f"courses/{branch_id}")
    result = []
    for c in data:
        groups = [
            {"id": g.get("id"), "title": g.get("title", "")}
            for g in c.get("groups", [])
            if g.get("id")
        ]
        result.append({"course": c.get("course"), "groups": groups})
    return result


def fetch_teachers(branch_id: int):
    data = _fetch(f"teachers-list/{branch_id}")
    teachers = []
    for t in data.get("teachers", []):
        name = (t.get("name") or "").strip()
        if t.get("id"):
            teachers.append({"id": t.get("id"), "name": name})
    return teachers


def fetch_timetable(group_id: int, week: int | None = None):
    path = f"timetable/{group_id}"
    if week is not None:
        path += f"/{week}"
    return _fetch(path)


def day_of_week_num(title: str) -> int | None:
    key = (title or "").strip()
    return DAY_TO_NUM.get(key)