import json
import os
import sys
import urllib.request
from datetime import date
from pathlib import Path

BASE = os.environ.get("API_BASE", "http://localhost:8010")
# Уникальный день для запуска — сегодня (староста создаёт рапортички только за текущий день)
_TEST_DAY = (date.today().year, date.today().month, date.today().day)

SAMPLE_DOCX = Path("/home/Utena/Desktop/report_card/!Рапортичка.docx")


def run_day():
    return _TEST_DAY


def day_str():
    y, m, d = run_day()
    return f"{y:04d}-{m:02d}-{d:02d}"


def req(method, path, token=None, body=None, files=None):
    url = BASE + path
    headers = {}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if files is not None:
        boundary = "----testboundary"
        parts = []
        for k, v in files.items():
            parts.append(
                ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; "
                 "filename=\"%s\"\r\nContent-Type: application/octet-stream\r\n\r\n"
                 % (boundary, k, v[0])).encode()
            )
            parts.append(v[1])
            parts.append(b"\r\n")
        parts.append((f"--{boundary}--\r\n").encode())
        data = b"".join(parts)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"

    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            raw = resp.read()
            ct = resp.headers.get("Content-Type", "")
            return resp.status, raw, ct
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type", "")


def ok(label, cond):
    print(("PASS" if cond else "FAIL"), "-", label)
    if not cond:
        sys.exit(1)


def login(user, pw):
    s, raw, _ = req("POST", "/auth/login", body={"login": user, "password": pw})
    ok(f"login {user}", s == 200)
    return json.loads(raw)["access_token"]


# Запуск:
#   1) python seed.py
#   2) python tests/setup_teacher2.py
#   3) python tests/test_api.py
if __name__ == "__main__":
    mon = login("starosta", "starosta123")
    tea = login("teacher", "teacher123")
    tea2 = login("teacher2", "teacher2")

    s, gr, _ = req("GET", "/groups", mon)
    groups = json.loads(gr)
    ok("groups list", s == 200 and len(groups) > 0)
    gid = groups[0]["id"]
    ok("group curator set", groups[0]["curator_id"] is not None)

    s, st, _ = req("GET", f"/students?group_id={gid}", mon)
    students = json.loads(st)
    ok("students count", len(students) >= 5)

    s, sub_r, _ = req("GET", "/subjects", mon)
    subjects = json.loads(sub_r)
    ok("subjects catalog global", s == 200 and len(subjects) >= 1)

    s, _, _ = req("POST", "/subjects", mon, body={"name": "Программирование"})
    ok("add subject (dedupe existing)", s == 200)

    s, sub_tea2, _ = req("GET", "/subjects", tea2)
    ok(
        "subject-teacher sees own subject",
        s == 200 and "[Физика]" in str([x["name"] for x in json.loads(sub_tea2)]),
    )

    s, groups_tea2, _ = req("GET", "/groups", tea2)
    g_tea2 = json.loads(groups_tea2)
    ok("subject-teacher sees group with own subject", s == 200 and any(g["id"] == gid for g in g_tea2))

    did = subjects[0]["id"]

    s, sess, _ = req("POST", "/sessions", mon, body={
        "group_id": gid, "date": day_str(), "pair_number": 1, "subject_id": did,
    })
    ok("create session", s == 201)
    session = json.loads(sess)
    sid = session["id"]
    ok("session has subject", session["subject_id"] == did)

    s, _, _ = req("PUT", f"/sessions/{sid}/records", mon, body={"records": [
        {"student_id": students[0]["id"], "mark": "late"},
        {"student_id": students[1]["id"], "mark": "absent"},
        {"student_id": students[2]["id"], "mark": "excused"},
        {"student_id": students[3]["id"], "mark": "present"},
    ]})
    ok("update records", s == 200)

    s, r, _ = req("GET", f"/sessions/{sid}", mon)
    detail = json.loads(r)
    marks = {x["student_id"]: x["mark"] for x in detail["records"]}
    ok("record marks set", marks[students[0]["id"]] == "late" and marks[students[1]["id"]] == "absent")

    s, tea2_sessions, _ = req("GET", f"/sessions?group_id={gid}", tea2)
    tea2_list = json.loads(tea2_sessions)
    ok("subject-teacher sees only own sessions", s == 200 and any(x["pair_number"] == 3 for x in tea2_list))

    s, all_sessions, _ = req("GET", f"/sessions?group_id={gid}", tea)
    ok("curator sees sessions", s == 200 and len(json.loads(all_sessions)) >= len(tea2_list))

    s, _, _ = req("POST", f"/sessions/{sid}/confirm", tea)
    ok("confirm by teacher", s == 200)

    s, _, _ = req("PUT", f"/sessions/{sid}/records", mon, body={"records": [
        {"student_id": students[0]["id"], "mark": "present"}]})
    ok("monitor cannot edit confirmed (403)", s == 403)

    s, _, _ = req("PUT", f"/sessions/{sid}/records", tea, body={"records": [
        {"student_id": students[0]["id"], "mark": "present"}]})
    ok("teacher cannot edit records (403)", s == 403)

    for fmt in ("pdf", "docx", "xlsx"):
        s, raw, ct = req("GET", f"/export/session/{sid}?fmt={fmt}", tea)
        ok(f"export session {fmt} ({ct[:40]}... len={len(raw)}B)", s == 200 and len(raw) > 1000)

    s, raw, ct = req("GET", f"/export/group/{gid}?date_from={day_str()}&date_to={day_str()}&fmt=pdf", tea)
    ok("export group day pdf", s == 200 and len(raw) > 1000)

    s2, sess2, _ = req("POST", "/sessions", mon, body={
        "group_id": gid, "date": day_str(), "pair_number": 2, "subject_id": did,
    })
    ok("create session pair2", s2 == 201)
    sid2 = json.loads(sess2)["id"]

    s, raw, ct = req("GET", f"/export/group/{gid}?date_from={day_str()}&date_to={day_str()}&fmt=docx", tea)
    ok("export group 2 pairs docx", s == 200 and len(raw) > 1000)

    s, raw2, _ = req("GET", f"/export/group/{gid}?date_from={day_str()}&date_to={day_str()}&fmt=pdf", tea2)
    ok("subject-teacher export own pairs only", s == 200 and len(raw2) > 1000)

    s, _, _ = req("POST", "/sessions", mon, body={
        "group_id": gid, "date": day_str(), "pair_number": 2, "subject_id": did,
    })
    ok("duplicate session rejected (409)", s == 409)

    if SAMPLE_DOCX.is_file():
        s, raw, ct = req("POST", "/upload/raport", mon, files={
            "file": ("raport.docx", SAMPLE_DOCX.read_bytes()),
        })
        ok("upload raport docx", s == 200)
        up = json.loads(raw)
        ok("parsed group", len(up["students"]) > 0)
        ok("parsed students", len(up["students"]) >= 5)
    else:
        print("SKIP - sample docx not found:", SAMPLE_DOCX)

    s, _, _ = req("POST", "/upload/raport/apply", mon, body={
        "group_name": "TEST.11.22.3", "group_year": 2026, "students": ["Демо Студент 01", "Демо Студент 02"],
    })
    ok("apply raport", s == 200)

    print("\nALL TESTS PASSED")