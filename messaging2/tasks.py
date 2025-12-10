# messaging2/tasks.py
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

from .models import SmsWhatsAppLog2, BulkJob2
from .utils import build_payload2, format_mobile2, check_whatsapp_number2

logger = get_task_logger(__name__)
logger.setLevel(logging.INFO)

def make_session():
    s = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.headers.update({"Content-Type": "application/json"})
    return s


@shared_task(bind=True)
def process_bulk_whatsapp2(self, excel_s3_path, template_choice, job_id, chunk_size=50):
    close_old_connections()
    try:
        job = BulkJob2.objects.get(job_id=job_id)
    except BulkJob2.DoesNotExist:
        logger.error("Job2 %s not found", job_id)
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

    num_chunks = ceil(total / chunk_size)
    logger.info("Job2 %s: %d rows split into %d chunks (chunk_size=%d)", job_id, total, num_chunks, chunk_size)

    for i in range(0, total, chunk_size):
        start = i
        end = min(i + chunk_size, total)
        process_bulk_whatsapp2_batch.apply_async(args=(excel_s3_path, template_choice, job_id, start, end))

    job.status = "Running"
    job.save(update_fields=["status"])
    # 🔥 Schedule finalizer (checks when all batches finish)
    finalize_bulk_job2.apply_async((job_id,), countdown=5)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def process_bulk_whatsapp2_batch(self, excel_s3_path, template_choice, job_id, start, end):
    logger.info("Job2 batch %s rows [%d:%d] started", job_id, start, end)
    close_old_connections()

    try:
        job = BulkJob2.objects.get(job_id=job_id)
    except BulkJob2.DoesNotExist:
        logger.error("Job2 %s not found", job_id)
        return

    try:
        with default_storage.open(excel_s3_path, "rb") as f:
            bytes_data = f.read()
        df = pd.read_excel(io.BytesIO(bytes_data), dtype=str).fillna("")
        rows = df.to_dict("records")[start:end]
    except Exception as e:
        logger.exception("Batch read error job2 %s: %s", job_id, e)
        raise

    session = make_session()
    session.headers.update({"Authorization": f"Bearer {settings.WHATSAPP2_ACCESS_TOKEN}"})
    post_url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP2_PHONE_NUMBER_ID}/messages"

    success_records = []
    failed_records = []
    local_success = 0
    local_failed = 0

    for idx, row in enumerate(rows, start=start):
        if idx % 20 == 0:
            close_old_connections()

        name = row.get("customer_name") or row.get("CustomerName") or ""
        raw_mobile = row.get("cust_mobile") or row.get("CustMobile") or ""
        mobile = format_mobile2(raw_mobile)

        try:
            check = check_whatsapp_number2(mobile)
        except Exception as e:
            logger.exception("check_whatsapp_number2 error for %s: %s", mobile, e)
            check = {"valid": False, "reason": "check error"}

        if not check.get("valid", False):
            reason = check.get("reason") or "Invalid or blocked"
            failed_records.append([name, mobile, reason])
            local_failed += 1
            SmsWhatsAppLog2.objects.create(
                customer_name=name,
                mobile=mobile,
                template_name=template_choice,
                sent_text_message="",
                status="Failed",
                message_id="",
                error_message=reason,
            )
            continue

        try:
            payload, rendered_text = build_payload2(template_choice, row)
        except Exception as e:
            reason = f"build_payload_error: {e}"
            logger.exception("Payload build error job2 %s row %s: %s", job_id, idx, e)
            failed_records.append([name, mobile, reason])
            local_failed += 1
            SmsWhatsAppLog2.objects.create(
                customer_name=name,
                mobile=mobile,
                template_name=template_choice,
                sent_text_message="",
                status="Failed",
                message_id="",
                error_message=reason,
            )
            continue

        try:
            resp = session.post(post_url, json=payload, timeout=30)
            try:
                j = resp.json()
            except Exception:
                j = {"error": {"message": f"Non-JSON response: {resp.text}", "code": resp.status_code}}

            if resp.ok and isinstance(j, dict) and j.get("messages"):
                msg_id = j["messages"][0].get("id", "")
                SmsWhatsAppLog2.objects.create(
                    customer_name=name,
                    mobile=mobile,
                    template_name=template_choice,
                    sent_text_message=rendered_text,
                    status="Delivered",
                    message_id=msg_id,
                    error_message="",
                )
                success_records.append([name, mobile, msg_id])
                local_success += 1
            else:
                if isinstance(j, dict) and j.get("error"):
                    err = j["error"]
                    err_msg = f"{err.get('code')} - {err.get('message')}"
                else:
                    err_msg = str(j)
                SmsWhatsAppLog2.objects.create(
                    customer_name=name,
                    mobile=mobile,
                    template_name=template_choice,
                    sent_text_message=rendered_text,
                    status="Failed",
                    message_id="",
                    error_message=err_msg,
                )
                failed_records.append([name, mobile, err_msg])
                local_failed += 1

        except requests.RequestException as e:
            logger.exception("HTTP error job2 sending to %s: %s", mobile, e)
            err_msg = str(e)
            SmsWhatsAppLog2.objects.create(
                customer_name=name,
                mobile=mobile,
                template_name=template_choice,
                sent_text_message=rendered_text,
                status="Failed",
                message_id="",
                error_message=err_msg,
            )
            failed_records.append([name, mobile, err_msg])
            local_failed += 1

        time.sleep(0.5)  # rate limiting

    try:
        with transaction.atomic():
            BulkJob2.objects.filter(job_id=job_id).update(
                sent_count=F('sent_count') + (local_success + local_failed),
                success_count=F('success_count') + local_success,
                failed_count=F('failed_count') + local_failed
            )
    except Exception:
        logger.exception("Failed updating counters for job2 %s", job_id)

    # Save batch report
    try:
        if success_records:
            buf = io.BytesIO()
            pd.DataFrame(success_records, columns=["Name", "Mobile", "MessageID"]).to_excel(buf, index=False)
            buf.seek(0)
            key = f"reports2/success_{job_id}_{start}_{end}.xlsx"
            default_storage.save(key, ContentFile(buf.read()))
        if failed_records:
            buf = io.BytesIO()
            pd.DataFrame(failed_records, columns=["Name", "Mobile", "Reason"]).to_excel(buf, index=False)
            buf.seek(0)
            key = f"reports2/failed_{job_id}_{start}_{end}.xlsx"
            default_storage.save(key, ContentFile(buf.read()))
    except Exception:
        logger.exception("Failed to save batch reports for job2 %s [%d:%d]", job_id, start, end)

    logger.info("Job2 batch %s rows [%d:%d] finished (success=%d failed=%d)",
                job_id, start, end, local_success, local_failed)








# ------------------------------------------------------------
# FINALIZER – Marks job2 as Completed when all batches finish
# ------------------------------------------------------------
@shared_task
def finalize_bulk_job2(job_id):
    try:
        job = BulkJob2.objects.get(job_id=job_id)

        # All rows processed?
        if job.sent_count >= job.total_customers:
            job.status = "Completed"
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "completed_at"])
            logger.info(f"Job2 {job_id} marked as COMPLETED.")
        else:
            # Not done yet — check again after 10 sec
            finalize_bulk_job2.apply_async((job_id,), countdown=10)

    except Exception as e:
        logger.exception(f"Finalize job2 failed for {job_id}: {e}")
