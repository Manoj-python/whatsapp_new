import io
import json
import os
import uuid
import requests
import pandas as pd
from openpyxl import Workbook
from openpyxl.drawing.image import Image as ExcelImage

from django.shortcuts import render, redirect, get_object_or_404
from django.core.files.storage import FileSystemStorage, default_storage
from django.core.files.base import ContentFile
from django.http import JsonResponse, HttpResponseBadRequest, FileResponse, Http404, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.db.models import Max

from .forms import UploadForm
from .models import SmsWhatsAppLog, BulkJob
from .tasks import process_bulk_whatsapp
from .utils import format_mobile


# ---------------------------
# WhatsApp Cloud API helpers
# ---------------------------
def send_whatsapp_text(to_number, text_body):
    access_token = settings.WHATSAPP_ACCESS_TOKEN
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text_body},
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def upload_whatsapp_media(file_obj):
    """
    Uploads a media file to WhatsApp cloud and returns the API response.
    NOTE: this will read the file pointer, so caller may want to seek back to 0 before saving locally.
    """
    access_token = settings.WHATSAPP_ACCESS_TOKEN
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    url = f"https://graph.facebook.com/v17.0/{phone_number_id}/media"
    headers = {"Authorization": f"Bearer {access_token}"}
    # make sure to pass raw bytes and filename/content-type
    file_obj.seek(0)
    files = {'file': (file_obj.name, file_obj.read(), file_obj.content_type)}
    data = {'messaging_product': 'whatsapp'}
    resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)
    resp.raise_for_status()
    return resp.json()


def send_whatsapp_media(to_number, media_id, media_type, caption=""):
    access_token = settings.WHATSAPP_ACCESS_TOKEN
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
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


# ---------------------------
# Bulk upload (unchanged)
# ---------------------------
def upload_and_send(request):
    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            choice = form.cleaned_data["template_choice"]
            excel_file = request.FILES["excel_file"]
            fs = FileSystemStorage(location="uploads/")
            filename = fs.save(excel_file.name, excel_file)
            file_path = fs.path(filename)
            df = pd.read_excel(file_path, dtype=str).fillna("")
            job_id = str(uuid.uuid4())
            BulkJob.objects.create(
                job_id=job_id,
                template_name=choice,
                total_customers=len(df),
                excel_file=f"uploads/{filename}",
            )
            process_bulk_whatsapp.delay(file_path, choice, job_id)
            return redirect("job_status", job_id=job_id)
    else:
        form = UploadForm()
    return render(request, "messaging/index.html", {"form": form})


def job_status(request, job_id):
    job = get_object_or_404(BulkJob, job_id=job_id)
    progress = 0
    if job.total_customers > 0:
        progress = round((job.sent_count / job.total_customers) * 100, 2)
    return render(request, "messaging/job_status.html", {"job": job, "progress": progress})


# ---------------------------
# Download Reports (example)
# ---------------------------
def download_success_report(request, job_id):
    file_path = "success_report.xlsx"
    if os.path.exists(file_path):
        return FileResponse(open(file_path, "rb"), as_attachment=True, filename=f"success_report_{job_id}.xlsx")
    raise Http404("Success report not found.")


def download_failed_report(request, job_id):
    file_path = "failed_report.xlsx"
    if os.path.exists(file_path):
        return FileResponse(open(file_path, "rb"), as_attachment=True, filename=f"failed_report_{job_id}.xlsx")
    raise Http404("Failed report not found.")


# ---------------------------
# Chat dashboard
# ---------------------------
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
        "MEDIA_URL": settings.MEDIA_URL,
    })


# ---------------------------
# Messages API
# ---------------------------
def chat_messages_api(request, mobile):
    normalized = format_mobile(str(mobile))
    messages_qs = SmsWhatsAppLog.objects.filter(mobile=normalized).order_by("sent_at")
    messages = []
    for msg in messages_qs:
        # Use absolute URL if media exists
        media_url = ""
        if msg.media_file:
            try:
                media_url = request.build_absolute_uri(msg.media_file.url)
            except Exception:
                media_url = msg.media_file.url
        messages.append({
            "id": msg.id,
            "mobile": msg.mobile,
            "sent_text_message": msg.sent_text_message or "",
            "message_type": msg.message_type,
            "sent_at": msg.sent_at.isoformat() if msg.sent_at else "",
            "message_id": msg.message_id,
            "content_type": msg.content_type or "text",
            "media_file": media_url,
        })
    return JsonResponse({"messages": messages})


# ---------------------------
# Send reply API (text + media)
# ---------------------------
@csrf_exempt
def send_reply_api(request):
    """
    Accepts:
      - multipart/form-data (mobile, text, media)
      - or JSON body {"mobile":"", "text":""}
    """
    try:
        if request.method != "POST":
            return HttpResponseBadRequest("POST required")

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

        mobile = format_mobile(mobile)

        if media_file:
            # Upload to WhatsApp cloud
            # Ensure file pointer at 0 before reading inside upload_whatsapp_media
            if hasattr(media_file, "seek"):
                try:
                    media_file.seek(0)
                except Exception:
                    pass
            upload_resp = upload_whatsapp_media(media_file)
            media_id = upload_resp.get("id")

            # Determine basic content type mapping (image, video, audio, document)
            mime_main = (media_file.content_type.split("/")[0] if media_file.content_type else "").lower()
            if mime_main in ("image", "video", "audio"):
                mapped_content_type = mime_main
            else:
                # application/* and others -> document
                mapped_content_type = "document"

            # For WhatsApp message type, use 'image', 'video', 'audio', or 'document'
            wa_media_type = mapped_content_type
            send_resp = send_whatsapp_media(mobile, media_id, wa_media_type, caption=text)
            content_type = mapped_content_type
        else:
            send_resp = send_whatsapp_text(mobile, text)
            content_type = "text"

        msg_id = ""
        if isinstance(send_resp, dict) and "messages" in send_resp:
            if send_resp["messages"]:
                msg_id = send_resp["messages"][0].get("id", "")

        # Create DB log
        log = SmsWhatsAppLog.objects.create(
            customer_name="",
            mobile=mobile,
            template_name="manual",
            sent_text_message=text or "",
            status="Delivered" if msg_id else "Sent",
            message_id=msg_id,
            message_type="Sent",
            content_type=content_type,
        )

        # Save attached media file locally (rewind pointer if necessary)
        if media_file:
            try:
                if hasattr(media_file, "seek"):
                    media_file.seek(0)
            except Exception:
                pass
            log.media_file.save(media_file.name, media_file)
            log.save()

        return JsonResponse({"status": "ok", "api_response": send_resp})
    except Exception as e:
        # In production, log the exception properly instead of printing
        return JsonResponse({"error": str(e)}, status=500)


# ---------------------------
# Webhook: incoming messages
# ---------------------------
@csrf_exempt
def whatsapp_webhook(request):
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        if mode == "subscribe" and token == getattr(settings, "WHATSAPP_VERIFY_TOKEN", ""):
            return HttpResponse(challenge, status=200)

        return HttpResponseBadRequest("Invalid verification.")


    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
            entries = data.get("entry", [])
            for entry in entries:
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    messages = value.get("messages", [])
                    contacts = value.get("contacts", [])

                    for msg in messages:
                        from_num = format_mobile(msg.get("from", ""))
                        msg_id = msg.get("id", "")
                        msg_type = msg.get("type", "text")
                        text_body = ""
                        content_type = "unknown"
                        media_file = None

                        # --- Text ---
                        if msg_type == "text":
                            text_body = msg["text"].get("body", "")
                            content_type = "text"

                        # --- Interactive ---
                        elif msg_type == "interactive":
                            content_type = "interactive"
                            interactive = msg.get("interactive", {})
                            if interactive.get("type") == "button":
                                text_body = interactive["button"].get("text", "")
                            elif interactive.get("type") == "list_reply":
                                text_body = interactive["list_reply"].get("title", "")

                        # --- Image ---
                        elif msg_type == "image":
                            content_type = "image"
                            image_info = msg.get("image", {})
                            media_id = image_info.get("id")
                            text_body = f"[Image received: {media_id}]"
                            media_file = download_whatsapp_media(media_id)

                        # --- Document ---
                        elif msg_type == "document":
                            content_type = "document"
                            doc_info = msg.get("document", {})
                            media_id = doc_info.get("id")
                            text_body = doc_info.get("filename", "[Document]")
                            media_file = download_whatsapp_media(media_id)

                        # --- Video ---
                        elif msg_type == "video":
                            content_type = "video"
                            vid_info = msg.get("video", {})
                            media_id = vid_info.get("id")
                            text_body = "[Video]"
                            media_file = download_whatsapp_media(media_id)

                        # --- Audio ---
                        elif msg_type == "audio":
                            content_type = "audio"
                            aud_info = msg.get("audio", {})
                            media_id = aud_info.get("id")
                            text_body = "[Audio]"
                            media_file = download_whatsapp_media(media_id)

                        # Save log
                        log = SmsWhatsAppLog.objects.create(
                            customer_name=(contacts[0].get("profile", {}).get("name") if contacts else ""),
                            mobile=from_num,
                            template_name="incoming",
                            sent_text_message=text_body,
                            status="Received",
                            message_type="Received",
                            message_id=msg_id,
                            content_type=content_type,
                        )

                        # Attach file if downloaded (media_file is (filename, bytes) or None)
                        if media_file:
                            filename, content = media_file
                            if filename and content:
                                log.media_file.save(filename, ContentFile(content))
                                log.save()

            return JsonResponse({"status": "received"})
        except Exception as e:
            # log exception in real app
            print("Webhook error:", e)
            return JsonResponse({"error": str(e)}, status=400)

    return HttpResponseBadRequest("Unsupported method.")


# ---------------------------
# Helper: download media from WhatsApp Cloud API
# ---------------------------
def download_whatsapp_media(media_id):
    """
    Downloads media file from WhatsApp Cloud API using its media_id.
    Returns tuple: (filename, binary_content) or None on error.
    """
    try:
        access_token = settings.WHATSAPP_ACCESS_TOKEN
        headers = {"Authorization": f"Bearer {access_token}"}

        # Step 1: get metadata (url + mime)
        meta_url = f"https://graph.facebook.com/v17.0/{media_id}"
        meta_resp = requests.get(meta_url, headers=headers, timeout=30)
        meta_resp.raise_for_status()
        meta_data = meta_resp.json()
        file_url = meta_data.get("url")
        mime_type = meta_data.get("mime_type", "")
        extension = mime_type.split("/")[-1] if "/" in mime_type else "bin"

        # Step 2: download file bytes
        file_resp = requests.get(file_url, headers=headers, timeout=30)
        file_resp.raise_for_status()
        filename = f"whatsapp_{media_id}.{extension}"
        return filename, file_resp.content
    except Exception as e:
        print("Failed to download media:", e)
        return None


# ---------------------------
# Export received messages to Excel (images embedded)
# ---------------------------
def export_received_messages_to_excel(request):
    wb = Workbook()
    ws = wb.active
    ws.title = "Received Messages"
    ws.append(["Mobile", "Message", "Media (if image)"])

    logs = SmsWhatsAppLog.objects.filter(message_type="Received").order_by("-sent_at")

    for log in logs:
        mobile = log.mobile
        message = log.sent_text_message or ""
        ws.append([mobile, message, ""])

        # If there's an image, embed it
        if log.media_file and log.content_type == "image":
            try:
                with default_storage.open(log.media_file.name, "rb") as f:
                    img_data = io.BytesIO(f.read())
                    img = ExcelImage(img_data)
                    img.width = 100
                    img.height = 100
                    img_cell = f"C{ws.max_row}"
                    ws.add_image(img, img_cell)
            except Exception:
                pass

    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="received_messages.xlsx"'
    wb.save(response)
    return response
