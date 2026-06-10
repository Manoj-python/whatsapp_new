import pandas as pd
import io
import json
import re
import uuid
import requests
import time
import traceback
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect, get_object_or_404
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Max, Count, Q, F
from django.conf import settings
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from .models import *
from .utils import *
from .tasks import *
from .forms import UploadForm3
from django.contrib.auth import authenticate
from django.contrib import messages
from django.core.paginator import Paginator
from .consumers import *

import pytz
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

def messaging3_login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(username=username, password=password)
        if user:
            # Custom session KEY
            request.session["messaging3_user"] = user.id
            return redirect("upload_and_send3")
        else:
            messages.error(request, "Invalid username or password")

    return render(request, "spl_case/login.html")

def messaging3_logout(request):
    request.session.pop("messaging3_user", None)
    return redirect("splcase_login")


def splcase_required(view_func):
    def wrapper(request, *args, **kwargs):
        # First check Django auth
        if request.user.is_authenticated:
            return view_func(request, *args, **kwargs)
        # Then check custom session key (legacy)
        if request.session.get("messaging3_user"):
            return view_func(request, *args, **kwargs)
        return redirect(settings.LOGIN_URL)
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
@splcase_required
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

def ws_group3(mobile: str) -> str:
    if not mobile:
        return ""
    return re.sub(r"\D", "", str(mobile))


def send_whatsapp_text3(to_number, text_body):
    """Send text message via WhatsApp API"""
    url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP3_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP3_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text_body[:4096]},
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()



def broadcast_delivery3(mobile, message_id, status):
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    from django.utils import timezone


    channel_layer = get_channel_layer()

    status = (status or "").lower()

    if status == "sent":
        norm = "Sent"
    elif status == "delivered":
        norm = "Delivered"
    elif status == "read":
        norm = "Read"
    else:
        norm = "Failed"

    # 🔥 UPDATE CONTACT TABLE (VERY IMPORTANT)
    ChatContact3.objects.filter(mobile=mobile).update(
        last_status=norm,

    )

    gm = ws_group3(mobile)

    # ===== CHAT TICKS =====
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

    # ===== GLOBAL TICKS (ALL USERS) =====
    async_to_sync(channel_layer.group_send)(
        "delivery_group3",
        {
            "type": "delivery.update",
            "message_id": message_id,
            "status": norm,
            "mobile": mobile
        }
    )

    # ===== 🔥 CONTACT UPDATE =====
    async_to_sync(channel_layer.group_send)(
        "global_contacts3",
        {
            "type": "contact.update",
            "contact": {
                "mobile": mobile,
                "last_status": norm,
                #"last_time": timezone.now().isoformat()
            }
        }
    )


# -----------------------------------------------------
# Bulk Upload Start (S3-safe)
# -----------------------------------------------------
@splcase_required
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

            # 🔥 FORCE TASK INTO WHATSAPP2_main QUEUE
            process_bulk_whatsapp3.apply_async(
                args=(s3_key, choice, job_id),
                queue="special_cases"
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
from adminpanel.views import get_agent_from_user
def chat_dashboard3(request):
    agent = get_agent_from_user(request.user)
    mobiles = (SmsWhatsAppLog3.objects.values("mobile").annotate(last_sent=Max("sent_at")).order_by("-last_sent"))
    seen = set()
    mobile_list = []
    for m in mobiles:
        normalized = format_mobile3(str(m["mobile"]))
        if normalized not in seen:
            seen.add(normalized)
            mobile_list.append({"mobile": normalized})
    return render(request, "spl_case/chat3.html", {
        "mobile_list": mobile_list,
        "user_name": request.user.username,
        "MEDIA_URL": settings.MEDIA_URL,
        "agent": agent,
        "user": request.user,
    })


# -----------------------------------------------------
# Get Messages for Mobile (returns public S3 URLs)
# -----------------------------------------------------
# in messaging2views.py (chat2_messages_api)
from django.core.paginator import Paginator


# -----------------------------------------------------
# Get Messages for Mobile (returns public S3 URLs)
# -----------------------------------------------------
def chat_messages_api3(request, mobile):
    mobile = format_mobile3(mobile)
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
            "sent_at": timezone.localtime(m.sent_at).isoformat(),
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




from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect, get_object_or_404
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Max, Count, Q, F
from django.conf import settings
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from django.contrib.auth import authenticate
from django.contrib import messages
from django.core.paginator import Paginator





def contacts_api3(request):
    q = request.GET.get("q", "").strip()
    qs = (
        SmsWhatsAppLog3.objects.values("mobile")
        .annotate(last_time=Max("sent_at"),
                  unread=Count("id", filter=Q(message_type="Received", status="Unread")))
        .order_by("-last_time")
    )

    if q:
        digits = re.sub(r"\D", "", q)
        if digits:
            qs = qs.filter(mobile__icontains=digits)
        else:
            mobiles_matching = SmsWhatsAppLog3.objects.filter(sent_text_message__icontains=q).values_list("mobile", flat=True).distinct()
            qs = qs.filter(mobile__in=list(mobiles_matching))

    result = [{
        "mobile": format_mobile3(item["mobile"]),
        "last_time": item["last_time"].isoformat() if item["last_time"] else "",
        "unread": item["unread"],
    } for item in qs]
    return JsonResponse({"contacts": result})


@csrf_exempt
def mark_read3(request, mobile):
    try:
        mobile_norm = format_mobile3(mobile)
        ChatContact3.objects.filter(mobile=mobile_norm).update(unread=0)
        channel_layer = get_channel_layer()
        gm = ws_group3(mobile_norm)
        if gm:
            async_to_sync(channel_layer.group_send)(
                f"chat3_{gm}",
                {
                    "type": "delivery.update",
                    "message_id": "",
                    "status": "Read",
                    "mobile": mobile_norm,
                }
            )
        async_to_sync(channel_layer.group_send)(
            "global_contacts3",
            {"type": "presence.update", "mobile": mobile_norm, "status": "updated"}
        )
        return JsonResponse({"status": "ok"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# =============================================
# SEND REPLY API - FIXED (NO RACE CONDITION)
# =============================================
# messaging2views.py - COMPLETE WORKING VERSION

@csrf_exempt
def send_reply_api3(request):
    """
    Send reply with media support - SAVE FIRST to prevent NO DB MATCH
    """
    try:
        if request.method != "POST":
            return HttpResponseBadRequest("POST required")

        # Parse request
        if "multipart/form-data" in request.META.get("CONTENT_TYPE", ""):
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

        mobile = format_mobile3(mobile)

        # File size validation
        if media_file:
            file_size_mb = media_file.size / (1024 * 1024)
            file_name = media_file.name.lower()

            if file_name.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                max_size = 5
            elif file_name.endswith(('.mp4', '.mov', '.avi', '.mkv', '.3gp')):
                max_size = 16
            else:
                max_size = 100

            if file_size_mb > max_size:
                return JsonResponse({
                    "error": f"File too large. Max {max_size}MB. Yours: {file_size_mb:.2f}MB"
                }, status=400)

        # Get agent name
        agent_name = None
        if request.session.get("messaging3_user"):
            from django.contrib.auth.models import User
            u = User.objects.filter(id=request.session["messaging3_user"]).first()
            if u:
                agent_name = u.username

        # =============================================
        # STEP 1: CREATE DATABASE RECORD FIRST (with temp ID)
        # =============================================
        temp_id = str(uuid.uuid4())

        log = SmsWhatsAppLog3.objects.create(
            customer_name=agent_name or "",
            mobile=mobile,
            sent_text_message=text or "",
            status="Sending",  # Status while sending
            message_id=temp_id,
            message_type="Sent",
            content_type="text",  # Will update later
        )
        clear_chat_cache3(mobile)


        # print(f"📝 [STEP 1] Saved pending message with temp ID: {temp_id}")

        # =============================================
        # STEP 2: SEND TO WHATSAPP
        # =============================================
        msg_id = ""
        content_type_val = "text"
        media_url = ""
        saved_path = None

        try:
            if media_file:
                # Determine media type
                file_name = media_file.name.lower()
                original_filename = media_file.name
                if file_name.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                    WHATSAPP2_media_type = "image"
                    content_type_val = "image"
                elif file_name.endswith(('.mp4', '.mov', '.avi', '.mkv')):
                    WHATSAPP2_media_type = "video"
                    content_type_val = "video"
                elif file_name.endswith(('.mp3', '.wav', '.ogg', '.m4a')):
                    WHATSAPP2_media_type = "audio"
                    content_type_val = "audio"
                else:
                    WHATSAPP2_media_type = "document"
                    content_type_val = "document"

                # Update content type in database
                SmsWhatsAppLog3.objects.filter(id=log.id).update(content_type=content_type_val)

                # print(f"📤 Uploading {WHATSAPP2_media_type}...")

                # Upload to WhatsApp
                upload_resp = upload_whatsapp_media3(media_file)
                media_id = upload_resp.get("id")

                if media_id:
                    send_resp = send_whatsapp_media3(
                        to_number=mobile,
                        media_id=media_id,
                        media_type=WHATSAPP2_media_type,
                        caption=text if text else "",
                        filename=original_filename
                    )
                    msg_id = send_resp.get("messages", [{}])[0].get("id", "")

                    # Save media file to storage
                    media_file.seek(0)
                    saved_path = default_storage.save(
                        f"chat3_media/{media_file.name}",
                        ContentFile(media_file.read())
                    )
                    media_url = default_storage.url(saved_path)

            elif text:
                send_resp = send_whatsapp_text3(mobile, text)
                msg_id = send_resp.get("messages", [{}])[0].get("id", "")

            # print(f"📨 [STEP 2] WhatsApp returned ID: {msg_id}")

            # =============================================
            # STEP 3: UPDATE RECORD WITH REAL WHATSAPP ID
            # =============================================
            if msg_id:
                # Update the existing record
                update_data = {
                    'message_id': msg_id,
                    'status': 'Sent'
                }
                if saved_path:
                    update_data['media_file'] = saved_path

                SmsWhatsAppLog3.objects.filter(id=log.id).update(**update_data)
                log.refresh_from_db()
                # print(f"✅ [STEP 3] Updated message from {temp_id} to {msg_id}")
            else:
                SmsWhatsAppLog3.objects.filter(id=log.id).update(
                    status="Failed",
                    error_message="No message ID returned from WhatsApp"
                )
                # print(f"❌ No WhatsApp ID returned")

        except Exception as e:
            SmsWhatsAppLog3.objects.filter(id=log.id).update(
                status="Failed",
                error_message=str(e)
            )
            # print(f"❌ Send failed: {e}")
            return JsonResponse({"error": f"Send failed: {str(e)}"}, status=500)

        # Update contact
        ChatContact3.objects.update_or_create(
            mobile=mobile,
            defaults={
                "last_msg": text or f"[{content_type_val.title()}]",
                "last_time": timezone.now(),
                "last_type": "Sent",
                "last_status": "Sent" if msg_id else "Failed",
                "unread": 0
            }
        )

        # WebSocket broadcast
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "global_contacts3",
            {
                "type": "contact.update",
                "contact": {
                    "mobile": mobile,
                    "last_msg": text or f"[{content_type_val.title()}]",
                    "last_time": timezone.now().isoformat(),
                    "last_type": "Sent",
                    "last_status": "Sent" if msg_id else "Failed",
                    "unread": 0
                }
            }
        )
        gm = re.sub(r"\D", "", mobile)

        if gm:
            async_to_sync(channel_layer.group_send)(
                f"chat3_{gm}",
                {
                    "type": "new_message",
                    "message": {
                        "id": log.id,
                        "mobile": mobile,
                        "sent_text_message": log.sent_text_message,
                        "content_type": content_type_val,
                        "media_file": media_url,
                        "sent_at": log.sent_at.isoformat(),
                        "message_type": "Sent",
                        "message_id": log.message_id,  # Now has real ID!
                        "status": log.status,
                        "sender_name": agent_name or "",
                    }
                }
            )

        return JsonResponse({
            "status": "ok",
            "message_id": msg_id,
            "sender_name": agent_name or "",
            "content_type": content_type_val,
            "media_url": media_url
        })

    except Exception as e:
        # print(f"Send reply error: {e}")
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


# =============================================
# WHATSAPP WEBHOOK - COMPLETE FIXED VERSION
# =============================================
@csrf_exempt
def whatsapp_webhook3(request):
    # print("🔥 WEBHOOK HIT")

    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    from django.db import transaction
    import json

    channel_layer = get_channel_layer()

    # ---------- VERIFY TOKEN (GET) ----------
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        if mode == "subscribe" and token == settings.WHATSAPP3_VERIFY_TOKEN:
            return HttpResponse(challenge, status=200)
        return HttpResponseBadRequest("Invalid verification.")

    # ---------- INCOMING WEBHOOK (POST) ----------
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
            entries = data.get("entry", [])

            for entry in entries:
                for change in entry.get("changes", []):
                    value = change.get("value", {})

                    # ======================================
                    # PROCESS INCOMING MESSAGES
                    # ======================================
                    for msg in value.get("messages", []):
                        msg_id = msg.get("id")
                        mobile = format_mobile3(msg.get("from", ""))

                        if msg_id and SmsWhatsAppLog3.objects.filter(message_id=msg_id).exists():
                            # print(f"⏭️ Duplicate message: {msg_id}")
                            continue

                        msg_type = msg.get("type", "text")
                        text_body = ""
                        content_type = "text"
                        media_file_data = None

                        if msg_type == "text":
                            text_body = msg["text"].get("body", "")
                            # print(f"📝 Text from {mobile}: {text_body[:50]}")

                        elif msg_type == "interactive":
                            interactive = msg.get("interactive", {})
                            content_type = "interactive"
                            if interactive.get("type") == "button":
                                text_body = interactive["button"].get("text", "")
                            elif interactive.get("type") == "list_reply":
                                text_body = interactive["list_reply"].get("title", "")

                        elif msg_type in ("image", "video", "audio", "document"):
                            media_id = msg[msg_type].get("id")
                            content_type = msg_type
                            text_body = f"[{msg_type.title()}]"
                            # print(f"📎 {msg_type} from {mobile}, media_id: {media_id}")
                            media_file_data = download_whatsapp_media3(media_id)
                            if media_file_data:
                                pass
                                # print(f"✅ Downloaded {msg_type}")
                            else:
                                pass
                                # print(f"❌ Failed to download {msg_type}")

                        elif msg_type == "unsupported":
                            error = msg.get("errors", [{}])[0].get("message", "Unknown")
                            # print(f"⚠️ Unsupported: {error}")
                            continue
                        customer_name = ""
                        contacts_data = value.get("contacts", [])
                        if contacts_data:
                            customer_name = contacts_data[0].get("profile", {}).get("name", "")
                            print(f"📛 Customer name: {customer_name}")

                        # Save message
                        with transaction.atomic():
                            log = SmsWhatsAppLog3.objects.create(
                                customer_name="",
                                mobile=mobile,
                                template_name="incoming",
                                sent_text_message=text_body,
                                status="Unread",
                                message_type="Received",
                                message_id=msg_id,
                                content_type=content_type,
                            )
                            clear_chat_cache3(mobile)


                            if media_file_data:
                                filename, content = media_file_data
                                log.media_file.save(filename, ContentFile(content))
                                log.save()
                                # print(f"💾 Saved media: {filename}")

                        # Update contact
                        obj, created = ChatContact3.objects.get_or_create(
                            mobile=mobile,
                            defaults={
                                "last_time": timezone.now(),
                                "last_msg": text_body or "",
                                "last_type": "Received",
                                "last_status": "Unread",
                                "unread": 1,
                            }
                        )
                        if not created:
                            ChatContact3.objects.filter(mobile=mobile).update(
                                last_time=timezone.now(),
                                last_msg=text_body or "",
                                last_type="Received",
                                last_status="Unread",
                                unread=F("unread") + 1
                            )

                        # WebSocket broadcast
                        gm = ws_group3(mobile)
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
                                        "sent_at": timezone.localtime(log.sent_at).isoformat(),
                                        "message_type": "Received",
                                        "message_id": log.message_id,
                                        "status": log.status,
                                        "sender_name": customer_name
                                    }
                                }
                            )

                        async_to_sync(channel_layer.group_send)(
                            "global_contacts3",
                            {
                                "type": "contact.update",
                                "contact": {
                                    "mobile": mobile,
                                    "last_msg": text_body or "",
                                    "last_type": "Received",
                                    "last_status": "Unread",
                                    "unread": obj.unread if created else obj.unread + 1,
                                    #"last_time": timezone.now().isoformat(),
                                }
                            }
                        )

                        # print(f"✅ Saved incoming {msg_type} from {mobile}")

                    # ======================================
                    # PROCESS STATUS UPDATES
                    # ======================================
                    for status in value.get("statuses", []):
                        msg_id = status.get("id")
                        status_type = (status.get("status") or "").lower()

                        if not msg_id:
                            continue

                        # print(f"📨 Status update: {msg_id} -> {status_type}")

                        # Message should already exist with real ID
                        obj = SmsWhatsAppLog3.objects.filter(message_id=msg_id).first()
                        # If not found, try to find by partial match (temp ID might still be there)
                        if not obj and len(msg_id) > 30:
                            # Try to find by the real ID pattern in any message
                            partial = msg_id[:30]
                            obj = SmsWhatsAppLog3.objects.filter(message_id__startswith=partial).first()
                            if obj:
                                # print(f"✅ Found by partial match, updating full ID")
                                SmsWhatsAppLog3.objects.filter(id=obj.id).update(message_id=msg_id)
                                obj.refresh_from_db()
                        # Also try to find by looking for messages with status "Sending"
                        if not obj:
                            # print(f"❌ Message not found: {msg_id}")
                            continue



                        mobile = obj.mobile
                        errors = status.get("errors",[])
                        if status_type == "sent":
                            norm = "Sent"
                        elif status_type == "delivered":
                            norm = "Delivered"
                        elif status_type == "read":
                            norm = "Read"
                        elif status_type == "failed":
                            norm = "Failed"
                            if errors:
                                err = errors[0]
                                code = int(err.get("code",0))
                                # handel reengagement
                                if code == 131047:
                                    norm = "Re-engagement Required"
                                elif code in [131026, 131051, 131011]:
                                    norm = "Blocked"
                                elif code in [131009, 131045]:
                                    norm = "Invalid"
                                elif code in [132000, 132001, 131008]:
                                    norm = "Template Failed"
                                elif code in [130429, 80007]:
                                    norm = "Rate Limited"
                                elif code in [10, 190, 200]:
                                    norm = "Auth Failed"
                                else:
                                    norm = f"Failed ({code})"

                        else:
                            continue

                        # Update database
                        SmsWhatsAppLog3.objects.filter(message_id=msg_id).update(status=norm,error_message=json.dumps(errors) if errors else "")
                        ChatContact3.objects.filter(mobile=mobile).update(last_status=norm)

                        # WebSocket update
                        gm = ws_group3(mobile)
                        if gm:
                            async_to_sync(channel_layer.group_send)(
                                f"chat3_{gm}",
                                {
                                    "type": "delivery.update",
                                    "message_id": msg_id,
                                    "status": norm,
                                    "mobile": mobile
                                }
                            )

                        async_to_sync(channel_layer.group_send)(
                                "global_contacts3",
                            {
                                "type":"contact.update",
                                "contact":{
                                    "mobile":mobile,
                                    "last_status":norm
                                }
                            }
                        )
                        print(f"✅ Updated {msg_id} to {norm}")
                        total_unread = ChatContact3.objects.filter(unread__gt=0).count()
                        async_to_sync(channel_layer.group_send)(
                            "global_contacts3",
                            {

                                "type": "unread.update",
                                "unread_count": total_unread

                            }
                        )

                        # print(f"✅ Updated {msg_id} to {norm}")

            return JsonResponse({"status": "received"})

        except Exception as e:
            # print(f"WEBHOOK ERROR: {e}")
            traceback.print_exc()
            return JsonResponse({"error": str(e)}, status=400)

    return HttpResponseBadRequest("Unsupported method")

# -----------------------------------------------------
# Download media from WA (helper)
# -----------------------------------------------------
def download_whatsapp_media3(media_id):
    """Download media from WhatsApp"""
    try:
        access_token = settings.WHATSAPP3_ACCESS_TOKEN
        headers = {"Authorization": f"Bearer {access_token}"}

        # Use v22.0
        meta_url = f"https://graph.facebook.com/v22.0/{media_id}"
        meta_resp = requests.get(meta_url, headers=headers, timeout=30)
        meta_resp.raise_for_status()
        meta = meta_resp.json()

        file_url = meta.get("url")
        mime = meta.get("mime_type", "")
        ext = mime.split("/")[-1] if "/" in mime else "bin"

        file_resp = requests.get(file_url, headers=headers, timeout=30)
        file_resp.raise_for_status()

        filename = f"WHATSAPP2_{media_id}.{ext}"
        return filename, file_resp.content

    except Exception as e:
        # print(f"Media download error: {e}")
        return None




# -----------------------------------------------------
# Contacts API (for sidebar)
# -----------------------------------------------------




from django.http import JsonResponse
from .models import SmsWhatsAppLog3

def get_contact_messages3(request):
    mobile = request.GET.get('mobile')
    if not mobile:
        return JsonResponse({'error': 'Mobile required'}, status=400)

    messages = SmsWhatsAppLog3.objects.filter(mobile=mobile).order_by('sent_at')

    data = {
        'messages': [{
            'id': m.id,
            'sent_text_message': m.sent_text_message,
            'message_type': m.message_type,
            'sent_at': m.sent_at.isoformat(),
            'content_type': m.content_type,
            'media_file': m.media_file.url if m.media_file else '',
            'status': m.status,
        } for m in messages]
    }
    return JsonResponse(data)

from django.http import StreamingHttpResponse, HttpResponseForbidden, Http404
from django.shortcuts import get_object_or_404

def view_secure_document3(request, log_id):
    """
    View secure NOC documents - only accessible to logged-in users
    """
    log = get_object_or_404(SmsWhatsAppLog3, id=log_id)

    filename = (log.media_file.name or "").lower()

    # Security check: Only allow NOC documents that were sent
    if (
        log.content_type != "document"
        or log.message_type != "Sent"
        or "noc" not in filename
    ):
        return HttpResponseForbidden("Not allowed")

    file_obj = default_storage.open(log.media_file.name, "rb")

    response = StreamingHttpResponse(file_obj, content_type="application/pdf")
    response["Content-Disposition"] = "inline; filename=NOC.pdf"
    response["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"

    return response

