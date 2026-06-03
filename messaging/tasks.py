import io
import time
import logging
from math import ceil
from django.core.files.base import ContentFile
from .utils import open_legal_pdf

import pandas as pd
import requests
from celery import shared_task
from celery.utils.log import get_task_logger
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from django.conf import settings
from django.utils import timezone
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db import transaction, close_old_connections
from django.db.models import F

from .models import *
from .utils import *

logger = get_task_logger(__name__)
logger.setLevel(logging.INFO)

# ==================================================
# MAIN BULK JOB
# ==================================================

def make_session():
    s = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
    )
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.headers.update({"Content-Type": "application/json"})
    return s

def upload_legal_pdf_to_whatsapp(pdf_filename, folder):
    """Upload PDF to WhatsApp - handles bytes correctly"""
    from io import BytesIO

    # Get PDF bytes from S3 or local
    pdf_bytes = open_legal_pdf(pdf_filename, folder)

    if not pdf_bytes:
        raise ValueError(f"Empty PDF: {pdf_filename}")

    # Create a BytesIO object that mimics a file
    file_obj = BytesIO(pdf_bytes)
    file_obj.name = pdf_filename
    file_obj.content_type = "application/pdf"

    return upload_whatsapp_media(file_obj)


@shared_task(bind=True, queue="whatsapp_main")
def process_bulk_whatsapp(self, excel_s3_path, template_choice, job_id, chunk_size=50):
    template_choice = str(template_choice)
    close_old_connections()

    try:
        job = BulkJob.objects.get(job_id=job_id)
    except BulkJob.DoesNotExist:
        return

    if job.status != "Pending":
        return

    job.status = "Running"
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])

    # Read Excel
    try:
        with default_storage.open(excel_s3_path, "rb") as f:
            data = f.read()
        df = pd.read_excel(io.BytesIO(data), dtype=str).fillna("")
    except Exception:
        job.status = "Failed"
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at"])
        return

    rows = df.to_dict("records")
    total = len(rows)

    # Total customers
    if template_choice == "17":
        job.total_customers = len({
            format_mobile(r.get("cust_mobile") or r.get("CustMobile"))
            for r in rows
            if r.get("cust_mobile") or r.get("CustMobile")
        })
    else:
        job.total_customers = total

    job.save(update_fields=["total_customers"])

    if total == 0:
        job.status = "Completed"
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at"])
        return

    # Create batches
    for i in range(0, total, chunk_size):
        process_bulk_whatsapp_batch.apply_async(
            args=(excel_s3_path, template_choice, job_id, i, min(i + chunk_size, total)),
            queue="whatsapp_main",
        )


# ==================================================
# BATCH WORKER (FIXED VERSION)
# ==================================================
@shared_task(bind=True, queue="whatsapp_main")
def process_bulk_whatsapp_batch(self, excel_s3_path, template_choice, job_id, start, end):
    from django.db import close_old_connections
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage
    from django.db.models import F
    from django.utils import timezone
    import io
    import pandas as pd
    import time
    import re

    close_old_connections()
    template_choice = str(template_choice)

    try:
        job = BulkJob.objects.get(job_id=job_id)
    except BulkJob.DoesNotExist:
        return

    if job.status != "Running":
        return

    # Read Excel chunk
    with default_storage.open(excel_s3_path, "rb") as f:
        df = pd.read_excel(io.BytesIO(f.read()), dtype=str).fillna("")

    rows = df.to_dict("records")[start:end]
    success_records = []
    failed_records = []
    local_success = 0
    local_failed = 0

    # ==================================================
    # 🚨 TEMPLATE 17 SPECIAL FLOW (NO DISTURB NORMAL FLOW)
    # ==================================================
    if template_choice == "17":
        # Read full Excel file for deduplication
        with default_storage.open(excel_s3_path, "rb") as f:
            df_full = pd.read_excel(io.BytesIO(f.read()), dtype=str).fillna("")

        all_rows = df_full.to_dict("records")

        # Extract unique mobiles from current batch
        mobiles = {
            format_mobile(r.get("cust_mobile") or r.get("CustMobile") or "")
            for r in rows
            if r.get("cust_mobile") or r.get("CustMobile")
        }

        for mobile in mobiles:
            try:
                # This function should process all messages for this mobile
                send_second_message_for_mobile(all_rows, mobile)
                local_success += 1
                print(f"✅ Template 17 sent to {mobile}")

            except Exception as e:
                err = str(e)
                print(f"❌ Template 17 failed for {mobile}: {err}")

                # Get name for this mobile (first occurrence)
                name = ""
                for r in rows:
                    if (format_mobile(r.get("cust_mobile") or r.get("CustMobile") or "")) == mobile:
                        name = r.get("customer_name") or r.get("CustomerName") or ""
                        break

                status_value = "Failed"

                if "131047" in err:
                    status_value = "Template Required"
                elif "131026" in err or "131051" in err:
                    status_value = "Blocked"
                elif "131009" in err or "131045" in err:
                    status_value = "Invalid"
                elif "132000" in err or "132001" in err:
                    status_value = "Template Failed"
                elif "timeout" in err.lower():
                    status_value = "Retry"
                elif "media" in err.lower():
                    status_value = "Media Failed"

                SmsWhatsAppLog.objects.create(
                    job_id=job_id,
                    customer_name=name,
                    mobile=mobile,
                    template_name=template_choice,
                    status=status_value,
                    message_type="Failed",
                    error_message=err,
                )
                local_failed += 1
                continue

        # Update job progress
        BulkJob.objects.filter(job_id=job_id).update(
            sent_count=F("sent_count") + (local_success + local_failed),
            success_count=F("success_count") + local_success,
            failed_count=F("failed_count") + local_failed,
        )

        job.refresh_from_db()

        if job.sent_count >= job.total_customers:
            job.status = "Completed"
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "completed_at"])
            finalize_bulk_job.delay(job_id)

        return  # Exit early for template 17

    # ==================================================
    # 🔽 NORMAL FLOW (All other templates from OLD CODE only)
    # ==================================================

    media_cache = {}

    session = make_session()
    session.headers.update({
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"
    })

    post_url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"

    for row in rows:
        name = row.get("customer_name") or row.get("CustomerName") or ""
        mobile = format_mobile(row.get("cust_mobile") or row.get("CustMobile") or "")

        # Skip WhatsApp number check (from old code - it's broken)
        print(f"📱 Sending to {mobile} without number check")

        try:
            media_id = None
            folder = None
            pdf_filename = None

            # ==================================================
            # 📁 SELECT PDF + FOLDER (ONLY OLD CODE TEMPLATES)
            # ==================================================

            if template_choice == "21":
                pdf_filename = row.get("welcome_pdf")
                folder = "welcome_pdfs"

            elif template_choice == "20":
                pdf_filename = row.get("guarantor_pdf_file")
                folder = "legal_pdfs"

            elif template_choice == "25":
                pdf_filename = row.get("lpc_pdf")
                folder = "legal_pdfs"

            elif template_choice == "30":
                pdf_filename = row.get("gur_telugu_registration_pdf")
                folder = "legal_pdfs"

            elif template_choice == "31":
                pdf_filename = row.get("cust_telugu_registration_pdf")
                folder = "legal_pdfs"

            elif template_choice == "32":
                pdf_filename = row.get("guarantor_registration_pdf")
                folder = "legal_pdfs"

            elif template_choice == "33":
                pdf_filename = row.get("customer_registration_pdf")
                folder = "legal_pdfs"
            elif template_choice == "35":
                pdf_filename = row.get("due_notice_pdf_file")
                folder = "legal_pdfs"

            elif template_choice == "19":
                pdf_filename = (
                    row.get("borrower_pdf_file")
                    or row.get("customer_pdf_file")
                )
                folder = "legal_pdfs"

            # ==================================================
            # 📤 UPLOAD TO WHATSAPP (ONLY IF PDF EXISTS)
            # ==================================================
            if pdf_filename:
                if not folder:
                    raise ValueError(f"Folder not set for template {template_choice}")

                print(f"📄 Template: {template_choice}, Folder: {folder}, File: {pdf_filename}")

                if pdf_filename not in media_cache:
                    upload_response = upload_legal_pdf_to_whatsapp(pdf_filename, folder)

                    if not upload_response or "id" not in upload_response:
                        raise ValueError(f"Media upload failed: {upload_response}")

                    media_cache[pdf_filename] = upload_response.get("id")

                media_id = media_cache[pdf_filename]

            # ==================================================
            # 📦 BUILD PAYLOAD
            # ==================================================
            payload, rendered_text = build_payload(
                template_choice,
                row,
                media_id
            )

            resp = session.post(post_url, json=payload, timeout=30)

            if not resp.ok:
                raise ValueError(f"API Error: {resp.text}")

            msg_id = resp.json()["messages"][0]["id"]

            # ==================================================
            # 📝 CREATE LOG
            # ==================================================
            log_content_type = "document" if pdf_filename else "text"

            log = SmsWhatsAppLog.objects.create(
                job_id=job_id,
                customer_name=name,
                mobile=mobile,
                template_name=template_choice,
                sent_text_message=rendered_text,
                status="Sent",
                message_id=msg_id,
                message_type="Sent",
                content_type=log_content_type,
            )

            # ==================================================
            # 💾 SAVE PDF TO DASHBOARD (IF EXISTS)
            # ==================================================
            if pdf_filename:
                try:
                    print(f"💾 Saving PDF: {pdf_filename} from {folder}")

                    pdf_bytes = open_legal_pdf(pdf_filename, folder)

                    if not pdf_bytes:
                        raise ValueError("Empty PDF")

                    if not isinstance(pdf_bytes, bytes):
                        pdf_bytes = bytes(pdf_bytes)

                    print(f"✅ PDF bytes received, size: {len(pdf_bytes)} bytes")
                    from pathlib import Path
                    original_filename = Path(pdf_filename).name

                    saved_path = default_storage.save(
                        f"chat_media/{original_filename}",
                        ContentFile(pdf_bytes)
                    )

                    SmsWhatsAppLog.objects.filter(id=log.id).update(
                        media_file=saved_path,
                        content_type="document"
                    )
                    log.refresh_from_db()
                    print("✅ PDF SAVED:", original_filename)

                except Exception as e:
                    print(f"❌ PDF SAVE FAILED: {e}")
                    import traceback
                    traceback.print_exc()

            # ==================================================
            # 📝 UPDATE CONTACT
            # ==================================================
            ChatContact.objects.update_or_create(
                mobile=mobile,
                defaults={
                    "last_msg": rendered_text or "[Media]",
                    "last_time": timezone.now(),
                    "last_type": "Sent",
                    "last_status": "Sent",
                    "unread": 0
                }
            )

            # ==================================================
            # 🔄 WEBSOCKET BROADCAST
            # ==================================================
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync

            channel_layer = get_channel_layer()
            gm = re.sub(r"\D", "", mobile)

            if gm:
                async_to_sync(channel_layer.group_send)(
                    f"chat_{gm}",
                    {
                        "type": "new_message",
                        "message": {
                            "id": log.id,
                            "mobile": mobile,
                            "sent_text_message": rendered_text,
                            "content_type": log_content_type,
                            "media_file": log.media_file.url if log.media_file else "",
                            "sent_at": log.sent_at.isoformat(),
                            "message_type": "Sent",
                            "message_id": msg_id,
                            "status": "Sent",
                            "sender_name": name,
                        }
                    }
                )

            async_to_sync(channel_layer.group_send)(
                "global_contacts",
                {
                    "type": "contact.update",
                    "contact": {
                        "mobile": mobile,
                        "last_msg": rendered_text or "[Media]",
                        "last_time": timezone.now().isoformat(),
                        "last_type": "Sent",
                        "last_status": "Sent",
                        "unread": 0
                    }
                }
            )

            success_records.append([name, mobile, msg_id])
            local_success += 1
            print(f"✅ Successfully sent to {mobile} - Message ID: {msg_id}")

        except Exception as e:
            err_msg = str(e)
            print(f"❌ Failed to send to {mobile}: {err_msg}")
            import traceback
            traceback.print_exc()

            # Error code handling from old code
            status_value = "Failed"

            if "131047" in err_msg:
                status_value = "Template Required"
            elif "131026" in err_msg or "131051" in err_msg:
                status_value = "Blocked"
            elif "131009" in err_msg or "131045" in err_msg:
                status_value = "Invalid"
            elif "132000" in err_msg or "132001" in err_msg:
                status_value = "Template Failed"
            elif "timeout" in err_msg.lower():
                status_value = "Retry"
            elif "media" in err_msg.lower():
                status_value = "Media Failed"

            SmsWhatsAppLog.objects.create(
                job_id=job_id,
                customer_name=name,
                mobile=mobile,
                template_name=template_choice,
                status=status_value,
                message_type="Failed",
                error_message=err_msg,
                content_type="text",
            )
            failed_records.append([name, mobile, err_msg])
            local_failed += 1

        time.sleep(0.3)

    # ==================================================
    # 📊 UPDATE JOB PROGRESS
    # ==================================================
    BulkJob.objects.filter(job_id=job_id).update(
        sent_count=F("sent_count") + (local_success + local_failed),
        success_count=F("success_count") + local_success,
        failed_count=F("failed_count") + local_failed,
    )

    job.refresh_from_db()

    if job.sent_count >= job.total_customers:
        job.status = "Completed"
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at"])
        finalize_bulk_job.delay(job_id)
# ==================================================
# FINALIZER
# ==================================================
@shared_task(bind=True, queue="whatsapp_main")
def finalize_bulk_job(self, job_id):
    try:
        job = BulkJob.objects.get(job_id=job_id)
    except BulkJob.DoesNotExist:
        return

    # Prevent double execution
    if job.success_report and job.failed_report:
        return

    # Get all field names from SmsWhatsAppLog (avoid auto-created ones like id, but include them anyway)
    from django.apps import apps
    model = SmsWhatsAppLog
    field_names = [f.name for f in model._meta.get_fields() if not f.auto_created]
    # For better readability, you can also define a fixed list of columns you want in reports
    # field_names = ['id', 'job_id', 'customer_name', 'mobile', 'template_name', 'status', 'sent_text_message', 'error_message', ...]

    success_qs = SmsWhatsAppLog.objects.filter(
        job_id=job_id, status__in=["Sent", "Delivered"]
    )
    failed_qs = SmsWhatsAppLog.objects.filter(
        job_id=job_id, status="Failed"
    )

    # Build DataFrames – always with correct columns
    if success_qs.exists():
        success_df = pd.DataFrame(list(success_qs.values()))
    else:
        success_df = pd.DataFrame(columns=field_names)

    if failed_qs.exists():
        failed_df = pd.DataFrame(list(failed_qs.values()))
    else:
        failed_df = pd.DataFrame(columns=field_names)

    # 🔥 Remove timezone from datetime columns (same as before)
    for df in [success_df, failed_df]:
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].dt.tz_localize(None)

    success_path = f"reports/{job_id}_success.xlsx"
    failed_path = f"reports/{job_id}_failed.xlsx"

    success_buffer = io.BytesIO()
    failed_buffer = io.BytesIO()

    # Always write both files (even empty ones)
    success_df.to_excel(success_buffer, index=False)
    failed_df.to_excel(failed_buffer, index=False)

    # Delete old files if they exist (optional but safe)
    if default_storage.exists(success_path):
        default_storage.delete(success_path)
    if default_storage.exists(failed_path):
        default_storage.delete(failed_path)

    # Save both reports unconditionally
    default_storage.save(success_path, ContentFile(success_buffer.getvalue()))
    job.success_report = success_path

    default_storage.save(failed_path, ContentFile(failed_buffer.getvalue()))
    job.failed_report = failed_path

    job.status = "Completed"
    job.completed_at = timezone.now()
    job.save(update_fields=[
        "success_report", "failed_report", "status", "completed_at"
    ])

    logger.info("Job %s COMPLETED and both reports generated", job_id)


@shared_task
def process_pending_webhook_updates():
    """Process any status updates that arrived before the message was saved"""
    from django.core.cache import cache
    from django.utils import timezone
    from datetime import timedelta

    keys = cache.keys("pending_wa_status_*")

    for key in keys:
        data = cache.get(key)
        if not data:
            continue

        msg_id = key.replace("pending_wa_status_", "")
        status_type = data.get('status')

        # Try to find the message now
        obj = SmsWhatsAppLog.objects.filter(message_id=msg_id).first()

        if obj:
            if status_type == "sent":
                norm = "Sent"
            elif status_type == "delivered":
                norm = "Delivered"
            elif status_type == "read":
                norm = "Read"
            else:
                continue

            SmsWhatsAppLog.objects.filter(id=obj.id).update(status=norm)
            print(f"✅ Processed pending status for {msg_id} -> {norm}")
            cache.delete(key)
        else:
            # If older than 60 seconds, remove
            timestamp = data.get('timestamp')
            if timestamp:
                from dateutil import parser
                if parser.parse(timestamp) < timezone.now() - timedelta(seconds=60):
                    cache.delete(key)

