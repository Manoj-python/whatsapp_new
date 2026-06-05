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
from django.http import StreamingHttpResponse, HttpResponseForbidden, Http404
from django.shortcuts import get_object_or_404
import pytz
import os
import tempfile
from django.conf import settings
from .models import *
from financehub.models import *
from django.shortcuts import render
from django.db.models import Q,Value
from django.core.paginator import Paginator
from django.db.models.functions import Replace
import unicodedata
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
from django.contrib.auth import authenticate, login as auth_login
from django.contrib import messages
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required

from .models import *
from .utils import *
from .tasks import *
from .forms import UploadForm2
from .consumers import *

import pytz
import os
import tempfile
from financehub.models import *
from django.db.models.functions import Replace
import unicodedata

# Import the unified app config from adminpanel
from adminpanel.views import APP_CONFIG, get_agent_from_user

# ============================================
# HELPER: get models for selected app
# ============================================
def get_models_for_app(request):
    """Return (case_model, contact_model, log_model, channel_group) for the app selected via ?app="""
    app_key = request.GET.get('app', 'psf')
    if app_key not in APP_CONFIG:
        app_key = 'psf'
    cfg = APP_CONFIG[app_key]
    return cfg['case_model'], cfg['contact_model'], cfg['log_model'], cfg['channel_group']

def get_case_model_for_app(request):
    """Convenience: only case model"""
    return get_models_for_app(request)[0]

def get_contact_model_for_app(request):
    """Convenience: only contact model"""
    return get_models_for_app(request)[1]

# ============================================
# AUTHENTICATION (unchanged)
# ============================================
def messaging2_login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(username=username, password=password)
        if user:
            auth_login(request, user)
            agent, created = Agent.objects.get_or_create(
                user=user,
                defaults={
                    'agent_id': f"AGT-{user.id}",
                    'name': user.get_full_name() or user.username,
                    'email': user.email or f"{user.username}@example.com",
                    'role': 'ADMIN' if user.is_superuser else 'AGENT'
                }
            )
            request.session["messaging2_user"] = user.id
            if agent.role == 'ADMIN':
                return redirect('admin_dashboard')
            elif agent.role == 'MANAGER':
                return redirect('manager_dashboard')
            elif agent.role == 'LEAD':
                return redirect('lead_dashboard')
            elif agent.role == 'LEGAL':
                return redirect('legal_dashboard')
            else:
                return redirect('agent_dashboard')
        else:
            messages.error(request, "Invalid username or password")
    return render(request, "messaging2/login.html")

def messaging2_logout(request):
    request.session.pop("messaging2_user", None)
    return redirect("messaging2_login")

def messaging2_required(view_func):
    def wrapper(request, *args, **kwargs):
        # First check Django auth
        if request.user.is_authenticated:
            return view_func(request, *args, **kwargs)
        # Then check custom session key (legacy)
        if request.session.get("messaging2_user"):
            return view_func(request, *args, **kwargs)
        return redirect(settings.LOGIN_URL)
    return wrapper
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
    ChatContact2.objects.filter(mobile=mobile).update(last_status=norm)
    gm = ws_group2(mobile)
    if gm:
        async_to_sync(channel_layer.group_send)(
            f"chat2_{gm}",
            {"type": "delivery.update", "message_id": message_id, "status": norm, "mobile": mobile}
        )
    async_to_sync(channel_layer.group_send)(
        "delivery_group2",
        {"type": "delivery.update", "message_id": message_id, "status": norm, "mobile": mobile}
    )
    async_to_sync(channel_layer.group_send)(
        "global_contacts2",
        {"type": "contact.update", "contact": {"mobile": mobile, "last_status": norm}}
    )

# -----------------------------------------------------
# Bulk Upload (PSF only - unchanged)
# -----------------------------------------------------
@messaging2_required
def upload_and_send2(request):
    if request.method == "POST":
        form = UploadForm2(request.POST, request.FILES)
        if form.is_valid():
            choice = form.cleaned_data["template_choice"]
            excel_file = request.FILES["excel_file"]
            unique_name = f"{uuid.uuid4().hex}_{excel_file.name}"
            s3_key = f"uploads2/{unique_name}"
            default_storage.save(s3_key, excel_file)
            with default_storage.open(s3_key, "rb") as f:
                data = f.read()
            df = pd.read_excel(io.BytesIO(data), dtype=str).fillna("")
            job_id = str(uuid.uuid4())
            BulkJob2.objects.create(
                job_id=job_id,
                template_name=choice,
                total_customers=len(df),
                excel_file=s3_key,
                status="Pending",
            )
            process_bulk_whatsapp2.apply_async(args=(s3_key, choice, job_id), queue="whatsapp_secondary")
            return redirect("job_status2", job_id=job_id)
    else:
        form = UploadForm2()
    return render(request, "messaging2/index.html", {"form": form})

def job_status2(request, job_id):
    job = get_object_or_404(BulkJob2, job_id=job_id)
    progress = 0
    if job.total_customers > 0:
        progress = round((job.sent_count / job.total_customers) * 100, 2)
    return render(request, "messaging2/job_status.html", {"job": job, "progress": progress})

def download_success_report2(request, job_id):
    job = get_object_or_404(BulkJob2, job_id=job_id)
    if job.success_report:
        return redirect(default_storage.url(job.success_report.name))
    raise Http404("Success report not found.")

def download_failed_report2(request, job_id):
    job = get_object_or_404(BulkJob2, job_id=job_id)
    if job.failed_report:
        return redirect(default_storage.url(job.failed_report.name))
    raise Http404("Failed report not found.")

# -----------------------------------------------------
# CHAT DASHBOARD (PSF only)
# -----------------------------------------------------
def chat_dashboard2(request):
    agent = get_agent_from_user(request.user)
    mobiles = (SmsWhatsAppLog2.objects.values("mobile").annotate(last_sent=Max("sent_at")).order_by("-last_sent"))
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
        "agent": agent,
        "user": request.user,
    })

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
            "sent_at": timezone.localtime(m.sent_at).isoformat(),
            "message_id": m.message_id,
            "content_type": m.content_type or "text",
            "media_file": media_url,
            "status": m.status or "",
            "sender_name": m.customer_name or "",
        }
    return JsonResponse({"messages": [to_json(m) for m in result], "has_more": pg.has_next()})

def contacts_api2(request):
    q = request.GET.get("q", "").strip()
    qs = (SmsWhatsAppLog2.objects.values("mobile")
          .annotate(last_time=Max("sent_at"),
                    unread=Count("id", filter=Q(message_type="Received", status="Unread")))
          .order_by("-last_time"))
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
from django.db.models import Max, Count, Q,F
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
                        caption=text if text else "",
                        filename=original_filename
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
        async_to_sync(channel_layer.group_send)(
            "global_contacts2",
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
                        customer_name = ""
                        contacts_data = value.get("contacts", [])
                        if contacts_data:
                            customer_name = contacts_data[0].get("profile", {}).get("name", "")
                            print(f"📛 Customer name: {customer_name}")  # Debug print


                        # Save message
                        with transaction.atomic():
                            log = SmsWhatsAppLog2.objects.create(
                                customer_name=customer_name,
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
                                        "sender_name": customer_name   # 🔥 ADD THIS LINE

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
                        SmsWhatsAppLog2.objects.filter(message_id=msg_id).update(status=norm,error_message=json.dumps(errors) if errors else "")
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

                        async_to_sync(channel_layer.group_send)(
                                "global_contacts2",
                            {
                                "type":"contact.update",
                                "contact":{
                                    "mobile":mobile,
                                    "last_status":norm
                                }
                            }
                        )
                        print(f"✅ Updated {msg_id} to {norm}")
                        total_unread = ChatContact2.objects.filter(unread__gt=0).count()
                        async_to_sync(channel_layer.group_send)(
                            "global_contacts2",
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

@csrf_exempt
def mark_read2(request, mobile):
    try:
        mobile_norm = format_mobile2(mobile)
        ChatContact2.objects.filter(mobile=mobile).update(unread=0)
        channel_layer = get_channel_layer()
        gm = ws_group2(mobile_norm)
        if gm:
            async_to_sync(channel_layer.group_send)(
                f"chat2_{gm}",
                {"type": "delivery.update", "message_id": "", "status": "Read", "mobile": mobile_norm}
            )
        async_to_sync(channel_layer.group_send)(
            "global_contacts2",
            {"type": "presence.update", "mobile": mobile_norm, "status": "updated"}
        )
        return JsonResponse({"status": "ok"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

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

def view_secure_document2(request, log_id):
    if not request.session.get("messaging2_user"):
        return HttpResponseForbidden("Authentication required.")
    log = get_object_or_404(SmsWhatsAppLog2, id=log_id)
    filename = (log.media_file.name or "").lower()
    is_noc_document = "noc" in filename
    if log.content_type != "document":
        return HttpResponseForbidden("Not allowed - This is not a document")
    if log.message_type.lower() not in ['sent', 'sending']:
        return HttpResponseForbidden("Not allowed - Only sent documents can be viewed")
    if not is_noc_document:
        return HttpResponseForbidden("Not allowed - This is not a NOC document")
    if not filename.endswith('.pdf'):
        return HttpResponseForbidden("Not allowed - NOC documents must be PDF files")
    file_obj = default_storage.open(log.media_file.name, "rb")
    response = StreamingHttpResponse(file_obj, content_type="application/pdf")
    response["Content-Disposition"] = "inline; filename=NOC.pdf"
    response["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response

# =============================== Escalation views =======================================================


# ============================================
# ESCALATION DASHBOARDS (APP-AWARE)
# ============================================

@messaging2_required
def agent_dashboard2(request):
    CaseModel = get_case_model_for_app(request)
    ContactModel = get_contact_model_for_app(request)
    agent = get_agent_from_user(request.user)
    cases = CaseModel.objects.filter(
        Q(assigned_to=agent) | Q(current_level='ESC1', assigned_to__isnull=True),
        status__in=['Open', 'In Progress', 'Reopened']
    ).exclude(status='Closed').order_by('-priority', '-created_at')
    stats = {
        'my_cases': cases.filter(assigned_to=agent).count(),
        'available_cases': cases.filter(assigned_to__isnull=True).count(),
        'resolved': CaseModel.objects.filter(resolved_by=agent.name).count(),
        'total_handled': CaseModel.objects.filter(assigned_to=agent).count(),
    }
    current_app = request.GET.get('app', 'psf')
    return render(request, 'messaging2/agent_dashboard.html', {
        'cases': cases,
        'stats': stats,
        'agent': agent,
        'current_app': current_app,
        'app_list': APP_CONFIG.items(),
    })

@messaging2_required
def legal_dashboard2(request):
    CaseModel = get_case_model_for_app(request)
    agent = get_agent_from_user(request.user)
    if agent.role != 'LEGAL':
        return redirect('agent_dashboard')
    cases = CaseModel.objects.filter(
        current_level='ESC2',
        status__in=['Open', 'In Progress', 'Reopened']
    ).exclude(status='Closed').order_by('-priority', '-created_at')
    stats = {
        'pending': cases.count(),
        'resolved': CaseModel.objects.filter(resolved_at_level='ESC2').count(),
        'escalated': CaseModel.objects.filter(previous_level='ESC2').count(),
    }
    current_app = request.GET.get('app', 'psf')
    return render(request, 'messaging2/legal_dashboard.html', {
        'cases': cases,
        'stats': stats,
        'agent': agent,
        'current_app': current_app,
        'app_list': APP_CONFIG.items(),
    })

@messaging2_required
def lead_dashboard2(request):
    CaseModel = get_case_model_for_app(request)
    agent = get_agent_from_user(request.user)
    if agent.role != 'LEAD':
        return redirect('agent_dashboard')
    cases = CaseModel.objects.filter(
        current_level='ESC3',
        status__in=['Open', 'In Progress', 'Reopened']
    ).exclude(status='Closed').order_by('-priority', '-created_at')
    agents = Agent.objects.filter(role='AGENT', is_active=True)
    total_cases = CaseModel.objects.filter(current_level='ESC3').count()
    open_cases = CaseModel.objects.filter(current_level='ESC3', status='Open').count()
    start_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    resolved_this_month = CaseModel.objects.filter(
        resolved_at_level='ESC3',
        resolved_at__gte=start_of_month
    ).count()
    priority_counts = {
        'urgent': CaseModel.objects.filter(current_level='ESC3', priority='Urgent').count(),
        'high': CaseModel.objects.filter(current_level='ESC3', priority='High').count(),
        'medium': CaseModel.objects.filter(current_level='ESC3', priority='Medium').count(),
        'low': CaseModel.objects.filter(current_level='ESC3', priority='Low').count(),
    }
    weekly_labels = []
    weekly_new_cases = []
    weekly_resolved_cases = []
    for i in range(6, -1, -1):
        date = timezone.now().date() - timedelta(days=i)
        weekly_labels.append(date.strftime('%a, %b %d'))
        start_of_day = timezone.make_aware(datetime.combine(date, datetime.min.time()))
        end_of_day = start_of_day + timedelta(days=1)
        weekly_new_cases.append(CaseModel.objects.filter(
            current_level='ESC3',
            created_at__gte=start_of_day,
            created_at__lt=end_of_day
        ).count())
        weekly_resolved_cases.append(CaseModel.objects.filter(
            resolved_at_level='ESC3',
            resolved_at__gte=start_of_day,
            resolved_at__lt=end_of_day
        ).count())
    current_app = request.GET.get('app', 'psf')
    return render(request, 'messaging2/lead_dashboard.html', {
        'cases': cases,
        'agents': agents,
        'agent': agent,
        'total_cases': total_cases,
        'open_cases': open_cases,
        'resolved_this_month': resolved_this_month,
        'priority_urgent': priority_counts['urgent'],
        'priority_high': priority_counts['high'],
        'priority_medium': priority_counts['medium'],
        'priority_low': priority_counts['low'],
        'weekly_labels': weekly_labels,
        'weekly_new_cases': weekly_new_cases,
        'weekly_resolved_cases': weekly_resolved_cases,
        'current_app': current_app,
        'app_list': APP_CONFIG.items(),
    })

@messaging2_required
def manager_dashboard2(request):
    CaseModel = get_case_model_for_app(request)
    agent = get_agent_from_user(request.user)
    if agent.role != 'MANAGER':
        return redirect('agent_dashboard')
    cases = CaseModel.objects.filter(
        current_level='ESC4',
        status__in=['Open', 'In Progress', 'Reopened']
    ).exclude(status='Closed').order_by('-priority', '-created_at')
    stats = {
        'pending': cases.count(),
        'resolved': CaseModel.objects.filter(resolved_at_level='ESC4').count(),
        'escalated_to_admin': CaseModel.objects.filter(current_level='ESC5').count(),
    }
    current_app = request.GET.get('app', 'psf')
    return render(request, 'messaging2/manager_dashboard.html', {
        'cases': cases,
        'stats': stats,
        'agent': agent,
        'current_app': current_app,
        'app_list': APP_CONFIG.items(),
    })

import json
import uuid
import re
from datetime import datetime, timedelta
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login as auth_login
from django.contrib import messages
from django.db.models import Q, Count
from django.utils import timezone
from django.core.paginator import Paginator
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import *

# ============================================
# AUTHENTICATION VIEWS
# ============================================



def get_case_detail_api2(request, case_id):
    CaseModel = get_case_model_for_app(request)
    try:
        case = CaseModel.objects.get(case_id=case_id)
        return JsonResponse({
            'success': True,
            'case': {
                'case_id': case.case_id,
                'customer_name': case.customer_name,
                'mobile': case.mobile,
                'current_level': case.current_level,
                'previous_level': case.previous_level,
                'status': case.status,
                'priority': case.priority,
                'loan_number': case.loan_number,
                'assigned_to_name': case.assigned_to_name,
                'created_by': case.created_by,
                'created_at': case.created_at.isoformat(),
                'resolved_at': case.resolved_at.isoformat() if case.resolved_at else None,
                'resolved_at_level': case.resolved_at_level,
                'resolved_by_role': case.resolved_by_role,
                'resolved_by': case.resolved_by,
                'issue_description': case.issue_description,
                'resolution_notes': case.resolution_notes,
                'reopen_count': case.reopen_count,
            }
        })
    except CaseModel.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Case not found'})

@csrf_exempt
def escalate_case_api2(request, case_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        CaseModel, ContactModel, _, channel_group = get_models_for_app(request)
        agent = get_agent_from_user(request.user)
        case = CaseModel.objects.get(case_id=case_id)
        data = json.loads(request.body)
        new_level = data.get('new_level')
        reason = data.get('reason', '')
        loan = data.get('loan', '')
        name = data.get('name', '')
        if not new_level:
            return JsonResponse({'error': 'New level required'}, status=400)
        if not case.can_escalate(agent, new_level):
            return JsonResponse({'error': 'You cannot escalate to this level'}, status=403)
        mobile = case.mobile
        case.escalate(new_level, agent, reason, loan, name)
        ContactModel.objects.filter(mobile=mobile).update(current_level=new_level)
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            channel_group,
            {"type": "contact.update", "contact": {"mobile": case.mobile, "current_level": new_level}}
        )
        return JsonResponse({'success': True, 'message': f'Case escalated to {new_level}', 'new_level': new_level})
    except CaseModel.DoesNotExist:
        return JsonResponse({'error': 'Case not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def resolve_case_api2(request, case_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        CaseModel, ContactModel, _, channel_group = get_models_for_app(request)
        agent = get_agent_from_user(request.user)
        case = CaseModel.objects.get(case_id=case_id)
        if not case.can_resolve(agent):
            return JsonResponse({'error': f'Cannot resolve case in {case.status} status'}, status=400)
        data = json.loads(request.body)
        resolution_notes = data.get('resolution_notes', '')
        case.resolve(agent, resolution_notes)
        ContactModel.objects.filter(mobile=case.mobile).update(current_level='RESOLVED')
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            channel_group,
            {"type": "contact.update", "contact": {"mobile": case.mobile, "current_level": 'RESOLVED'}}
        )
        return JsonResponse({'success': True, 'message': 'Case resolved successfully', 'case': {'case_id': case.case_id, 'status': case.status, 'current_level': case.current_level}})
    except CaseModel.DoesNotExist:
        return JsonResponse({'error': 'Case not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def close_case_api2(request, case_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        CaseModel, ContactModel, _, channel_group = get_models_for_app(request)
        agent = get_agent_from_user(request.user)
        if agent.role != 'ADMIN':
            return JsonResponse({'error': 'Only Admin can close cases'}, status=403)
        case = CaseModel.objects.get(case_id=case_id)
        if not case.can_close(agent):
            return JsonResponse({'error': f'Cannot close case in {case.status} status'}, status=400)
        data = json.loads(request.body)
        close_reason = data.get('close_reason', '')
        case.close(agent, close_reason)
        ContactModel.objects.filter(mobile=case.mobile).update(current_level='CLOSED', last_status='Closed')
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            channel_group,
            {"type": "contact.update", "contact": {"mobile": case.mobile, "current_level": 'CLOSED'}}
        )
        return JsonResponse({'success': True, 'message': f'Case {case.case_id} closed successfully'})
    except CaseModel.DoesNotExist:
        return JsonResponse({'error': 'Case not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def reopen_case_api2(request, case_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        CaseModel = get_case_model_for_app(request)
        agent = get_agent_from_user(request.user)
        case = CaseModel.objects.get(case_id=case_id)
        if case.status == 'Closed':
            return JsonResponse({'error': 'Cannot reopen a closed case. Only admin can reopen closed cases.'}, status=400)
        if case.status != 'Resolved':
            return JsonResponse({'error': f'Only resolved cases can be reopened. Current status: {case.status}'}, status=400)
        data = json.loads(request.body)
        reopen_reason = data.get('reopen_reason', '')
        target_level = data.get('target_level', None)
        if agent.role != 'ADMIN' and not agent.can_view_case(case):
            return JsonResponse({'error': 'You do not have permission to reopen this case'}, status=403)
        case.reopen(agent, reopen_reason, target_level)
        return JsonResponse({'success': True, 'message': f'Case reopened to {case.current_level}'})
    except CaseModel.DoesNotExist:
        return JsonResponse({'error': 'Case not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def assign_case_api2(request, case_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        CaseModel = get_case_model_for_app(request)
        agent = get_agent_from_user(request.user)
        if agent.role not in ['LEAD', 'ADMIN']:
            return JsonResponse({'error': 'Only Team Lead or Admin can assign cases'}, status=403)
        case = CaseModel.objects.get(case_id=case_id)
        data = json.loads(request.body)
        agent_id = data.get('agent_id')
        target_agent = Agent.objects.get(id=agent_id)
        case.assign_to_agent(target_agent, agent.name, data.get('notes', ''))
        return JsonResponse({'success': True})
    except CaseModel.DoesNotExist:
        return JsonResponse({'error': 'Case not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def get_case_timeline_api2(request, case_id):
    CaseModel = get_case_model_for_app(request)
    case = get_object_or_404(CaseModel, case_id=case_id)
    logs = case.escalation_logs.all()[:50]
    return JsonResponse({
        'logs': [{
            'from_level': log.from_level,
            'to_level': log.to_level,
            'escalated_by': log.escalated_by,
            'reason': log.reason,
            'created_at': log.created_at.isoformat()
        } for log in logs]
    })

def get_case_action_permissions2(request, case_id):
    try:
        CaseModel = get_case_model_for_app(request)
        agent = get_agent_from_user(request.user)
        case = CaseModel.objects.get(case_id=case_id)
        permissions = {
            'can_view': agent.can_view_case(case) or agent.role == 'ADMIN',
            'can_escalate': case.can_escalate(agent, '') and agent.role != 'ADMIN' and case.status not in ['Resolved', 'Closed'],
            'can_resolve': case.can_resolve(agent),
            'can_close': case.can_close(agent),
            'can_reopen': case.status == 'Resolved' and (agent.role == 'ADMIN' or agent.can_view_case(case)),
            'can_assign': agent.role in ['LEAD', 'ADMIN'] and case.status not in ['Resolved', 'Closed'],
        }
        escalation_options = []
        if agent.role != 'ADMIN' and case.status not in ['Resolved', 'Closed']:
            for level in agent.ESCALATION_MATRIX.get(agent.role, []):
                escalation_options.append({'level': level, 'name': dict(CaseModel.ESCALATION_CHOICES).get(level, level)})
        return JsonResponse({
            'success': True,
            'permissions': permissions,
            'escalation_options': escalation_options,
            'case_status': case.status,
            'case_level': case.current_level,
            'user_role': agent.role,
        })
    except CaseModel.DoesNotExist:
        return JsonResponse({'error': 'Case not found'}, status=404)

def get_resolved_cases_api2(request):
    CaseModel = get_case_model_for_app(request)
    agent = get_agent_from_user(request.user)
    if agent.role != 'ADMIN':
        return JsonResponse({'error': 'Admin access required'}, status=403)
    resolved_cases = CaseModel.objects.filter(status='Resolved', current_level='RESOLVED').order_by('-resolved_at')
    cases_data = [{
        'case_id': c.case_id,
        'customer_name': c.customer_name,
        'mobile': c.mobile,
        'loan_number': c.loan_number,
        'resolved_at_level': c.resolved_at_level,
        'resolved_by_role': c.resolved_by_role,
        'resolved_by': c.resolved_by,
        'resolved_at': c.resolved_at.isoformat(),
        'resolution_notes': c.resolution_notes,
        'reopen_count': c.reopen_count,
    } for c in resolved_cases]
    return JsonResponse({'success': True, 'cases': cases_data, 'total': resolved_cases.count()})

def get_dashboard_stats_api2(request):
    CaseModel = get_case_model_for_app(request)
    agent = get_agent_from_user(request.user)
    stats = {'role': agent.role, 'level': agent.level, 'name': agent.name}
    if agent.role == 'ADMIN':
        stats.update({
            'total_cases': CaseModel.objects.count(),
            'open_cases': CaseModel.objects.filter(status='Open').count(),
            'in_progress': CaseModel.objects.filter(status='In Progress').count(),
            'resolved_pending_close': CaseModel.objects.filter(status='Resolved', current_level='RESOLVED').count(),
            'closed_cases': CaseModel.objects.filter(status='Closed').count(),
            'escalated_to_admin': CaseModel.objects.filter(current_level='ESC5').count(),
        })
    elif agent.role == 'MANAGER':
        stats.update({
            'my_level_cases': CaseModel.objects.filter(current_level='ESC4', status__in=['Open', 'In Progress']).count(),
            'resolved_at_my_level': CaseModel.objects.filter(resolved_at_level='ESC4').count(),
        })
    elif agent.role == 'LEAD':
        stats.update({
            'my_level_cases': CaseModel.objects.filter(current_level='ESC3', status__in=['Open', 'In Progress']).count(),
            'resolved_at_my_level': CaseModel.objects.filter(resolved_at_level='ESC3').count(),
            'assigned_agents': Agent.objects.filter(role='AGENT', is_active=True).count(),
        })
    elif agent.role == 'LEGAL':
        stats.update({
            'my_level_cases': CaseModel.objects.filter(current_level='ESC2', status__in=['Open', 'In Progress']).count(),
            'resolved_at_my_level': CaseModel.objects.filter(resolved_at_level='ESC2').count(),
        })
    else:  # AGENT
        stats.update({
            'assigned_to_me': CaseModel.objects.filter(assigned_to=agent, status__in=['Open', 'In Progress']).count(),
            'resolved_by_me': CaseModel.objects.filter(resolved_by=agent.name).count(),
        })
    return JsonResponse(stats)

def get_case_by_mobile2(request):
    mobile = request.GET.get('mobile', '')
    if not mobile:
        return JsonResponse({'error': 'Mobile required'}, status=400)
    mobile = format_mobile2(mobile)
    CaseModel = get_case_model_for_app(request)
    case = CaseModel.objects.filter(mobile=mobile).order_by('-created_at').first()
    if case:
        return JsonResponse({
            'case': {
                'case_id': case.case_id,
                'customer_name': case.customer_name or mobile,
                'loan_number': case.loan_number,
                'created_by': case.created_by or 'System',
                'assigned_to_name': case.assigned_to_name or 'Unassigned',
                'current_level': case.current_level,
                'status': case.status,
                'priority': case.priority,
                'issue_description': case.issue_description or '',
                'created_at': case.created_at.isoformat(),
            }
        })
    return JsonResponse({'case': None})

@csrf_exempt
def create_case_from_chat_api2(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
        mobile = data.get('mobile', '')
        customer_name = data.get('customer_name', '')
        agent_name = data.get('agent_name', 'Agent')
        issue_description = data.get('issue_description', '')
        mobile = format_mobile2(mobile)
        if not customer_name or customer_name.strip() == "":
            customer_name = mobile
        CaseModel, ContactModel, _, _ = get_models_for_app(request)
        existing_case = CaseModel.objects.filter(mobile=mobile, status__in=['Open', 'In Progress', 'Resolved']).first()
        if existing_case:
            return JsonResponse({
                'success': True,
                'case': {
                    'case_id': existing_case.case_id,
                    'customer_name': existing_case.customer_name,
                    'created_by': existing_case.created_by,
                    'assigned_to_name': existing_case.assigned_to_name or 'Unassigned',
                    'current_level': existing_case.current_level,
                    'status': existing_case.status,
                    'priority': existing_case.priority,
                    'issue_description': existing_case.issue_description or '',
                },
                'existing': True
            })
        case_id = f"CASE-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        case = CaseModel.objects.create(
            case_id=case_id,
            customer_name=customer_name,
            mobile=mobile,
            issue_description=issue_description[:500],
            source='WhatsApp',
            current_level='ESC1',
            status='Open',
            priority='Medium',
            created_by=agent_name,
            assigned_to=None,
            assigned_to_name=None,
            loan_number=data.get('loan_number', ''),
        )
        ContactModel.objects.update_or_create(mobile=mobile, defaults={'current_level': case.current_level})
        return JsonResponse({'success': True, 'case': {'case_id': case.case_id, 'customer_name': case.customer_name, 'current_level': case.current_level, 'status': case.status}, 'existing': False})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@messaging2_required
def get_user_role_api2(request):
    try:
        agent = Agent.objects.get(user=request.user)
        role_display_names = {'AGENT': 'Normal Agent', 'LEGAL': 'Legal Team', 'LEAD': 'Team Lead', 'MANAGER': 'Manager', 'ADMIN': 'Administrator'}
        esc_levels = {'ESC1': {'icon': '1', 'color': '#4caf50', 'name': 'Level 1 - Agent'}, 'ESC2': {'icon': '2', 'color': '#2196f3', 'name': 'Level 2 - Legal'}, 'ESC3': {'icon': '3', 'color': '#ff9800', 'name': 'Level 3 - Lead'}, 'ESC4': {'icon': '4', 'color': '#9c27b0', 'name': 'Level 4 - Manager'}, 'ESC5': {'icon': '5', 'color': '#f44336', 'name': 'Level 5 - Admin'}}
        level = agent.level
        level_info = esc_levels.get(level, {'icon': '?', 'color': '#666', 'name': 'Unknown'})
        return JsonResponse({'success': True, 'role': agent.role, 'role_display': role_display_names.get(agent.role, agent.role), 'level': level, 'level_info': level_info, 'name': agent.name, 'email': agent.email})
    except Agent.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Agent profile not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)



