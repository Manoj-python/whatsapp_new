# messaging/tasks.py
import io
import time
import logging
from math import ceil

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

from .models import SmsWhatsAppLog, BulkJob
from .utils import build_payload, format_mobile, check_whatsapp_number

logger = get_task_logger(__name__)
logger.setLevel(logging.INFO)


# -----------------------------
# HTTP SESSION (RETRIES)
# -----------------------------
def make_session():
    s = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.headers.update({"Content-Type": "application/json"})
    return s


# -----------------------------
# MAIN BULK JOB
# -----------------------------
@shared_task(bind=True)
def process_bulk_whatsapp(self, excel_s3_path, template_choice, job_id, chunk_size=50):
    try:
        close_old_connections()
        job = BulkJob.objects.get(job_id=job_id)
    except BulkJob.DoesNotExist:
        logger.error("Job %s not found", job_id)
        return

    job.status = "Queued"
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])

    # Read excel
    try:
        with default_storage.open(excel_s3_path, "rb") as f:
            data = f.read()
        df = pd.read_excel(io.BytesIO(data), dtype=str).fillna("")
    except Exception as e:
        logger.exception("Failed reading Excel for job %s: %s", job_id, e)
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

    # Split into chunks
    for i in range(0, total, chunk_size):
        start = i
        end = min(i + chunk_size, total)

        process_bulk_whatsapp_batch.apply_async(
            args=(excel_s3_path, template_choice, job_id, start, end),
            queue="whatsapp_main"        # IMPORTANT
        )

    job.status = "Running"
    job.save(update_fields=["status"])

    # Schedule finalizer
    finalize_bulk_job.apply_async((job_id,), countdown=10, queue="whatsapp_main")


# -----------------------------
# BATCH WORKER
# -----------------------------
@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def process_bulk_whatsapp_batch(self, excel_s3_path, template_choice, job_id, start, end):

    logger.info("Batch job %s rows [%d:%d] STARTED", job_id, start, end)
    close_old_connections()

    try:
        job = BulkJob.objects.get(job_id=job_id)
    except BulkJob.DoesNotExist:
        return

    # Read excel slice
    try:
        with default_storage.open(excel_s3_path, "rb") as f:
            data = f.read()
        df = pd.read_excel(io.BytesIO(data), dtype=str).fillna("")
        rows = df.to_dict("records")[start:end]
    except Exception as e:
        logger.exception("Batch read error %s: %s", job_id, e)
        raise

    session = make_session()
    session.headers.update({"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"})
    post_url = f"https://graph.facebook.com/v17.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"

    success_records = []
    failed_records = []
    local_success = 0
    local_failed = 0

    for idx, row in enumerate(rows, start=start):

        if idx % 20 == 0:
            close_old_connections()

        name = row.get("customer_name") or row.get("CustomerName") or ""
        raw_mobile = row.get("cust_mobile") or row.get("CustMobile") or ""
        mobile = format_mobile(raw_mobile)

        # WhatsApp validation
        try:
            check = check_whatsapp_number(mobile)
        except Exception as e:
            logger.exception("check_whatsapp_number error: %s", e)
            check = {"valid": False, "reason": "Error validating"}
        
        if not check.get("valid", False):
            reason = check.get("reason")
            failed_records.append([name, mobile, reason])
            local_failed += 1
            SmsWhatsAppLog.objects.create(
                customer_name=name,
                mobile=mobile,
                template_name=template_choice,
                sent_text_message="",
                status="Failed",
                message_id="",
                error_message=reason,
            )
            continue

        # Build payload
        try:
            payload, rendered_text = build_payload(template_choice, row)
        except Exception as e:
            reason = f"Payload build error: {e}"
            failed_records.append([name, mobile, reason])
            local_failed += 1
            SmsWhatsAppLog.objects.create(
                customer_name=name,
                mobile=mobile,
                template_name=template_choice,
                sent_text_message="",
                status="Failed",
                message_id="",
                error_message=reason,
            )
            continue

        # Send message
        try:
            resp = session.post(post_url, json=payload, timeout=30)
            j = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}

            if resp.ok and j.get("messages"):
                msg_id = j["messages"][0]["id"]
                SmsWhatsAppLog.objects.create(
                    customer_name=name,
                    mobile=mobile,
                    template_name=template_choice,
                    sent_text_message=rendered_text,
                    status="Delivered",
                    message_id=msg_id,
                )
                success_records.append([name, mobile, msg_id])
                local_success += 1
            else:
                error_msg = j.get("error", {}).get("message", "Unknown error")
                failed_records.append([name, mobile, error_msg])
                local_failed += 1
                SmsWhatsAppLog.objects.create(
                    customer_name=name,
                    mobile=mobile,
                    template_name=template_choice,
                    sent_text_message=rendered_text,
                    status="Failed",
                    error_message=error_msg,
                )
        except Exception as e:
            logger.exception("HTTP error sending: %s", e)
            failed_records.append([name, mobile, str(e)])
            local_failed += 1

        time.sleep(0.5)

    # Update counters
    try:
        with transaction.atomic():
            BulkJob.objects.filter(job_id=job_id).update(
                sent_count=F("sent_count") + local_success + local_failed,
                success_count=F("success_count") + local_success,
                failed_count=F("failed_count") + local_failed,
            )
    except Exception:
        logger.exception("Counter update failed for job %s", job_id)

    # Save batch reports
    try:
        if success_records:
            buf = io.BytesIO()
            pd.DataFrame(success_records, columns=["Name", "Mobile", "MessageID"]).to_excel(buf, index=False)
            buf.seek(0)
            default_storage.save(f"reports/success_{job_id}_{start}_{end}.xlsx", ContentFile(buf.read()))

        if failed_records:
            buf = io.BytesIO()
            pd.DataFrame(failed_records, columns=["Name", "Mobile", "Reason"]).to_excel(buf, index=False)
            buf.seek(0)
            default_storage.save(f"reports/failed_{job_id}_{start}_{end}.xlsx", ContentFile(buf.read()))
    except Exception:
        logger.exception("Failed saving batch files")

    logger.info("Batch job %s rows [%d:%d] DONE", job_id, start, end)


# -----------------------------
# FINALIZER — waits for all batches before merging
# -----------------------------
@shared_task(bind=True)
def finalize_bulk_job(self, job_id):

    try:
        job = BulkJob.objects.get(job_id=job_id)
    except BulkJob.DoesNotExist:
        return

    total = job.total_customers or 0
    sent = job.sent_count or 0

    # Not finished yet — check again
    if sent < total:
        finalize_bulk_job.apply_async((job_id,), countdown=10, queue="whatsapp_main")
        return

    success_files = []
    failed_files = []

    try:
        dirs, files = default_storage.listdir("reports")
    except Exception:
        files = []

    for f in files:
        if f.startswith(f"success_{job_id}_"):
            success_files.append("reports/" + f)
        elif f.startswith(f"failed_{job_id}_"):
            failed_files.append("reports/" + f)

    # Merge success
    if success_files:
        frames = []
        for k in success_files:
            try:
                with default_storage.open(k, "rb") as f:
                    frames.append(pd.read_excel(f))
            except:
                pass
        if frames:
            df = pd.concat(frames, ignore_index=True)
            buf = io.BytesIO()
            df.to_excel(buf, index=False)
            buf.seek(0)
            final_key = f"reports/final_success_{job_id}.xlsx"
            default_storage.save(final_key, ContentFile(buf.read()))
            job.success_report = final_key

    # Merge failed
    if failed_files:
        frames = []
        for k in failed_files:
            try:
                with default_storage.open(k, "rb") as f:
                    frames.append(pd.read_excel(f))
            except:
                pass
        if frames:
            df = pd.concat(frames, ignore_index=True)
            buf = io.BytesIO()
            df.to_excel(buf, index=False)
            buf.seek(0)
            final_key = f"reports/final_failed_{job_id}.xlsx"
            default_storage.save(final_key, ContentFile(buf.read()))
            job.failed_report = final_key

    job.status = "Completed"
    job.completed_at = timezone.now()

    update_fields = ["status", "completed_at"]
    if job.success_report:
        update_fields.append("success_report")
    if job.failed_report:
        update_fields.append("failed_report")

    job.save(update_fields=update_fields)

    logger.info("FINALIZED job %s", job_id)
