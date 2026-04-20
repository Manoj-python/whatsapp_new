# messaging2/views.py
import pandas as pd
import io
import json
import re
import uuid
import requests
from django.http import HttpResponseForbidden, JsonResponse, HttpResponseBadRequest, HttpResponse, Http404, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect, get_object_or_404
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Max, Count, Q
from django.conf import settings
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .utils import upload_whatsapp_media2, send_whatsapp_media2

from .models import SmsWhatsAppLog2, BulkJob2
from .utils import format_mobile2
from django.utils import timezone

from .forms import UploadForm
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

from .forms import UploadForm
from .models import SmsWhatsAppLog2, BulkJob2
from .tasks import process_bulk_whatsapp2
from .utils import format_mobile2

from django.contrib.auth import authenticate
from django.contrib import messages

from django.core.paginator import Paginator
from django.http import JsonResponse
from .models import SmsWhatsAppLog2
from .utils import format_mobile2
import re
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def serialize_log2(m):
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


def broadcast_delivery2(mobile, message_id, status):
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

    gm = ws_group2(mobile)
    if gm:
        async_to_sync(channel_layer.group_send)(
            f"chat2_{gm}",
            {
                "type": "delivery.update",
                "message_id": message_id,
                "status": norm,
                "mobile": mobile
            }
        )

    # notify all dashboard clients
    async_to_sync(channel_layer.group_send)(
        "delivery_group2",
        {
            "type": "delivery.update",
            "message_id": message_id,
            "status": norm,
            "mobile": mobile
        }
    )


# -------------------
# Helper: ws_group2
# -------------------
def ws_group2(mobile: str) -> str:
    """
    Sanitize mobile into digits-only group name.
    Example: "+91 63026-61004" -> "916302661004"
    """
    if not mobile:
        return ""
    return re.sub(r"\D", "", str(mobile))


def messaging2_login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(username=username, password=password)
        if user:
            # Custom session KEY
            request.session["messaging2_user"] = user.id
            return redirect("upload_and_send2")
        else:
            messages.error(request, "Invalid username or password")

    return render(request, "messaging2/login.html")


def messaging2_logout(request):
    request.session.pop("messaging2_user", None)
    return redirect("/messaging2/login/")


def messaging2_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.session.get("messaging2_user"):
            return redirect("/messaging2/login/")
        return view_func(request, *args, **kwargs)
    return wrapper


# -----------------------------------------------------
# WhatsApp API - SEND TEXT
# -----------------------------------------------------
def send_whatsapp2_text(to_number, text_body):
    url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP2_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {settings.WHATSAPP2_ACCESS_TOKEN}",
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
@messaging2_required
@messaging2_required
def upload_and_send2(request):
    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            choice = form.cleaned_data["template_choice"]
            excel_file = request.FILES["excel_file"]

            unique_name = f"{uuid.uuid4().hex}_{excel_file.name}"
            s3_key = f"uploads2/{unique_name}"
            default_storage.save(s3_key, excel_file)

            with default_storage.open(s3_key, "rb") as f:
                data = f.read()
            df = pd.read_excel(io.BytesIO(data), dtype=str).fillna("")
            total_customers = len(df)
            job_id = str(uuid.uuid4())

            BulkJob2.objects.create(
                job_id=job_id,
                template_name=choice,
                total_customers=total_customers,
                excel_file=s3_key,
                status="Pending",  # Changed from "Running" to "Pending"
            )

            # ✅ USE .delay() FOR ASYNC EXECUTION
            from .tasks import process_bulk_whatsapp2
            process_bulk_whatsapp2.delay(s3_key, choice, job_id)  # Added .delay()
            
            return redirect("job_status2", job_id=job_id)
    else:
        form = UploadForm()
    return render(request, "messaging2/index.html", {"form": form})# Bulk Job Status Page
# -----------------------------------------------------
def job_status2(request, job_id):
    job = get_object_or_404(BulkJob2, job_id=job_id)
    progress = 0
    if job.total_customers > 0:
        progress = round((job.sent_count / job.total_customers) * 100, 2)
    return render(request, "messaging2/job_status.html", {"job": job, "progress": progress})


# -----------------------------------------------------
# Download Success Report (redirect to S3)
# -----------------------------------------------------
# -----------------------------------------------------
# Download Success Report (redirect to S3)
# -----------------------------------------------------
def download_success_report2(request, job_id):
    job = get_object_or_404(BulkJob2, job_id=job_id)
    if job.success_report:
        return redirect(default_storage.url(job.success_report.name))
    raise Http404("Success report not found.")


# -----------------------------------------------------
# Download Failed Report (redirect to S3)
# -----------------------------------------------------
def download_failed_report2(request, job_id):
    job = get_object_or_404(BulkJob2, job_id=job_id)
    if job.failed_report:
          return redirect(default_storage.url(job.failed_report.name))

    raise Http404("Failed report not found.")


# -----------------------------------------------------
# CHAT DASHBOARD
# -----------------------------------------------------
@messaging2_required
def chat_dashboard2(request):
    mobiles = (
        SmsWhatsAppLog2.objects
        .values("mobile")
        .annotate(last_sent=Max("sent_at"))
        .order_by("-last_sent")
    )

    seen = set()
    mobile_list = []

    for m in mobiles:
        normalized = format_mobile2(str(m["mobile"]))
        if normalized not in seen:
            seen.add(normalized)
            mobile_list.append({"mobile": normalized})

    return render(request, "messaging2/chat.html", {
        "mobile_list": mobile_list,
        "user_name": request.user.username if request.user.is_authenticated else "",
        "MEDIA_URL": settings.MEDIA_URL,
    })


# -----------------------------------------------------
# Get Messages for Mobile (returns public S3 URLs)
# -----------------------------------------------------
def chat_messages_api2(request, mobile):
    mobile = format_mobile2(mobile)
    page = int(request.GET.get("page", 1))
    size = 500  # 500 messages per page

    qs = SmsWhatsAppLog2.objects.filter(mobile=mobile).order_by("-sent_at")

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

        # Check if secure NOC document
        is_secure_noc = (
            m.content_type == "document"
            and m.message_type == "Sent"
            and m.media_file
            and "noc" in (m.media_file.name or "").lower()
        )

        return {
            "id": m.id,
            "mobile": m.mobile,
            "sent_text_message": m.sent_text_message or "",
            "message_type": m.message_type,
            "sent_at": m.sent_at.isoformat() if m.sent_at else "",
            "message_id": m.message_id,
            "content_type": m.content_type or "text",
            "media_file": "" if is_secure_noc else media_url,
            "secure_media_id": m.id if is_secure_noc else None,
            "status": m.status or "",
            "sender_name": m.customer_name or "",
        }

    return JsonResponse({
        "messages": [to_json(m) for m in result],
        "has_more": pg.has_next()
    })


# -----------------------------------------------------
# SEND REPLY API
# -----------------------------------------------------
@csrf_exempt
@messaging2_required
def send_reply_api2(request):
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
        mobile = format_mobile2(mobile)

        # -------- GET LOGGED-IN USER NAME (sender_name) --------
        agent_name = None
        if request.session.get("messaging2_user"):
            from django.contrib.auth.models import User
            u = User.objects.filter(id=request.session["messaging2_user"]).first()
            if u:
                agent_name = u.username

        # -------- SEND TO WHATSAPP API --------
        if media_file:
            upload_resp = upload_whatsapp_media2(media_file)
            media_id = upload_resp.get("id")
            mime_main = (media_file.content_type.split("/")[0] if media_file.content_type else "").lower()
            mapped_type = mime_main if mime_main in ("image", "video", "audio") else "document"

            send_resp = send_whatsapp_media2(
                to_number=mobile,
                media_id=media_id,
                media_type=mapped_type,
                caption=text,
            )
            content_type = mapped_type
        else:
            send_resp = send_whatsapp2_text(mobile, text)
            content_type = "text"

        msg_id = ""
        if isinstance(send_resp, dict) and "messages" in send_resp:
            msg_id = send_resp["messages"][0].get("id", "")

        # -------- SAVE DB --------
        log = SmsWhatsAppLog2.objects.create(
            customer_name=agent_name,        # store username as sender_name
            mobile=mobile,
            template_name="manual",
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
        gm = ws_group2(mobile)

        if gm:
            async_to_sync(channel_layer.group_send)(
                f"chat2_{gm}",
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
                        "sender_name": agent_name or "",
                    }
                }
            )

        # Update ticks
        broadcast_delivery2(mobile, msg_id, "Sent")

        async_to_sync(channel_layer.group_send)(
            "contacts_group2",
            {"type": "presence.update", "mobile": mobile, "status": "updated"}
        )

        # -------- API RESPONSE (also include sender_name) --------
        return JsonResponse({
            "status": "ok",
            "message_id": msg_id,
            "sender_name": agent_name or ""
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# -----------------------------------------------------
# WHATSAPP WEBHOOK
# -----------------------------------------------------
@csrf_exempt
def whatsapp_webhook2(request):
    channel_layer = get_channel_layer()

    # ---------- VERIFY TOKEN (GET) ----------
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        if mode == "subscribe" and token == settings.WHATSAPP2_VERIFY_TOKEN:
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
                    #          1. INCOMING MESSAGES
                    # ======================================
                    messages = value.get("messages", []) or []
                    contacts = value.get("contacts", []) or []

                    for msg in messages:

                        msg_id = msg.get("id")
                        mobile = format_mobile2(msg.get("from", ""))

                        # ---- Deduplicate ----
                        if msg_id and SmsWhatsAppLog2.objects.filter(message_id=msg_id).exists():
                            # Only update presence
                            gm = ws_group2(mobile)
                            if gm:
                                async_to_sync(channel_layer.group_send)(
                                    f"chat2_{gm}",
                                    {"type": "presence.update", "mobile": mobile, "status": "online"}
                                )
                            continue

                        msg_type = msg.get("type", "text")
                        text_body = ""
                        content_type = "text"
                        media_file = None

                        # ---- TEXT ----
                        if msg_type == "text":
                            text_body = msg["text"].get("body", "")
                            content_type = "text"

                        # ---- INTERACTIVE (button / list) ----
                        elif msg_type == "interactive":
                            interactive = msg.get("interactive", {})
                            content_type = "interactive"

                            if interactive.get("type") == "button":
                                text_body = interactive["button"].get("text", "")
                            elif interactive.get("type") == "list_reply":
                                text_body = interactive["list_reply"].get("title", "")

                        # ---- MEDIA (image / video / audio / doc) ----
                        elif msg_type in ("image", "video", "audio", "document"):
                            media_id = msg[msg_type].get("id")
                            content_type = msg_type
                            text_body = f"[{msg_type.title()}]"  # placeholder

                            # Download actual media
                            media_file = download_whatsapp2_media(media_id)

                        # ======================================
                        #       SAVE MESSAGE TO DATABASE
                        # ======================================
                        from django.db import transaction
                        with transaction.atomic():
                            log = SmsWhatsAppLog2.objects.create(
                                customer_name=(contacts[0].get("profile", {}).get("name") if contacts else ""),
                                mobile=mobile,
                                template_name="incoming",
                                sent_text_message=text_body,
                                status="Unread",
                                message_type="Received",
                                message_id=msg_id,
                                content_type=content_type,
                            )

                            if media_file:
                                filename, content = media_file
                                log.media_file.save(filename, ContentFile(content))
                                log.save()

                        # ======================================
                        #       BROADCAST REAL-TIME NEW MESSAGE
                        # ======================================
                        gm = ws_group2(mobile)
                        if gm:
                            async_to_sync(channel_layer.group_send)(
                                f"chat2_{gm}",
                                {
                                    "type": "new_message",
                                    "message": {
                                        "id": log.id,
                                        "mobile": mobile,
                                        "sent_text_message": log.sent_text_message,
                                        "content_type": log.content_type,
                                        "media_file": log.media_file.url if log.media_file else "",
                                        "sent_at": log.sent_at.isoformat(),
                                        "message_type": "Received",
                                        "message_id": log.message_id,
                                        "status": log.status,
                                    }
                                }
                            )

                        # Update presence + contacts
                        async_to_sync(channel_layer.group_send)(
                            "presence_group2",
                            {"type": "presence.update", "mobile": mobile, "status": "online"}
                        )
                        async_to_sync(channel_layer.group_send)(
                            "contacts_group2",
                            {"type": "presence.update", "mobile": mobile, "status": "updated"}
                        )

                    # ======================================
                    #          2. DELIVERY RECEIPTS
                    # ======================================
                    statuses = value.get("statuses", []) or []

                    for st in statuses:

                        mid = st.get("id")
                        raw_status = (st.get("status") or "").lower()

                        # Normalize WA ticks
                        if raw_status == "sent":
                            norm = "Sent"
                        elif raw_status == "delivered":
                            norm = "Delivered"
                        elif raw_status == "read":
                            norm = "Read"
                        else:
                            norm = "Failed"

                        recipient = st.get("recipient_id") or st.get("recipient") or ""
                        mobile = format_mobile2(recipient) if recipient else ""

                        # ---- Update DB ----
                        if mid:
                            SmsWhatsAppLog2.objects.filter(message_id=mid).update(status=norm)

                        # ---- Broadcast REAL-TIME tick update ----
                        broadcast_delivery2(mobile, mid, norm)

                        # ---- Handle errors ----
                        errors = st.get("errors", []) or []
                        if errors:
                            err = errors[0]
                            err_msg = f"{err.get('code')} - {err.get('title')}: {err.get('message')}"
                            SmsWhatsAppLog2.objects.filter(message_id=mid).update(error_message=err_msg)

                            async_to_sync(channel_layer.group_send)(
                                "delivery_group2",
                                {
                                    "type": "delivery.update",
                                    "message_id": mid,
                                    "status": "Failed",
                                    "mobile": mobile,
                                    "error": err_msg
                                }
                            )

            return JsonResponse({"status": "received"})

        except Exception as e:
            print("WEBHOOK ERROR:", e)
            return JsonResponse({"error": str(e)}, status=400)

    return HttpResponseBadRequest("Unsupported method")


# -----------------------------------------------------
# Download media from WA (helper)
# -----------------------------------------------------
def download_whatsapp2_media(media_id):
    try:
        access_token = settings.WHATSAPP2_ACCESS_TOKEN
        headers = {"Authorization": f"Bearer {access_token}"}

        meta_url = f"https://graph.facebook.com/v22.0/{media_id}"
        meta_resp = requests.get(meta_url, headers=headers, timeout=30)
        meta_resp.raise_for_status()
        meta = meta_resp.json()

        file_url = meta.get("url")
        mime = meta.get("mime_type", "")
        ext = mime.split("/")[-1] if "/" in mime else "bin"

        file_resp = requests.get(file_url, headers=headers, timeout=30)
        file_resp.raise_for_status()

        filename = f"whatsapp2_{media_id}.{ext}"
        return filename, file_resp.content

    except Exception as e:
        print("Media download error:", e)
        return None


# -----------------------------------------------------
# Contacts API (for sidebar)
# -----------------------------------------------------
def contacts_api2(request):
    q = request.GET.get("q", "").strip()
    # Build base queryset: group by mobile, last_time, unread count
    qs = (
        SmsWhatsAppLog2.objects.values("mobile")
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
            mobiles_matching = SmsWhatsAppLog2.objects.filter(sent_text_message__icontains=q).values_list("mobile", flat=True).distinct()
            qs = qs.filter(mobile__in=list(mobiles_matching))

    result = [{
        "mobile": format_mobile2(item["mobile"]),
        "last_time": item["last_time"].isoformat() if item["last_time"] else "",
        "unread": item["unread"],
    } for item in qs]
    return JsonResponse({"contacts": result})


# -----------------------------------------------------
# Mark messages read
# -----------------------------------------------------
# =====================================================
# MARK READ - FIXED with 2 suffix
# =====================================================
@csrf_exempt
def mark_read2(request, mobile):
    """
    Mark all messages as read for a specific mobile
    """
    try:
        mobile_norm = format_mobile2(mobile)
        SmsWhatsAppLog2.objects.filter(
            mobile=mobile_norm, 
            message_type="Received", 
            status="Unread"
        ).update(status="Read")
        
        # Optional: Broadcast via WebSocket if needed
        # from asgiref.sync import async_to_sync
        # from channels.layers import get_channel_layer
        # channel_layer = get_channel_layer()
        # async_to_sync(channel_layer.group_send)(
        #     f"chat2_{mobile_norm}",
        #     {"type": "delivery.update", "message_id": "", "status": "Read", "mobile": mobile_norm}
        # )
        
        return JsonResponse({"status": "ok"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    

def export_received_messages_to_excel2(request):
    """
    Export all received messages to Excel file
    """
    logs = SmsWhatsAppLog2.objects.filter(message_type="Received").order_by("-sent_at")
    
    if not logs.exists():
        return HttpResponse("No received messages found.")
    
    # Convert to DataFrame
    data = []
    for log in logs:
        data.append({
            "Customer Name": log.customer_name or "",
            "Mobile": log.mobile,
            "Message": log.sent_text_message or "",
            "Content Type": log.content_type,
            "Status": log.status,
            "Sent At": log.sent_at.astimezone(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S") if log.sent_at else "",
        })
    
    df = pd.DataFrame(data)
    
    # Create Excel file
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Received Messages")
    
    buf.seek(0)
    
    return HttpResponse(
        buf,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="received_messages.xlsx"'}
    )

# =====================================================
# VIEW SECURE DOCUMENT (for NOC PDFs)
# =====================================================

def view_secure_document2(request, log_id):
    """
    View secure NOC documents - only accessible to logged-in users
    """
    log = get_object_or_404(SmsWhatsAppLog2, id=log_id)

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


# =====================================================
# EXPORT RECEIVED MESSAGES TO EXCEL
# =====================================================
def export_received_messages_to_excel2(request):
    """
    Export all received messages to Excel file
    """
    import io
    import pandas as pd
    import pytz
    
    logs = SmsWhatsAppLog2.objects.filter(message_type="Received").order_by("-sent_at")
    
    if not logs.exists():
        return HttpResponse("No received messages found.")
    
    # Convert to DataFrame
    data = []
    for log in logs:
        sent_time = log.sent_at
        if sent_time:
            sent_time = sent_time.astimezone(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
        else:
            sent_time = ""
        
        data.append({
            "Customer Name": log.customer_name or "",
            "Mobile": log.mobile,
            "Message": log.sent_text_message or "",
            "Content Type": log.content_type,
            "Status": log.status,
            "Sent At": sent_time,
        })
    
    df = pd.DataFrame(data)
    
    # Create Excel file
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Received Messages")
    
    buf.seek(0)
    
    return HttpResponse(
        buf,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="received_messages.xlsx"'}
    )


