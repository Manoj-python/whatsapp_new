# financehub/views.py

import os
import tempfile
from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.core.paginator import Paginator
from django.db.models import Q

from .models import UploadHistory, Lcc, Feedback
from .forms import FeedbackForm
from financehub.tasks import process_loan_file


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
@financehub_required
def upload_loan_data(request):

    msg = None
    error = None

    if request.method == "POST":
        file = request.FILES.get("file")
        user = request.user.username

        if not file:
            return render(request, "financehub/upload.html",
                          {"error": "Please select a file."})

        if file.size > MAX_UPLOAD_SIZE:
            return render(request, "financehub/upload.html",
                          {"error": "File too large. Max 25MB allowed."})

        filename = file.name
        ext = filename.split(".")[-1].lower()

        if ext not in ("csv", "xlsx", "xls"):
            return render(request, "financehub/upload.html",
                          {"error": "Only CSV/XLS/XLSX allowed."})

        tmp_dir = getattr(settings, "DATA_UPLOAD_TEMP_DIR", tempfile.gettempdir())
        tmp_path = os.path.join(tmp_dir, f"upload_{filename}")

        with open(tmp_path, "wb+") as f:
            for chunk in file.chunks():
                f.write(chunk)

        upload_record = UploadHistory.objects.create(
            filename=filename,
            uploaded_by=user
        )

        # Send to Celery Worker
        process_loan_file.delay(upload_record.id, tmp_path, ext)

        msg = "Upload successful! Background processing started."

    return render(request, "financehub/upload.html", {"msg": msg, "error": error})






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
