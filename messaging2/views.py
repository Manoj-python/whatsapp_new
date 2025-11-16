import os
import json
import uuid
import requests
import pandas as pd
from io import BytesIO
from django.shortcuts import render, redirect, get_object_or_404
from django.core.files.storage import FileSystemStorage
from django.http import (
    JsonResponse,
    HttpResponse,
    HttpResponseBadRequest,
)
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.db.models import Max
from django.core.files.base import ContentFile

from .forms import UploadForm
from .models import SmsWhatsAppLog2, BulkJob2
from .tasks import process_bulk_whatsapp2
from .utils import format_mobile2


# ------------------------
# Send Text Message
# ------------------------
def send_whatsapp2_text(to_number, text_body):
    access_token = settings.WHATSAPP2_ACCESS_TOKEN
    phone_number_id = settings.WHATSAPP2_PHONE_NUMBER_ID
    if not access_token or not phone_number_id:
        raise RuntimeError("Missing WhatsApp2 access token or phone number ID")

    url = f"https://graph.facebook.com/v22.0/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to_number, "type": "text", "text": {"body": text_body}}
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()

def send_whatsapp2_media(to_number, file_obj, media_type):
    import requests
    from django.conf import settings

    access_token = settings.WHATSAPP2_ACCESS_TOKEN
    phone_number_id = settings.WHATSAPP2_PHONE_NUMBER_ID

    if not access_token or not phone_number_id:
        raise RuntimeError("Missing WhatsApp2 access token or phone number ID")

    # Upload Media
    upload_url = f'https://graph.facebook.com/v22.0/{phone_number_id}/media'
    headers = {'Authorization': f'Bearer {access_token}'}
    files = {'file': (file_obj.name, file_obj, file_obj.content_type)}
    data = {'messaging_product': 'whatsapp', 'type': media_type}

    resp = requests.post(upload_url, headers=headers, files=files, data=data)
    resp.raise_for_status()
    media_id = resp.json().get('id')

    # Send Media Message
    url = f'https://graph.facebook.com/v22.0/{phone_number_id}/messages'
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": media_type,
        media_type: {"id": media_id}
    }
    resp2 = requests.post(url, headers=headers, json=payload)
    resp2.raise_for_status()
    return resp2.json()

# Upload Excel + Trigger Bulk Sending
# ------------------------
def upload_and_send2(request):
    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            choice = form.cleaned_data["template_choice"]
            excel_file = request.FILES["excel_file"]

            fs = FileSystemStorage(location="uploads2/")
            filename = fs.save(excel_file.name, excel_file)
            file_path = fs.path(filename)

            df = pd.read_excel(file_path, dtype=str).fillna("")
            total_customers = len(df)

            job_id = str(uuid.uuid4())
            job = BulkJob2.objects.create(
                job_id=job_id,
                template_name=choice,
                total_customers=total_customers,
                excel_file=f"uploads2/{filename}",
                status="Pending",
            )

            process_bulk_whatsapp2.delay(file_path, choice, job_id)
            return redirect("job_status2", job_id=job_id)
    else:
        form = UploadForm()
    return render(request, "messaging2/index.html", {"form": form})

# ------------------------
# Job Status
# ------------------------
def job_status2(request, job_id):
    job = get_object_or_404(BulkJob2, job_id=job_id)
    progress = 0
    if job.total_customers > 0:
        progress = round((job.sent_count / job.total_customers) * 100, 2)
    return render(request, "messaging2/job_status.html", {"job": job, "progress": progress})

## ------------------------
# Chat Dashboard
# ------------------------
def chat_dashboard2(request):
    mobiles = (SmsWhatsAppLog2.objects
               .values("mobile")
               .annotate(last_sent=Max("sent_at"))
               .order_by("-last_sent"))

    seen = set()
    mobile_list = []
    for m in mobiles:
        normalized = format_mobile2(str(m["mobile"]))
        if normalized not in seen:
            seen.add(normalized)
            mobile_list.append({"mobile": normalized})

    return render(request, "messaging2/chat.html", {"mobile_list": mobile_list, "MEDIA_URL": settings.MEDIA_URL})





# ------------------------
# Fetch Messages API
# ------------------------
def chat_messages_api2(request, mobile):
    normalized = format_mobile2(str(mobile))
    messages_qs = SmsWhatsAppLog2.objects.filter(mobile=normalized).order_by("sent_at")

    messages = []
    for msg in messages_qs:
        media_url = msg.media_file.url if msg.media_file else ""
        display_text = msg.sent_text_message or ""

        if display_text.startswith("[Image received"):
            display_text = "📷 Image"
        elif display_text.startswith("[Audio"):
            display_text = "🎧 Audio"
        elif display_text.startswith("[Video"):
            display_text = "🎬 Video"
        elif display_text.startswith("[Document"):
            display_text = "📄 Document"

        messages.append({
            "id": msg.id,
            "mobile": msg.mobile,
            "sent_text_message": display_text,
            "message_type": msg.message_type,
            "sent_at": msg.sent_at,
            "message_id": msg.message_id,
            "content_type": msg.content_type or "text",
            "media_file": media_url,
        })

    return JsonResponse({"messages": messages})

import json
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from .models import SmsWhatsAppLog2
  # Your existing utils
# ------------------------
# Send Reply API (Text + Media)
# ------------------------

@csrf_exempt
def send_reply_api2(request):
    try:
        if request.method != "POST":
            return HttpResponseBadRequest("POST required")

        # Handle both JSON and multipart/form-data
        if request.content_type.startswith("multipart/form-data"):
            mobile = request.POST.get("mobile", "").strip()
            text = request.POST.get("text", "").strip()
            media_file = request.FILES.get("media")
        else:
            payload = json.loads(request.body.decode("utf-8"))
            mobile = payload.get("mobile", "").strip()
            text = payload.get("text", "").strip()
            media_file = None

        if not mobile:
            return HttpResponseBadRequest("mobile required")

        mobile = format_mobile2(mobile)
        msg_id = ""
        content_type = "text"

        # If media file exists
        if media_file:
            mime_main = media_file.content_type.split("/")[0]
            if mime_main == "image":
                media_type = "image"
            elif mime_main == "video":
                media_type = "video"
            elif mime_main == "audio":
                media_type = "audio"
            else:
                media_type = "document"

            send_resp = send_whatsapp2_media(mobile, media_file, media_type)
            content_type = media_type
            if isinstance(send_resp, dict) and "messages" in send_resp:
                msg_id = send_resp["messages"][0].get("id", "")

            # Send text separately if provided
            if text:
                text_resp = send_whatsapp2_text(mobile, text)

        else:
            # Only text
            send_resp = send_whatsapp2_text(mobile, text)
            if isinstance(send_resp, dict) and "messages" in send_resp:
                msg_id = send_resp["messages"][0].get("id", "")

        # Log the message
        log = SmsWhatsAppLog2.objects.create(
            customer_name="",
            mobile=mobile,
            template_name="manual",
            sent_text_message=text or "",
            status="Delivered" if msg_id else "Sent",
            message_id=msg_id,
            message_type="Sent",
            content_type=content_type,
        )

        # Save media file in log if exists
        if media_file:
            log.media_file.save(media_file.name, media_file)
            log.save()

        return JsonResponse({"status": "ok", "api_response": send_resp})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# ----------------------------------------------------------
# WhatsApp Webhook (App2)
# ----------------------------------------------------------
@csrf_exempt
def whatsapp_webhook2(request):
    # ✅ Verification step
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        if mode == "subscribe" and token == getattr(settings, "WHATSAPP2_VERIFY_TOKEN", ""):
            # ✅ Meta expects plain challenge string, not JSON
            return HttpResponse(challenge)
        return HttpResponseBadRequest("Invalid verification token.")

    # ✅ Incoming messages
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
            entries = data.get("entry", [])
            for entry in entries:
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    messages = value.get("messages", [])
                    contacts = value.get("contacts", [])

                    for msg in messages:
                        from_num = format_mobile2(msg.get("from", ""))
                        msg_id = msg.get("id", "")
                        msg_type = msg.get("type", "text")
                        text_body = ""
                        content_type = "unknown"
                        media_file = None

                        if msg_type == "text":
                            text_body = msg["text"].get("body", "")
                            content_type = "text"

                        elif msg_type == "image":
                            content_type = "image"
                            media_id = msg["image"].get("id")
                            text_body = f"[Image received: {media_id}]"
                            media_file = download_whatsapp2_media(media_id)

                        elif msg_type == "document":
                            content_type = "document"
                            media_id = msg["document"].get("id")
                            text_body = msg["document"].get("filename", "[Document]")
                            media_file = download_whatsapp2_media(media_id)

                        log = SmsWhatsAppLog2.objects.create(
                            customer_name=(contacts[0].get("profile", {}).get("name") if contacts else ""),
                            mobile=from_num,
                            template_name="incoming",
                            sent_text_message=text_body,
                            status="Received",
                            message_type="Received",
                            message_id=msg_id,
                            content_type=content_type,
                        )

                        if media_file:
                            filename, content = media_file
                            log.media_file.save(filename, ContentFile(content))
                            log.save()

            return JsonResponse({"status": "received"})

        except Exception as e:
            print("Webhook2 error:", e)
            return JsonResponse({"error": str(e)}, status=400)

    return HttpResponseBadRequest("Unsupported method.")


# ----------------------------------------------------------
# Helper: Download media for WhatsApp2
# ----------------------------------------------------------
def download_whatsapp2_media(media_id):
    try:
        access_token = settings.WHATSAPP2_ACCESS_TOKEN
        headers = {"Authorization": f"Bearer {access_token}"}
        meta_url = f"https://graph.facebook.com/v22.0/{media_id}"
        meta_resp = requests.get(meta_url, headers=headers, timeout=30)
        meta_resp.raise_for_status()
        meta_data = meta_resp.json()
        file_url = meta_data.get("url")
        mime_type = meta_data.get("mime_type", "")
        extension = mime_type.split("/")[-1] if "/" in mime_type else "bin"
        file_resp = requests.get(file_url, headers=headers, timeout=30)
        file_resp.raise_for_status()
        filename = f"whatsapp2_{media_id}.{extension}"
        return filename, file_resp.content
    except Exception as e:
        print("Failed to download media (app2):", e)
        return None


# ----------------------------------------------------------
# Download success report (App2)
# ----------------------------------------------------------
def download_success_report2(request, job_id):
    job = get_object_or_404(BulkJob2, job_id=job_id)
    logs = SmsWhatsAppLog2.objects.filter(job=job, status__icontains="Delivered")

    if not logs.exists():
        return HttpResponse("No successful messages found for this job.")

    df = pd.DataFrame(list(logs.values("mobile", "sent_text_message", "status", "sent_at")))
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Success")
    buffer.seek(0)

    response = HttpResponse(
        buffer,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="success_report_{job_id}.xlsx"'
    return response


# ----------------------------------------------------------
# Download failed report (App2)
# ----------------------------------------------------------
def download_failed_report2(request, job_id):
    job = get_object_or_404(BulkJob2, job_id=job_id)
    logs = SmsWhatsAppLog2.objects.filter(job=job, status__icontains="Failed")

    if not logs.exists():
        return HttpResponse("No failed messages found for this job.")

    df = pd.DataFrame(list(logs.values("mobile", "sent_text_message", "status", "sent_at")))
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Failed")
    buffer.seek(0)

    response = HttpResponse(
        buffer,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="failed_report_{job_id}.xlsx"'
    return response


# ----------------------------------------------------------
# Export received messages to Excel (App2)
# ----------------------------------------------------------
def export_received_messages_to_excel2(request):
    logs = SmsWhatsAppLog2.objects.filter(message_type="Received").order_by("-sent_at")

    if not logs.exists():
        return HttpResponse("No received messages found.")

    df = pd.DataFrame(list(logs.values("customer_name", "mobile", "sent_text_message", "sent_at")))
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Received")
    buffer.seek(0)

    response = HttpResponse(
        buffer,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="received_messages.xlsx"'
    return response
