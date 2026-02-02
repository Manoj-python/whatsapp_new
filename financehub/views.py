
import os
import tempfile
import unicodedata
import datetime

from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.core.paginator import Paginator
from django.db.models import Q
from django.core.cache import cache

# Models
from datetime import datetime

from .models import (
    UploadHistory,
    Lcc,
    Feedback,
    ExecutiveVisitScheduling,
    Clu,
    Freshdesk,
    DueNotice,
    Visiter, 
    Dialer, # ✅ ADD THIS
)

# Forms
from .forms import FeedbackForm

# Celery tasks
from financehub.tasks import (
    process_universal_file,
)

# Decorator for session protection
from django.contrib.auth.decorators import login_required

# ---------------------------------------------------------------------
# LOGIN
# ---------------------------------------------------------------------
def fh_login(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "").strip()

        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)
            request.session["financehub_user"] = user.id
            return redirect("upload_loan_data")
        else:
            messages.error(request, "Invalid username or password")

    return render(request, "financehub/login.html")


# ---------------------------------------------------------------------
# LOGOUT
# ---------------------------------------------------------------------
def fh_logout(request):
    request.session.pop("financehub_user", None)
    return redirect("fh_login")


# ---------------------------------------------------------------------
# SESSION CHECK DECORATOR
# ---------------------------------------------------------------------
def financehub_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.session.get("financehub_user"):
            return redirect("fh_login")
        return view_func(request, *args, **kwargs)
    return wrapper


MAX_UPLOAD_SIZE = 25 * 1024 * 1024  # 25 MB


# ---------------------------------------------------------------------
# FILE UPLOAD + CELERY PROCESSING
# ---------------------------------------------------------------------
# ---------------------------------------------------------------------
# UNIVERSAL FILE UPLOAD (WITH DROPDOWN)
# ---------------------------------------------------------------------
from financehub.tasks import process_universal_file
from .models import UploadHistory

FILE_TYPES = [
    ("lcc", "LCC"),
    ("collection_allocations", "Collection Allocations"),
    ("clu", "CLU"),
    ("repo", "Repo"),
    ("paid", "Paid"),
    ("closed", "Closed"),
    ("dialer", "Dialer"),
    ("duenotice", "Due Notice"),
    ("visiter", "Visiter"),
    ("employee_master", "Employee Master"),
    ("freshdesk", "Freshdesk"),
    ("esebuzz", "EseBuzz"),
    ("hero", "Hero"),
    ("kotakecs", "Kotak ECS"),
    ("smsquare", "SMSquare"),
    ("upi", "UPI"),
    ("executive_visit_scheduling", "Executive Visit Scheduling"),



]
@financehub_required
def upload_loan_data(request):

    msg = None
    error = None

    if request.method == "POST":

        file_type = request.POST.get("file_type")
        file = request.FILES.get("file")

        if not file_type:
            return render(request, "financehub/upload.html",
                          {"error": "Please select file type.", "file_types": FILE_TYPES})

        if not file:
            return render(request, "financehub/upload.html",
                          {"error": "Please choose a file.", "file_types": FILE_TYPES})

        ext = file.name.split(".")[-1].lower()
        if ext not in ("csv", "xlsx", "xls"):
            return render(request, "financehub/upload.html",
                          {"error": "Only CSV / XLS / XLSX allowed.", "file_types": FILE_TYPES})

        # save temp file
        tmp_dir = getattr(settings, "DATA_UPLOAD_TEMP_DIR", tempfile.gettempdir())
        tmp_path = os.path.join(tmp_dir, f"upload_{file.name}")

        with open(tmp_path, "wb+") as f:
            for chunk in file.chunks():
                f.write(chunk)

        # create upload history entry
        upload = UploadHistory.objects.create(
            filename=file.name,
            uploaded_by=request.user.username,
            file_type=file_type,
            status="processing",
            total_rows=0,
            processed_rows=0
        )

        # launch celery
        process_universal_file.delay(upload.id, tmp_path, ext, file_type)

        msg = f"Upload started! Upload ID = {upload.id}"

        return render(request, "financehub/upload.html", {
            "msg": msg,
            "file_types": FILE_TYPES,
            "upload_id": upload.id
        })

    return render(request, "financehub/upload.html", {
        "file_types": FILE_TYPES
    })





# LCC LIST WITH POWER SEARCH + PAGINATION (100 PER PAGE)
from django.db.models import Q
from django.core.paginator import Paginator


# ---------------------------------------------------------------------
# LCC LIST WITH PAGINATION + SEARCH
# ---------------------------------------------------------------------
import unicodedata
from django.db.models import Q
from django.core.paginator import Paginator

import unicodedata
from django.db.models import Q
from django.core.paginator import Paginator

def normalize_excel_text(text):
    """Clean any hidden characters & normalize Excel-pasted values."""
    if not text:
        return ""

    # Normalize Unicode
    text = unicodedata.normalize("NFKD", text)

    # Remove invisible characters including TAB (%09)
    INVISIBLE = ["\u200b", "\u200c", "\u200d", "\ufeff", "\t", "\n", "\r"]
    for ch in INVISIBLE:
        text = text.replace(ch, "")

    # Normalize various hyphens
    HYPHENS = ["‐", "-", "‒", "–", "—", "―"]
    for h in HYPHENS:
        text = text.replace(h, "-")

    # Keep only alphanumeric and hyphen
    cleaned = []
    for c in text:
        if c.isalnum() or c == "-":
            cleaned.append(c)

    return "".join(cleaned).strip()


@financehub_required
def lcc_list(request):

    search_raw = request.GET.get("search", "")
    search_clean = normalize_excel_text(search_raw)

    base_qs = Lcc.objects.all()

    # -----------------------------------------------------
    # ✅ CASE 1: NO SEARCH → SHOW FULL DATA FROM ID 1
    # -----------------------------------------------------
    if not search_clean:
        qs = base_qs.order_by("id")

    else:
        # -----------------------------------------------------
        # ✅ STEP 1: FIND EXACT MATCH (LOAN / MOBILE / GUARANTOR / VEHICLE)
        # -----------------------------------------------------
        primary = base_qs.filter(
            Q(loan_number__iexact=search_clean) |
            Q(cust_mobile__iexact=search_clean) |
            Q(guarantor_mobile__iexact=search_clean) |
            Q(vehicle_no__iexact=search_clean)
        )

        # -----------------------------------------------------
        # ✅ STEP 2: IF NOTHING EXACT → FALLBACK TO NAME SEARCH
        # -----------------------------------------------------
        if not primary.exists():
            qs = base_qs.filter(
                Q(customer_name__icontains=search_clean) |
                Q(guarantor__icontains=search_clean)
            ).order_by("id")

        else:
            # -----------------------------------------------------
            # ✅ STEP 3: CLEAN EMPTY / ZERO VALUES BEFORE EXPANSION
            # -----------------------------------------------------
            mobile_set = set(
                x for x in primary.values_list("cust_mobile", flat=True)
                if x not in ["", None, "0"]
            ) | set(
                x for x in primary.values_list("guarantor_mobile", flat=True)
                if x not in ["", None, "0"]
            )

            vehicle_set = set(
                x for x in primary.values_list("vehicle_no", flat=True)
                if x not in ["", None]
            )

            # -----------------------------------------------------
            # ✅ STEP 4: EXPAND ONLY WITH CLEAN VALUES
            # -----------------------------------------------------
            qs = base_qs.filter(
                Q(cust_mobile__in=mobile_set) |
                Q(guarantor_mobile__in=mobile_set) |
                Q(vehicle_no__in=vehicle_set) |
                Q(id__in=primary.values("id"))
            ).distinct().order_by("id")

    # -----------------------------------------------------
    # ✅ PAGINATION (STABLE & CLEAN)
    # -----------------------------------------------------
    paginator = Paginator(qs, 50)
    page = request.GET.get("page")
    page_obj = paginator.get_page(page)

    params = request.GET.copy()
    params.pop("page", None)
    params["search"] = search_clean

    return render(request, "financehub/lcc.html", {
        "data": page_obj,
        "search": search_clean,
        "query_string": params.urlencode(),
    })



def build_latest_payment_map(loan_numbers):
    payment_latest_map = {}
    payment_source_map = {}

    def push_payment(loan, status, date, amount, source):
        date_parsed = parse_payment_date_safe(date)
        if not loan:
            return

        # track all sources
        payment_source_map.setdefault(loan, set()).add(source)

        # date required to be latest
        if not date_parsed:
            return

        current = payment_latest_map.get(loan)
        if not current or date_parsed > current["date"]:
            payment_latest_map[loan] = {
                "status": clean_payment_value(status),
                "date": date_parsed,
                "amount": clean_payment_value(amount),
                "source": source,  # temp
            }

    # HERO
    for h in Hero.objects.filter(referencenumber__in=loan_numbers):
        push_payment(h.referencenumber, h.status, h.date, h.amount, "HERO")

    # KOTAK
    for k in KotakECS.objects.filter(loannumber__in=loan_numbers):
        push_payment(k.loannumber, k.ecsstatus, k.ecsdate, k.amount, "KOTAK")

    # ESEBUZZ
    for e in EseBuzz.objects.filter(loanno__in=loan_numbers):
        push_payment(e.loanno, e.status, e.initiateddate, e.amount, "ESEBUZZ")

    # SMSQUARE
    for s in Smsquare.objects.filter(uniqueregistrationnumber__in=loan_numbers):
        push_payment(s.uniqueregistrationnumber, s.status, s.date, s.amount, "SMSQUARE")

    # UPI
    for u in Upi.objects.filter(loannoreference__in=loan_numbers):
        push_payment(u.loannoreference, u.paymentstatus, u.paymentdatetime, u.transactionamount, "UPI")

    # merge sources
    for loan, latest in payment_latest_map.items():
        latest["source"] = " + ".join(sorted(payment_source_map.get(loan, [])))

    return payment_latest_map


# ---------------------------------------------------------------------
# CREATE FEEDBACK
# ---------------------------------------------------------------------
def normalize_mobile(num):
    if not num:
        return None
    s = str(num).strip()
    if s.startswith("91") and len(s) == 12:
        return s[2:]
    return s

@financehub_required
def feedback_create(request):

    loan_no = request.GET.get("loan", "")
    emp_id = request.user.username

    # ----------------------------
    # CASE 1: DIRECT OPEN
    # ----------------------------
    if not loan_no:

        if request.method == "POST":
            form = FeedbackForm(request.POST)
            if form.is_valid():
                form.save()
                return redirect("feedback_list")
        else:
            form = FeedbackForm(initial={"EmpID": emp_id})

        return render(request, "financehub/feedback_form.html", {
            "form": form,
            "loan_no": "",
            "combined_rows": [],
            "freshdesk_tickets": [],   # ✅ SAFE DEFAULT
        })

    # ----------------------------
    # CASE 2: OPENED FROM LCC TABLE
    # ----------------------------
    try:
        l = Lcc.objects.get(loan_number=loan_no)
    except Lcc.DoesNotExist:
        l = None

    payment = None
    if loan_no:
        payment_map = build_latest_payment_map([loan_no])
        payment = payment_map.get(loan_no)


    cust_mobile = l.cust_mobile if l else ""
    guar_mobile = l.guarantor_mobile if l else ""
    veh_no = l.vehicle_no if l else ""
    cust_name = l.customer_name if l else ""
    guar_name = l.guarantor if l else ""

    # =========================================================
    # DIALER DATA (LATEST PER DISP)
    # =========================================================


    dialer_row = {
        "Dialer_PTP": "",
        "Dialer_PTP_Date": "",
        "Dialer_PTP_Remarks": "",

        "Dialer_RTP": "",
        "Dialer_RTP_Date": "",
        "Dialer_RTP_Remarks": "",

        "Dialer_Thirdparty": "",
        "Dialer_Thirdparty_Date": "",
        "Dialer_Thirdparty_Remarks": "",

        "Dialer_other": "",
        "Dialer_other_Date": "",
        "Dialer_other_Remarks": "",
    }

    cust_mobile_norm = normalize_mobile(cust_mobile)

    if cust_mobile_norm:
        base_qs = Dialer.objects.filter(
            mobile=cust_mobile_norm
        ).exclude(ptp_date__isnull=True).exclude(ptp_date="")

        # PTP
        obj = base_qs.filter(disp__iexact="PTP").order_by("-created_at").first()
        if obj:
            dialer_row.update({
                "Dialer_PTP": obj.disp,
                "Dialer_PTP_Date": obj.ptp_date,
                "Dialer_PTP_Remarks": obj.remarks,
            })

        # RTP
        obj = base_qs.filter(disp__iexact="RTP").order_by("-created_at").first()
        if obj:
            dialer_row.update({
                "Dialer_RTP": obj.disp,
                "Dialer_RTP_Date": obj.ptp_date,
                "Dialer_RTP_Remarks": obj.remarks,
            })

        # THIRD PARTY
        obj = base_qs.filter(disp__iexact="THIRD PARTY").order_by("-created_at").first()
        if obj:
            dialer_row.update({
                "Dialer_Thirdparty": obj.disp,
                "Dialer_Thirdparty_Date": obj.ptp_date,
                "Dialer_Thirdparty_Remarks": obj.remarks,
            })

        # OTHER
        obj = base_qs.exclude(
            disp__in=["PTP", "RTP", "THIRD PARTY"]
        ).order_by("-created_at").first()
        if obj:
            dialer_row.update({
                "Dialer_other": obj.disp,
                "Dialer_other_Date": obj.ptp_date,
                "Dialer_other_Remarks": obj.remarks,
            })


    # =========================================================
    # ✅ NEW: FRESHDESK MATCH (LOAN NUMBER INSIDE SUBJECT)
    # =========================================================
    freshdesk_tickets = []

    if loan_no:
        freshdesk_tickets = Freshdesk.objects.filter(
            subject__icontains=loan_no
        ).order_by("-created_at")
    # =========================================================

    duenotices = []
    if loan_no:
        duenotices = DueNotice.objects.filter(
            loan_number=loan_no
        ).order_by("-id")

    # =========================================================
# ✅ CLU VISITS (MATCHED BY LOAN NUMBER)
# =========================================================
    clu_visits = []

    if loan_no:
        clu_visits = Clu.objects.filter(
            loan_number=loan_no
        ).order_by("-created_at")

    # VISITERS (MATCH BY LOAN NUMBER)
    visitors = []
    if loan_no:
        visitors = Visiter.objects.filter(
            loan_number=loan_no
        ).order_by("-created_at")



    # ----------------------------
    # EXACT LOAN FEEDBACK
    # ----------------------------
    exact_fb = list(
        Feedback.objects.filter(LoanNO=loan_no).order_by("-id")
    )

    # ----------------------------
    # RELATED LOANS (SAFE LOGIC)
    # ----------------------------
    filters = Q()

    if cust_mobile not in ["", None, "0"]:
        filters |= Q(cust_mobile=cust_mobile)

    if guar_mobile not in ["", None, "0"]:
        filters |= Q(guarantor_mobile=guar_mobile)

    if veh_no not in ["", None]:
        filters |= Q(vehicle_no=veh_no)

    if filters:
        related_qs = Lcc.objects.filter(filters).exclude(loan_number=loan_no)
    else:
        related_qs = Lcc.objects.none()

    related_loan_numbers = [x.loan_number for x in related_qs]

    # ----------------------------
    # RELATED FEEDBACK
    # ----------------------------
    related_fb_all = Feedback.objects.filter(
        LoanNO__in=related_loan_numbers
    ).order_by("-id")

    related_map = {}
    for fb in related_fb_all:
        related_map.setdefault(fb.LoanNO, []).append(fb)

    # ----------------------------
    # BUILD COMBINED HISTORY TABLE
    # ----------------------------
    combined_rows = []

    for fb in exact_fb:
        combined_rows.append({
            "loan": fb.LoanNO,
            "vehicle": veh_no,
            "cust_mobile": cust_mobile,
            "guar_mobile": guar_mobile,
            "cust_name": cust_name,
            "guar_name": guar_name,
            "feedback": fb,
        })

    for rl in related_qs:
        fblist = related_map.get(rl.loan_number, [])
        if fblist:
            for fb in fblist:
                combined_rows.append({
                    "loan": rl.loan_number,
                    "vehicle": rl.vehicle_no,
                    "cust_mobile": rl.cust_mobile,
                    "guar_mobile": rl.guarantor_mobile,
                    "cust_name": rl.customer_name,
                    "guar_name": rl.guarantor,
                    "feedback": fb,
                })
        else:
            combined_rows.append({
                "loan": rl.loan_number,
                "vehicle": rl.vehicle_no,
                "cust_mobile": rl.cust_mobile,
                "guar_mobile": rl.guarantor_mobile,
                "cust_name": rl.customer_name,
                "guar_name": rl.guarantor,
                "feedback": None,
            })

    # ----------------------------
    # FORM
    # ----------------------------
    initial = {
        "EmpID": emp_id,
        "LoanNO": loan_no,
        "customer_name": cust_name,
        "vehicle_no": veh_no,
    }

    if request.method == "POST":
        form = FeedbackForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("feedback_list")
    else:
        form = FeedbackForm(initial=initial)

    return render(request, "financehub/feedback_form.html", {
        "form": form,
        "loan_no": loan_no,
        "combined_rows": combined_rows,
        "freshdesk_tickets": freshdesk_tickets,
        "duenotices": duenotices,
        "clu_visits": clu_visits,  # ✅ NEW
        "visitors": visitors,  # ✅ NEW
        "payment": payment,
        "dialer_row": dialer_row,

    })


from django.shortcuts import render
from django.db.models import Q
import datetime
from .models import Feedback


# ---------------------------------------------------------------------
# FEEDBACK LIST - POWER SEARCH + PAGINATION (100/page)
# ---------------------------------------------------------------------

from django.core.paginator import Paginator
from django.db.models import Q
import datetime

@financehub_required
def feedback_list(request):

    def clean(v):
        return v.strip() if v and v != "None" else None

    emp       = clean(request.GET.get("emp"))
    date_str  = clean(request.GET.get("date"))
    ftype     = clean(request.GET.get("ftype"))
    ctype     = clean(request.GET.get("ctype"))
    visiting  = clean(request.GET.get("visiting"))
    executive = clean(request.GET.get("executive"))
    ptp       = clean(request.GET.get("ptp"))
    vdate     = clean(request.GET.get("vdate"))
    search    = clean(request.GET.get("search"))

    qs = Feedback.objects.all().order_by("-id")

    # Power search
    if search:
        qs = qs.filter(
            Q(LoanNO__icontains=search) |
            Q(customer_name__icontains=search) |
            Q(vehicle_no__icontains=search) |
            Q(Remarks__icontains=search) |
            Q(EmpID__icontains=search)
        )

    # Filters
    if emp:
        qs = qs.filter(EmpID__iexact=emp)

    if date_str:
        try:
            qs = qs.filter(Date=datetime.datetime.strptime(date_str, "%Y-%m-%d"))
        except:
            pass

    if ftype:
        qs = qs.filter(Dropdown=ftype)

    if ctype:
        qs = qs.filter(feedback_dropdwon=ctype)

    if visiting:
        qs = qs.filter(visiting_required=(visiting == "yes"))

    if executive:
        qs = qs.filter(executive_id=executive)

    if ptp:
        try:
            qs = qs.filter(PTPDate=datetime.datetime.strptime(ptp, "%Y-%m-%d"))
        except:
            pass

    if vdate:
        try:
            qs = qs.filter(visit_date=datetime.datetime.strptime(vdate, "%Y-%m-%d"))
        except:
            pass

    # Pagination
    paginator = Paginator(qs, 1000)
    page_obj = paginator.get_page(request.GET.get("page"))

    params = request.GET.copy()
    params.pop("page", None)

    filters = {
        "emp": emp or "",
        "date": date_str or "",
        "ftype": ftype or "",
        "ctype": ctype or "",
        "visiting": visiting or "",
        "executive": executive or "",
        "ptp": ptp or "",
        "vdate": vdate or "",
        "search": search or "",
    }

    return render(request, "financehub/feedback_list.html", {
        "data": page_obj,
        "filters": filters,
        "query_string": params.urlencode(),
        "FTYPES": Feedback.DROPDOWN_CHOICES,
        "CTYPES": Feedback.FEEDBACK_CHOICES,
    })





# ---------------------------------------------------------------
# AJAX PROGRESS CHECK
# ---------------------------------------------------------------
# financehub/views.py (top imports)
from django.http import JsonResponse
# ... other imports remain

# upload_progress (already exists), ensure it uses JsonResponse
def upload_progress(request, upload_id):
    try:
        u = UploadHistory.objects.get(id=upload_id)
        return JsonResponse({
            "status": u.status,
            "processed": u.processed_rows,
            "total": u.total_rows,
            "percent": u.progress_percentage(),
            "error": u.error_message or "",
        })
    except UploadHistory.DoesNotExist:
        return JsonResponse({"error": "Invalid Upload ID"}, status=404)






from openpyxl import Workbook
from django.http import HttpResponse


def export_lcc_excel(final_data):
    wb = Workbook()
    ws = wb.active
    ws.title = "Loan Status Report"

    # ======================
    # HEADER ROW
    # ======================
    headers = [
        "Loan Number",
        "Customer Name",
        "Company",
        "Branch",
        "Division",
        "EMI",
        "Loan Status",
        "Received Date",
        "CM",
        "TL",
        "Executive",
        "Visit Date",
        "Visit Status",
    ]
    ws.append(headers)

    # ======================
    # DATA ROWS
    # ======================
    for r in final_data:
        ws.append([
            r["loan_number"],
            r["customer_name"],
            r["company"],
            r["branch"],
            r.get("division", ""),
            r["emi_due_2"],
            r["loan_status"],
            r["received_date"],
            r["cm"],
            r["tl"],
            r["exec"],
            r["visit_date"],
            r["visit_status"],
        ])

    # ======================
    # RESPONSE
    # ======================
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = (
        'attachment; filename="loan_status_report.xlsx"'
    )

    wb.save(response)
    return response




from django.http import HttpResponse
from reportlab.lib.pagesizes import legal, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from datetime import date

# ======================================================
# STYLES
# ======================================================
styles = getSampleStyleSheet()

wrap_style = ParagraphStyle(
    "wrap",
    parent=styles["Normal"],
    fontSize=6.5,
    leading=7.5,
    wordWrap="CJK",
)

# ======================================================
# HELPERS
# ======================================================
def clean_colon_zero(value):
    if not value:
        return ""
    value = str(value).strip()
    if value in ("00:0", "0:00"):
        return ""
    return value


def wrap_cell(value, max_chars=50):
    if not value:
        return Paragraph("", wrap_style)

    text = str(value)
    lines = [text[i:i + max_chars] for i in range(0, len(text), max_chars)]
    return Paragraph("<br/>".join(lines), wrap_style)


# ======================================================
# 🔥 FINAL SORT KEY (EMI → DATE)
# ======================================================
def lcc_final_sort_key(row):
    """
    FINAL SORT ORDER:

    1️⃣ EMI DUE (PRIMARY)
       - SEZ first
       - Numeric EMI (higher → lower)
       - Zero / blank last

    2️⃣ INSTALLMENT DATE (SECONDARY)
       - Oldest date first
    """

    # -----------------------
    # INSTALLMENT DATE
    # -----------------------
    inst_date = row.get("installment_date")
    if not inst_date:
        inst_date = date.max  # empty dates last

    # -----------------------
    # EMI PROCESSING
    # -----------------------
    emi_raw = str(row.get("emi_due_2", "")).strip().lower()

    # SEZ → TOP PRIORITY
    if emi_raw == "sez":
        emi_group = 0
        emi_value = float("inf")

    # NUMERIC EMI
    else:
        try:
            emi_value = float(emi_raw)
            if emi_value > 0:
                emi_group = 1
            else:
                emi_group = 2  # zero EMI
        except Exception:
            emi_group = 2
            emi_value = 0

    # -----------------------
    # SORT TUPLE
    # -----------------------
    return (
        emi_group,      # SEZ → numeric → zero
        -emi_value,     # BIG EMI FIRST
        inst_date       # OLDEST DATE FIRST
    )


# ======================================================
# PDF EXPORT
# ======================================================
def export_lcc_pdf(final_data):

    # ✅ APPLY FINAL SORT
    final_data = sorted(final_data, key=lcc_final_sort_key)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="lcc_legal_report.pdf"'

    doc = SimpleDocTemplate(
        response,
        pagesize=landscape(legal),
        leftMargin=6,
        rightMargin=6,
        topMargin=8,
        bottomMargin=8,
    )

    table_data = [[
        "S/No","Company","Branch","Loan No","Vehicle No","Loan Date",
        "Customer Name","Mobile","Guarantor","G. Mobile",
        "Class","Inst Date","Month TBC","Total",
        "LPC","VAS","EMI","EMI 2","Run EMI",
        "Paid","Bal","Inst",
        "Last Rcvd","Seize","Address","Executive"
    ]]

    for i, r in enumerate(final_data, 1):
        table_data.append([
            i,
            wrap_cell(r.get("company"), 20),
            wrap_cell(r.get("branch"), 20),
            wrap_cell(r.get("loan_number"), 20),
            wrap_cell(r.get("vehicle_no"), 20),
            wrap_cell(r.get("loan_date"), 15),
            wrap_cell(r.get("customer_name"), 25),
            wrap_cell(r.get("cust_mobile"), 15),
            wrap_cell("" if str(r.get("guarantor")) == "0" else r.get("guarantor"), 25),
            wrap_cell("" if str(r.get("guarantor_mobile")) == "0" else r.get("guarantor_mobile"), 15),
            wrap_cell(r.get("vehicle_class"), 15),
            wrap_cell(r.get("installment_date"), 15),
            wrap_cell(clean_colon_zero(r.get("month_tbc")), 10),
            wrap_cell(r.get("total_dues"), 10),
            wrap_cell(r.get("lpc_dues"), 10),
            wrap_cell(r.get("vas_hl"), 10),
            wrap_cell(r.get("emi_due"), 10),
            wrap_cell(
                "" if str(r.get("emi_due_2")).strip().lower() == "0"
                else str(r.get("emi_due_2")).upper(),
                10
            ),
            wrap_cell(r.get("running_emi"), 10),
            wrap_cell(r.get("paid_inst"), 10),
            wrap_cell(r.get("balance_inst"), 10),
            wrap_cell(r.get("inst"), 8),
            wrap_cell(r.get("last_rcvd_date"), 15),
            wrap_cell(r.get("seize_date"), 15),
            wrap_cell(r.get("customer_address"), 50),
            wrap_cell(r.get("collection_executive"), 20),
        ])

    col_widths = [
        18, 38, 40, 48, 48, 40,
        58, 48, 58, 48,
        33, 40, 28, 38,
        28, 28, 28, 28, 28,
        18, 18, 18,
        40, 38,
        100, 60
    ]

    table = Table(table_data, colWidths=col_widths, repeatRows=1)

    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("BACKGROUND", (0,0), (-1,0), colors.darkblue),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("FONT", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 3),
        ("RIGHTPADDING", (0,0), (-1,-1), 3),
        ("TOPPADDING", (0,0), (-1,-1), 2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
    ]))

    doc.build([table])
    return response





import datetime
from collections import Counter
from django.shortcuts import render
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.db.models import Q


from .models import (
    Lcc,
    ExecutiveVisitScheduling,
    Clu,
    CollectionAllocations,
    Repo,
    Paid,
    Closed,
    Hero,
    KotakECS,
    EseBuzz,
    Smsquare,
    Upi,
    Freshdesk, 
    Dialer,
    DueNotice,
)

def parse_emi_bucket(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


EMI_BUCKETS = {
    "0_0": (0, 0),
    "1_5": (1, 5),
    "6_10": (6, 10),
    "11_20": (11, 20),
    "21_50": (21, 50),
    "50_plus": (51, None),
}

# ------------------------------------------------------------------
# CLU VISIT DATE PARSER
# ------------------------------------------------------------------
def parse_visited_on(value):
    if not value:
        return None

    value = value.strip()
    formats = [
        "%b %d,%Y, %I:%M:%S %p",
        "%d-%b-%Y %I:%M %p",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
    ]

    for fmt in formats:
        try:
            return datetime.datetime.strptime(value, fmt)
        except Exception:
            continue

    return None


# ------------------------------------------------------------------
# EMI NORMALIZER
# ------------------------------------------------------------------
def normalize_emi(value):
    if value is None:
        return ""
    return str(value).strip().lower()


def parse_payment_date_safe(val):
    if not val:
        return None

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%b %d,%Y, %I:%M:%S %p",
    ):
        try:
            return datetime.datetime.strptime(str(val).strip(), fmt)
        except Exception:
            continue
    return None

def clean_payment_value(val):
    if not val:
        return None
    val = str(val).strip()
    return None if val.lower() == "nan" else val
# ------------------------------------------------------------------
# PAYMENT STATUS LOGIC (MINIMAL SAFE FIX)
# ------------------------------------------------------------------

TOLERANCE = 500

def get_loan_status(lcc, paid_amount, repo_set, closed_set):
    loan_no = lcc.loan_number

    # 1️⃣ CLOSED
    if loan_no in closed_set:
        return "CLOSED"

    # 2️⃣ REPO
    if loan_no in repo_set:
        return "REPO"

    # 3️⃣ EMI = 0 / SEZ / NONE (unchanged logic, only interpretation)
    if str(lcc.emi_due_2).strip().lower() in ("0", "", "none", "sez"):
        return "PAID" if paid_amount and paid_amount > 0 else "NOT PAID"

    # 4️⃣ Parse values
    try:
        received = float(paid_amount or 0)
        month_tbc = float(lcc.month_tbc or 0)
        total_dues = float(lcc.total_dues or 0)
        emi_due_2 = float(lcc.emi_due_2)
    except Exception:
        return "NOT PAID"

    # 5️⃣ Calculate revised month TBC (UNCHANGED)
    if month_tbc == 0:
        revised_month_tbc = total_dues / emi_due_2 if emi_due_2 else 0
    else:
        revised_month_tbc = month_tbc

    # ✅ 6️⃣ FINAL DECISION (ONLY SMALL ADDITION: received > 0)
    if received > 0 and (
        received >= revised_month_tbc or
        (revised_month_tbc - received) <= TOLERANCE
    ):
        return "PAID"
    elif received > 0:
        return "PARTLY PAID"
    else:
        return "NOT PAID"







# ------------------------------------------------------------------
# EXECUTIVE VISIT SCHEDULE LIST
# ------------------------------------------------------------------
import hashlib
@financehub_required
def executive_visit_schedule_list(request):

    qs_hash = hashlib.md5(
            request.GET.urlencode().encode()
        ).hexdigest()

    cache_key = f"exec_schedule_{request.user.id}_{qs_hash}"

    division   = request.GET.get("division", "").strip()
    blc_case = request.GET.get("blc_case", "").strip()

    loanno     = request.GET.get("loanno", "").strip()
    empid      = request.GET.get("empid", "").strip()
    from_date  = request.GET.get("from_date", "").strip()
    to_date    = request.GET.get("to_date", "").strip()


    role = request.GET.get("role", "").strip()
    search_empid = request.GET.get("search_empid", "").strip()

    loan_status_filter = request.GET.get("loan_status", "").strip()
    emi_bucket = request.GET.get("emi_bucket", "").strip()


    # ✅ NEW: EMI FILTER FLAGS
    remove_zeros = request.GET.get("remove_zeros") == "1"
    remove_sez   = request.GET.get("remove_sez") == "1"

    # ✅ NEW: BRANCH / CENTRE FILTERS
    branch = request.GET.get("branch", "").strip()
    centre_name = request.GET.get("centre_name", "").strip()
    visit_filter = request.GET.get("visit_filter", "").strip()

    login_empid = request.user.username
    today = datetime.date.today()

    # ==========================================================
    # 1️⃣ BASE LCC
    # ==========================================================
    lcc_qs = Lcc.objects.all().order_by("loan_number")

    if division:
        lcc_qs = lcc_qs.filter(division__icontains=division)

    # ✅ NEW: Branch filter
    if branch:
        lcc_qs = lcc_qs.filter(branch=branch)
    # ✅ BLC CASE FILTER
    if blc_case:
        lcc_qs = lcc_qs.filter(blc_cases__icontains=blc_case.strip())


    # ✅ NEW: Centre filter
    if centre_name:
        lcc_qs = lcc_qs.filter(centre_name=centre_name)

    if loanno:
        lcc_qs = lcc_qs.filter(loan_number__icontains=loanno)

    loan_numbers = list(lcc_qs.values_list("loan_number", flat=True))

    # ==========================================================
    # REPO / CLOSED / PAID DATA
    # ==========================================================
    repo_set = set(
        Repo.objects.filter(
            agreement_number__in=loan_numbers
        ).values_list("agreement_number", flat=True)
    )

    closed_set = set(
        Closed.objects.filter(
            loan_number__in=loan_numbers
        ).values_list("loan_number", flat=True)
    )

    paid_map = {}
    received_date_map = {}

    for p in Paid.objects.filter(loan_number__in=loan_numbers):
        try:
            amt = float(p.received_amount or 0)
        except Exception:
            amt = 0

        paid_map[p.loan_number] = paid_map.get(p.loan_number, 0) + amt

        if p.received_date:
            prev = received_date_map.get(p.loan_number)
            if not prev or p.received_date > prev:
                received_date_map[p.loan_number] = p.received_date
    # ==========================================================
    # ✅ PAYMENT MERGE (LATEST ONLY + MULTI SOURCE)
    # ==========================================================

    payment_latest_map = {}
    payment_source_map = {}

    def push_payment(loan, status, date, amount, source):
        date_parsed = parse_payment_date_safe(date)
        if not loan:
            return

        # ✅ Track ALL sources (even if date missing)
        payment_source_map.setdefault(loan, set()).add(source)

        # ❌ If date missing → cannot be latest
        if not date_parsed:
            return

        current = payment_latest_map.get(loan)

        if not current or date_parsed > current["date"]:
            payment_latest_map[loan] = {
                "status": clean_payment_value(status),
                "date": date_parsed,
                "amount": clean_payment_value(amount),
                "source": source,   # temporary, final source set later
            }


    # -------------------------
    # HERO
    # -------------------------
    for h in Hero.objects.filter(referencenumber__in=loan_numbers):
        push_payment(
            h.referencenumber,
            h.status,
            h.date,
            h.amount,
            "HERO"
        )

    # -------------------------
    # KOTAK ECS
    # -------------------------
    for k in KotakECS.objects.filter(loannumber__in=loan_numbers):
        push_payment(
            k.loannumber,
            k.ecsstatus,
            k.ecsdate,
            k.amount,
            "KOTAK"
        )

    # -------------------------
    # ESEBUZZ
    # -------------------------
    for e in EseBuzz.objects.filter(loanno__in=loan_numbers):
        push_payment(
            e.loanno,
            e.status,
            e.initiateddate,
            e.amount,
            "ESEBUZZ"
        )

    # -------------------------
    # SMSQUARE
    # -------------------------
    for s in Smsquare.objects.filter(uniqueregistrationnumber__in=loan_numbers):
        push_payment(
            s.uniqueregistrationnumber,
            s.status,
            s.date,
            s.amount,
            "SMSQUARE"
        )

    # -------------------------
    # UPI
    # -------------------------
    for u in Upi.objects.filter(loannoreference__in=loan_numbers):
        push_payment(
            u.loannoreference,
            u.paymentstatus,
            u.paymentdatetime,
            u.transactionamount,
            "UPI"
        )


    # ==========================================================
    # ✅ FINAL SOURCE MERGE (UPI + HERO + etc.)
    # ==========================================================
    for loan, latest in payment_latest_map.items():
        sources = payment_source_map.get(loan, set())
        latest["source"] = " + ".join(sorted(sources))

    # ==========================================================
    # 2️⃣ COLLECTION ALLOCATIONS (UNCHANGED)
    # ==========================================================
    alloc_qs = CollectionAllocations.objects.filter(
        loan_number__in=loan_numbers
    )

    if CollectionAllocations.objects.filter(manager_employee_id=login_empid).exists():
        login_role = "CM"
    elif CollectionAllocations.objects.filter(tl_employee_id=login_empid).exists():
        login_role = "TL"
    else:
        login_role = "EXEC"

    if login_role == "CM":
        alloc_qs = alloc_qs.filter(manager_employee_id=login_empid)
    elif login_role == "TL":
        alloc_qs = alloc_qs.filter(tl_employee_id=login_empid)
    else:
        alloc_qs = alloc_qs.filter(employee_id=login_empid)

    if role == "CM" and search_empid:
        alloc_qs = alloc_qs.filter(
            Q(tl_employee_id=search_empid) |
            Q(employee_id=search_empid)
        )
    elif role == "TL" and search_empid:
        alloc_qs = alloc_qs.filter(tl_employee_id=search_empid)
    elif role == "EXEC" and search_empid:
        alloc_qs = alloc_qs.filter(employee_id=search_empid)

    if role or search_empid:
        loan_numbers = list(
            alloc_qs.values_list("loan_number", flat=True)
        )

    alloc_map = {a.loan_number: a for a in alloc_qs}

    # ==========================================================
    # 3️⃣ VISITS (UNCHANGED)
    # ==========================================================
    visit_qs = ExecutiveVisitScheduling.objects.filter(
        loanno__in=loan_numbers
    )

    if empid:
        visit_qs = visit_qs.filter(empid__icontains=empid)

    if from_date and to_date:
        visit_qs = visit_qs.filter(
            visit_schedule_date__range=[from_date, to_date]
        )
    elif from_date:
        visit_qs = visit_qs.filter(visit_schedule_date__gte=from_date)
    elif to_date:
        visit_qs = visit_qs.filter(visit_schedule_date__lte=to_date)

    visit_map = {}
    for v in visit_qs:
        visit_map.setdefault(v.loanno, []).append(v)

    # ==========================================================
    # 4️⃣ CLU LATEST VISIT (UNCHANGED)
    # ==========================================================
    latest_visit_map = {}
    for c in Clu.objects.filter(loan_number__in=loan_numbers).values("loan_number", "visited_on"):
        dt = parse_visited_on(c["visited_on"])
        if not dt:
            continue
        loan = c["loan_number"]
        if loan not in latest_visit_map or dt > latest_visit_map[loan]["dt"]:
            latest_visit_map[loan] = {"dt": dt, "visited_on": c["visited_on"]}



    
    # =========================================================
    # VISITOR (LATEST PER LOAN NUMBER)
    # =========================================================
    visitor_map = {}

    for v in (
        Visiter.objects
        .filter(loan_number__in=loan_numbers)
        .order_by("-created_at")
    ):
        if v.loan_number not in visitor_map:
            visitor_map[v.loan_number] = v


    # =========================================================
    # DUE NOTICE (LATEST PER LOAN)
    # =========================================================
    due_notice_map = {}

    for n in (
        DueNotice.objects
        .filter(loan_number__in=loan_numbers)
        .order_by("-notice_date", "-id")
    ):
        if n.loan_number not in due_notice_map:
            due_notice_map[n.loan_number] = n


    # =========================================================
# FRESHDESK (LATEST PER LOAN NUMBER)
# =========================================================
    freshdesk_map = {}
    loan_set = set(loan_numbers)
    for f in Freshdesk.objects.filter(subject__isnull=False).order_by("-created_time"):
        subject = f.subject or ""
        for ln in loan_set:
            if ln in subject:
                freshdesk_map.setdefault(ln, f)



    # =========================================================
# DIALER FULL DATA (SAME AS FEEDBACK / EXCEL)
# =========================================================

    def normalize_mobile(num):
        if not num:
            return None
        s = str(num).strip()
        if s.startswith("91") and len(s) == 12:
            return s[2:]
        return s


    dialer_map = {}

    cust_mobiles = {
        normalize_mobile(l.cust_mobile)
        for l in lcc_qs
        if l.cust_mobile
    }

    dialer_qs = Dialer.objects.filter(
        mobile__in=cust_mobiles
    ).order_by("-created_at")


    for d in dialer_qs:
        mobile = normalize_mobile(d.mobile)
        if not mobile:
            continue

        dialer_map.setdefault(mobile, {
            "Dialer_PTP": "",
            "Dialer_PTP_Date": "",
            "Dialer_PTP_Remarks": "",

            "Dialer_RTP": "",
            "Dialer_RTP_Date": "",
            "Dialer_RTP_Remarks": "",

            "Dialer_Thirdparty": "",
            "Dialer_Thirdparty_Date": "",
            "Dialer_Thirdparty_Remarks": "",

            "Dialer_other": "",
            "Dialer_other_Date": "",
            "Dialer_other_Remarks": "",
        })

        row = dialer_map[mobile]
        disp = (d.disp or "").upper()

        if disp == "PTP" and not row["Dialer_PTP"]:
            row.update({
                "Dialer_PTP": d.disp,
                "Dialer_PTP_Date": d.ptp_date,
                "Dialer_PTP_Remarks": d.remarks,
            })

        elif disp == "RTP" and not row["Dialer_RTP"]:
            row.update({
                "Dialer_RTP": d.disp,
                "Dialer_RTP_Date": d.ptp_date,
                "Dialer_RTP_Remarks": d.remarks,
            })

        elif disp == "THIRD PARTY" and not row["Dialer_Thirdparty"]:
            row.update({
                "Dialer_Thirdparty": d.disp,
                "Dialer_Thirdparty_Date": d.ptp_date,
                "Dialer_Thirdparty_Remarks": d.remarks,
            })

        elif not row["Dialer_other"]:
            row.update({
                "Dialer_other": d.disp,
                "Dialer_other_Date": d.ptp_date,
                "Dialer_other_Remarks": d.remarks,
            })





    # ==========================================================
    # 5️⃣ FINAL DATA (UNCHANGED LOGIC)
    # ==========================================================
    final_data = []

    for l in lcc_qs.filter(loan_number__in=loan_numbers):
        visitor = visitor_map.get(l.loan_number)

        notice = due_notice_map.get(l.loan_number)


        cust_mobile_norm = normalize_mobile(l.cust_mobile)

        dialer = dialer_map.get(cust_mobile_norm, {})
        
        fd = freshdesk_map.get(l.loan_number)

        payment = payment_latest_map.get(l.loan_number)

        emi_value = normalize_emi(l.emi_due_2)

        if remove_zeros and emi_value in ("0", "0.0"):
            continue

        if remove_sez and emi_value == "sez":
            continue

        visits = visit_map.get(l.loan_number, [])
        alloc = alloc_map.get(l.loan_number)
        last_visit = latest_visit_map.get(l.loan_number)

        future_visits = [x for x in visits if x.visit_schedule_date and x.visit_schedule_date >= today]
        pending_visits = [x for x in visits if not x.visit_status]

        if future_visits:
            v = min(future_visits, key=lambda x: x.visit_schedule_date)
        elif pending_visits:
            v = max(pending_visits, key=lambda x: x.visit_schedule_date)
        elif visits:
            v = max(visits, key=lambda x: x.visit_schedule_date)
        else:
            v = None

        status = get_loan_status(
            l,
            paid_map.get(l.loan_number, 0),
            repo_set,
            closed_set
        )




        final_data.append({
            # =========================
            # LIST / LOGIC FIELDS
            # =========================
            "obj": v,
            "loan_status": status,
            "bucket_position": l.emi_due_2,
            "received_date": received_date_map.get(l.loan_number),
            "cm": alloc.cm if alloc else "",
            "cm_id": alloc.manager_employee_id if alloc else "",
            "tl": alloc.tl if alloc else "",
            "tl_id": alloc.tl_employee_id if alloc else "",
            "exec": alloc.executive_name if alloc else "",
            "exec_id": alloc.employee_id if alloc else "",
            "empid": v.empid if v else None,
            "visit_date": v.visit_schedule_date if v else None,
            "visit_status": v.visit_status if v else None,
            "not_visited_reason": v.not_visited_reason if v else None,
            "latest_visited_on": last_visit["visited_on"] if last_visit else "",
            "has_schedule": bool(v),
            "blc_case": l.blc_cases,
            "division": l.division,

            # =========================
            # PDF FIELDS (NO DUPLICATES)
            # =========================
            "company": l.company,
            "branch": l.branch,
            "loan_number": l.loan_number,
            "vehicle_no": l.vehicle_no,
            "loan_date": l.loan_date,
            "customer_name": l.customer_name,
            "cust_mobile": l.cust_mobile,
            "guarantor": l.guarantor,
            "guarantor_mobile": l.guarantor_mobile,
            "vehicle_class": l.vehicle_class,
            "installment_date": l.installment_date,
            "month_tbc": l.month_tbc,
            "total_dues": l.total_dues,
            "lpc_dues": l.lpc_dues,
            "vas_hl": l.vas_hl,
            "emi_due": l.emi_due,
            "emi_due_2": l.emi_due_2,
            "running_emi": l.running_emi,
            "paid_inst": l.paid_inst,
            "balance_inst": l.balance_inst,
            "inst": l.inst,
            "last_rcvd_date": l.last_rcvd_date,
            "seize_date": l.seize_date,
            "customer_address": l.customer_address,
            "collection_executive": alloc.executive_name if alloc else "",
             # ✅ PAYMENT OUTPUT
            "payment_status": payment["status"] if payment else "",
            "payment_date": payment["date"].date() if payment else "",
            "payment_amount": payment["amount"] if payment else "",
            "payment_source": payment["source"] if payment else "",

            
            # =========================
            # FRESHDESK
            # =========================
            "Freshdesk_Description": fd.description if fd else "",
            "Freshdesk_Status": fd.status if fd else "",
            "Freshdesk_Group": fd.group if fd else "",
            "Freshdesk_Createdtime": fd.created_time if fd else "",

            # =========================
            # DIALER (FULL)
            # =========================
            "Dialer_PTP": dialer.get("Dialer_PTP", ""),
            "Dialer_PTP_Date": dialer.get("Dialer_PTP_Date", ""),
            "Dialer_PTP_Remarks": dialer.get("Dialer_PTP_Remarks", ""),

            "Dialer_RTP": dialer.get("Dialer_RTP", ""),
            "Dialer_RTP_Date": dialer.get("Dialer_RTP_Date", ""),
            "Dialer_RTP_Remarks": dialer.get("Dialer_RTP_Remarks", ""),

            "Dialer_Thirdparty": dialer.get("Dialer_Thirdparty", ""),
            "Dialer_Thirdparty_Date": dialer.get("Dialer_Thirdparty_Date", ""),
            "Dialer_Thirdparty_Remarks": dialer.get("Dialer_Thirdparty_Remarks", ""),

            "Dialer_other": dialer.get("Dialer_other", ""),
            "Dialer_other_Date": dialer.get("Dialer_other_Date", ""),
            "Dialer_other_Remarks": dialer.get("Dialer_other_Remarks", ""),
            # =========================
            # DUE NOTICE
            # =========================
            "notice_send_to": notice.send_to if notice else "",
            "notice_bar_number": notice.bar_number if notice else "",
            "notice_date": notice.notice_date if notice else "",
            "notice_type": notice.type_of_notice if notice else "",
            "notice_status": notice.notice_status if notice else "",
            "notice_status_label": notice.get_notice_status_display() if notice else "",
            "notice_delivery_date": notice.delivery_date if notice else "",
            "notice_return_date": notice.return_date if notice else "",

            # =========================
            # VISITOR
            # =========================
            "visitor_purpose": visitor.purpose if visitor else "",
            "visitor_remark": visitor.remarks if visitor else "",


        })


    # ==========================================================
    # STATUS COUNTS (UNCHANGED)
    # ==========================================================
    status_counts = Counter()
    for row in final_data:
        key = row["loan_status"].replace(" ", "_")
        status_counts[key] += 1

    if loan_status_filter:
        final_data = [r for r in final_data if r["loan_status"] == loan_status_filter]

    final_data.sort(
        key=lambda x: (not x["has_schedule"], x["visit_date"] or datetime.date.max)
    )



    # ==========================================================
    # ✅ NEW: DROPDOWN DATA
    # ==========================================================
    branches = (
        Lcc.objects.exclude(branch__isnull=True)
        .exclude(branch__exact="")
        .values_list("branch", flat=True)
        .distinct()
        .order_by("branch")
    )

    centres_qs = (
        Lcc.objects.exclude(centre_name__isnull=True)
        .exclude(centre_name__exact="")
    )
    if branch:
        centres_qs = centres_qs.filter(branch=branch)

    centres = (
        centres_qs.values_list("centre_name", flat=True)
        .distinct()
        .order_by("centre_name")
    )


        # ==========================================================
    # ✅ BLC CASE DROPDOWN DATA
    # ==========================================================
    blc_cases = (
        Lcc.objects.exclude(blc_cases__isnull=True)
        .exclude(blc_cases__exact="")
        .values_list("blc_cases", flat=True)
        .distinct()
        .order_by("blc_cases")
    )

        # ==========================================================
    # ✅ EMI BUCKET FILTER (SAFE – PYTHON LEVEL)
    # ==========================================================
    if emi_bucket in EMI_BUCKETS:
        low, high = EMI_BUCKETS[emi_bucket]

        filtered_data = []
        for row in final_data:
            emi = parse_emi_bucket(row.get("bucket_position"))

            if emi is None:
                continue

            if high is None:
                if emi >= low:
                    filtered_data.append(row)
            else:
                if low <= emi <= high:
                    filtered_data.append(row)

        final_data = filtered_data

# ==========================================================
# ✅ VISIT STATUS FILTER (VISITED / NOT VISITED / SCHEDULED / NOT SCHEDULED)
# ==========================================================
    if visit_filter == "visited":
        final_data = [
            r for r in final_data
            if r.get("visit_status") == "visited"
        ]

    elif visit_filter == "not_visited":
        final_data = [
            r for r in final_data
            if r.get("visit_status") == "not_visited"
        ]

    elif visit_filter == "scheduled":
        final_data = [
            r for r in final_data
            if r.get("has_schedule")
            and (not r.get("visit_status") or r.get("visit_status") == "")
        ]

    elif visit_filter == "not_scheduled":
        final_data = [
            r for r in final_data
            if not r.get("has_schedule")
        ]

    if request.GET.get("download") == "pdf":
        return export_lcc_pdf(final_data)
    
    if request.GET.get("download") == "excel":
        return export_lcc_excel(final_data)


    paginator = Paginator(final_data, 500)
    page_obj = paginator.get_page(request.GET.get("page"))

 
    response = render(request, "financehub/executive_visit_schedule_list.html", {
        "data": page_obj,
        "total_count": paginator.count,
        "division": division,
        "loanno": loanno,
        "empid": empid,
        "from_date": from_date,
        "to_date": to_date,
        "role": role,
        "search_empid": search_empid,
        "loan_status": loan_status_filter,
        "status_counts": status_counts,

        "remove_zeros": remove_zeros,
        "remove_sez": remove_sez,
        "branch": branch,
        "centre_name": centre_name,
        "branches": branches,
        "centres": centres,
        "emi_bucket": emi_bucket,
        "visit_filter": visit_filter,
        "blc_cases": blc_cases,
        "selected_blc_case": blc_case,
    })

    cache.set(cache_key, response, 60)
    return response



@financehub_required
def executive_visit_schedule_edit(request, pk):
    obj = ExecutiveVisitScheduling.objects.get(pk=pk)

    if request.method == "POST":
        obj.loanno = request.POST.get("loanno")
        obj.empid = request.POST.get("empid")
        obj.visit_schedule_date = request.POST.get("visit_schedule_date")
        obj.save()

        messages.success(request, "Visit schedule updated successfully")
        return redirect("executive_visit_schedule_list")

    return render(request, "financehub/executive_visit_schedule_edit.html", {
        "obj": obj
    })





@financehub_required
def executive_my_visits(request):
    empid = request.user.username  # employee_id

    visits = ExecutiveVisitScheduling.objects.filter(
        empid=empid
    ).order_by("visit_schedule_date")

    # collect loan numbers
    loan_numbers = list(
        visits.values_list("loanno", flat=True)
    )

    # fetch LCC data
    lcc_map = {
        l.loan_number: l
        for l in Lcc.objects.filter(loan_number__in=loan_numbers)
    }

    # merge data
    data = []
    for v in visits:
        lcc = lcc_map.get(v.loanno)

        data.append({
            "visit": v,                          # IMPORTANT
            "loan_number": v.loanno,
            "visit_date": v.visit_schedule_date,
            "status": v.visit_status,
            "customer_name": lcc.customer_name if lcc else "",
            "vehicle_no": lcc.vehicle_no if lcc else "",
        })

    return render(request, "financehub/executive_my_visits.html", {
        "data": data
    })





from django.utils import timezone

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from .models import (
    ExecutiveVisitScheduling,
    CollectionAllocations,   # ✅ REQUIRED
)


from django.utils import timezone
@financehub_required
def executive_visit_response(request, pk):

    visit = get_object_or_404(ExecutiveVisitScheduling, pk=pk)
    next_url = request.POST.get("next") or request.GET.get("next")

    # EXEC CHECK (unchanged logic)
    is_exec = CollectionAllocations.objects.filter(
        employee_id=request.user.username
    ).exists()

    if request.method == "POST":

        # ---------------- RESPONSE (ALWAYS)
        visit.visit_status = request.POST.get("visit_status")

        reason = request.POST.get("not_visited_reason", "").strip()
        if visit.visit_status == "not_visited":
            visit.not_visited_reason = reason
        else:
            visit.not_visited_reason = ""   # clear old reason safely

        # ---------------- SCHEDULING (ONLY IF PROVIDED & NOT EXEC)
        if not is_exec:

            empid = request.POST.get("empid")
            visit_date = request.POST.get("visit_schedule_date")

            # ✅ ONLY UPDATE IF USER CHANGED IT
            if empid:
                visit.empid = empid

            if visit_date:
                visit.visit_schedule_date = visit_date

        visit.save()
        return redirect(next_url or "executive_visit_schedule_list")

    return render(request, "financehub/executive_visit_response.html", {
        "visit": visit,
        "next": next_url,
        "is_exec": is_exec,
    })




from django.db.models import Q
from django.core.paginator import Paginator
from .models import DueNotice

@financehub_required
def due_notice_list(request):

    query = request.GET.get("q", "").strip()
    qs = DueNotice.objects.all().order_by("-created_at")

    # 🔍 SEARCH
    if query:
        qs = qs.filter(
            Q(loan_number__icontains=query) |
            Q(bar_number__icontains=query) |
            Q(vehicle_no__icontains=query) |
            Q(customer_name__icontains=query) |
            Q(company__icontains=query) |
            Q(branch__icontains=query) |
            Q(send_to__icontains=query) |
            Q(type_of_notice__icontains=query) |
            Q(notice_status__icontains=query)
        )

    # 🔄 UPDATE STATUS + DATE
    if request.method == "POST":
        notice_id = request.POST.get("notice_id")
        status = request.POST.get("notice_status")
        delivery_date = request.POST.get("delivery_date")
        return_date = request.POST.get("return_date")

        if notice_id and status:
            update_data = {"notice_status": status}

            if status == DueNotice.NoticeStatus.DELIVERED:
                if not delivery_date:
                    return redirect(f"{request.path}?q={query}")
                update_data["delivery_date"] = delivery_date
                update_data["return_date"] = None

            elif status == DueNotice.NoticeStatus.RETURNED:
                if not return_date:
                    return redirect(f"{request.path}?q={query}")
                update_data["return_date"] = return_date
                update_data["delivery_date"] = None

            else:  # IN TRANSIT
                update_data["delivery_date"] = None
                update_data["return_date"] = None

            DueNotice.objects.filter(id=notice_id).update(**update_data)

        return redirect(f"{request.path}?q={query}")

    # 📄 PAGINATION
    paginator = Paginator(qs, 500)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    STATUS_CHOICES = DueNotice.NoticeStatus.choices

    return render(
        request,
        "financehub/due_notice_list.html",
        {
            "page_obj": page_obj,
            "query": query,
            "status_choices": STATUS_CHOICES,
        },
    )
