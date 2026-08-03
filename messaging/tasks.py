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
from .utils import open_legal_pdf

from .models import *
from .utils import *

# ============================================================
# 🔥 IMPORT API CHECK FUNCTIONS
# ============================================================
from .utils import needs_api_check, check_smsquare_payment_status

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


@shared_task(bind=True, queue="messaging")
def process_bulk_whatsapp(self, excel_s3_path, template_choice, job_id,user_id=None, chunk_size=250):
    template_choice = str(template_choice)
    close_old_connections()
    from django.contrib.auth.models import User
    agent_name = "System"
    if user_id:
        try:
            user = User.objects.get(id=user_id)
            agent_name = user.get_full_name() or user.username
        except User.DoesNotExist:
            pass


    try:
        job = BulkJob.objects.get(job_id=job_id)
    except BulkJob.DoesNotExist:
        return

    if job.status != "Pending":
        return

    job.status = "Running"

    # ===== DEBUG START =====
    import inspect

    print("========== DEBUG ==========")
    print("timezone =", timezone)
    print("type =", type(timezone))
    print("module =", getattr(timezone, "__module__", None))
    try:
        print("file =", inspect.getfile(timezone))
    except Exception as e:
        print("file error:", e)
    print("===========================")
    # ===== DEBUG END =====
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
            args=(excel_s3_path, template_choice, job_id, i, min(i + chunk_size, total),agent_name),
            queue="messaging",
        )


# ==================================================
# BATCH WORKER (FIXED VERSION WITH API CHECK)
# ==================================================
@shared_task(bind=True, queue="messaging")
def process_bulk_whatsapp_batch(self, excel_s3_path, template_choice, job_id, start, end,agent_name="System"):
    from django.db import close_old_connections
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage
    from django.db.models import F
    import io
    import pandas as pd
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
    local_skipped = 0  # ✅ Track PAID customers who are skipped

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
                send_second_message_for_mobile(all_rows, mobile,agent_name)
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

                ERROR_MAP = {
                    "131026": "NOT_ON_WHATSAPP",
                    "131011": "BLOCKED_BY_USER",
                    "130403": "BLOCKED_BY_BUSINESS",
                    "131050": "OPTED_OUT",
                    "190": "TOKEN_ERROR",
                    "131009": "INVALID_PARAMETER",
                    "131000": "UNKNOWN_ERROR",
                    "131045": "REGISTRATION_ERROR",
                    "131047": "24H_WINDOW_EXPIRED",
                    "131051": "UNSUPPORTED_MESSAGE_TYPE",
                    "132000": "TEMPLATE_PARAM_ERROR",
                    "132001": "TEMPLATE_NOT_FOUND",
                    "132015": "TEMPLATE_PAUSED",
                    "132016": "TEMPLATE_DISABLED",
                    "130429": "RATE_LIMIT",
                    "131056": "TOO_MANY_MESSAGES",
                }

                for code, label in ERROR_MAP.items():
                    if code in err:
                        status_value = label
                        break

                SmsWhatsAppLog.objects.create(
                    job_id=job_id,
                    customer_name=agent_name,
                    sender_name=name,
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
    # 🔽 NORMAL FLOW (All other templates)
    # ==================================================

    # ✅ Check if this template needs API check
    check_api = needs_api_check(template_choice)
    logger.info(f"📋 Template {template_choice} - API Check: {'YES' if check_api else 'NO'}")

    media_cache = {}

    session = make_session()
    session.headers.update({
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"
    })

    post_url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"

    for row in rows:
        name = row.get("customer_name") or row.get("CustomerName") or ""
        mobile = format_mobile(row.get("cust_mobile") or row.get("CustMobile") or "")
        loan_number = row.get("loan_number") or row.get("LoanNumber") or ""  # ✅ Get loan number from Excel

        if not mobile:
            local_failed += 1
            continue

        # ============================================================
        # 🔍 API CHECK - Only for selected templates
        # ============================================================
       # tasks.py - In process_bulk_whatsapp_batch function

# ============================================================
# 🔍 API CHECK - Only for selected templates
# ============================================================
        if check_api:
            try:
                # ✅ Pass loan_number to check function
                status = check_smsquare_payment_status(mobile, loan_number)
                
                if status['is_paid']:
                    # ✅ PAID → Skip (no message)
                    print(f"✅ {mobile} - PAID, skipping")
                    local_skipped += 1
                    
                    # ✅ CREATE A LOG ENTRY FOR SKIPPED CUSTOMER
                    SmsWhatsAppLog.objects.create(
                        job_id=job_id,
                        customer_name=agent_name,
                        sender_name=name,
                        mobile=mobile,
                        template_name=template_choice,
                        status='PAID',
                        message_type='Skipped',
                        error_message=f"Customer is PAID (Total Due: ₹{status.get('total_due', 0)})",
                        sent_text_message=f"PAID - No message sent (Total Due: ₹{status.get('total_due', 0)})",
                        sent_at=timezone.now(),
                    )
                    continue
                else:
                    print(f"❌ {mobile} - UNPAID (₹{status['total_due']})")
            except Exception as api_error:
                # If API fails, assume UNPAID (send reminder)
                print(f"⚠️ API Error for {mobile}: {api_error}")
                print(f"📱 {mobile} - Assuming UNPAID, sending")
        else:
            # ❌ No API check → Send to ALL
            print(f"📱 {mobile} - No API check, sending")
        # ============================================================
        # 📤 SEND MESSAGE (Existing logic)
        # ============================================================
        try:
            media_id = None
            folder = None
            pdf_filename = None

            # ==================================================
            # 📁 SELECT PDF + FOLDER
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

            elif template_choice == "37":
                pdf_filename = row.get("presale_notices_borrower_pdf")
                folder = "legal_pdfs"
            elif template_choice == "41":
                pdf_filename = row.get("hpt_pending_pdf")
                folder = "noc_pdfs"
            
            elif template_choice == "48":
                pdf_filename = row.get("doc_sms_portal_pdf")
                folder = "noc_pdfs"                
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
                customer_name=agent_name,
                sender_name=name,
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
            contact, created = ChatContact.objects.get_or_create(
                mobile=mobile,
                defaults={
                    "last_msg": rendered_text or "[Media]",
                    "last_time": timezone.now(),
                    "last_type": "Sent",
                    "last_status": "Sent",
                    "unread": 0
                }
            )
            if not created:
                # Only update non‑unread fields
                ChatContact.objects.filter(mobile=mobile).update(
                    last_msg=rendered_text or "[Media]",
                    last_time=timezone.now(),
                    last_type="Sent",
                    last_status="Sent"
                    # ❌ 'unread' is NOT updated – it stays as it was
                )
                contact.refresh_from_db()

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
                            "sender_name": agent_name,
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
                        "unread": contact.unread
                    }
                }
            )

            success_records.append([name, mobile, msg_id])
            local_success += 1
            print(f"✅ Successfully sent to {mobile} - Message ID: {msg_id}")

        except Exception as e:
            err = str(e)
            print(f"❌ Failed to send to {mobile}: {err}")

            # Get name for this mobile (first occurrence)
            name = ""
            for r in rows:
                if (format_mobile(r.get("cust_mobile") or r.get("CustMobile") or "")) == mobile:
                    name = r.get("customer_name") or r.get("CustomerName") or ""
                    break

            status_value = "Failed"

            ERROR_MAP = {
                "131026": "NOT_ON_WHATSAPP",
                "131011": "BLOCKED_BY_USER",
                "130403": "BLOCKED_BY_BUSINESS",
                "131050": "OPTED_OUT",
                "190": "TOKEN_ERROR",
                "131009": "INVALID_PARAMETER",
                "131000": "UNKNOWN_ERROR",
                "131045": "REGISTRATION_ERROR",
                "131047": "24H_WINDOW_EXPIRED",
                "131051": "UNSUPPORTED_MESSAGE_TYPE",
                "132000": "TEMPLATE_PARAM_ERROR",
                "132001": "TEMPLATE_NOT_FOUND",
                "132015": "TEMPLATE_PAUSED",
                "132016": "TEMPLATE_DISABLED",
                "130429": "RATE_LIMIT",
                "131056": "TOO_MANY_MESSAGES",
            }

            for code, label in ERROR_MAP.items():
                if code in err:
                    status_value = label
                    break

            SmsWhatsAppLog.objects.create(
                job_id=job_id,
                customer_name=agent_name,
                sender_name=name,
                mobile=mobile,
                template_name=template_choice,
                status=status_value,
                message_type="Failed",
                error_message=err,
            )
            local_failed += 1
            continue

    # ==================================================
    # 📊 UPDATE JOB PROGRESS (FIXED)
    # ==================================================
    BulkJob.objects.filter(job_id=job_id).update(
        sent_count=F("sent_count") + local_success,
        success_count=F("success_count") + local_success,
        failed_count=F("failed_count") + local_failed,
        skipped_count=F("skipped_count") + local_skipped,  # ✅ ADD THIS
    )

    job.refresh_from_db()

    # ✅ Check ALL processed customers
    processed = job.sent_count + job.skipped_count + job.failed_count

    # Log summary for this batch
    logger.info(f"📊 Batch {start}-{end} Summary: Sent={local_success}, Skipped={local_skipped}, Failed={local_failed}")
    logger.info(f"📊 Job Progress: {processed}/{job.total_customers} (Sent={job.sent_count}, Skipped={job.skipped_count}, Failed={job.failed_count})")

    if processed >= job.total_customers:
        job.status = "Completed"
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at"])
        finalize_bulk_job.delay(job_id)
        logger.info(f"✅ Job {job_id} COMPLETED!")
    else:
        logger.info(f"⏳ Job {job_id} in progress: {processed}/{job.total_customers}")


# ==================================================
# FINALIZER
# ==================================================
@shared_task(bind=True, queue="messaging")
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
    job_id=job_id, status__in=["Sent", "Delivered", "Read"]
    )
    failed_qs = SmsWhatsAppLog.objects.exclude(
        status__in=["Sent", "Delivered", "Read"]
    ).filter(
        job_id=job_id
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
