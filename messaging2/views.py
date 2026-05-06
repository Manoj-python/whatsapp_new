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
from .forms import UploadForm2
from django.contrib.auth import authenticate
from django.contrib import messages
from django.core.paginator import Paginator
from .consumers import *

import pytz


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

def ws_group2(mobile: str) -> str:
    if not mobile:
        return ""
    return re.sub(r"\D", "", str(mobile))


def send_whatsapp_text2(to_number, text_body):
    """Send text message via WhatsApp API"""
    url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP2_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP2_ACCESS_TOKEN}",
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



def broadcast_delivery2(mobile, message_id, status):
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
    ChatContact2.objects.filter(mobile=mobile).update(
        last_status=norm,

    )

    gm = ws_group2(mobile)

    # ===== CHAT TICKS =====
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

    # ===== GLOBAL TICKS (ALL USERS) =====
    async_to_sync(channel_layer.group_send)(
        "delivery_group2",
        {
            "type": "delivery.update",
            "message_id": message_id,
            "status": norm,
            "mobile": mobile
        }
    )

    # ===== 🔥 CONTACT UPDATE =====
    async_to_sync(channel_layer.group_send)(
        "global_contacts2",
        {
            "type": "contact.update",
            "contact": {
                "mobile": mobile,
                "last_status": norm,
                #"last_time": timezone.now().isoformat()
            }
        }
    )

# -------------------
# Helper: ws_group2
# -------------------


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
# Bulk Upload Start (S3-safe)
# -----------------------------------------------------
@messaging2_required
def upload_and_send2(request):
    if request.method == "POST":
        form = UploadForm2(request.POST, request.FILES)
        if form.is_valid():
            choice = form.cleaned_data["template_choice"]
            excel_file = request.FILES["excel_file"]

            # Save uploaded Excel to S3 under uploads/
            unique_name = f"{uuid.uuid4().hex}_{excel_file.name}"
            s3_key = f"uploads2/{unique_name}"
            default_storage.save(s3_key, excel_file)

            # Read Excel from S3 into pandas
            with default_storage.open(s3_key, "rb") as f:
                data = f.read()

            df = pd.read_excel(io.BytesIO(data), dtype=str).fillna("")
            job_id = str(uuid.uuid4())

            # Create Bulk Job
            BulkJob2.objects.create(
                job_id=job_id,
                template_name=choice,
                total_customers=len(df),
                excel_file=s3_key,
                status="Pending",
            )

            # 🔥 FORCE TASK INTO WHATSAPP2_main QUEUE
            process_bulk_whatsapp2.apply_async(
                args=(s3_key, choice, job_id),
                queue="whatsapp_secondary"
            )

            return redirect("job_status2", job_id=job_id)

    else:
        form = UploadForm2()

    return render(request, "messaging2/index.html", {"form": form})


# -----------------------------------------------------
# Bulk Job Status Page
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
        "user_name": request.user.username,
        "MEDIA_URL": settings.MEDIA_URL,
    })


# -----------------------------------------------------
# Get Messages for Mobile (returns public S3 URLs)
# -----------------------------------------------------
# in messaging2views.py (chat2_messages_api)
from django.core.paginator import Paginator


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



# messaging2views.py - COMPLETE FIXED VERSION

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
from django.db.models import Max, Count, Q
from django.conf import settings
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone








# =============================================
# SEND REPLY API - FIXED WITH SAVE FIRST PATTERN
# =============================================
# messaging2views.py - COMPLETE WORKING VERSION (NO DUPLICATES)

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

from django.contrib.auth import authenticate
from django.contrib import messages
from django.core.paginator import Paginator


# =============================================
# HELPER FUNCTIONS
# =============================================
def ws_group2(mobile: str) -> str:
    if not mobile:
        return ""
    return re.sub(r"\D", "", str(mobile))


def send_whatsapp_text2(to_number, text_body):
    """Send text message via WhatsApp API"""
    url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP2_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP2_ACCESS_TOKEN}",
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


def download_whatsapp_media2(media_id):
    """Download media from WhatsApp"""
    try:
        access_token = settings.WHATSAPP2_ACCESS_TOKEN
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



# =============================================
# CHAT DASHBOARD & MESSAGES API
# =============================================



def chat_messages_api2(request, mobile):
    mobile = format_mobile2(mobile)
    page = int(request.GET.get("page", 1))
    size = 500

    qs = SmsWhatsAppLog2.objects.filter(mobile=mobile).order_by("-sent_at")
    paginator = Paginator(qs, size)

    try:
        pg = paginator.page(page)
    except:
        return JsonResponse({"messages": [], "has_more": False})

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
            "sender_name": m.customer_name or "",
        }

    return JsonResponse({
        "messages": [to_json(m) for m in result],
        "has_more": pg.has_next()
    })


def contacts_api2(request):
    q = request.GET.get("q", "").strip()
    qs = (
        SmsWhatsAppLog2.objects.values("mobile")
        .annotate(last_time=Max("sent_at"),
                  unread=Count("id", filter=Q(message_type="Received", status="Unread")))
        .order_by("-last_time")
    )

    if q:
        digits = re.sub(r"\D", "", q)
        if digits:
            qs = qs.filter(mobile__icontains=digits)
        else:
            mobiles_matching = SmsWhatsAppLog2.objects.filter(sent_text_message__icontains=q).values_list("mobile", flat=True).distinct()
            qs = qs.filter(mobile__in=list(mobiles_matching))

    result = [{
        "mobile": format_mobile2(item["mobile"]),
        "last_time": item["last_time"].isoformat() if item["last_time"] else "",
        "unread": item["unread"],
    } for item in qs]
    return JsonResponse({"contacts": result})


@csrf_exempt
def mark_read2(request, mobile):
    try:
        mobile_norm = format_mobile2(mobile)
        ChatContact2.objects.filter(mobile=mobile_norm).update(unread=0)
        channel_layer = get_channel_layer()
        gm = ws_group2(mobile_norm)
        if gm:
            async_to_sync(channel_layer.group_send)(
                f"chat2_{gm}",
                {
                    "type": "delivery.update",
                    "message_id": "",
                    "status": "Read",
                    "mobile": mobile_norm,
                }
            )
        async_to_sync(channel_layer.group_send)(
            "global_contacts2",
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
def send_reply_api2(request):
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

        mobile = format_mobile2(mobile)

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
        if request.session.get("messaging2_user"):
            from django.contrib.auth.models import User
            u = User.objects.filter(id=request.session["messaging2_user"]).first()
            if u:
                agent_name = u.username

        # =============================================
        # STEP 1: CREATE DATABASE RECORD FIRST (with temp ID)
        # =============================================
        temp_id = str(uuid.uuid4())

        log = SmsWhatsAppLog2.objects.create(
            customer_name=agent_name or "",
            mobile=mobile,
            sent_text_message=text or "",
            status="Sending",  # Status while sending
            message_id=temp_id,
            message_type="Sent",
            content_type="text",  # Will update later
        )
        clear_chat_cache2(mobile)


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
                SmsWhatsAppLog2.objects.filter(id=log.id).update(content_type=content_type_val)

                # print(f"📤 Uploading {WHATSAPP2_media_type}...")

                # Upload to WhatsApp
                upload_resp = upload_whatsapp_media2(media_file)
                media_id = upload_resp.get("id")

                if media_id:
                    send_resp = send_whatsapp_media2(
                        to_number=mobile,
                        media_id=media_id,
                        media_type=WHATSAPP2_media_type,
                        caption=text if text else ""
                    )
                    msg_id = send_resp.get("messages", [{}])[0].get("id", "")

                    # Save media file to storage
                    media_file.seek(0)
                    saved_path = default_storage.save(
                        f"chat2_media/{media_file.name}",
                        ContentFile(media_file.read())
                    )
                    media_url = default_storage.url(saved_path)

            elif text:
                send_resp = send_whatsapp_text2(mobile, text)
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

                SmsWhatsAppLog2.objects.filter(id=log.id).update(**update_data)
                log.refresh_from_db()
                # print(f"✅ [STEP 3] Updated message from {temp_id} to {msg_id}")
            else:
                SmsWhatsAppLog2.objects.filter(id=log.id).update(
                    status="Failed",
                    error_message="No message ID returned from WhatsApp"
                )
                # print(f"❌ No WhatsApp ID returned")

        except Exception as e:
            SmsWhatsAppLog2.objects.filter(id=log.id).update(
                status="Failed",
                error_message=str(e)
            )
            # print(f"❌ Send failed: {e}")
            return JsonResponse({"error": f"Send failed: {str(e)}"}, status=500)

        # Update contact
        ChatContact2.objects.update_or_create(
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
        gm = re.sub(r"\D", "", mobile)

        if gm:
            async_to_sync(channel_layer.group_send)(
                f"chat2_{gm}",
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
def whatsapp_webhook2(request):
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
                    # PROCESS INCOMING MESSAGES
                    # ======================================
                    for msg in value.get("messages", []):
                        msg_id = msg.get("id")
                        mobile = format_mobile2(msg.get("from", ""))

                        if msg_id and SmsWhatsAppLog2.objects.filter(message_id=msg_id).exists():
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
                            media_file_data = download_whatsapp_media2(media_id)
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

                        # Save message
                        with transaction.atomic():
                            log = SmsWhatsAppLog2.objects.create(
                                customer_name="",
                                mobile=mobile,
                                template_name="incoming",
                                sent_text_message=text_body,
                                status="Unread",
                                message_type="Received",
                                message_id=msg_id,
                                content_type=content_type,
                            )
                            clear_chat_cache2(mobile)


                            if media_file_data:
                                filename, content = media_file_data
                                log.media_file.save(filename, ContentFile(content))
                                log.save()
                                # print(f"💾 Saved media: {filename}")

                        # Update contact
                        obj, created = ChatContact2.objects.get_or_create(
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
                            ChatContact2.objects.filter(mobile=mobile).update(
                                last_time=timezone.now(),
                                last_msg=text_body or "",
                                last_type="Received",
                                last_status="Unread",
                                unread=F("unread") + 1
                            )

                        # WebSocket broadcast
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
                                        "sent_at": timezone.localtime(log.sent_at).isoformat(),
                                        "message_type": "Received",
                                        "message_id": log.message_id,
                                        "status": log.status,
                                    }
                                }
                            )

                        async_to_sync(channel_layer.group_send)(
                            "global_contacts2",
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
                        obj = SmsWhatsAppLog2.objects.filter(message_id=msg_id).first()
                        # If not found, try to find by partial match (temp ID might still be there)
                        if not obj and len(msg_id) > 30:
                            # Try to find by the real ID pattern in any message
                            partial = msg_id[:30]
                            obj = SmsWhatsAppLog2.objects.filter(message_id__startswith=partial).first()
                            if obj:
                                # print(f"✅ Found by partial match, updating full ID")
                                SmsWhatsAppLog2.objects.filter(id=obj.id).update(message_id=msg_id)
                                obj.refresh_from_db()
                        # Also try to find by looking for messages with status "Sending"
                        if not obj:
                            # print(f"❌ Message not found: {msg_id}")
                            continue



                        mobile = obj.mobile
                        if status_type == "sent":
                            norm = "Sent"
                        elif status_type == "delivered":
                            norm = "Delivered"
                        elif status_type == "read":
                            norm = "Read"
                        else:
                            continue

                        # Update database
                        SmsWhatsAppLog2.objects.filter(message_id=msg_id).update(status=norm)
                        ChatContact2.objects.filter(mobile=mobile).update(last_status=norm)

                        # WebSocket update
                        gm = ws_group2(mobile)
                        if gm:
                            async_to_sync(channel_layer.group_send)(
                                f"chat2_{gm}",
                                {
                                    "type": "delivery.update",
                                    "message_id": msg_id,
                                    "status": norm,
                                    "mobile": mobile
                                }
                            )
                        print(f"✅ Updated {msg_id} to {norm}")
                        total_unread = ChatContact2.objects.filter(unread__gt=0).count()
                        async_to_sync(channel_layer.group_send)(
                            "global_contacts2",
                            {
                                "type": "contact.update",
                                "contact": {
                                    "mobile": mobile,
                                    "last_status": norm,
                                    #"last_time": timezone.now().isoformat(),
                                    "type": "unread.update",
                                    "unread_count": total_unread
                                }
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
def download_whatsapp_media2(media_id):
    """Download media from WhatsApp"""
    try:
        access_token = settings.WHATSAPP2_ACCESS_TOKEN
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

def contacts_api2(request):
    from django.db import connection
    from django.utils import timezone

    query = """
        SELECT
            l.mobile,
            MAX(l.sent_at) as last_time,
            SUM(CASE WHEN l.message_type = 'Received' AND l.status = 'Unread' THEN 1 ELSE 0 END) as unread,
            (
                SELECT l2.sent_text_message
                FROM messaging2_smswhatsapplog2 l2
                WHERE l2.mobile = l.mobile
                ORDER BY l2.sent_at DESC
                LIMIT 1
            ) as last_msg
        FROM messaging2_smswhatsapplog2 l
        GROUP BY l.mobile
        HAVING last_msg IS NOT NULL AND last_msg != ''
        ORDER BY last_time DESC
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

    result = []

    for row in rows:
        result.append({
            "mobile": format_mobile2(row[0]),
            "last_time": timezone.localtime(row[1]).isoformat() if row[1] else "",
            "unread": row[2] or 0,
            "last_msg": row[3] or ""
        })

    return JsonResponse({"contacts": result})
# -----------------------------------------------------
# Mark messages read
# -----------------------------------------------------

@csrf_exempt
def mark_read2(request, mobile):
    try:
        mobile_norm = format_mobile2(mobile)
        ChatContact2.objects.filter(mobile=mobile).update(unread=0)
        channel_layer = get_channel_layer()
        gm = ws_group2(mobile_norm)
        if gm:
            # conversation level read
            async_to_sync(channel_layer.group_send)(
                f"chat2_{gm}",
                {
                    "type": "delivery.update",
                    "message_id": "",    # empty => conversation-level read
                    "status": "Read",
                    "mobile": mobile_norm,
                }
            )

        # notify contacts to refresh unread count
        async_to_sync(channel_layer.group_send)(
            "global_contacts2",
            {"type": "presence.update", "mobile": mobile_norm, "status": "updated"}
        )

        return JsonResponse({"status": "ok"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


from django.http import JsonResponse
from .models import SmsWhatsAppLog2

def get_contact_messages2(request):
    mobile = request.GET.get('mobile')
    if not mobile:
        return JsonResponse({'error': 'Mobile required'}, status=400)

    messages = SmsWhatsAppLog2.objects.filter(mobile=mobile).order_by('sent_at')

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
