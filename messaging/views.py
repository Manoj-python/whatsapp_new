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
from .models import SmsWhatsAppLog, BulkJob
from .utils import format_mobile  # keep existing
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
from .models import SmsWhatsAppLog, BulkJob
from .tasks import process_bulk_whatsapp
from .utils import format_mobile


from django.contrib.auth import authenticate
from django.contrib import messages



from django.core.paginator import Paginator
from django.http import JsonResponse
from .models import SmsWhatsAppLog
from .utils import format_mobile
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
            f"chat_{gm}",
            {
                "type": "delivery.update",
                "message_id": message_id,
                "status": norm,
                "mobile": mobile
            }
        )

    # notify all dashboard clients
    async_to_sync(channel_layer.group_send)(
        "delivery_group",
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

def messaging_login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(username=username, password=password)
        if user:
            # Custom session KEY
            request.session["messaging_user"] = user.id
            return redirect("upload_and_send")
        else:
            messages.error(request, "Invalid username or password")

    return render(request, "messaging/login.html")

def messaging_logout(request):
    request.session.pop("messaging_user", None)
    return redirect("/login/")


def messaging_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.session.get("messaging_user"):
            return redirect("/login/")
        return view_func(request, *args, **kwargs)
    return wrapper




# -----------------------------------------------------
# WhatsApp API - SEND TEXT
# -----------------------------------------------------
def send_whatsapp_text(to_number, text_body):
    url = f"https://graph.facebook.com/v17.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
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
# Upload media to WhatsApp Cloud (same behaviour)
# -----------------------------------------------------
def upload_whatsapp_media(file_obj):
    access_token = settings.WHATSAPP_ACCESS_TOKEN
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    url = f"https://graph.facebook.com/v17.0/{phone_number_id}/media"
    headers = {"Authorization": f"Bearer {access_token}"}

    file_obj.seek(0)
    files = {'file': (file_obj.name, file_obj.read(), file_obj.content_type)}
    data = {'messaging_product': 'whatsapp'}

    resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)
    resp.raise_for_status()
    return resp.json()


# -----------------------------------------------------
# Send media (image/video/audio/document)
# -----------------------------------------------------
def send_whatsapp_media(to_number, media_id, media_type, caption=""):
    url = f"https://graph.facebook.com/v17.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
               "Content-Type": "application/json"}

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": media_type,
        media_type: {"id": media_id},
    }
    if caption and media_type in ("image", "video"):
        payload[media_type]["caption"] = caption

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


# -----------------------------------------------------
# Bulk Upload Start (S3-safe)
# -----------------------------------------------------
@messaging_required
def upload_and_send(request):
    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            choice = form.cleaned_data["template_choice"]
            excel_file = request.FILES["excel_file"]

            # Save uploaded Excel to S3 under uploads/
            unique_name = f"{uuid.uuid4().hex}_{excel_file.name}"
            s3_key = f"uploads/{unique_name}"
            default_storage.save(s3_key, excel_file)

            # Read Excel from S3 into pandas via a small temp buffer
            with default_storage.open(s3_key, "rb") as f:
                data = f.read()
            df = pd.read_excel(io.BytesIO(data), dtype=str).fillna("")
            job_id = str(uuid.uuid4())

            BulkJob.objects.create(
                job_id=job_id,
                template_name=choice,
                total_customers=len(df),
                excel_file=s3_key,
                status="Pending",
            )

            # Kick off background Celery job using S3 key
            process_bulk_whatsapp.delay(s3_key, choice, job_id)
            return redirect("job_status", job_id=job_id)
    else:
        form = UploadForm()
    return render(request, "messaging/index.html", {"form": form})


# -----------------------------------------------------
# Bulk Job Status Page
# -----------------------------------------------------
def job_status(request, job_id):
    job = get_object_or_404(BulkJob, job_id=job_id)
    progress = 0
    if job.total_customers > 0:
        progress = round((job.sent_count / job.total_customers) * 100, 2)
    return render(request, "messaging/job_status.html", {"job": job, "progress": progress})


# -----------------------------------------------------
# Download Success Report (redirect to S3)
# -----------------------------------------------------
def download_success_report(request, job_id):
    job = get_object_or_404(BulkJob, job_id=job_id)
    if job.success_report:
        return redirect(default_storage.url(job.success_report.name))
    raise Http404("Success report not found.")


# -----------------------------------------------------
# Download Failed Report (redirect to S3)
# -----------------------------------------------------
def download_failed_report(request, job_id):
    job = get_object_or_404(BulkJob, job_id=job_id)
    if job.failed_report:
          return redirect(default_storage.url(job.failed_report.name))

    raise Http404("Failed report not found.")


# -----------------------------------------------------
# CHAT DASHBOARD
# -----------------------------------------------------
@messaging_required
def chat_dashboard(request):
    mobiles = (
        SmsWhatsAppLog.objects
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

    return render(request, "messaging/chat.html", {
        "mobile_list": mobile_list,
        "user_name": request.user.username,
        "MEDIA_URL": settings.MEDIA_URL,
    })


# -----------------------------------------------------
# Get Messages for Mobile (returns public S3 URLs)
# -----------------------------------------------------
# in messaging/views.py (chat_messages_api)
from django.core.paginator import Paginator


# -----------------------------------------------------
# Get Messages for Mobile (returns public S3 URLs)
# -----------------------------------------------------
def chat_messages_api(request, mobile):
    mobile = format_mobile(mobile)
    page = int(request.GET.get("page", 1))
    size = 500  # 500 messages per page

    qs = SmsWhatsAppLog.objects.filter(mobile=mobile).order_by("-sent_at")

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
def send_reply_api(request):
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
        if request.session.get("messaging_user"):
            from django.contrib.auth.models import User
            u = User.objects.filter(id=request.session["messaging_user"]).first()
            if u:
                agent_name = u.username

        # -------- SEND TO WHATSAPP API --------
        if media_file:
            upload_resp = upload_whatsapp_media(media_file)
            media_id = upload_resp.get("id")
            mime_main = (media_file.content_type.split("/")[0] if media_file.content_type else "").lower()
            mapped_type = mime_main if mime_main in ("image", "video", "audio") else "document"

            send_resp = send_whatsapp_media(
                to_number=mobile,
                media_id=media_id,
                media_type=mapped_type,
                caption=text,
            )
            content_type = mapped_type
        else:
            send_resp = send_whatsapp_text(mobile, text)
            content_type = "text"

        msg_id = ""
        if isinstance(send_resp, dict) and "messages" in send_resp:
            msg_id = send_resp["messages"][0].get("id", "")

        # -------- SAVE DB --------
        log = SmsWhatsAppLog.objects.create(
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
                f"chat_{gm}",
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
            "contacts_group",
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
# WHATSAPP WEBHOOK
# -----------------------------------------------------
@csrf_exempt
def whatsapp_webhook(request):
    channel_layer = get_channel_layer()

    # ---------- VERIFY TOKEN (GET) ----------
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
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
                        mobile = format_mobile(msg.get("from", ""))

                        # ---- Deduplicate ----
                        if msg_id and SmsWhatsAppLog.objects.filter(message_id=msg_id).exists():
                            # Only update presence
                            gm = ws_group(mobile)
                            if gm:
                                async_to_sync(channel_layer.group_send)(
                                    f"chat_{gm}",
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
                            media_file = download_whatsapp_media(media_id)

                        # ======================================
                        #       SAVE MESSAGE TO DATABASE
                        # ======================================
                        from django.db import transaction
                        with transaction.atomic():
                            log = SmsWhatsAppLog.objects.create(
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
                        gm = ws_group(mobile)
                        if gm:
                            async_to_sync(channel_layer.group_send)(
                                f"chat_{gm}",
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
                            "presence_group",
                            {"type": "presence.update", "mobile": mobile, "status": "online"}
                        )
                        async_to_sync(channel_layer.group_send)(
                            "contacts_group",
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
                        mobile = format_mobile(recipient) if recipient else ""

                        # ---- Update DB ----
                        if mid:
                            SmsWhatsAppLog.objects.filter(message_id=mid).update(status=norm)

                        # ---- Broadcast REAL-TIME tick update ----
                        broadcast_delivery(mobile, mid, norm)

                        # ---- Handle errors ----
                        errors = st.get("errors", []) or []
                        if errors:
                            err = errors[0]
                            err_msg = f"{err.get('code')} - {err.get('title')}: {err.get('message')}"
                            SmsWhatsAppLog.objects.filter(message_id=mid).update(error_message=err_msg)

                            async_to_sync(channel_layer.group_send)(
                                "delivery_group",
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
def download_whatsapp_media(media_id):
    try:
        access_token = settings.WHATSAPP_ACCESS_TOKEN
        headers = {"Authorization": f"Bearer {access_token}"}

        meta_url = f"https://graph.facebook.com/v17.0/{media_id}"
        meta_resp = requests.get(meta_url, headers=headers, timeout=30)
        meta_resp.raise_for_status()
        meta = meta_resp.json()

        file_url = meta.get("url")
        mime = meta.get("mime_type", "")
        ext = mime.split("/")[-1] if "/" in mime else "bin"

        file_resp = requests.get(file_url, headers=headers, timeout=30)
        file_resp.raise_for_status()

        filename = f"whatsapp_{media_id}.{ext}"
        return filename, file_resp.content

    except Exception as e:
        print("Media download error:", e)
        return None





# -----------------------------------------------------
# Contacts API (for sidebar)
# -----------------------------------------------------
def contacts_api(request):
    q = request.GET.get("q", "").strip()
    # Build base queryset: group by mobile, last_time, unread count
    qs = (
        SmsWhatsAppLog.objects.values("mobile")
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
            mobiles_matching = SmsWhatsAppLog.objects.filter(sent_text_message__icontains=q).values_list("mobile", flat=True).distinct()
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
def mark_read(request, mobile):
    try:
        mobile_norm = format_mobile(mobile)
        SmsWhatsAppLog.objects.filter(mobile=mobile_norm, message_type="Received", status="Unread").update(status="Read")

        channel_layer = get_channel_layer()
        gm = ws_group(mobile_norm)
        if gm:
            # conversation level read
            async_to_sync(channel_layer.group_send)(
                f"chat_{gm}",
                {
                    "type": "delivery.update",
                    "message_id": "",    # empty => conversation-level read
                    "status": "Read",
                    "mobile": mobile_norm,
                }
            )

        # notify contacts to refresh unread count
        async_to_sync(channel_layer.group_send)(
            "contacts_group",
            {"type": "presence.update", "mobile": mobile_norm, "status": "updated"}
        )

        return JsonResponse({"status": "ok"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)




