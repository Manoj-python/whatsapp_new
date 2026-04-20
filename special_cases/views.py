import os
import tempfile
from django.conf import settings
from .tasks import process_universal_file
from .models import *
from financehub.views import financehub_required
from financehub.models import *
from django.shortcuts import render
from django.db.models import Q,Value
from django.core.paginator import Paginator
from django.db.models.functions import Replace
import unicodedata
from django.http import JsonResponse


FILE_TYPES = [
    ("write_off", "Write Off"),
    ("dealer_ta_balances", "Dealer TA Balances"),
    ("auction", "Auction"),
    ("ledger", "Ledger"),
]

def splcase_login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(username=username, password=password)
        if user:
            # Custom session KEY
            request.session["spl_user"] = user.id
            return redirect("upload")
        else:
            messages.error(request, "Invalid username or password")

    return render(request, "spl_case/login.html")

def splcase_logout(request):
    request.session.pop("spl_user", None)
    return redirect("/login3/")


def splcase_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.session.get("spl_user"):
            return redirect("splcase_login")
        return view_func(request, *args, **kwargs)
    return wrapper



@splcase_required
def upload_data(request):

    if request.method == "POST":
        file_type = request.POST.get("file_type")
        file = request.FILES.get("file")

        if not file_type:
            return render(request, "spl_case/upload_xcel.html", {
                "error": "Please select file type.",
                "file_types": FILE_TYPES
            })

        if not file:
            return render(request, "spl_case/upload_xcel.html", {
                "error": "Please choose a file.",
                "file_types": FILE_TYPES
            })

        # ✅ VALIDATE EXTENSION
        ext = file.name.split(".")[-1].lower()
        if ext not in ("csv", "xlsx", "xls"):
            return render(request, "spl_case/upload_xcel.html", {
                "error": "Only CSV / XLS / XLSX allowed.",
                "file_types": FILE_TYPES
            })

        # ✅ SAVE FILE TEMP
        tmp_dir = getattr(settings, "DATA_UPLOAD_TEMP_DIR", tempfile.gettempdir())
        tmp_path = os.path.join(tmp_dir, f"upload_{file.name}")

        with open(tmp_path, "wb+") as f:
            for chunk in file.chunks():
                f.write(chunk)

        # ✅ CREATE HISTORY
        upload = SPLUploadHistory.objects.create(
            filename=file.name,
            uploaded_by=request.user.username,
            file_type=file_type,
            status="processing",
            total_rows=0,
            processed_rows=0
        )

        # ✅ CALL CELERY
        process_universal_file.delay(upload.id, tmp_path, ext, file_type)

        return render(request, "spl_case/upload_xcel.html", {
            "msg": f"Upload started! ID = {upload.id}",
            "file_types": FILE_TYPES,
            "upload_id": upload.id
        })

    return render(request, "spl_case/upload_xcel.html", {
        "file_types": FILE_TYPES
    })



def upload_spl_progress(request, upload_id):
    try:
        upload = SPLUploadHistory.objects.get(id=upload_id)

        # ✅ Avoid division error
        total = upload.total_rows or 0
        processed = upload.processed_rows or 0

        percent = 0
        if total > 0:
            percent = int((processed / total) * 100)

        return JsonResponse({
            "status": upload.status,
            "processed": processed,
            "total": total,
            "percent": percent,
            "error": upload.error_message or "",
        })

    except SPLUploadHistory.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "error": "Invalid Upload ID"
        }, status=404)

    except Exception as e:
        return JsonResponse({
            "status": "error",
            "error": str(e)
        }, status=500)

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


@splcase_required
def lcc_detail_list(request):

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

    return render(request, "spl_case/lcc_list.html", {
        "data": page_obj,
        "search": search_clean,
        "query_string": params.urlencode(),
    })


# ================= VIEW =================
@financehub_required
def write_off_list(request):
    search_raw = request.GET.get("search", "").strip()
    search_clean = normalize_excel_text(search_raw)

    base_qs = Write_Off.objects.all()

    # ================= NO SEARCH =================
    if not search_raw:
        qs = base_qs.order_by("id")

    else:
        # ================= PRIMARY EXACT MATCH =================
        primary = base_qs.filter(
            Q(loan_no__iexact=search_clean) |
            Q(vehicle_no__iexact=search_clean) |
            Q(cif_id__iexact=search_clean) |
            Q(customer_mobile__iexact=search_clean) |
            Q(guarantor_mobile__iexact=search_clean)
        )

        # ================= NAME SEARCH =================
        if not primary.exists():

            # remove spaces for matching
            search_name = search_raw.replace(" ", "").lower()

            qs = base_qs.annotate(
                clean_customer=Replace(
                    Replace("customer_name", Value(" "), Value("")),
                    Value("\t"),
                    Value("")
                ),
                clean_guarantor=Replace(
                    Replace("guarantor_name", Value(" "), Value("")),
                    Value("\t"),
                    Value("")
                )
            ).filter(
                Q(clean_customer__icontains=search_name) |
                Q(clean_guarantor__icontains=search_name)
            ).order_by("id")

        # ================= RELATED RECORDS =================
        else:
            mobile_set = set(
                x for x in primary.values_list("customer_mobile", flat=True)
                if x not in ["", None, "0"]
            ) | set(
                x for x in primary.values_list("guarantor_mobile", flat=True)
                if x not in ["", None, "0"]
            )

            vehicle_set = set(
                x for x in primary.values_list("vehicle_no", flat=True)
                if x not in ["", None]
            )

            qs = base_qs.filter(
                Q(customer_mobile__in=mobile_set) |
                Q(guarantor_mobile__in=mobile_set) |
                Q(vehicle_no__in=vehicle_set) |
                Q(id__in=primary.values("id"))
            ).distinct().order_by("id")

    # ================= PAGINATION =================
    paginator = Paginator(qs, 50)
    page = request.GET.get("page")
    page_obj = paginator.get_page(page)

    # ================= KEEP SEARCH =================
    params = request.GET.copy()
    params.pop("page", None)
    params["search"] = search_raw

    return render(request, "spl_case/write_off.html", {
        "data": page_obj,
        "search": search_raw,
        "query_string": params.urlencode(),
    })


@splcase_required
def ledger_list(request):
    search_raw = request.GET.get("search", "").strip()
    search_clean = normalize_excel_text(search_raw)

    base_qs = Ledger.objects.all()

    # ================= NO SEARCH =================
    if not search_raw:
        qs = base_qs.order_by("id")

    else:
        # ================= PRIMARY EXACT MATCH =================
        primary = base_qs.filter(
            Q(employee_id__iexact=search_clean) |
            Q(mobile_no__iexact=search_clean) |
            Q(reporting_manager__icontains=search_clean) |
            Q(company__iexact=search_clean) 
           
        )

        # ================= NAME SEARCH =================
        if not primary.exists():

            # remove spaces for matching
            search_name = search_raw.replace(" ", "").lower()

            qs = base_qs.annotate(
                clean_customer=Replace(
                    Replace("name", Value(" "), Value("")),
                    Value("\t"),
                    Value("")
                ),
                
            ).filter(
                Q(clean_customer__icontains=search_name) 
                
            ).order_by("id")

        # ================= RELATED RECORDS =================
        else:
            mobile_set = set(
                x for x in primary.values_list("mobile_no", flat=True)
                if x not in ["", None, "0"]
            ) 

            qs = base_qs.filter(
                Q(mobile_no__in=mobile_set) |
                
                Q(id__in=primary.values("id"))
            ).distinct().order_by("id")

    # ================= PAGINATION =================
    paginator = Paginator(qs, 50)
    page = request.GET.get("page")
    page_obj = paginator.get_page(page)

    # ================= KEEP SEARCH =================
    params = request.GET.copy()
    params.pop("page", None)
    params["search"] = search_raw

    return render(request, "spl_case/ledger.html", {
        "data": page_obj,
        "search": search_raw,
        "query_string": params.urlencode(),
    })

@splcase_required
def auction_list(request):
    search_raw = request.GET.get("search", "").strip()
    search_clean = normalize_excel_text(search_raw)

    base_qs = Auction.objects.all()

    # ================= NO SEARCH =================
    if not search_raw:
        qs = base_qs.order_by("id")

    else:
        # ================= PRIMARY EXACT MATCH =================
        primary = base_qs.filter(
            Q(loan_no__iexact=search_clean) |
            Q(veh_no__iexact=search_clean) |
            Q(cif_id__iexact=search_clean) |
            Q(customer_mobile__iexact=search_clean) |
            Q(guarantor_mobile__iexact=search_clean)
        )

        # ================= NAME SEARCH =================
        if not primary.exists():

            # remove spaces for matching
            search_name = search_raw.replace(" ", "").lower()

            qs = base_qs.annotate(
                clean_customer=Replace(
                    Replace("customer_name", Value(" "), Value("")),
                    Value("\t"),
                    Value("")
                ),
                clean_guarantor=Replace(
                    Replace("guarantor_name", Value(" "), Value("")),
                    Value("\t"),
                    Value("")
                )
            ).filter(
                Q(clean_customer__icontains=search_name) |
                Q(clean_guarantor__icontains=search_name)
            ).order_by("id")

        # ================= RELATED RECORDS =================
        else:
            mobile_set = set(
                x for x in primary.values_list("customer_mobile", flat=True)
                if x not in ["", None, "0"]
            ) | set(
                x for x in primary.values_list("guarantor_mobile", flat=True)
                if x not in ["", None, "0"]
            )

            vehicle_set = set(
                x for x in primary.values_list("veh_no", flat=True)
                if x not in ["", None]
            )

            qs = base_qs.filter(
                Q(customer_mobile__in=mobile_set) |
                Q(guarantor_mobile__in=mobile_set) |
                Q(veh_no__in=vehicle_set) |
                Q(id__in=primary.values("id"))
            ).distinct().order_by("id")

    # ================= PAGINATION =================
    paginator = Paginator(qs, 50)
    page = request.GET.get("page")
    page_obj = paginator.get_page(page)

    # ================= KEEP SEARCH =================
    params = request.GET.copy()
    params.pop("page", None)
    params["search"] = search_raw

    return render(request, "spl_case/auction.html", {
        "data": page_obj,
        "search": search_raw,
        "query_string": params.urlencode(),
    })


@splcase_required
def dealer_list(request):
    search_raw = request.GET.get("search", "").strip()
    search_clean = normalize_excel_text(search_raw)

    base_qs = Dealer_TA_Balances.objects.all()

    # ================= NO SEARCH =================
    if not search_raw:
        qs = base_qs.order_by("id")

    else:
        # ================= PRIMARY EXACT MATCH =================
        primary = base_qs.filter(
            Q(sales_manager__iexact=search_clean) |
            Q(dealer__iexact=search_clean) 
           
        )

        # ================= NAME SEARCH =================
        if not primary.exists():

            # remove spaces for matching
            search_name = search_raw.replace(" ", "").lower()

            qs = base_qs.annotate(
                clean_customer=Replace(
                    Replace("dealer", Value(" "), Value("")),
                    Value("\t"),
                    Value("")
                ),
                
            ).filter(
                Q(clean_customer__icontains=search_name) 
                
            ).order_by("id")

        # ================= RELATED RECORDS =================
        else:
            dealer_set = set(
                x for x in primary.values_list("dealer", flat=True)
                if x not in ["", None, "0"]
            ) 

            qs = base_qs.filter(
                Q(dealer__in=dealer_set) |
                
                Q(id__in=primary.values("id"))
            ).distinct().order_by("id")

    # ================= PAGINATION =================
    paginator = Paginator(qs, 50)
    page = request.GET.get("page")
    page_obj = paginator.get_page(page)

    # ================= KEEP SEARCH =================
    params = request.GET.copy()
    params.pop("page", None)
    params["search"] = search_raw

    return render(request, "spl_case/dealer.html", {
        "data": page_obj,
        "search": search_raw,
        "query_string": params.urlencode(),
    })


# ==============================Chatapp============================================

# ==============================Chatapp============================================

# ==============================Chatapp============================================

# messaging/views.py
import pandas as pd
import io
import json
import re
import uuid
import requests
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect, get_object_or_404
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Max, Count, Q
from django.conf import settings
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .utils import *

from .models import SmsWhatsAppLog3, BulkJob3
from .utils import format_mobile  # keep existing
from django.utils import timezone

from django.contrib.auth import authenticate, login, logout
from django.contrib import messages

import io
import json
import os
import uuid
import requests
import pandas as pd
import pytz
from django.shortcuts import render, redirect, get_object_or_404
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.http import JsonResponse, HttpResponseBadRequest, FileResponse, Http404, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.db.models import Max, Count, Q

from .forms import *
from .models import *
from .tasks import *
from .utils import *


from django.contrib.auth import authenticate
from django.contrib import messages



from django.core.paginator import Paginator
from django.http import JsonResponse

import re
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

def serialize_log(m):
    return {
        "id": m.id,
        "message_id": m.message_id,
        "mobile": m.mobile,
        "sent_text_message": m.sent_text_message,
        "message_type": m.message_type,
        "content_type": m.content_type,
        "media_file": m.media_file.url if m.media_file else "",
        "sent_at": m.sent_at.isoformat() if m.sent_at else "",
        "status": m.status,
    }



def broadcast_delivery(mobile, message_id, status):
    """
    Normalize WhatsApp delivery statuses and broadcast via WebSocket in real-time.
    """
    channel_layer = get_channel_layer()

    # normalize to WhatsApp-style tick words
    status = (status or "").lower()

    if status == "sent":
        norm = "Sent"
    elif status == "delivered":
        norm = "Delivered"
    elif status == "read":
        norm = "Read"
    else:
        norm = "Failed"

    gm = ws_group(mobile)
    if gm:
        async_to_sync(channel_layer.group_send)(
            f"chat3_{gm}",
            {
                "type": "delivery.update",
                "message_id": message_id,
                "status": norm,
                "mobile": mobile
            }
        )

    # notify all dashboard clients
    async_to_sync(channel_layer.group_send)(
        "delivery_group3",
        {
            "type": "delivery.update",
            "message_id": message_id,
            "status": norm,
            "mobile": mobile
        }
    )


# -------------------
# Helper: ws_group
# -------------------
def ws_group(mobile: str) -> str:
    """
    Sanitize mobile into digits-only group name.
    Example: "+91 63026-61004" -> "916302661004"
    """
    if not mobile:
        return ""
    return re.sub(r"\D", "", str(mobile))





# -----------------------------------------------------
# WhatsApp API - SEND TEXT
# -----------------------------------------------------
def send_whatsapp_text3(to_number, text_body):
    url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP3_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {settings.WHATSAPP3_ACCESS_TOKEN}",
               "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text_body},
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()



# -----------------------------------------------------
# Bulk Upload Start (S3-safe)
# -----------------------------------------------------
# -----------------------------------------------------
# Bulk Upload Start (S3-safe)
# -----------------------------------------------------
def upload_and_send3(request):
    if request.method == "POST":
        form = UploadForm3(request.POST, request.FILES)
        if form.is_valid():
            choice = form.cleaned_data["template_choice"]
            excel_file = request.FILES["excel_file"]

            # Save uploaded Excel to S3 under uploads/
            unique_name = f"{uuid.uuid4().hex}_{excel_file.name}"
            s3_key = f"uploads3/{unique_name}"
            default_storage.save(s3_key, excel_file)

            # Read Excel from S3 into pandas
            with default_storage.open(s3_key, "rb") as f:
                data = f.read()

            df = pd.read_excel(io.BytesIO(data), dtype=str).fillna("")
            job_id = str(uuid.uuid4())

            # Create Bulk Job
            BulkJob3.objects.create(
                job_id=job_id,
                template_name=choice,
                total_customers=len(df),
                excel_file=s3_key,
                status="Pending",
            )

            # 🔥 FORCE TASK INTO whatsapp_main QUEUE
            process_bulk_whatsapp3.apply_async(
                args=(s3_key, choice, job_id),
                queue="whatsapp_secondary"
            )

            return redirect("job_status3", job_id=job_id)

    else:
        form = UploadForm3()

    return render(request, "spl_case/upload.html", {"form": form})


# -----------------------------------------------------
# Bulk Job Status Page
# -----------------------------------------------------
def job_status3(request, job_id):
    job = get_object_or_404(BulkJob3, job_id=job_id)
    progress = 0
    if job.total_customers > 0:
        progress = round((job.sent_count / job.total_customers) * 100, 2)
    return render(request, "spl_case/job_status.html", {"job": job, "progress": progress})


# -----------------------------------------------------
# Download Success Report (redirect to S3)
# -----------------------------------------------------
def download_success_report3(request, job_id):
    job = get_object_or_404(BulkJob3, job_id=job_id)
    if job.success_report:
        return redirect(default_storage.url(job.success_report.name))
    raise Http404("Success report not found.")


# -----------------------------------------------------
# Download Failed Report (redirect to S3)
# -----------------------------------------------------
def download_failed_report3(request, job_id):
    job = get_object_or_404(BulkJob3, job_id=job_id)
    if job.failed_report:
          return redirect(default_storage.url(job.failed_report.name))

    raise Http404("Failed report not found.")


# -----------------------------------------------------
# CHAT DASHBOARD
# -----------------------------------------------------
# @splcase_required
def chat_dashboard3(request):
    mobiles = (
        SmsWhatsAppLog3.objects
        .values("mobile")
        .annotate(last_sent=Max("sent_at"))
        .order_by("-last_sent")
    )

    seen = set()
    mobile_list = []

    for m in mobiles:
        normalized = format_mobile(str(m["mobile"]))
        if normalized not in seen:
            seen.add(normalized)
            mobile_list.append({"mobile": normalized})

    return render(request, "spl_case/chat3.html", {
        "mobile_list": mobile_list,
        "user_name": request.user.username,
        "MEDIA_URL": settings.MEDIA_URL,
    })


# -----------------------------------------------------
# Get Messages for Mobile (returns public S3 URLs)
# -----------------------------------------------------
# in messaging/views.py (chat3_messages_api)
from django.core.paginator import Paginator


# -----------------------------------------------------
# Get Messages for Mobile (returns public S3 URLs)
# -----------------------------------------------------
def chat3_messages_api3(request, mobile):
    mobile = format_mobile(mobile)
    page = int(request.GET.get("page", 1))
    size = 500  # 500 messages per page

    qs = SmsWhatsAppLog3.objects.filter(mobile=mobile).order_by("-sent_at")

    paginator = Paginator(qs, size)

    try:
        pg = paginator.page(page)
    except:
        return JsonResponse({"messages": [], "has_more": False})

    # Messages oldest → newest
    result = list(pg.object_list)[::-1]

    def to_json(m):
        media_url = ""
        if m.media_file:
            try:
                media_url = default_storage.url(m.media_file.name)
            except:
                media_url = getattr(m.media_file, "url", "")

        return {
            "id": m.id,
            "mobile": m.mobile,
            "sent_text_message": m.sent_text_message or "",
            "message_type": m.message_type,
            "sent_at": m.sent_at.isoformat() if m.sent_at else "",
            "message_id": m.message_id,
            "content_type": m.content_type or "text",
            "media_file": media_url,
            "status": m.status or "",
            "sender_name": m.customer_name or "",      # ★ added sender_name
        }

    return JsonResponse({
        "messages": [to_json(m) for m in result],
        "has_more": pg.has_next()
    })


# -----------------------------------------------------
# SEND REPLY API
# -----------------------------------------------------
# -----------------------------------------------------
# SEND REPLY API (FINAL + PATCHED WITH sender_name)
# -----------------------------------------------------

# -----------------------------------------------------
# SEND REPLY API
# -----------------------------------------------------
@csrf_exempt
def send_reply_api3(request):
    try:
        if request.method != "POST":
            return HttpResponseBadRequest("POST required")

        # Detect form-data OR JSON
        content_type_header = request.META.get("CONTENT_TYPE", "") or request.content_type or ""
        if content_type_header.startswith("multipart/form-data"):
            mobile = request.POST.get("mobile", "").strip()
            text = request.POST.get("text", "").strip()
            media_file = request.FILES.get("media")
        else:
            payload = json.loads(request.body.decode("utf-8") or "{}")
            mobile = payload.get("mobile", "").strip()
            text = payload.get("text", "").strip()
            media_file = None

        if not mobile:
            return HttpResponseBadRequest("mobile required")

        # Normalize
        mobile = format_mobile(mobile)

        # -------- GET LOGGED-IN USER NAME (sender_name) --------
        agent_name = None
        if request.session.get("spl_user"):
            from django.contrib.auth.models import User
            u = User.objects.filter(id=request.session["spl_user"]).first()
            if u:
                agent_name = u.username

        # -------- SEND TO WHATSAPP3 API --------
        if media_file:
            upload_resp = upload_whatsapp_media3(media_file)
            media_id = upload_resp.get("id")
            mime_main = (media_file.content_type.split("/")[0] if media_file.content_type else "").lower()
            mapped_type = mime_main if mime_main in ("image", "video", "audio") else "document"

            send_resp = send_whatsapp_media3(
                to_number=mobile,
                media_id=media_id,
                media_type=mapped_type,
                caption=text,
            )
            content_type = mapped_type
        else:
            send_resp = send_whatsapp_text3(mobile, text)
            content_type = "text"

        msg_id = ""
        if isinstance(send_resp, dict) and "messages" in send_resp:
            msg_id = send_resp["messages"][0].get("id", "")

        # -------- SAVE DB --------
        log = SmsWhatsAppLog3.objects.create(
            customer_name=agent_name,        # ★ store username as sender_name
            mobile=mobile,
            sent_text_message=text or "",
            status="Sent",
            message_id=msg_id,
            message_type="Sent",
            content_type=content_type,
        )

        if media_file:
            log.media_file.save(media_file.name, media_file)
            log.save()

        # -------- WEBSOCKET BROADCAST --------
        channel_layer = get_channel_layer()
        gm = ws_group(mobile)

        if gm:
            async_to_sync(channel_layer.group_send)(
                f"chat3_{gm}",
                {
                    "type": "new_message",
                    "message": {
                        "id": log.id,
                        "mobile": mobile,
                        "sent_text_message": log.sent_text_message,
                        "content_type": log.content_type,
                        "media_file": log.media_file.url if log.media_file else "",
                        "sent_at": log.sent_at.isoformat(),
                        "message_type": "Sent",
                        "message_id": log.message_id,
                        "status": log.status,
                        "sender_name": agent_name or "",     # ★ include sender_name
                    }
                }
            )

        # Update ticks
        broadcast_delivery(mobile, msg_id, "Sent")

        async_to_sync(channel_layer.group_send)(
            "contacts_group3",
            {"type": "presence.update", "mobile": mobile, "status": "updated"}
        )

        # -------- API RESPONSE (also include sender_name) --------
        return JsonResponse({
            "status": "ok",
            "message_id": msg_id,
            "sender_name": agent_name or ""     # ★ return sender_name to client
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)





# -----------------------------------------------------
# WHATSAPP3 WEBHOOK
# -----------------------------------------------------
import json
import requests

from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.db import transaction, close_old_connections
from django.core.files.base import ContentFile

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer



# ----------------------------------------
# MEDIA DOWNLOAD
# ----------------------------------------
def download_whatsapp_media3(media_id):
    try:
        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP3_ACCESS_TOKEN}"
        }

        meta_url = f"https://graph.facebook.com/v17.0/{media_id}"
        meta_res = requests.get(meta_url, headers=headers, timeout=10)
        meta_res.raise_for_status()

        meta = meta_res.json()
        file_url = meta.get("url")
        mime = meta.get("mime_type", "")

        if not file_url:
            print("❌ No media URL")
            return None

        ext = mime.split(";")[0].split("/")[-1]

        file_res = requests.get(file_url, headers=headers, timeout=20)
        file_res.raise_for_status()

        filename = f"wa_{media_id}.{ext}"

        return filename, file_res.content

    except Exception as e:
        print("❌ DOWNLOAD ERROR:", e)
        return None


# ----------------------------------------
# WEBHOOK
# ----------------------------------------
@csrf_exempt
def whatsapp_webhook3(request):
    close_old_connections()
    channel_layer = get_channel_layer()

    # ---------- VERIFY ----------
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        if mode == "subscribe" and token == settings.WHATSAPP3_VERIFY_TOKEN:
            return HttpResponse(challenge, status=200)

        return HttpResponseBadRequest("Invalid verification.")

    # ---------- POST ----------
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
            print("🔥 WEBHOOK:", data)

            entries = data.get("entry", [])

            for entry in entries:
                for change in entry.get("changes", []):
                    value = change.get("value", {})

                    # =============================
                    # 1️⃣ MESSAGES
                    # =============================
                    messages = value.get("messages", []) or []
                    contacts = value.get("contacts", []) or []

                    for msg in messages:
                        try:
                            msg_id = msg.get("id")
                            mobile = format_mobile(msg.get("from", ""))

                            # ---- Deduplicate ----
                            if msg_id and SmsWhatsAppLog3.objects.filter(message_id=msg_id).exists():
                                continue

                            msg_type = msg.get("type", "text")

                            text_body = ""
                            content_type = "text"
                            media_id = None

                            # TYPE HANDLING
                            if msg_type == "text":
                                text_body = msg.get("text", {}).get("body", "")

                            elif msg_type in ("image", "video", "audio", "document"):
                                media_obj = msg.get(msg_type, {})
                                media_id = media_obj.get("id")
                                content_type = msg_type
                                text_body = f"[{msg_type}]"

                            elif msg_type == "interactive":
                                content_type = "interactive"
                                interactive = msg.get("interactive", {})
                                text_body = interactive.get("button", {}).get("text", "")

                            # ---- SAVE DB ----
                            with transaction.atomic():
                                log = SmsWhatsAppLog3.objects.create(
                                    customer_name=(contacts[0].get("profile", {}).get("name") if contacts else ""),
                                    mobile=mobile,
                                    template_name="incoming",
                                    sent_text_message=text_body,
                                    status="Unread",
                                    message_type="Received",
                                    message_id=msg_id,
                                    content_type=content_type,
                                    media_id=media_id
                                )

                            print("✅ SAVED:", log.id)

                            # ---- MEDIA SAVE ----
                            if media_id:
                                media = download_whatsapp_media3(media_id)
                                if media:
                                    filename, content = media
                                    log.media_file.save(filename, ContentFile(content))
                                    log.save()
                                    print("✅ MEDIA SAVED:", log.id)

                            # ---- REALTIME CHAT ----
                            gm = ws_group(mobile)
                            if gm:
                                async_to_sync(channel_layer.group_send)(
                                    f"chat3_{gm}",
                                    {
                                        "type": "new_message",
                                        "message": {
                                            "id": log.id,
                                            "mobile": mobile,
                                            "sent_text_message": text_body,
                                            "content_type": content_type,
                                            "media_file": log.media_file.url if log.media_file else "",
                                            "sent_at": log.sent_at.isoformat(),
                                            "message_type": "Received",
                                            "message_id": msg_id,
                                            "status": "Unread",
                                        }
                                    }
                                )

                            # ---- PRESENCE UPDATE ----
                            async_to_sync(channel_layer.group_send)(
                                "presence_group3",
                                {"type": "presence.update", "mobile": mobile, "status": "online"}
                            )

                            # ---- CONTACTS UPDATE ----
                            async_to_sync(channel_layer.group_send)(
                                "contacts_group3",
                                {"type": "presence.update", "mobile": mobile, "status": "updated"}
                            )

                        except Exception as inner_err:
                            print("❌ Message error:", inner_err)

                    # =============================
                    # 2️⃣ STATUS (TICKS)
                    # =============================
                    statuses = value.get("statuses", []) or []

                    for st in statuses:
                        try:
                            mid = st.get("id")
                            raw_status = (st.get("status") or "").lower()

                            norm = {
                                "sent": "Sent",
                                "delivered": "Delivered",
                                "read": "Read"
                            }.get(raw_status, "Failed")

                            mobile = format_mobile(st.get("recipient_id", ""))

                            print("📩 STATUS:", mid, norm)

                            # DB update
                            if mid:
                                SmsWhatsAppLog3.objects.filter(message_id=mid).update(status=norm)

                            # UI tick update
                            async_to_sync(channel_layer.group_send)(
                                "delivery_group3",
                                {
                                    "type": "delivery.update",
                                    "message_id": mid,
                                    "status": norm,
                                    "mobile": mobile
                                }
                            )

                        except Exception as e:
                            print("❌ STATUS ERROR:", e)

            return JsonResponse({"status": "ok"})

        except Exception as e:
            print("🔥 WEBHOOK ERROR:", e)
            return JsonResponse({"error": str(e)}, status=400)

    return HttpResponseBadRequest("Invalid method")

# @csrf_exempt
# def refresh_media(request):
#     media_id = request.GET.get("media_id")

#     try:
#         url = f"https://graph.facebook.com/v17.0/{media_id}"
#         headers = {
#             "Authorization": f"Bearer {settings.WHATSAPP3_ACCESS_TOKEN}"
#         }

#         res = requests.get(url, headers=headers)
#         res.raise_for_status()

#         return JsonResponse({"url": res.json().get("url")})

#     except Exception as e:
#         return JsonResponse({"error": str(e)}, status=400)

# from django.http import StreamingHttpResponse
# import requests

# def stream_media(request):
#     media_id = request.GET.get("media_id")
#     print(media_id,"lllllllllllllllll")

#     if not media_id or media_id == "undefined":
#         return JsonResponse({"error": "Invalid media_id"}, status=400)

#     try:
#         headers = {
#             "Authorization": f"Bearer {settings.WHATSAPP3_ACCESS_TOKEN}"
#         }

#         # Step 1: get actual media URL
#         meta_url = f"https://graph.facebook.com/v17.0/{media_id}"
#         meta_res = requests.get(meta_url, headers=headers)
#         meta_res.raise_for_status()

#         media_url = meta_res.json().get("url")

#         # Step 2: stream file
#         file_res = requests.get(media_url, headers=headers, stream=True)

#         return StreamingHttpResponse(
#     file_res.iter_content(chunk_size=8192),
#     content_type=file_res.headers.get("Content-Type"),
#     headers={"Cache-Control": "public, max-age=3600"}
# )
#     except Exception as e:
#         return JsonResponse({"error": str(e)}, status=500)

# -----------------------------------------------------
# Download media from WA (helper)
# -----------------------------------------------------
import requests
from django.conf import settings

def download_whatsapp_media3(media_id):
    try:
        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP3_ACCESS_TOKEN}"
        }

        # STEP 1: get media URL
        meta_url = f"https://graph.facebook.com/v17.0/{media_id}"
        meta_res = requests.get(meta_url, headers=headers)
        meta_res.raise_for_status()

        meta = meta_res.json()
        file_url = meta.get("url")
        mime = meta.get("mime_type", "")

        # extension fix
        ext = mime.split(";")[0].split("/")[-1]

        # STEP 2: download file
        file_res = requests.get(file_url, headers=headers)
        file_res.raise_for_status()

        filename = f"wa_{media_id}.{ext}"

        return filename, file_res.content

    except Exception as e:
        print("❌ DOWNLOAD ERROR:", e)
        return None




# -----------------------------------------------------
# Contacts API (for sidebar)
# -----------------------------------------------------
def contacts_api3(request):
    q = request.GET.get("q", "").strip()
    # Build base queryset: group by mobile, last_time, unread count
    qs = (
        SmsWhatsAppLog3.objects.values("mobile")
        .annotate(last_time=Max("sent_at"),
                  unread=Count("id", filter=Q(message_type="Received", status="Unread")))
        .order_by("-last_time")
    )

    # If search present, do fast DB-level filtering on mobile OR message text
    if q:
        # normalize q digits for phone search; also keep text search
        digits = re.sub(r"\D", "", q)
        if digits:
            # search mobile-like (digits may be partial)
            qs = qs.filter(mobile__icontains=digits)
        else:
            # search by message text across logs (returns mobiles that match)
            mobiles_matching = SmsWhatsAppLog3.objects.filter(sent_text_message__icontains=q).values_list("mobile", flat=True).distinct()
            qs = qs.filter(mobile__in=list(mobiles_matching))

    result = [{
        "mobile": format_mobile(item["mobile"]),
        "last_time": item["last_time"].isoformat() if item["last_time"] else "",
        "unread": item["unread"],
    } for item in qs]
    return JsonResponse({"contacts": result})

# -----------------------------------------------------
# Mark messages read
# -----------------------------------------------------

@csrf_exempt
def mark_read3(request, mobile):
    try:
        mobile_norm = format_mobile(mobile)
        SmsWhatsAppLog3.objects.filter(mobile=mobile_norm, message_type="Received", status="Unread").update(status="Read")

        channel_layer = get_channel_layer()
        gm = ws_group(mobile_norm)
        if gm:
            # conversation level read
            async_to_sync(channel_layer.group_send)(
                f"chat3_{gm}",
                {
                    "type": "delivery.update",
                    "message_id": "",    # empty => conversation-level read
                    "status": "Read",
                    "mobile": mobile_norm,
                }
            )

        # notify contacts to refresh unread count
        async_to_sync(channel_layer.group_send)(
            "contacts_group3",
            {"type": "presence.update", "mobile": mobile_norm, "status": "updated"}
        )

        return JsonResponse({"status": "ok"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


