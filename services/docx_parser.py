import io
import re
import zipfile
from typing import Optional
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{%s}" % W_NS


def _extract_tables(docx_bytes: bytes):
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    tables = []
    for tbl in root.iter(W + "tbl"):
        table = []
        for tr in tbl.findall(W + "tr"):
            row = []
            for tc in tr.findall(W + "tc"):
                text = "".join(
                    t.text or ""
                    for t in tc.iter(W + "t")
                )
                row.append(text.strip())
            table.append(row)
        tables.append(table)
    return tables


def parse_raport(docx_bytes: bytes) -> dict:
    """Извлекает группу, год и список студентов из DOCX рапортички."""
    tables = _extract_tables(docx_bytes)

    group_name: Optional[str] = None
    year: Optional[int] = None
    students: list[str] = []

    for table in tables:
        for row in table:
            joined = " ".join(row)

            m = re.search(r"Группа\s*([A-Za-zА-Яа-яЁё]{1,5}\.\d{2}\.\d{2}\.\d+)", joined)
            if m and not group_name:
                candidate = m.group(1).strip()
                if re.match(r"^[-А-Яа-яЁёA-Za-z.0-9]+$", candidate):
                    group_name = candidate

            if year is None:
                ym = re.search(r"(20\d{2})\s*г", joined) or re.search(r"\b(20\d{2})\b", joined)
                if ym:
                    y = int(ym.group(1))
                    if 2000 <= y <= 2100:
                        year = y

            for cell in row:
                name = cell.strip()
                if not name or " " not in name:
                    continue
                name = re.sub(r"\s+", " ", name)
                if re.search(r"Подпись|писатель", name):
                    continue
                if _looks_like_student(name):
                    if name not in students:
                        students.append(name)

    return {
        "group_name": group_name or "Не найдена",
        "group_year": year,
        "students": students,
    }


def _looks_like_student(name: str) -> bool:
    if re.search(r"\s", name) is None:
        return False
    parts = [p for p in name.split() if p]
    if not (2 <= len(parts) <= 4):
        return False
    for p in parts:
        if not re.match(r"^[А-Яа-яЁёA-Za-z\-']+$", p):
            return False
    return True