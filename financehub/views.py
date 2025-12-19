# financehub/views.py

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

# Models
from datetime import datetime

from .models import (
    UploadHistory,
    Lcc,
    Feedback,
    ExecutiveVisitScheduling,
    Clu,   # ✅ ADD THIS
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
    paginator = Paginator(qs, 1000)
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





# ---------------------------------------------------------------------
# CREATE FEEDBACK
# ---------------------------------------------------------------------

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
        })

    # ----------------------------
    # CASE 2: OPENED FROM LCC TABLE
    # ----------------------------
    try:
        l = Lcc.objects.get(loan_number=loan_no)
    except Lcc.DoesNotExist:
        l = None

    cust_mobile = l.cust_mobile if l else ""
    guar_mobile = l.guarantor_mobile if l else ""
    veh_no = l.vehicle_no if l else ""
    cust_name = l.customer_name if l else ""
    guar_name = l.guarantor if l else ""

    # ----------------------------
    # EXACT LOAN FEEDBACK
    # ----------------------------
    exact_fb = list(Feedback.objects.filter(LoanNO=loan_no).order_by("-id"))

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

    related_qs = Lcc.objects.filter(filters).exclude(loan_number=loan_no)

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









import datetime
from django.shortcuts import render
from django.core.paginator import Paginator

from .models import (
    Lcc,
    ExecutiveVisitScheduling,
    Clu,
)

from django.contrib.auth.decorators import login_required


# ------------------------------------------------------------------
# CLU VISIT DATE PARSER (ROBUST)
# ------------------------------------------------------------------
def parse_visited_on(value):
    if not value:
        return None

    value = value.strip()

    formats = [
        "%b %d,%Y, %I:%M:%S %p",   # Nov 14,2024, 9:50:54 PM
        "%d-%b-%Y %I:%M %p",       # 14-Nov-2024 09:50 PM
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
# EXECUTIVE VISIT SCHEDULE LIST
# ------------------------------------------------------------------
@login_required
def executive_visit_schedule_list(request):

    division   = request.GET.get("division", "").strip()
    loanno     = request.GET.get("loanno", "").strip()
    empid      = request.GET.get("empid", "").strip()
    from_date  = request.GET.get("from_date", "").strip()
    to_date    = request.GET.get("to_date", "").strip()

    final_data = []

    # ==========================================================
    # 1️⃣ BASE → LCC
    # ==========================================================
    lcc_qs = Lcc.objects.all().order_by("loan_number")

    if division:
        lcc_qs = lcc_qs.filter(division__icontains=division)

    if loanno:
        lcc_qs = lcc_qs.filter(loan_number__icontains=loanno)

    loan_numbers = list(
        lcc_qs.values_list("loan_number", flat=True)
    )

    # ==========================================================
    # 2️⃣ VISIT SCHEDULING
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

    # ----------------------------------------------------------
    # MAP: loan_number → list of visits
    # ----------------------------------------------------------
    visit_map = {}
    for v in visit_qs:
        visit_map.setdefault(v.loanno, []).append(v)

    # ==========================================================
    # 3️⃣ CLU → LATEST VISIT PER LOAN
    # ==========================================================
    clu_rows = Clu.objects.filter(
        loan_number__in=loan_numbers
    ).values("loan_number", "visited_on")

    latest_visit_map = {}

    for c in clu_rows:
        dt = parse_visited_on(c["visited_on"])
        if not dt:
            continue

        loan = c["loan_number"]

        if (
            loan not in latest_visit_map
            or dt > latest_visit_map[loan]["dt"]
        ):
            latest_visit_map[loan] = {
                "dt": dt,
                "visited_on": c["visited_on"],
            }

    # ==========================================================
    # 4️⃣ FINAL MERGE (1 ROW PER LOAN)
    # ==========================================================
    for l in lcc_qs:

        visits = visit_map.get(l.loan_number, [])
        last_visit = latest_visit_map.get(l.loan_number)

        if visits:
            # earliest scheduled visit
            v = min(visits, key=lambda x: x.visit_schedule_date)

            final_data.append({
                "obj": v,
                "loan_number": l.loan_number,
                "customer_name": l.customer_name,
                "vehicle_no": l.vehicle_no,
                "empid": v.empid,
                "visit_date": v.visit_schedule_date,
                "visit_status": v.visit_status,
                "not_visited_reason": v.not_visited_reason,
                "latest_visited_on": last_visit["visited_on"] if last_visit else "",
                "has_schedule": True,
            })
        else:
            final_data.append({
                "obj": None,
                "loan_number": l.loan_number,
                "customer_name": l.customer_name,
                "vehicle_no": l.vehicle_no,
                "empid": None,
                "visit_date": None,
                "visit_status": None,
                "not_visited_reason": None,
                "latest_visited_on": last_visit["visited_on"] if last_visit else "",
                "has_schedule": False,
            })

    # ==========================================================
    # 5️⃣ SORT → SCHEDULED FIRST
    # ==========================================================
    final_data.sort(
        key=lambda x: (
            not x["has_schedule"],
            x["visit_date"] or datetime.date.max
        )
    )

    # ==========================================================
    # 6️⃣ PAGINATION
    # ==========================================================
    paginator = Paginator(final_data, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "financehub/executive_visit_schedule_list.html", {
        "data": page_obj,
        "total_count": paginator.count,

        "division": division,
        "loanno": loanno,
        "empid": empid,
        "from_date": from_date,
        "to_date": to_date,
    })










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

@financehub_required
def executive_visit_response(request, pk):
    obj = ExecutiveVisitScheduling.objects.get(pk=pk)

    if not (
        request.user.is_staff
        or request.user.is_superuser
        or obj.empid == request.user.username
    ):
        messages.error(request, "Unauthorized access")
        return redirect("executive_visit_schedule_list")

    if request.method == "POST":
        status = request.POST.get("visit_status")
        reason = request.POST.get("not_visited_reason")

        obj.visit_status = status
        obj.not_visited_reason = reason if status == "not_visited" else ""
        obj.responded_at = timezone.now()   # ✅ FIX
        obj.save()

        messages.success(request, "Visit response saved successfully")

        if request.user.is_staff or request.user.is_superuser:
            return redirect("executive_visit_schedule_list")
        else:
            return redirect("executive_my_visits")

    return render(request, "financehub/executive_visit_response.html", {
        "obj": obj
    })





