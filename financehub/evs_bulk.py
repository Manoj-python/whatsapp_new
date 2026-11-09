"""Executive Visit Schedule bulk upload (9 Nov 2026). Called by tasks.process_universal_file."""
import csv, datetime as dt, re

LOAN = ("loanno", "loannumber", "loan", "agreementno", "agreementnumber")
EMP = ("empid", "employeeid", "employeeno", "employeenumber", "empno")
DATE = ("visitscheduledate", "visitdate", "scheduledate", "date")
FORMATS = ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%Y-%m-%d %H:%M:%S")
SHOW = 30  # problems listed


def _text(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():  # Excel turns 5436 into 5436.0
        v = int(v)
    return str(v).replace("\xa0", " ").strip()


def _date(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    s = _text(v)
    for f in FORMATS:
        try:
            return dt.datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None


def _col(headers, names):
    for i, h in enumerate(headers):
        if h in names:
            return i
    return None


def check(table, *, loans, emps, alloc, today):
    """table = header row + rows. loans: UPPER loan no -> loan no as stored; emps: known employee ids;
    alloc: loan no -> allocated employee id. Returns (rows [(line, loan, emp, date)], problems)."""
    headers = [re.sub(r"[^a-z0-9]", "", _text(h).lower()) for h in table[0]] if table else []
    li, ei, di = _col(headers, LOAN), _col(headers, EMP), _col(headers, DATE)
    if li is None or di is None:
        return [], ["the sheet needs the columns LoanNo, EmpID, VisitScheduleDate (EmpID may be blank)"]
    rows, problems, seen = [], [], {}
    for n, r in enumerate(table[1:], start=2):
        r = list(r) + [None] * len(headers)
        if all(_text(v) == "" for v in r):
            continue
        raw, emp, when = _text(r[li]), _text(r[ei]) if ei is not None else "", _date(r[di])
        loan = loans.get(raw.upper())
        bad = []
        if not raw:
            bad.append("loan number is blank")
        elif not loan:
            bad.append("loan %s is not in the loan list" % raw)
        elif loan in seen:
            bad.append("loan %s is also on line %s" % (raw, seen[loan]))
        if loan and not emp:
            emp = alloc.get(loan, "")
            if not emp:
                bad.append("EmpID is blank and loan %s has no allocated executive" % raw)
        elif emp and emp not in emps:
            bad.append("employee %s is not known" % emp)
        if when is None:
            bad.append("visit date %r is not a date (use DD-MM-YYYY)" % _text(r[di]))
        elif when < today:
            bad.append("visit date %s is before today" % when.strftime("%d-%m-%Y"))
        if bad:
            problems.append("line %s: %s" % (n, "; ".join(bad)))
        else:
            seen[loan] = n
            rows.append((n, loan, emp, when))
    if not rows and not problems:
        problems.append("the sheet has no rows")
    return rows, problems


def _read(path, ext):
    if ext == "csv":
        with open(path, newline="", encoding="utf-8-sig") as f:
            return [r for r in csv.reader(f)]
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    return [list(r) for r in wb.active.iter_rows(values_only=True)]


def run(upload, path, ext):
    from django.db import transaction
    from django.utils import timezone
    from .models import Lcc, EmployeeMaster, CollectionAllocations, ExecutiveVisitScheduling as EVS

    table = _read(path, ext)
    li = _col([re.sub(r"[^a-z0-9]", "", _text(h).lower()) for h in table[0]], LOAN) if table else None
    raw = {_text(r[li]).upper() for r in table[1:] if li is not None and li < len(r)} - {""}
    loans = {l.upper(): l for l in Lcc.objects.filter(loan_number__in=raw).values_list("loan_number", flat=True)}
    allocs = {}
    for a in CollectionAllocations.objects.filter(loan_number__in=list(loans.values())).order_by("id"):
        allocs.setdefault(a.loan_number, []).append(a)
    ids = {(a.employee_id or "").strip() for l in allocs.values() for a in l}
    dept = dict(EmployeeMaster.objects.filter(employee_number__in=ids).values_list("employee_number", "curr_department"))
    alloc = {}
    for loan, l in allocs.items():  # same pick as the pop-up default: the collection executive, else the newest
        coll = [a for a in l if "COLL" in (dept.get((a.employee_id or "").strip()) or "").upper()] if len(l) > 1 else []
        alloc[loan] = ((coll or l)[-1].employee_id or "").strip()
    emps = set(EmployeeMaster.objects.values_list("employee_number", flat=True)) | \
        set(CollectionAllocations.objects.values_list("employee_id", flat=True).distinct())
    emps = {_text(e) for e in emps if e}

    rows, problems = check(table, loans=loans, emps=emps, alloc=alloc, today=timezone.localdate())
    upload.total_rows = len(rows) + len(problems)
    if problems:
        upload.status = "error"
        upload.error_message = "Nothing was saved - %s problem%s\n%s%s" % (
            len(problems), "" if len(problems) == 1 else "s", "\n".join(problems[:SHOW]),
            "\n... and %s more" % (len(problems) - SHOW) if len(problems) > SHOW else "")
        upload.save()
        return
    latest = {}
    for o in EVS.objects.filter(loanno__in=[r[1] for r in rows]).order_by("id"):
        latest[o.loanno] = o
    new = moved = changed = same = 0
    with transaction.atomic():
        for _n, loan, emp, when in rows:
            o = latest.get(loan)
            if o and o.visit_schedule_date == when:
                if o.empid != emp:
                    o.empid = emp
                    o.save(update_fields=["empid"])
                    changed += 1
                else:
                    same += 1
                continue
            EVS.objects.create(loanno=loan, empid=emp, visit_schedule_date=when)  # old row stays as history
            if o:
                moved += 1
            else:
                new += 1
    upload.processed_rows = len(rows)
    upload.status = "completed"
    upload.error_message = "Saved: %s new, %s rescheduled, %s executive changed, %s already the same." % (
        new, moved, changed, same)
    upload.save()


if __name__ == "__main__":
    t = dt.date(2026, 11, 9)
    L = {"AB1": "AB1", "AB2": "AB2", "AB3": "AB3"}
    ok, bad = check([["Loan No", "Emp ID", "Visit Schedule Date"],
                     ["ab1", 5436.0, "10-11-2026"], ["AB2", "", dt.datetime(2026, 11, 12)], [None, None, None]],
                    loans=L, emps={"5436"}, alloc={"AB2": "7001"}, today=t)
    assert bad == [] and ok == [(2, "AB1", "5436", dt.date(2026, 11, 10)), (3, "AB2", "7001", dt.date(2026, 11, 12))], (ok, bad)
    ok, bad = check([["LoanNo", "EmpID", "VisitScheduleDate"], ["ZZ", "1", "x"], ["AB1", "9", "01-11-2026"],
                     ["AB3", "", "11/11/2026"], ["AB1", "5436", "2026-11-20"], ["AB2", "5436", "2026-11-20"],
                     ["AB2", "5436", "2026-11-21"]], loans=L, emps={"5436"}, alloc={}, today=t)
    assert len(ok) == 2 and [p.split(":")[0] for p in bad] == ["line 2", "line 3", "line 4", "line 7"], bad
    assert "not in the loan list" in bad[0] and "not a date" in bad[0] and "not known" in bad[1] and "before today" in bad[1]
    assert "no allocated executive" in bad[2] and "also on line 6" in bad[3]
    assert check([["Loan", "Something"]], loans=L, emps=set(), alloc={}, today=t)[1][0].startswith("the sheet needs")
    print("evs_bulk self-check ok")
