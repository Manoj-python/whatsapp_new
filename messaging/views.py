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
from adminpanel.views import APP_CONFIG
from .models import *
from .utils import *
from .tasks import *
from .forms import UploadForm
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

def ws_group(mobile: str) -> str:
    if not mobile:
        return ""
    return re.sub(r"\D", "", str(mobile))


def send_whatsapp_text(to_number, text_body):
    """Send text message via WhatsApp API"""
    url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
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



def broadcast_delivery(mobile, message_id, status):
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
    ChatContact.objects.filter(mobile=mobile).update(
        last_status=norm,

    )

    gm = ws_group(mobile)

    # ===== CHAT TICKS =====
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

    # ===== GLOBAL TICKS (ALL USERS) =====
    async_to_sync(channel_layer.group_send)(
        "delivery_group",
        {
            "type": "delivery.update",
            "message_id": message_id,
            "status": norm,
            "mobile": mobile
        }
    )

    # ===== 🔥 CONTACT UPDATE =====
    async_to_sync(channel_layer.group_send)(
        "global_contacts",
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
# Helper: ws_group
# -------------------


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
    return redirect("admin_login")


def messaging_required(view_func):
    def wrapper(request, *args, **kwargs):
        # First check Django auth
        if request.user.is_authenticated:
            return view_func(request, *args, **kwargs)
        # Then check custom session key (legacy)
        if request.session.get("messaging_user"):
            return view_func(request, *args, **kwargs)
        return redirect(settings.LOGIN_URL)
    return wrapper

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

            # Read Excel from S3 into pandas
            with default_storage.open(s3_key, "rb") as f:
                data = f.read()

            df = pd.read_excel(io.BytesIO(data), dtype=str).fillna("")
            job_id = str(uuid.uuid4())

            # Create Bulk Job
            BulkJob.objects.create(
                job_id=job_id,
                template_name=choice,
                total_customers=len(df),
                excel_file=s3_key,
                status="Pending",
            )

            # 🔥 FORCE TASK INTO WHATSAPP2_main QUEUE
            process_bulk_whatsapp.apply_async(
                args=(s3_key, choice, job_id),
                queue="messaging"
            )

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

from adminpanel.views import get_agent_from_user
# -----------------------------------------------------
# CHAT DASHBOARD
# -----------------------------------------------------
from django.contrib.auth.decorators import login_required
@messaging_required
def chat_dashboard(request):
    agent = get_agent_from_user(request.user)
    mobiles = (SmsWhatsAppLog.objects.values("mobile").annotate(last_sent=Max("sent_at")).order_by("-last_sent"))
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
        "agent": agent,
        "user": request.user,
    })


# -----------------------------------------------------
# Get Messages for Mobile (returns public S3 URLs)
# -----------------------------------------------------
# in messagingviews.py (chat2_messages_api)
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



# messagingviews.py - COMPLETE FIXED VERSION

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



def download_whatsapp_media(media_id):
    """Download media from WhatsApp"""
    try:
        access_token = settings.WHATSAPP_ACCESS_TOKEN
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

        filename = f"WHATSAPP_{media_id}.{ext}"
        return filename, file_resp.content

    except Exception as e:
        # print(f"Media download error: {e}")
        return None



# =============================================
# CHAT DASHBOARD & MESSAGES API
# =============================================



def contacts_api(request):
    q = request.GET.get("q", "").strip()
    qs = (
        SmsWhatsAppLog.objects.values("mobile")
        .annotate(last_time=Max("sent_at"),
                  unread=Count("id", filter=Q(message_type="Received", status="Unread")))
        .order_by("-last_time")
    )

    if q:
        digits = re.sub(r"\D", "", q)
        if digits:
            qs = qs.filter(mobile__icontains=digits)
        else:
            mobiles_matching = SmsWhatsAppLog.objects.filter(sent_text_message__icontains=q).values_list("mobile", flat=True).distinct()
            qs = qs.filter(mobile__in=list(mobiles_matching))

    result = [{
        "mobile": format_mobile(item["mobile"]),
        "last_time": item["last_time"].isoformat() if item["last_time"] else "",
        "unread": item["unread"],
    } for item in qs]
    return JsonResponse({"contacts": result})


@csrf_exempt
def mark_read(request, mobile):
    try:
        mobile_norm = format_mobile(mobile)
        ChatContact.objects.filter(mobile=mobile_norm).update(unread=0)
        channel_layer = get_channel_layer()
        gm = ws_group(mobile_norm)
        if gm:
            async_to_sync(channel_layer.group_send)(
                f"chat_{gm}",
                {
                    "type": "delivery.update",
                    "message_id": "",
                    "status": "Read",
                    "mobile": mobile_norm,
                }
            )
        async_to_sync(channel_layer.group_send)(
            "global_contacts",
            {"type": "presence.update", "mobile": mobile_norm, "status": "updated"}
        )
        return JsonResponse({"status": "ok"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# =============================================
# SEND REPLY API - FIXED (NO RACE CONDITION)
# =============================================
# messagingviews.py - COMPLETE WORKING VERSION


@csrf_exempt
def send_reply_api(request):
    """
    Send reply with media support - FIXED VOICE MESSAGES
    """
    try:
        if request.method != "POST":
            return HttpResponseBadRequest("POST required")

        # Parse request
        if "multipart/form-data" in request.META.get("CONTENT_TYPE", ""):
            mobile = request.POST.get("mobile", "").strip()
            text = request.POST.get("text", "").strip()
            is_voice = request.POST.get("is_voice", "false") == "true"
            media_file = request.FILES.get("media")
        else:
            payload = json.loads(request.body.decode("utf-8") or "{}")
            mobile = payload.get("mobile", "").strip()
            text = payload.get("text", "").strip()
            is_voice = payload.get("is_voice", False)
            media_file = None

        if not mobile:
            return HttpResponseBadRequest("mobile required")

        mobile = format_mobile(mobile)

        # File size validation
        if media_file:
            file_size_mb = media_file.size / (1024 * 1024)
            file_name = media_file.name.lower()

            # Voice messages max 16MB
            if file_name.endswith(('.mp3', '.wav', '.ogg', '.m4a', '.webm', '.mpeg', '.mpga', '.aac')):
                max_size = 16
            elif file_name.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
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
        if request.session.get("messaging_user"):
            from django.contrib.auth.models import User
            u = User.objects.filter(id=request.session["messaging_user"]).first()
            if u:
                agent_name = u.username

        # =============================================
        # STEP 1: CREATE DATABASE RECORD FIRST
        # =============================================
        temp_id = str(uuid.uuid4())

        log = SmsWhatsAppLog.objects.create(
            customer_name=agent_name or "",
            mobile=mobile,
            sent_text_message=text or "",
            status="Sending",
            message_id=temp_id,
            message_type="Sent",
            content_type="audio" if is_voice or (media_file and media_file.name.lower().endswith(('.mp3','.mpeg', '.wav', '.ogg', '.m4a', '.webm'))) else "text",
        )
        clear_chat_cache(mobile)

        # =============================================
        # STEP 2: SEND TO WHATSAPP
        # =============================================
        msg_id = ""
        content_type_val = "audio" if is_voice or (media_file and media_file.name.lower().endswith(('.mp3', '.mpeg','.wav', '.ogg', '.m4a', '.webm'))) else "text"
        media_url = ""
        saved_path = None

        try:
            if media_file:
                file_name = media_file.name.lower()
                original_filename = media_file.name
                
                # Determine media type
                if file_name.endswith(('.mp3', '.wav', '.ogg', '.m4a', '.webm','.mpeg')):
                    whatsapp_media_type = "audio"
                    content_type_val = "audio"
                elif file_name.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                    whatsapp_media_type = "image"
                    content_type_val = "image"
                elif file_name.endswith(('.mp4', '.mov', '.avi', '.mkv')):
                    whatsapp_media_type = "video"
                    content_type_val = "video"
                else:
                    whatsapp_media_type = "document"
                    content_type_val = "document"

                # Update content type in database
                SmsWhatsAppLog.objects.filter(id=log.id).update(content_type=content_type_val)

                # Upload to WhatsApp (this will handle WebM -> OGG conversion)
                upload_resp = upload_whatsapp_media(media_file)
                media_id = upload_resp.get("id")

                if media_id:
                    # For audio, we MUST send as audio type - captions are NOT allowed
                    if whatsapp_media_type == "audio":
                        send_resp = send_whatsapp_media(
                            to_number=mobile,
                            media_id=media_id,
                            media_type="audio",
                            caption="",  # IMPORTANT: audio messages CANNOT have captions
                            filename=original_filename
                        )
                    else:
                        send_resp = send_whatsapp_media(
                            to_number=mobile,
                            media_id=media_id,
                            media_type=whatsapp_media_type,
                            caption=text if text else "",
                            filename=original_filename
                        )
                    
                    msg_id = send_resp.get("messages", [{}])[0].get("id", "")

                    # Save media file to storage
                    media_file.seek(0)
                    saved_path = default_storage.save(
                        f"chat_media/{media_file.name}",
                        ContentFile(media_file.read())
                    )
                    media_url = default_storage.url(saved_path)

            elif text:
                send_resp = send_whatsapp_text(mobile, text)
                msg_id = send_resp.get("messages", [{}])[0].get("id", "")

            # =============================================
            # STEP 3: UPDATE RECORD WITH REAL WHATSAPP ID
            # =============================================
            if msg_id:
                update_data = {
                    'message_id': msg_id,
                    'status': 'Sent'
                }
                if saved_path:
                    update_data['media_file'] = saved_path

                SmsWhatsAppLog.objects.filter(id=log.id).update(**update_data)
                log.refresh_from_db()
            else:
                SmsWhatsAppLog.objects.filter(id=log.id).update(
                    status="Failed",
                    error_message="No message ID returned from WhatsApp"
                )

        except Exception as e:
            SmsWhatsAppLog.objects.filter(id=log.id).update(
                status="Failed",
                error_message=str(e)
            )
            return JsonResponse({"error": f"Send failed: {str(e)}"}, status=500)

        # Update contact
        ChatContact.objects.update_or_create(
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
            "global_contacts",
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
                f"chat_{gm}",
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
                        "message_id": log.message_id,
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
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)








from adminpanel.views import APP_CONFIG
def get_app_models(app_key):
    """Return (log_model, contact_model, channel_group, chat_prefix) for the given app."""
    cfg = APP_CONFIG.get(app_key)
    if not cfg:
        raise ValueError(f"Invalid app_key: {app_key}")
    return (
        cfg['log_model'],
        cfg['contact_model'],
        cfg['channel_group'],
        cfg['chat_prefix']
    )

PTP_CONFIRM_KEYWORDS = ["confirm", "నిర్ధారించు"]
PTP_RESCHEDULE_KEYWORDS = ["reschedule", "రీషెడ్యూల్"]
from messaging2.views import ws_group2
def broadcast_ptp_response(app_key, mobile, status, customer_name):
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    cfg = APP_CONFIG.get(app_key)
    if not cfg:
        return
    chat_prefix = cfg['chat_prefix']
    if app_key == 'sms':
        gm = ws_group(mobile)
    else:
        gm = ws_group2(mobile)
    if not gm:
        return
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"{chat_prefix}_{gm}",
        {"type": "new_message", "message": {
            "id": None,
            "mobile": mobile,
            "sent_text_message": f"[PTP {status}]",
            "content_type": "interactive",
            "media_file": "",
            "sent_at": timezone.localtime(timezone.now()).isoformat(),
            "message_type": "Received",
            "message_id": "ptp_response",
            "status": "Read",
            "sender_name": customer_name,
            "ptp_status": status
        }}
    )
    # optional global broadcast
    async_to_sync(channel_layer.group_send)(
        "ptp_updates",
        {"type": "ptp.response", "mobile": mobile, "status": status, "customer_name": customer_name}
    )

@csrf_exempt
def get_ptp_details_view(request):
    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': 'GET required'}, status=405)

    app_key = request.GET.get('app')
    mobile = request.GET.get('mobile')
    if not app_key or not mobile:
        return JsonResponse({'success': False, 'error': 'app and mobile required'}, status=200)

    # 🔥 Clean mobile: remove all non‑digits, and strip leading '91' if present
    import re
    mobile_clean = re.sub(r'\D', '', mobile)
    if mobile_clean.startswith('91') and len(mobile_clean) > 10:
        mobile_clean = mobile_clean[2:]          # remove country code
    if len(mobile_clean) != 10:
        # fallback: try last 10 digits
        mobile_clean = mobile_clean[-10:]

    try:
        data = get_details(app_key, mobile_clean)   # now clean
        data['total_due'] = round(data['due_amount'] + data['lpi_due'] + data['vas_due'] + data['collection_charges'], 2)
        return JsonResponse({'success': True, **data})
    except Exception as e:
        logger.error(f"PTP details error: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=200)

@csrf_exempt
def send_ptp_template_view(request):
    """
    POST /messaging2/api/send-ptp-template/?app=sms
    Body: { mobile, customer_name, amount, due_date, loan_number, lang }
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    app_key = request.GET.get('app')
    if not app_key:
        return JsonResponse({'success': False, 'error': 'app parameter required'}, status=200)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    mobile = data.get('mobile')
    customer_name = data.get('customer_name')
    amount = data.get('amount')
    due_date = data.get('due_date')
    loan_number = data.get('loan_number')
    lang = data.get('lang', 'en')
    agent = get_agent_from_user(request.user)
    sender_name = agent.name

    # Validation
    if not mobile:
        return JsonResponse({'success': False, 'error': 'Mobile required'}, status=200)
    if not amount or float(amount) <= 0:
        return JsonResponse({'success': False, 'error': 'Valid amount required'}, status=200)
    if not due_date:
        return JsonResponse({'success': False, 'error': 'Due date required'}, status=200)
    if not loan_number:
        return JsonResponse({'success': False, 'error': 'Loan number required'}, status=200)

    # Send the template
    try:
        # Ensure mobile is formatted for WhatsApp (with country code, digits only)
        mobile_digits = ''.join(filter(str.isdigit, mobile))
        if len(mobile_digits) > 10:
            mobile_digits = mobile_digits[-10:]
        # Add '91' if not present (adjust as per your app)
        if not mobile_digits.startswith('91') and len(mobile_digits) == 10:
            mobile_digits = '91' + mobile_digits

        result = send_whatsapp_ptp_template(
            app_key=app_key,
            to=mobile_digits,
            customer_name=customer_name or 'Customer',
            amount=amount,
            due_date=due_date,
            loan_number=loan_number,
            lang=lang
        )

        # ========== Log the message ==========
        cfg = APP_CONFIG[app_key]
        LogModel = cfg['log_model']
        ContactModel = cfg['contact_model']
        chat_prefix = cfg['chat_prefix']
        app_name = cfg.get('app_name', '')
        final_sender_name = sender_name if sender_name else app_name


        # Construct a readable log message
        log_text = f"PTP template sent: {customer_name}, ₹{amount} by {due_date} against {loan_number} [{lang.upper()}]"

        msg_id = result.get('messages', [{}])[0].get('id', '')

        log_entry = LogModel.objects.create(
            customer_name=final_sender_name,
            mobile=mobile,   # store original number (with +)
            sent_text_message=log_text,
            message_type="Sent",
            content_type="template",
            status="Sent",
            template_name=f"ptp_confirm_{lang}",
            message_id=msg_id,
             
        )

        # Update contact
        ContactModel.objects.update_or_create(
            mobile=mobile,
            defaults={
                'last_msg': log_text[:50] + "...",
                'last_time': timezone.now(),
                'last_type': "Sent",
                'last_status': "Sent",
                'unread': 0,
            }
        )

        # ========== WebSocket broadcast ==========
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        # Pick the correct group function
        if app_key == 'psf':
            gm = ws_group2(mobile)
        else:
            gm = ws_group(mobile)

        if gm:
            async_to_sync(channel_layer.group_send)(
                f"{chat_prefix}_{gm}",
                {
                    "type": "new_message",
                    "message": {
                        "id": log_entry.id,
                        "mobile": mobile,
                        "sent_text_message": log_text,
                        "content_type": "template",
                        "media_file": "",
                        "sent_at": timezone.localtime(log_entry.sent_at).isoformat(),
                        "message_type": "Sent",
                        "message_id": log_entry.message_id,
                        "status": "Sent",
                        "sender_name": final_sender_name
                    }
                }
            )

        return JsonResponse({'success': True, 'result': result})

    except Exception as e:
        logger.error(f"PTP send error for {app_key}: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


from messaging2.tasks import send_welcome_message
# =============================================
# WHATSAPP WEBHOOK - COMPLETE WORKING VERSION WITH QUICK REPLY BUTTON HANDLING
# =============================================
from messaging2.tasks import send_welcome_message,clear_button_clicked,was_button_clicked_recently,mark_button_clicked
# =============================================
# WHATSAPP WEBHOOK - COMPLETE WORKING VERSION WITH QUICK REPLY BUTTON HANDLING
# =============================================
@csrf_exempt
def whatsapp_webhook(request):
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
                    # PROCESS INCOMING MESSAGES
                    # ======================================
                    for msg in value.get("messages", []):
                        msg_id = msg.get("id")
                        mobile = format_mobile(msg.get("from", ""))

                        if msg_id and SmsWhatsAppLog.objects.filter(message_id=msg_id).exists():
                            continue

                        msg_type = msg.get("type", "text")
                        text_body = ""
                        content_type = "text"
                        media_file_data = None
                        button_response = ""

                        # ======================================
                        # DEBUG - SEE EXACT META PAYLOAD
                        # ======================================
                        # print("=" * 80)
                        # print("RAW WHATSAPP MESSAGE")
                        # print(json.dumps(msg, indent=2))
                        # print("=" * 80)

                        # ======================================
                        # TEXT MESSAGES
                        # ======================================
                        if msg_type == "text":

                            text_body = msg.get("text", {}).get("body", "").strip()
                            text_lower = text_body.lower().strip()
                            print(f"📝 Raw text from {mobile}: '{text_body}'")
                            if any(kw in text_lower for kw in PTP_CONFIRM_KEYWORDS):
                                content_type = "interactive"
                                button_response = json.dumps({
                                    "type": "ptp_quick_reply",
                                    "button_title": text_body,
                                    "action": "CONFIRM",
                                    "source": "ptp_template",
                                    "timestamp": timezone.now().isoformat()
                                })
                                text_body = f"[PTP Confirm] {text_body}"
                                mark_button_clicked(mobile)
                                broadcast_ptp_response('sms', mobile, "CONFIRMED", customer_name)
                                print(f"✅ PTP Confirmed by {mobile}")

                            elif any(kw in text_lower for kw in PTP_RESCHEDULE_KEYWORDS):
                                content_type = "interactive"
                                button_response = json.dumps({
                                    "type": "ptp_quick_reply",
                                    "button_title": text_body,
                                    "action": "RESCHEDULE",
                                    "source": "ptp_template",
                                    "timestamp": timezone.now().isoformat()
                                })
                                text_body = f"[PTP Reschedule] {text_body}"
                                mark_button_clicked(mobile)
                                broadcast_ptp_response('sms', mobile, "RESCHEDULED", customer_name)
                                print(f"🔄 PTP Rescheduled by {mobile}")


                            elif text_body in ["Interested", "Not Interested", "Call Now"]:

                                content_type = "interactive"

                                context_id = None
                                if msg.get("context"):
                                    context_id = msg.get("context", {}).get("id")

                                button_response = json.dumps({
                                    "type": "quick_reply_text",
                                    "button_title": text_body,
                                    "button_text": text_body,
                                    "context_message_id": context_id,
                                    "source": "text_quick_reply",
                                    "timestamp": timezone.now().isoformat()
                                })

                                text_body = f"[Button Click] {text_body}"
                                mark_button_clicked(mobile)

                                print(f"🔘 Quick Reply captured via TEXT: {text_body}")

                            else:
                                print(f"📝 Regular text from {mobile}: {text_body}")


                        # ======================================
                        # TEMPLATE QUICK REPLY BUTTONS
                        # ======================================
                        elif msg_type == "button":

                            button = msg.get("button", {})

                            button_text = button.get("text", "")
                            button_payload = button.get("payload", "")

                            content_type = "button"

                            button_response = json.dumps({
                                "type": "template_quick_reply",
                                "button_text": button_text,
                                "button_payload": button_payload,
                                "source": "button",
                                "timestamp": timezone.now().isoformat()
                            })

                            text_body = f"[Button Click] {button_text}"
                            mark_button_clicked(mobile)

                            print(
                                f"🔘 Template Button Clicked: "
                                f"text={button_text}, payload={button_payload}"
                            )


                        # ======================================
                        # INTERACTIVE MESSAGES
                        # ======================================
                        elif msg_type == "interactive":

                            interactive = msg.get("interactive", {})
                            content_type = "interactive"

                            interactive_type = interactive.get("type")

                            print(
                                f"🎯 Interactive message from "
                                f"{mobile}: {interactive_type}"
                            )

                            # BUTTON REPLY
                            if interactive_type == "button_reply":

                                button_reply = interactive.get("button_reply", {})

                                button_id = button_reply.get("id", "")
                                button_title = button_reply.get("title", "")

                                button_response = json.dumps({
                                    "type": "button_click",
                                    "button_id": button_id,
                                    "button_title": button_title,
                                    "source": "interactive_button_reply",
                                    "timestamp": timezone.now().isoformat()
                                })

                                text_body = f"[Button Click] {button_title}"
                                mark_button_clicked(mobile)

                                print(
                                    f"🔘 Button Reply: "
                                    f"id={button_id}, title={button_title}"
                                )

                            # LIST REPLY
                            elif interactive_type == "list_reply":

                                list_reply = interactive.get("list_reply", {})

                                list_id = list_reply.get("id", "")
                                list_title = list_reply.get("title", "")

                                button_response = json.dumps({
                                    "type": "list_selection",
                                    "list_id": list_id,
                                    "list_title": list_title,
                                    "source": "interactive_list",
                                    "timestamp": timezone.now().isoformat()
                                })

                                text_body = f"[List Selection] {list_title}"
                                mark_button_clicked(mobile)


                                print(
                                    f"📋 List selected: "
                                    f"id={list_id}, title={list_title}"
                                )

                            # CTA URL
                            elif interactive_type == "cta_url":

                                cta = interactive.get("cta_url", {})

                                button_title = cta.get("title", "")

                                button_response = json.dumps({
                                    "type": "cta_click",
                                    "button_title": button_title,
                                    "source": "interactive_cta",
                                    "timestamp": timezone.now().isoformat()
                                })

                                text_body = f"[CTA Click] {button_title}"

                                print(f"🔗 CTA clicked: {button_title}")

                            # FALLBACK
                            else:

                                text_body = f"[Interactive] {interactive_type}"
                                mark_button_clicked(mobile)

                                button_response = json.dumps({
                                    "type": "unknown_interactive",
                                    "interactive_type": interactive_type,
                                    "raw_data": interactive,
                                    "timestamp": timezone.now().isoformat()
                                })

                                print(
                                    f"⚠️ Unknown interactive type: "
                                    f"{interactive_type}"
                                )
                        # ======================================
                        # MEDIA MESSAGES
                        # ======================================
                        elif msg_type in ("image", "video", "audio", "document"):
                            media_id = msg[msg_type].get("id")
                            content_type = msg_type
                            text_body = f"[{msg_type.title()}]"
                            media_file_data = download_whatsapp_media(media_id)
                            print(f"📎 Media message: {msg_type} from {mobile}")

                        # ======================================
                        # UNSUPPORTED MESSAGES
                        # ======================================
                        elif msg_type == "unsupported":
                            error = msg.get("errors", [{}])[0].get("message", "Unknown")
                            print(f"⚠️ Unsupported message from {mobile}: {error}")
                            continue

                        # ======================================
                        # GET CUSTOMER NAME
                        # ======================================
                        customer_name = ""
                        contacts_data = value.get("contacts", [])
                        if contacts_data:
                            customer_name = contacts_data[0].get("profile", {}).get("name", "")
                            print(f"📛 Customer name: {customer_name}")
                        last_incoming = SmsWhatsAppLog.objects.filter(mobile=mobile,message_type='Received').order_by('-sent_at').first()
                        send_welcome = False
                        if not last_incoming:
                            send_welcome = True
                        elif (timezone.now() - last_incoming.sent_at).total_seconds() > 21600:  # 1 hour
                            send_welcome = True

                        # ======================================
                        # SAVE MESSAGE TO DATABASE
                        # ======================================
                        with transaction.atomic():
                            log = SmsWhatsAppLog.objects.create(
                                customer_name=customer_name,
                                mobile=mobile,
                                template_name="incoming",
                                sent_text_message=text_body if text_body else "[Empty Message]",
                                status="Unread",
                                message_type="Received",
                                message_id=msg_id,
                                content_type=content_type,
                                button_response=button_response,
                            )
                            clear_chat_cache(mobile)

                            if media_file_data:
                                filename, content = media_file_data
                                log.media_file.save(filename, ContentFile(content))
                                log.save()

                        print(f"💾 Saved message {log.id} from {mobile}: {text_body[:50] if text_body else 'Empty'}")
                        # ======================================
                        # AUTO LEAD CREATION FROM INTERESTED BUTTON
                        # ======================================
                        try:
                            interested_clicked = False

                            if "[Button Click] Interested" in text_body:
                                interested_clicked = True

                            if interested_clicked:
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
                                                "media_file": "",
                                                "sent_at": timezone.localtime(log.sent_at).isoformat(),
                                                "message_type": "Received",
                                                "message_id": log.message_id,
                                                "status": log.status,
                                                "sender_name": customer_name
                                            }
                                        }
                                    )

                                message = (
                                    "ధన్యవాదాలు! 🙏\n\n"
                                    "మీ ఆసక్తిని నమోదు చేసుకున్నాము.\n\n"
                                    "మా Sales టీమ్ త్వరలో మిమ్మల్ని సంప్రదిస్తుంది.\n\n"
                                    "📞 8333000111\n\n"
                                    "SMSquare"
                                )

                                # ----------------------------------
                                # SEND WHATSAPP AUTO REPLY
                                # ----------------------------------
                                resp = send_whatsapp_text(mobile, message)

                                msg_id = ""
                                try:
                                    if isinstance(resp, dict):
                                        msg_id = resp.get("messages", [{}])[0].get("id", "")
                                except Exception:
                                    pass

                                if not msg_id:
                                    msg_id = f"AUTO-{uuid.uuid4().hex[:12]}"

                                # ----------------------------------
                                # SAVE AUTO REPLY TO CHAT HISTORY
                                # ----------------------------------
                                auto_log = SmsWhatsAppLog.objects.create(
                                    customer_name="SMSquare",
                                    mobile=mobile,
                                    template_name="auto_reply",
                                    sent_text_message=message,
                                    status="Sent",
                                    message_type="Sent",
                                    message_id=msg_id,
                                    content_type="text",
                                )

                                clear_chat_cache(mobile)

                                # ----------------------------------
                                # UPDATE CONTACT
                                # ----------------------------------
                                ChatContact.objects.filter(mobile=mobile).update(
                                    last_time=timezone.now(),
                                    last_msg=message,
                                    last_type="Sent",
                                    last_status="Sent"
                                )

                                # ----------------------------------
                                # WEBSOCKET UPDATE CHAT WINDOW
                                # ----------------------------------
                                gm = ws_group(mobile)

                                if gm:
                                    async_to_sync(channel_layer.group_send)(
                                        f"chat_{gm}",
                                        {
                                            "type": "new_message",
                                            "message": {
                                                "id": auto_log.id,
                                                "mobile": mobile,
                                                "sent_text_message": message,
                                                "content_type": "text",
                                                "media_file": "",
                                                "sent_at": timezone.localtime(
                                                    auto_log.sent_at
                                                ).isoformat(),
                                                "message_type": "Sent",
                                                "message_id": msg_id,
                                                "status": "Sent",
                                                "sender_name": "SMSquare"
                                            }
                                        }
                                    )

                                # ----------------------------------
                                # CREATE SALES CASE
                                # ----------------------------------
                                from adminpanel.models import SupportGroup
                                from financehub.models import Lcc
                                from django.core.cache import cache

                                cache_key = "sales_team_mapping_psf"
                                mapping = cache.get(cache_key)
                                if mapping is None:
                                    sales_group = SupportGroup.objects.get(name="Sales")
                                    zone1_subgroup = Subgroup.objects.get(
                                            name="Zone 1 - AP / KA - Sundeep",
                                            group=sales_group
                                        )
                                    zone2_subgroup = Subgroup.objects.get(
                                            name="Zone 2 - TS - Venkat",
                                            group=sales_group
                                        )
                                    marketing_category = Category.objects.get(
                                            name="Marketing Leads",
                                            group=sales_group
                                        )
                                    mapping = {
                                            'sales_group': sales_group,
                                            'zone1_subgroup': zone1_subgroup,
                                            'zone2_subgroup': zone2_subgroup,
                                            'marketing_category': marketing_category,
                                        }
                                    cache.set(cache_key, mapping, 3600)  # 1 hour
                                sales_group = mapping['sales_group']
                                zone1_subgroup = mapping['zone1_subgroup']
                                zone2_subgroup = mapping['zone2_subgroup']
                                marketing_category = mapping['marketing_category']
                                lcc_record = Lcc.objects.filter(cust_mobile=mobile).only('loan_number').first()
                                loan_number = lcc_record.loan_number if lcc_record else ""
                                # ---- Determine subgroup ----
                                if "AP" in loan_number.upper():
                                    subgroup = zone1_subgroup
                                else:
                                    subgroup = zone2_subgroup 

                                existing_case = Case.objects.filter(
                                    mobile=mobile,
                                    group=sales_group
                                ).exclude(
                                    status__in=["Closed"]
                                ).only('id').first()

                                if not existing_case:

                                    sales_group = SupportGroup.objects.get(name="Sales")

                                    case=Case.objects.create(
                                        case_id=f"LEAD-{uuid.uuid4().hex[:8].upper()}",
                                        customer_name=customer_name,
                                        mobile=mobile,
                                        issue_description="Customer clicked Interested on WhatsApp Loan Campaign",
                                        group=sales_group,
                                        subgroup=subgroup,
                                        category=marketing_category,
                                        current_level="ESC2",
                                        status="Open",
                                        priority="Medium",
                                        source="WhatsApp Marketing Campaign",
                                        created_by="System Auto Lead"
                                    )
                                    case._skip_ticket_open = True
                                    case.save(update_fields=['_skip_ticket_open'])
                                    print(f"✅ Sales Lead Created: {mobile}")

                        except Exception as e:
                            print("Lead creation error:", str(e))
                        # ======================================
                        # UPDATE CONTACT
                        # ======================================
                        obj, created = ChatContact.objects.get_or_create(
                            mobile=mobile,
                            defaults={
                                "last_time": timezone.now(),
                                "last_msg": text_body if text_body else "[Button Click]",
                                "last_type": "Received",
                                "last_status": "Unread",
                                "unread": 1,
                            }
                        )
                        if not created:
                            ChatContact.objects.filter(mobile=mobile).update(
                                last_time=timezone.now(),
                                last_msg=text_body if text_body else "[Button Click]",
                                last_type="Received",
                                last_status="Unread",
                                unread=F("unread") + 1
                            )
                        if send_welcome:
                            print(f"🔍 TASK: mobile={mobile}, flag={was_button_clicked_recently(mobile)}")

                            if was_button_clicked_recently(mobile):
                                clear_button_clicked(mobile)
                            else:
                                send_welcome_message.delay('sms', mobile, customer_name)

                        # ======================================
                        # WEBSOCKET BROADCAST - CHAT GROUP
                        # ======================================
                        gm = ws_group(mobile)
                        if gm and not interested_clicked:
                            ws_message = {
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

                            if button_response:
                                try:
                                    btn_data = json.loads(button_response)
                                    ws_message["button_title"] = btn_data.get("button_title") or btn_data.get("list_title")
                                    ws_message["interaction_type"] = btn_data.get("type")
                                except:
                                    pass

                            async_to_sync(channel_layer.group_send)(
                                f"chat_{gm}",
                                {"type": "new_message", "message": ws_message}
                            )

                        # ======================================
                        # WEBSOCKET BROADCAST - GLOBAL CONTACTS
                        # ======================================
                        async_to_sync(channel_layer.group_send)(
                            "global_contacts",
                            {
                                "type": "contact.update",
                                "contact": {
                                    "mobile": mobile,
                                    "last_msg": text_body if text_body else "[Button Click]",
                                    "last_type": "Received",
                                    "last_status": "Unread",
                                    "unread": obj.unread if created else obj.unread + 1,
                                }
                            }
                        )

                        if button_response:
                            print(f"✅ Button response saved for {mobile}")

                    # ======================================
                    # PROCESS STATUS UPDATES
                    # ======================================
                    for status in value.get("statuses", []):
                        msg_id = status.get("id")
                        status_type = (status.get("status") or "").lower()

                        if not msg_id:
                            continue

                        obj = SmsWhatsAppLog.objects.filter(message_id=msg_id).first()
                        if not obj and len(msg_id) > 30:
                            partial = msg_id[:30]
                            obj = SmsWhatsAppLog.objects.filter(message_id__startswith=partial).first()
                            if obj:
                                SmsWhatsAppLog.objects.filter(id=obj.id).update(message_id=msg_id)
                                obj.refresh_from_db()

                        if not obj:
                            continue

                        mobile = obj.mobile
                        errors = status.get("errors", [])

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
                                code = int(err.get("code", 0))

                                error_map = {
                                    131047: "24H_WINDOW_EXPIRED", 131026: "NOT_ON_WHATSAPP",
                                    131051: "UNSUPPORTED_MESSAGE_TYPE", 131011: "BLOCKED_BY_USER",
                                    130403: "BLOCKED_BY_BUSINESS", 131050: "OPTED_OUT",
                                    190: "TOKEN_ERROR", 131009: "INVALID_PARAMETER",
                                    131000: "UNKNOWN_ERROR", 131045: "REGISTRATION_ERROR",
                                    132000: "TEMPLATE_PARAM_ERROR", 132001: "TEMPLATE_NOT_FOUND",
                                    132015: "TEMPLATE_PAUSED", 132016: "TEMPLATE_DISABLED",
                                    130429: "RATE_LIMIT", 131056: "TOO_MANY_MESSAGES",
                                }
                                norm = error_map.get(code, f"Failed_{code}")
                        else:
                            continue

                        SmsWhatsAppLog.objects.filter(message_id=msg_id).update(
                            status=norm, error_message=json.dumps(errors) if errors else ""
                        )
                        ChatContact.objects.filter(mobile=mobile).update(last_status=norm)

                        gm = ws_group(mobile)
                        if gm:
                            async_to_sync(channel_layer.group_send)(
                                f"chat_{gm}",
                                {"type": "delivery.update", "message_id": msg_id, "status": norm, "mobile": mobile}
                            )

                        async_to_sync(channel_layer.group_send)(
                            "global_contacts",
                            {"type": "contact.update", "contact": {"mobile": mobile, "last_status": norm}}
                        )

                        total_unread = ChatContact.objects.filter(unread__gt=0).count()
                        async_to_sync(channel_layer.group_send)(
                            "global_contacts", {"type": "unread.update", "unread_count": total_unread}
                        )

                        print(f"✅ Updated {msg_id} to {norm}")

            return JsonResponse({"status": "received"})

        except Exception as e:
            print(f"❌ WEBHOOK ERROR: {e}")
            traceback.print_exc()
            return JsonResponse({"error": str(e)}, status=400)

    return HttpResponseBadRequest("Unsupported method")








from django.http import JsonResponse
from .models import SmsWhatsAppLog

def get_contact_messages(request):
    mobile = request.GET.get('mobile')
    if not mobile:
        return JsonResponse({'error': 'Mobile required'}, status=400)

    messages = SmsWhatsAppLog.objects.filter(mobile=mobile).order_by('sent_at')

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

def view_secure_document(request, log_id):
    """
    View secure NOC documents - only accessible to logged-in users
    """
    log = get_object_or_404(SmsWhatsAppLog, id=log_id)

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


@csrf_exempt
def fetch_padmasai_details(request):
    mobile = request.GET.get('mobile')
    if not mobile:
        return JsonResponse({'success': False, 'error': 'Mobile number required'})

    # Optional cache
    cache_key = f'lcc_{mobile.lstrip("+")}'
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse({'success': True, **cached})

    result = lcc_details(mobile)
    if result:
        cache.set(cache_key, result, 300)
        return JsonResponse({'success': True, **result})
    else:
        return JsonResponse({'success': False, 'error': 'No details found'})
