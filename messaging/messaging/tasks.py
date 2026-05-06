import io
import time
import logging

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
from django.db import close_old_connections
from django.db.models import F
from django.core.files.base import ContentFile
from .models import *
from .utils import (
    upload_whatsapp_media,
    build_payload,
    format_mobile,
    check_whatsapp_number,
    send_second_message_for_mobile,
    open_legal_pdf,
)

logger = get_task_logger(__name__)
logger.setLevel(logging.INFO)


# ==================================================
# HTTP SESSION
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


# ====
# ==================================================
# Upload Legal PDF
# ==================================================
def upload_legal_pdf_to_whatsapp(pdf_filename, folder):
    f = open_legal_pdf(pdf_filename, folder)

    class WhatsAppFile:
        name = pdf_filename
        content_type = "application/pdf"

        def read(self):
            return f.read()

        def seek(self, pos):
            pass

    return upload_whatsapp_media(WhatsAppFile())



# ==================================================
# MAIN BULK TASK
# ==================================================
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
# BATCH TASK
# ==================================================

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
@shared_task(bind=True, queue="whatsapp_main")
def process_bulk_whatsapp_batch(self, excel_s3_path, template_choice, job_id, start, end):
    from django.db import close_old_connections
    close_old_connections()
    template_choice = str(template_choice)

    close_old_connections()

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

    local_success = 0
    local_failed = 0

    # ==================================================
    # 🚨 TEMPLATE 17 SPECIAL FLOW (NO DISTURB NORMAL FLOW)
    # ==================================================
    if template_choice == "17":

        with default_storage.open(excel_s3_path, "rb") as f:
            df_full = pd.read_excel(io.BytesIO(f.read()), dtype=str).fillna("")

        all_rows = df_full.to_dict("records")

        mobiles = {
            format_mobile(r.get("cust_mobile") or r.get("CustMobile") or "")
            for r in rows
            if r.get("cust_mobile") or r.get("CustMobile")
        }

        for mobile in mobiles:
            try:
                send_second_message_for_mobile(all_rows, mobile)
                local_success += 1
            except Exception as e:
                SmsWhatsAppLog.objects.create(
                    job_id=job_id,
                    mobile=mobile,
                    template_name="17",
                    status="Failed",
                    message_type="Sent",
                    error_message=str(e),
                )
                local_failed += 1

        BulkJob.objects.filter(job_id=job_id).update(
            sent_count=F("sent_count") + (local_success + local_failed),
            success_count=F("success_count") + local_success,
            failed_count=F("failed_count") + local_failed,
        )

        return

    # ==================================================
    # 🔽 NORMAL FLOW
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

        try:
            check = check_whatsapp_number(mobile)
        except Exception as e:
            SmsWhatsAppLog.objects.create(
                job_id=job_id,
                customer_name=name,
                mobile=mobile,
                template_name=template_choice,
                status="Failed",
                message_type="Sent",
                error_message=f"Validation error: {str(e)}",
            )
            local_failed += 1
            continue

        if not check.get("valid", False):
            SmsWhatsAppLog.objects.create(
                job_id=job_id,
                customer_name=name,
                mobile=mobile,
                template_name=template_choice,
                status="Failed",
                message_type="Sent",
                error_message=check.get("reason"),
            )
            local_failed += 1
            continue

        try:
            media_id = None
            folder = None
            pdf_filename = None   # ✅ IMPORTANT

            # ==================================================
            # 📁 SELECT PDF + FOLDER (FIXED LOGIC)
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

                # 🔍 DEBUG (remove later)
                print("TEMPLATE:", template_choice)
                print("FOLDER:", folder)
                print("FILE:", pdf_filename)

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
                raise ValueError(resp.text)

            msg_id = resp.json()["messages"][0]["id"]

            # ==================================================
            # 💾 SAVE PDF TO DASHBOARD
            # ==================================================
            media_file_obj = None
            content_type_val = "text"
            pdf_source = None

            if pdf_filename:

                content_type_val = "document"
                pdf_source = pdf_filename

                try:
                    media_file_obj = open_legal_pdf(pdf_source, folder)
                except Exception as e:
                    logger.warning(f"Chat PDF open failed: {e}")

            # ==================================================
            # 📝 SAVE LOG
            # ==================================================
            log = SmsWhatsAppLog.objects.create(
                job_id=job_id,
                customer_name=name,
                mobile=mobile,
                template_name=template_choice,
                sent_text_message=rendered_text,
                status="Delivered",
                message_id=msg_id,
                message_type="Sent",
                content_type=content_type_val,
            )
            ChatContact.objects.update_or_create(
                mobile=mobile,
                defaults={
                    "last_msg": rendered_text or "[Media]",
                    "last_time": timezone.now(),
                    "last_type": "Sent",
                    "last_status": "Delivered",
                    "unread": 0 
                }
               )
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "global_contacts",
            {
                "type": "contact.update",
                "contact": {
            "mobile": mobile,
            "last_msg": rendered_text or "[Media]",
            "last_time": timezone.now().isoformat(),
            "last_type": "Sent",
            "last_status": "Delivered",
            "unread": 0
        }
    }
)

            # ==================================================
            # 📎 ATTACH PDF FILE
            # ==================================================
            if media_file_obj:
                try:
                    media_file_obj.seek(0)
                    pdf_bytes = media_file_obj.read()

                    file_buffer = io.BytesIO(pdf_bytes)

                    log.media_file.save(
                        pdf_source,
                        ContentFile(file_buffer.getvalue())
                    )
                    log.save()

                except Exception as e:
                    logger.warning(f"Chat PDF save failed: {e}")

            local_success += 1

        except Exception as e:
            SmsWhatsAppLog.objects.create(
                job_id=job_id,
                customer_name=name,
                mobile=mobile,
                template_name=template_choice,
                status="Failed",
                message_type="Sent",
                error_message=str(e),
            )
            local_failed += 1

        time.sleep(0.3)
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


@shared_task(bind=True, queue="whatsapp_main")
def finalize_bulk_job(self, job_id):

    try:
        job = BulkJob.objects.get(job_id=job_id)
    except BulkJob.DoesNotExist:
        return

    # Prevent double execution
    if job.success_report and job.failed_report:
        return

    success_qs = SmsWhatsAppLog.objects.filter(
        job_id=job_id,
        status__in=["Sent", "Delivered"]
    )

    failed_qs = SmsWhatsAppLog.objects.filter(
        job_id=job_id,
        status="Failed"
    )

    success_df = pd.DataFrame(list(success_qs.values()))
    failed_df = pd.DataFrame(list(failed_qs.values()))

    # 🔥 REMOVE TIMEZONE FROM DATETIME COLUMNS
    for df in [success_df, failed_df]:
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].dt.tz_localize(None)

    success_path = f"reports/{job_id}_success.xlsx"
    failed_path = f"reports/{job_id}_failed.xlsx"

    success_buffer = io.BytesIO()
    failed_buffer = io.BytesIO()

    success_df.to_excel(success_buffer, index=False)
    failed_df.to_excel(failed_buffer, index=False)

    if default_storage.exists(success_path):
        default_storage.delete(success_path)

    if default_storage.exists(failed_path):
        default_storage.delete(failed_path)

    default_storage.save(success_path, ContentFile(success_buffer.getvalue()))
    default_storage.save(failed_path, ContentFile(failed_buffer.getvalue()))

    job.success_report = success_path
    job.failed_report = failed_path
    job.status = "Completed"
    job.completed_at = timezone.now()

    job.save(update_fields=[
        "success_report",
        "failed_report",
        "status",
        "completed_at"
    ])

    logger.info("Job %s COMPLETED and reports generated", job_id)


