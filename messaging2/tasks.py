import io
import time
import logging
from math import ceil
from django.core.files.base import ContentFile
from .utils import open_legal_pdf2

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

from .models import SmsWhatsAppLog2, BulkJob2
from .utils import build_payload2, format_mobile2, check_whatsapp_number2

logger = get_task_logger(__name__)
logger.setLevel(logging.INFO)

# -------------------------------------------------
# HTTP SESSION
# -------------------------------------------------
def make_session():
    s = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
    )
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.headers.update({"Content-Type": "application/json"})
    return s


# ==================================================
# MAIN BULK JOB
# ==================================================
@shared_task(bind=True)
def process_bulk_whatsapp2(self, excel_s3_path, template_choice, job_id, chunk_size=50):

    close_old_connections()
    try:
        job = BulkJob2.objects.get(job_id=job_id)
    except BulkJob2.DoesNotExist:
        logger.error("Job2 %s not found", job_id)
        return

    # Check if job already completed
    if job.status == "Completed":
        logger.info(f"Job2 {job_id} already completed, skipping")
        return

    job.status = "Queued"
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])

    try:
        with default_storage.open(excel_s3_path, "rb") as f:
            bytes_data = f.read()
        df = pd.read_excel(io.BytesIO(bytes_data), dtype=str).fillna("")
    except Exception as e:
        logger.exception("Failed to read Excel for job2 %s: %s", job_id, e)
        job.status = "Failed"
        job.save(update_fields=["status"])
        return

    rows = df.to_dict("records")
    total = len(rows)

    job.total_customers = total
    job.save(update_fields=["total_customers"])

    if total == 0:
        job.status = "Completed"
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at"])
        return

    for i in range(0, total, chunk_size):
        start = i
        end = min(i + chunk_size, total)
        process_bulk_whatsapp2_batch.apply_async(
            args=(excel_s3_path, template_choice, job_id, start, end),
            queue="whatsapp_secondary",
        )

    job.status = "Running"
    job.save(update_fields=["status"])

    finalize_bulk_job2.apply_async((job_id,), countdown=10, queue="whatsapp_secondary")

# ==================================================
# BATCH WORKER (FINAL PRODUCTION VERSION WITH ANTI-DUPLICATE)
# ==================================================
@shared_task(bind=True)
def process_bulk_whatsapp2_batch(self, excel_s3_path, template_choice, job_id, start, end):

    logger.info("Job2 batch %s rows [%d:%d] started", job_id, start, end)
    close_old_connections()

    # --------------------------------------------------
    # PREVENT RE-PROCESSING ON CELERY RESTART
    # Check if this batch was already processed
    # --------------------------------------------------
    try:
        job = BulkJob2.objects.get(job_id=job_id)
        
        # If job is already Completed, don't process
        if job.status == "Completed":
            logger.info(f"Job2 {job_id} already completed, skipping batch {start}-{end}")
            return
            
        # Check if this specific batch might have been processed
        # by looking at sent_count vs expected
        if job.sent_count >= end:
            logger.info(f"Batch {start}-{end} for job {job_id} appears already processed, skipping")
            return
            
    except BulkJob2.DoesNotExist:
        logger.warning("Job2 %s deleted. Stopping batch [%d:%d]", job_id, start, end)
        return

    # --------------------------------------------------
    # READ EXCEL
    # --------------------------------------------------
    try:
        with default_storage.open(excel_s3_path, "rb") as f:
            bytes_data = f.read()

        df = pd.read_excel(io.BytesIO(bytes_data), dtype=str).fillna("")
        rows = df.to_dict("records")[start:end]

    except Exception as e:
        logger.exception("Batch read error job2 %s: %s", job_id, e)
        return

    # --------------------------------------------------
    # WHATSAPP SESSION
    # --------------------------------------------------
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {settings.WHATSAPP2_ACCESS_TOKEN}"
    })

    post_url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP2_PHONE_NUMBER_ID}/messages"

    success_records = []
    failed_records = []
    local_success = 0
    local_failed = 0

    # --------------------------------------------------
    # PROCESS EACH ROW
    # --------------------------------------------------
    for idx, row in enumerate(rows, start=start):

        if idx % 20 == 0:
            close_old_connections()

        name = row.get("customer_name") or row.get("CustomerName") or ""
        raw_mobile = row.get("cust_mobile") or row.get("CustMobile") or ""
        mobile = format_mobile2(raw_mobile)
        
        # Skip if no mobile
        if not mobile:
            reason = "No mobile number provided"
            SmsWhatsAppLog2.objects.create(
                customer_name=name,
                mobile=mobile,
                template_name=template_choice,
                sent_text_message="",
                status="Failed",
                message_id="",
                content_type="text",
                error_message=reason,
            )
            failed_records.append([name, mobile, reason])
            local_failed += 1
            continue
            
        # ----------------------------------------------
        # CHECK WHATSAPP NUMBER
        # ----------------------------------------------
        try:
            check = check_whatsapp_number2(mobile)
        except Exception as e:
            logger.exception("check_whatsapp_number2 error for %s: %s", mobile, e)
            check = {"valid": False, "reason": "check error"}

        if not check.get("valid", False):
            reason = check.get("reason") or "Invalid or blocked"

            SmsWhatsAppLog2.objects.create(
                customer_name=name,
                mobile=mobile,
                template_name=template_choice,
                sent_text_message="",
                status="Failed",
                message_id="",
                content_type="text",
                error_message=reason,
            )

            failed_records.append([name, mobile, reason])
            local_failed += 1
            continue

        # ----------------------------------------------
        # BUILD PAYLOAD + TEMPLATE TEXT
        # ----------------------------------------------
        try:
            payload, rendered_text = build_payload2(template_choice, row)
        except Exception as e:
            reason = f"build_payload_error: {e}"

            logger.exception("Payload build error job2 %s row %s: %s", job_id, idx, e)

            SmsWhatsAppLog2.objects.create(
                customer_name=name,
                mobile=mobile,
                template_name=template_choice,
                sent_text_message="",
                status="Failed",
                message_id="",
                content_type="text",
                error_message=reason,
            )

            failed_records.append([name, mobile, reason])
            local_failed += 1
            continue

        # ----------------------------------------------
        # SEND WHATSAPP MESSAGE
        # ----------------------------------------------
        try:
            resp = session.post(post_url, json=payload, timeout=30)

            try:
                j = resp.json()
            except Exception:
                j = {"error": {"message": resp.text, "code": resp.status_code}}

            # =====================================================
            # SUCCESS — MESSAGE SENT
            # =====================================================
            if resp.ok and isinstance(j, dict) and j.get("messages"):

                msg_id = j["messages"][0].get("id", "")

                # ----------------------------------------------
                # DETERMINE CONTENT TYPE
                # ----------------------------------------------
                content_type = "text"
                media_filename = None

                if template_choice in ("13", "14", "21", "22", "23", "24"):
                    content_type = "document"

                    if template_choice == "14":
                        media_filename = row.get("guarantor_pdf_file")
                    elif template_choice == "21":
                        media_filename = row.get("smf_lok_doc_file")
                    elif template_choice == "22":
                        media_filename = row.get("smf_guarantor_pdf_file")
                    elif template_choice == "23":
                        media_filename = row.get("psf_customer_pdf_file")
                    elif template_choice == "24":
                        media_filename = row.get("psf_guarantor_pdf_file")
                    else:
                        media_filename = row.get("borrower_pdf_file") or row.get("customer_pdf_file")

                # ----------------------------------------------
                # SAVE MESSAGE LOG (IMPORTANT)
                # ----------------------------------------------
                log = SmsWhatsAppLog2.objects.create(
                    customer_name=name,
                    mobile=mobile,
                    template_name=template_choice,
                    sent_text_message=rendered_text,
                    status="Delivered",
                    message_id=msg_id,
                    content_type=content_type,
                    error_message="",
                )

                # ----------------------------------------------
                # ATTACH LEGAL DOCUMENT TO LOG
                # ----------------------------------------------
                if content_type == "document" and media_filename:
                    try:
                        with open_legal_pdf2(media_filename) as f:
                            log.media_file.save(
                                media_filename,
                                ContentFile(f.read()),
                                save=True
                            )
                    except Exception as e:
                        logger.warning(
                            "Failed attaching legal PDF %s for mobile %s: %s",
                            media_filename,
                            mobile,
                            e
                        )

                success_records.append([name, mobile, msg_id])
                local_success += 1

            # =====================================================
            # WHATSAPP ERROR RESPONSE
            # =====================================================
            else:
                err = j.get("error", {})
                err_msg = f"{err.get('code')} - {err.get('message')}"

                SmsWhatsAppLog2.objects.create(
                    customer_name=name,
                    mobile=mobile,
                    template_name=template_choice,
                    sent_text_message=rendered_text,
                    status="Failed",
                    message_id="",
                    content_type="text",
                    error_message=err_msg,
                )

                failed_records.append([name, mobile, err_msg])
                local_failed += 1

        # =====================================================
        # NETWORK ERROR
        # =====================================================
        except requests.RequestException as e:
            err_msg = str(e)

            logger.exception("HTTP error job2 sending to %s: %s", mobile, e)

            SmsWhatsAppLog2.objects.create(
                customer_name=name,
                mobile=mobile,
                template_name=template_choice,
                sent_text_message=rendered_text,
                status="Failed",
                message_id="",
                content_type="text",
                error_message=err_msg,
            )

            failed_records.append([name, mobile, err_msg])
            local_failed += 1

        # ----------------------------------------------
        # RATE LIMIT PROTECTION
        # ----------------------------------------------
        time.sleep(0.5)

    # --------------------------------------------------
    # UPDATE JOB COUNTERS
    # --------------------------------------------------
    try:
        with transaction.atomic():
            BulkJob2.objects.filter(job_id=job_id).update(
                sent_count=F("sent_count") + (local_success + local_failed),
                success_count=F("success_count") + local_success,
                failed_count=F("failed_count") + local_failed,
            )
    except Exception:
        logger.exception("Failed updating counters for job2 %s", job_id)

    # --------------------------------------------------
    # SAVE REPORT FILES
    # --------------------------------------------------
    try:
        if success_records:
            buf = io.BytesIO()
            pd.DataFrame(success_records, columns=["Name", "Mobile", "MessageID"]).to_excel(buf, index=False)
            buf.seek(0)
            default_storage.save(
                f"reports2/success_{job_id}_{start}_{end}.xlsx",
                ContentFile(buf.read()),
            )

        if failed_records:
            buf = io.BytesIO()
            pd.DataFrame(failed_records, columns=["Name", "Mobile", "Reason"]).to_excel(buf, index=False)
            buf.seek(0)
            default_storage.save(
                f"reports2/failed_{job_id}_{start}_{end}.xlsx",
                ContentFile(buf.read()),
            )
    except Exception:
        logger.exception("Failed saving batch reports for job2 %s [%d:%d]", job_id, start, end)

    logger.info(
        "Job2 batch %s rows [%d:%d] finished (success=%d failed=%d)",
        job_id, start, end, local_success, local_failed
    )

# ==================================================
# FINALIZER (FIXED WITH ANTI-DUPLICATE CHECK)
# ==================================================
@shared_task(bind=True)
def finalize_bulk_job2(self, job_id):

    try:
        job = BulkJob2.objects.get(job_id=job_id)
    except BulkJob2.DoesNotExist:
        return

    # PREVENT RE-FINALIZING
    if job.status == "Completed":
        logger.info(f"Job2 {job_id} already completed, skipping finalize")
        return

    total = job.total_customers or 0
    sent = job.sent_count or 0

    if sent < total:
        logger.info("Job2 %s still running (%s/%s)", job_id, sent, total)
        return

    job.status = "Completed"
    job.completed_at = timezone.now()
    job.save(update_fields=["status", "completed_at"])

    logger.info("FINALIZED job2 %s", job_id)
