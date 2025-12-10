# messaging2/views.py
import os
import pytz
import json
import uuid
import requests
import pandas as pd
import io
from django.contrib.auth.decorators import login_required


from django.shortcuts import render, redirect, get_object_or_404
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.db.models import Max
from django.db.models import Count, Q

from .forms import UploadForm
from .models import SmsWhatsAppLog2, BulkJob2
from .tasks import process_bulk_whatsapp2
from .utils import format_mobile2
from django.contrib.auth import authenticate
from django.contrib import messages

def messaging2_login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(username=username, password=password)
        if user:
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




# WhatsApp helpers (send and upload) — same as before (v22 endpoints)
def send_whatsapp2_text(to_number, text_body):
    access_token = settings.WHATSAPP2_ACCESS_TOKEN
    phone_number_id = settings.WHATSAPP2_PHONE_NUMBER_ID
    url = f"https://graph.facebook.com/v22.0/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to_number, "type": "text", "text": {"body": text_body}}
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()

def send_whatsapp2_media(to_number, file_obj, media_type):
    access_token = settings.WHATSAPP2_ACCESS_TOKEN
    phone_number_id = settings.WHATSAPP2_PHONE_NUMBER_ID
    upload_url = f'https://graph.facebook.com/v22.0/{phone_number_id}/media'
    headers = {'Authorization': f'Bearer {access_token}'}
    files = {'file': (file_obj.name, file_obj, file_obj.content_type)}
    data = {'messaging_product': 'whatsapp'}
    resp = requests.post(upload_url, headers=headers, files=files, data=data, timeout=60)
    resp.raise_for_status()
    media_id = resp.json().get('id')
    url = f'https://graph.facebook.com/v22.0/{phone_number_id}/messages'
    payload = {"messaging_product": "whatsapp", "to": to_number, "type": media_type, media_type: {"id": media_id}}
    resp2 = requests.post(url, headers={'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'},
                          json=payload, timeout=30)
    resp2.raise_for_status()
    return resp2.json()


# Upload Excel + Trigger Bulk (App2) — S3-based
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

            # Read from S3 into pandas
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
                status="Pending",
            )

            process_bulk_whatsapp2.delay(s3_key, choice, job_id)
            return redirect("job_status2", job_id=job_id)
    else:
        form = UploadForm()
    return render(request, "messaging2/index.html", {"form": form})

def job_status2(request, job_id):
    job = get_object_or_404(BulkJob2, job_id=job_id)
    progress = 0
    if job.total_customers > 0:
        progress = round((job.sent_count / job.total_customers) * 100, 2)
    return render(request, "messaging2/job_status.html", {"job": job, "progress": progress})

@messaging2_required
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

@messaging2_required
def chat_messages_api2(request, mobile):
    normalized = format_mobile2(str(mobile))
    messages_qs = SmsWhatsAppLog2.objects.filter(mobile=normalized).order_by("sent_at")
    messages = []
    for msg in messages_qs:
        media_url = ""
        if msg.media_file:
            try:
                media_url = default_storage.url(msg.media_file.name)
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
            "status": msg.status or ""
        })
    return JsonResponse({"messages": messages})

@csrf_exempt
def send_reply_api2(request):
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
        mobile = format_mobile2(mobile)
        msg_id = ""
        content_type = "text"
        send_resp = None
        if media_file:
            mime_main = (media_file.content_type.split("/")[0] if media_file.content_type else "").lower()
            media_type = mime_main if mime_main in ("image", "video", "audio") else "document"
            send_resp = send_whatsapp2_media(mobile, media_file, media_type)
            content_type = media_type
            if isinstance(send_resp, dict) and "messages" in send_resp and send_resp["messages"]:
                msg_id = send_resp["messages"][0].get("id", "")
            if text:
                try:
                    send_whatsapp2_text(mobile, text)
                except Exception:
                    pass
        else:
            send_resp = send_whatsapp2_text(mobile, text)
            if isinstance(send_resp, dict) and "messages" in send_resp and send_resp["messages"]:
                msg_id = send_resp["messages"][0].get("id", "")
        status_field = "Sent"
        log = SmsWhatsAppLog2.objects.create(
            customer_name="",
            mobile=mobile,
            template_name="manual",
            sent_text_message=text or "",
            status=status_field,
            message_id=msg_id,
            message_type="Sent",
            content_type=content_type,
        )
        if media_file:
            log.media_file.save(media_file.name, media_file)
            log.save()
        return JsonResponse({"status": "ok", "api_response": send_resp})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def whatsapp_webhook2(request):
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")
        if mode == "subscribe" and token == getattr(settings, "WHATSAPP2_VERIFY_TOKEN", ""):
            return HttpResponse(challenge)
        return HttpResponseBadRequest("Invalid verification token.")
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
                            status="Unread",
                            message_type="Received",
                            message_id=msg_id,
                            content_type=content_type,
                        )
                        if media_file:
                            filename, content = media_file
                            if filename and content:
                                log.media_file.save(filename, ContentFile(content))
                                log.save()
                    statuses = value.get("statuses", [])
                    for st in statuses:
                        mid = st.get("id")
                        delivery_status = st.get("status")
                        SmsWhatsAppLog2.objects.filter(message_id=mid).update(status=delivery_status)
                        errors = st.get("errors", [])
                        if errors:
                            err = errors[0]
                            SmsWhatsAppLog2.objects.filter(message_id=mid).update(
                                error_message=f"{err.get('code')} - {err.get('title')}: {err.get('message')}"
                            )
            return JsonResponse({"status": "received"})
        except Exception as e:
            print("Webhook2 error:", e)
            return JsonResponse({"error": str(e)}, status=400)
    return HttpResponseBadRequest("Unsupported method.")


def download_success_report2(request, job_id):
    job = get_object_or_404(BulkJob2, job_id=job_id)

    if job.success_report:
        return redirect(default_storage.url(job.success_report))

    logs = SmsWhatsAppLog2.objects.filter(
        sent_at__gte=job.started_at,
        sent_at__lte=job.completed_at,
        status__icontains="Delivered"
    )

    if not logs.exists():
        return HttpResponse("No successful messages found for this job.")

    records = []
    for log in logs:
        sent_time = log.sent_at
        if sent_time:
            sent_time = sent_time.astimezone(pytz.timezone("Asia/Kolkata")).replace(tzinfo=None)
        else:
            sent_time = ""

        records.append({
            "Mobile": log.mobile,
            "Message": log.sent_text_message,
            "Status": log.status,
            "SentAt": sent_time,
        })

    df = pd.DataFrame(records)

    # ENSURE ALL DATETIME COLUMNS ARE NAIVE
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.tz_localize(None)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Success")

    buf.seek(0)

    return HttpResponse(
        buf,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="success_report_{job_id}.xlsx"'}
    )




def download_failed_report2(request, job_id):
    job = get_object_or_404(BulkJob2, job_id=job_id)

    if job.failed_report:
        return redirect(default_storage.url(job.failed_report))

    logs = SmsWhatsAppLog2.objects.filter(
        sent_at__gte=job.started_at,
        sent_at__lte=job.completed_at,
        status__icontains="Failed"
    )

    if not logs.exists():
        return HttpResponse("No failed messages found for this job.")

    records = []
    for log in logs:
        sent_time = log.sent_at
        if sent_time:
            sent_time = sent_time.astimezone(pytz.timezone("Asia/Kolkata")).replace(tzinfo=None)
        else:
            sent_time = ""

        records.append({
            "Mobile": log.mobile,
            "Message": log.sent_text_message,
            "Status": log.status,
            "Error": log.error_message,
            "SentAt": sent_time,
        })

    df = pd.DataFrame(records)

    # ENSURE ALL DATETIME COLUMNS ARE NAIVE
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.tz_localize(None)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Failed")

    buf.seek(0)

    return HttpResponse(
        buf,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="failed_report_{job_id}.xlsx"'}
    )




def export_received_messages_to_excel2(request):
    logs = SmsWhatsAppLog2.objects.filter(message_type="Received").order_by("-sent_at")
    if not logs.exists():
        return HttpResponse("No received messages found.")
    df = pd.DataFrame(list(logs.values("customer_name", "mobile", "sent_text_message", "sent_at")))
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Received")
    buf.seek(0)
    return HttpResponse(buf, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": 'attachment; filename="received_messages.xlsx"'})

@messaging2_required
def contacts_api2(request):
    qs = (
        SmsWhatsAppLog2.objects
        .values("mobile")
        .annotate(
            last_time=Max("sent_at"),
            unread=Count("id", filter=Q(message_type="Received", status="Unread"))
        )
        .order_by("-last_time")
    )
    result = []
    for item in qs:
        result.append({
            "mobile": format_mobile2(item["mobile"]),
            "last_time": item["last_time"].isoformat() if item["last_time"] else "",
            "unread": item["unread"],
        })
    return JsonResponse({"contacts": result})

@csrf_exempt
def mark_read(request, mobile):
    mobile = format_mobile2(mobile)
    SmsWhatsAppLog2.objects.filter(mobile=mobile, message_type="Received", status="Unread").update(status="Read")
    return JsonResponse({"status": "ok"})


# add near the top helpers in messaging2/views.py

def download_whatsapp2_media(media_id):
    """
    Download media bytes from WhatsApp Cloud API (App2).
    Returns: (filename, content_bytes) or None on error.
    """
    try:
        access_token = settings.WHATSAPP2_ACCESS_TOKEN
        headers = {"Authorization": f"Bearer {access_token}"}

        # 1) get media metadata (contains temporary URL + mime)
        meta_url = f"https://graph.facebook.com/v22.0/{media_id}"
        meta_resp = requests.get(meta_url, headers=headers, timeout=30)
        meta_resp.raise_for_status()
        meta = meta_resp.json()

        file_url = meta.get("url")
        mime = meta.get("mime_type", "") or ""
        ext = mime.split("/")[-1] if "/" in mime else "bin"

        if not file_url:
            # fallback: try 'url' field inside 'data' or similar
            file_url = meta.get("data", {}).get("url")

        # 2) download file bytes from the temporary URL
        file_resp = requests.get(file_url, headers=headers, timeout=60)
        file_resp.raise_for_status()

        filename = f"whatsapp2_{media_id}.{ext}"
        return filename, file_resp.content

    except Exception as e:
        # keep same logging style as your other code
        print("download_whatsapp2_media error:", e)
        return None


