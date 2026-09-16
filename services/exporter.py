import calendar
import io
import re
from collections import OrderedDict
from datetime import date

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt
from fpdf import FPDF
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session, joinedload

from models import AttendanceSession, Group, MarkValue

MARK_RU = {
    MarkValue.present: "",
    MarkValue.late: "н",
    MarkValue.absent: "нн",
    MarkValue.excused: "у",
    MarkValue.o: "о",
}

NOTO_REGULAR = "/usr/share/fonts/noto/NotoSans-Regular.ttf"
NOTO_BOLD = "/usr/share/fonts/noto/NotoSans-Bold.ttf"

TITLE = "Учет посещаемости занятий"


class _Sheet:
    """Одна страница рапортички — один день."""

    def __init__(self, day_date: date, group: Group, pairs: list):
        self.date = day_date
        self.group_name = group.name
        self.year = group.year or day_date.year
        self.pairs = pairs  # list of {"pair_number","discipline","marks","confirmed"}


def build_sheets(db: Session, group: Group, sessions: list) -> list:
    """Группирует сессии по дням, сохраняя порядок пар."""
    by_day: OrderedDict = OrderedDict()
    for s in sorted(sessions, key=lambda x: (x.date, x.pair_number)):
        by_day.setdefault(s.date, []).append(s)

    sheets = []
    for day, sess_list in by_day.items():
        pairs = []
        for s in sess_list:
            marks = {r.student_id: r.mark for r in s.records}
            pairs.append(
                {
                    "pair_number": s.pair_number,
                    "discipline": s.subject.name if s.subject else "",
                    "confirmed": s.confirmed,
                    "marks": marks,
                }
            )
        sheets.append(_Sheet(day, group, pairs))
    return sheets


def _students(db: Session, group: Group):
    return sorted(group.students, key=lambda st: st.full_name)


# ----------------------------- DOCX -----------------------------

def generate_docx(db: Session, group: Group, sheets: list) -> bytes:
    doc = Document()
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    new_w, new_h = section.page_height, section.page_width
    section.page_width, section.page_height = new_w, new_h
    section.left_margin = Cm(1)
    section.right_margin = Cm(1)
    section.top_margin = Cm(1)
    section.bottom_margin = Cm(1)

    normal = doc.styles["Normal"]
    normal.font.size = Pt(10)
    normal.font.name = "Noto Sans"

    for idx, sheet in enumerate(sheets):
        if idx > 0:
            doc.add_page_break()
        _append_docx_sheet(doc, db, group, sheet)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _append_docx_sheet(doc, db, group, sheet):
    lines = doc.paragraphs[0] if doc.paragraphs else None
    if lines is not None and not lines.text:
        p = lines
    else:
        p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run(TITLE).bold = True

    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    day = sheet.date.day
    month = sheet.date.month
    meta.add_run(
        f"дата {day:02d}.{month:02d}.{sheet.year}г      "
        f"{sheet.year}"
    )

    n_sessions = len(sheet.pairs)
    disc_row = [
        d["discipline"] if d["discipline"] else f"Пара {d['pair_number']}"
        for d in sheet.pairs
    ]
    ncols = 2 + n_sessions  # №, ФИО + пары
    table = doc.add_table(rows=0, cols=ncols)
    table.style = "Table Grid"

    widths = [Cm(1), Cm(7.5)] + [Cm(4.0)] * n_sessions

    def add_row(cells_text, bold=False):
        row = table.add_row()
        for i, txt in enumerate(cells_text):
            cell = row.cells[i]
            cell.text = ""
            par = cell.paragraphs[0]
            run = par.add_run(txt)
            run.bold = bold
            par.alignment = WD_ALIGN_PARAGRAPH.CENTER
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            cell.width = widths[i]
        return row

    add_row([f"№", "ФИО студента"] + disc_row, bold=True)
    header = add_row(["Группа", sheet.group_name] + [""] * n_sessions, bold=True)

    students = _students(db, group)
    num = 1
    for st in students:
        cells = [str(num), st.full_name]
        for d in sheet.pairs:
            mark = d["marks"].get(st.id, MarkValue.present)
            cells.append(MARK_RU.get(mark, ""))
        add_row(cells)
        num += 1

    sig = add_row(["", ""] + [""] * n_sessions)
    sig.cells[1].merge(sig.cells[ncols - 1])
    sig.cells[1].text = ""
    p = sig.cells[1].paragraphs[0]
    p.add_run("Подпись преподавателя___________")


# ----------------------------- XLSX -----------------------------

def generate_xlsx(db: Session, group: Group, sheets: list) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)

    thin = Side(style="thin", color="000000")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    green = PatternFill("solid", fgColor="C6EFCE")
    yellow = PatternFill("solid", fgColor="FFEB9C")
    red = PatternFill("solid", fgColor="FFC7CE")
    grey = PatternFill("solid", fgColor="D9D9D9")
    header_fill = PatternFill("solid", fgColor="BDD7EE")

    for sheet in sheets:
        ws = wb.create_sheet(sheet.date.isoformat())
        ws.title = sheet.date.strftime("%d.%m.%y")

        ws["A1"] = TITLE
        ws["A1"].font = Font(bold=True, size=14)
        meta_col = 2 + len(sheet.pairs)
        ws.cell(row=1, column=meta_col, value=f"дата {sheet.date.strftime('%d.%m.%Y')}г  {sheet.year}")
        if meta_col > 2:
            ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=meta_col - 1)

        header_row = 2
        headers = ["№", "ФИО студента"] + [
            d["discipline"] or f"Пара {d['pair_number']}"
            for d in sheet.pairs
        ]
        for ci, h in enumerate(headers, start=1):
            c = ws.cell(row=header_row, column=ci, value=h)
            c.font = Font(bold=True)
            c.fill = header_fill
            c.border = border

        ws.cell(row=header_row, column=1, value="Группа").font = Font(bold=True)
        ws.cell(row=header_row, column=2, value=sheet.group_name)
        ws.cell(row=header_row, column=2).border = border

        students = _students(db, group)
        r = header_row + 1
        for num, st in enumerate(students, start=1):
            ws.cell(row=r, column=1, value=num).border = border
            name_cell = ws.cell(row=r, column=2, value=st.full_name)
            name_cell.border = border
            for ci, dct in enumerate(sheet.pairs, start=3):
                mark = dct["marks"].get(st.id, MarkValue.present)
                val = MARK_RU.get(mark, "")
                c = ws.cell(row=r, column=ci, value=val)
                c.border = border
                c.alignment = Alignment(horizontal="center", vertical="center")
                if mark == MarkValue.present:
                    c.fill = green
                elif mark == MarkValue.late:
                    c.fill = yellow
                elif mark == MarkValue.absent:
                    c.fill = red
                elif mark == MarkValue.excused:
                    c.fill = grey
            r += 1

        ws.cell(row=r + 1, column=2, value="Подпись преподавателя___________")

        ws.column_dimensions["A"].width = 5
        ws.column_dimensions["B"].width = 38
        for ci in range(3, 3 + len(sheet.pairs)):
            ws.column_dimensions[get_column_letter(ci)].width = 24

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ----------------- МЕСЯЧНАЯ ВЕДОМОСТЬ ЧАСОВ (XLSX) -----------------

MONTHS_RU = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]

SPECIALTY_HEADER = (
    "Специальность 09.02.07 Информационные системы и программирование "
    "квалификация Специалист по информационным системам"
)

HOURS_PER_PAIR = 2

# «н» (не был), «нн» (неуважительная причина), «у» (уважительная) = пропуск
MISSED_MARKS = {MarkValue.late, MarkValue.absent, MarkValue.excused}


def _group_course(group: Group, year: int, month: int) -> int:
    """Курс из года набора в названии группы: ТЕСТ.01.01.1 -> 2024 год набора."""
    m = re.search(r"\.(\d{2})\.(\d+)$", group.name or "")
    if not m:
        return 1
    admission = 2000 + int(m.group(1))
    acad_year = year if month >= 9 else year - 1
    return max(1, acad_year - admission + 1)


def generate_monthly_hours_xlsx(db: Session, group: Group, year: int, month: int) -> bytes:
    """Ведомость учета часов, пропущенных студентами (по макету шаблона)."""
    days_in_month = calendar.monthrange(year, month)[1]
    sessions = (
        db.query(AttendanceSession)
        .options(joinedload(AttendanceSession.records))
        .filter(
            AttendanceSession.group_id == group.id,
            AttendanceSession.date >= date(year, month, 1),
            AttendanceSession.date <= date(year, month, days_in_month),
        )
        .all()
    )

    # (student_id, day) -> часов пропуска за день; (student_id, "excused") -> часов по уважит.
    day_hours: dict = {}
    excused_hours: dict = {}
    for s in sessions:
        day = s.date.day
        for r in s.records:
            if r.mark in MISSED_MARKS:
                key = (r.student_id, day)
                day_hours[key] = day_hours.get(key, 0) + HOURS_PER_PAIR
            if r.mark == MarkValue.excused:
                excused_hours[r.student_id] = (
                    excused_hours.get(r.student_id, 0) + HOURS_PER_PAIR
                )

    wb = Workbook()
    ws = wb.active
    ws.title = f"{MONTHS_RU[month - 1]} {year % 100:02d} посещ"
    ws.freeze_panes = "B1"

    thin = Side(style="thin", color="000000")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left_center = Alignment(horizontal="left", vertical="center", wrap_text=True)

    # --- Заголовок (A1:AJ1) ---
    month_name = MONTHS_RU[month - 1]
    course = _group_course(group, year, month)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=36)
    c = ws.cell(
        row=1, column=1,
        value=(
            "Ведомость учета часов, пропущенных студентами\n"
            f"{SPECIALTY_HEADER}    курс {course} группа {group.name} "
            f"месяц {month_name.capitalize()}"
        ),
    )
    c.font = Font(name="Times New Roman", size=11)
    c.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 40.5

    # --- Шапка (строка 2) и числа месяца (строка 3) ---
    ws.cell(row=2, column=1, value="№").alignment = center
    ws.cell(row=2, column=2, value="Ф.И.О.").alignment = center
    ws.merge_cells(start_row=2, start_column=3, end_row=2, end_column=33)
    ws.cell(row=2, column=3, value="Числа месяца").alignment = center
    ws.merge_cells(start_row=2, start_column=34, end_row=2, end_column=36)
    ws.cell(row=2, column=34, value="Пропуски").alignment = center
    ws.row_dimensions[2].height = 18.75

    for d in range(1, 32):
        ws.cell(row=3, column=2 + d, value=d).alignment = center
    ws.row_dimensions[3].height = 15.75

    # --- Студенты ---
    students = _students(db, group)
    r = 4
    for num, st in enumerate(students, start=1):
        ws.row_dimensions[r].height = 14.1
        total = 0
        for d in range(1, 32):
            h = day_hours.get((st.id, d), 0)
            if h:
                c = ws.cell(row=r, column=2 + d, value=h)
                c.alignment = center
            total += h
        excused = excused_hours.get(st.id, 0)
        ws.cell(row=r, column=1, value=num).alignment = center
        ws.cell(row=r, column=2, value=st.full_name).alignment = left_center
        c = ws.cell(row=r, column=34, value=excused or None)
        c.alignment = center
        c = ws.cell(row=r, column=35, value=(total - excused) or None)
        c.alignment = center
        c = ws.cell(row=r, column=36, value=total or None)
        c.alignment = center
        r += 1

    # --- Итоги ---
    ws.cell(row=r, column=32, value="Всего:").alignment = center
    ws.cell(row=r, column=34, value=sum(excused_hours.values()) or None).alignment = center
    ws.cell(row=r, column=35, value=sum(
        (day_hours.get((st.id, d), 0) for st in students for d in range(1, 32))
    ) - sum(excused_hours.values()) or None).alignment = center
    ws.cell(row=r, column=36, value=sum(
        day_hours.get((st.id, d), 0) for st in students for d in range(1, 32)
    ) or None).alignment = center

    # --- Подпись куратора ---
    r += 1
    ws.merge_cells(start_row=r, start_column=10, end_row=r, end_column=18)
    ws.cell(row=r, column=10, value="Подпись куратора группы").alignment = center
    ws.cell(row=r, column=19, value="_____________________").alignment = center

    # --- Границы и ширина колонок ---
    for row in ws.iter_rows(min_row=2, max_row=r, min_col=1, max_col=36):
        for cell in row:
            cell.border = border

    ws.column_dimensions["A"].width = 3.85
    ws.column_dimensions["B"].width = 19.42
    for d in range(1, 32):
        ws.column_dimensions[get_column_letter(2 + d)].width = 3.0
    ws.column_dimensions["AH"].width = 6.13
    ws.column_dimensions["AI"].width = 6.7
    ws.column_dimensions["AJ"].width = 6.56

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ----------------------------- PDF -----------------------------

class _Pdf(FPDF):
    def header(self):
        pass

    def footer(self):
        pass


def generate_pdf(db: Session, group: Group, sheets: list) -> bytes:
    pdf = _Pdf(orientation="L", unit="mm", format="A4")
    pdf.add_font("Noto", "", NOTO_REGULAR)
    pdf.add_font("Noto", "B", NOTO_BOLD)
    pdf.set_auto_page_break(auto=True, margin=12)

    for sheet in sheets:
        pdf.add_page()
        _append_pdf_sheet(pdf, db, group, sheet)
    return bytes(pdf.output())


def _append_pdf_sheet(pdf, db, group, sheet):
    page_w = pdf.w - pdf.l_margin - pdf.r_margin

    pdf.set_font("Noto", "B", 14)
    pdf.cell(page_w, 10, TITLE, align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Noto", "", 11)
    pdf.cell(page_w, 8, f"дата {sheet.date.strftime('%d.%m.%Y')}г      {sheet.year}", align="R", new_x="LMARGIN", new_y="NEXT")

    ncols = 2 + len(sheet.pairs)
    col_w = [16, 80] + [ (page_w - 96) / len(sheet.pairs) ] * len(sheet.pairs)
    col_w = [max(w, 20) for w in col_w]

    row_h = 10
    line_h = 4

    def draw_row(cells, bold=False, fill=None):
        x0 = pdf.get_x()
        y0 = pdf.get_y()
        pdf.set_font("Noto", "B" if bold else "", 9)
        if fill:
            pdf.set_fill_color(*fill)
        pdf.set_draw_color(0, 0, 0)
        y_line = y0
        for i, txt in enumerate(cells):
            x = x0 + sum(col_w[:i])
            if y_line + row_h > pdf.h - pdf.b_margin:
                pdf.add_page()
                y0 = pdf.get_y()
                y_line = y0
            pdf.rect(x, y_line, col_w[i], row_h, style="D")
            if fill:
                pdf.rect(x, y_line, col_w[i], row_h, style="F")
            pdf.set_xy(x + 1, y_line + 1)
            pdf.multi_cell(col_w[i] - 2, line_h, str(txt), align="C" if i != 1 else "L")
        pdf.set_xy(x0, y0 + row_h)

    draw_row([f"№", "ФИО студента"] + [
        d["discipline"] or f"Пара {d['pair_number']}" for d in sheet.pairs
    ], bold=True, fill=(189, 215, 238))

    draw_row(["Группа", sheet.group_name] + [""] * len(sheet.pairs), bold=True)

    students = _students(db, group)
    num = 1
    for st in students:
        cells = [str(num), st.full_name]
        for d in sheet.pairs:
            mark = d["marks"].get(st.id, MarkValue.present)
            val = MARK_RU.get(mark, "")
            fill = None
            if mark == MarkValue.present:
                fill = (198, 239, 206)
            elif mark == MarkValue.late:
                fill = (255, 235, 156)
            elif mark == MarkValue.absent:
                fill = (255, 199, 206)
            elif mark == MarkValue.excused:
                fill = (217, 217, 217)
            cells.append(val)
        draw_row(cells, fill=fill)
        num += 1

    pdf.set_font("Noto", "", 10)
    pdf.ln(6)
    pdf.cell(page_w, 8, "Подпись преподавателя___________")

    if any(d["confirmed"] for d in sheet.pairs):
        pdf.cell(page_w, 8, "Подлинность подтверждена преподавателем", align="R")


def export_bytes(db: Session, group: Group, sessions: list, fmt: str) -> tuple[bytes, str]:
    sheets = build_sheets(db, group, sessions)
    if fmt == "docx":
        data = generate_docx(db, group, sheets)
        return data, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if fmt == "xlsx":
        data = generate_xlsx(db, group, sheets)
        return data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    data = generate_pdf(db, group, sheets)
    return data, "application/pdf"


def export_filename(fmt: str, group: Group, date_from, date_to) -> str:
    f = fmt.lower()
    if date_from == date_to or (date_from and date_to and date_from == date_to):
        return f"raport_{group.name}_{date_from.isoformat()}.{f}"
    return f"raport_{group.name}_{date_from.isoformat()}_{date_to.isoformat()}.{f}"