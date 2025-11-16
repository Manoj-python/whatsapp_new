import os
import asyncio
import aiohttp
import pandas as pd
from asgiref.sync import sync_to_async
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from .models import SmsWhatsAppLog2, BulkJob2
from .utils import build_payload2  # must return (payload, rendered_text)


# ----------------------------------------------------------
# Async Helper: Send WhatsApp message via Cloud API (App2)
# ----------------------------------------------------------
async def send_whatsapp2_async(session, payload):
    """
    Send WhatsApp message asynchronously using App2 Meta Cloud API.
    """
    url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP2_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP2_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        async with session.post(url, headers=headers, json=payload, timeout=30) as resp:
            return await resp.json()
    except Exception as e:
        return {"error": {"message": str(e)}}


# ----------------------------------------------------------
# Celery Task: Bulk WhatsApp Sending (App2)
# ----------------------------------------------------------
@shared_task
def process_bulk_whatsapp2(excel_path, template_choice, job_id):
    """
    Celery task for sending bulk WhatsApp messages using App2 credentials.
    Supports async I/O for better performance.
    """

    async def run_sends():
        # ✅ Load job safely
        try:
            job = await sync_to_async(BulkJob2.objects.get)(job_id=job_id)
        except BulkJob2.DoesNotExist:
            print(f"[ERROR] Job {job_id} not found.")
            return

        job.status = "Running"
        await sync_to_async(job.save)(update_fields=["status"])

        # ✅ Read Excel
        df = pd.read_excel(excel_path, dtype=str).fillna("")
        success_records, failed_records = [], []
        success_count, failed_count = 0, 0

        async with aiohttp.ClientSession() as session:
            rows = df.to_dict("records")

            # ✅ Process rows in batches
            for i in range(0, len(rows), 15):
                batch = rows[i:i + 15]
                tasks, payloads, messages = [], [], []

                for row in batch:
                    try:
                        payload, rendered_text = build_payload2(template_choice, row)
                        payloads.append(payload)
                        messages.append(rendered_text)
                        tasks.append(send_whatsapp2_async(session, payload))
                    except Exception as e:
                        failed_records.append([
                            row.get("customer_name") or row.get("CustomerName"),
                            row.get("cust_mobile") or row.get("CustMobile"),
                            str(e)
                        ])
                        failed_count += 1
                        continue

                # ✅ Send concurrently
                responses = await asyncio.gather(*tasks, return_exceptions=True)

                for row, result, payload, rendered_text in zip(batch, responses, payloads, messages):
                    name = row.get("customer_name") or row.get("CustomerName") or ""
                    mobile = row.get("cust_mobile") or row.get("CustMobile") or ""

                    try:
                        if isinstance(result, dict) and "messages" in result:
                            status = "Delivered"
                            msg_id = result["messages"][0].get("id", "")
                            err = ""
                            success_records.append([name, mobile, msg_id])
                            success_count += 1
                        else:
                            status = "Failed"
                            msg_id = ""
                            err = (
                                (result.get("error") and result["error"].get("message"))
                                if isinstance(result, dict)
                                else str(result)
                            )
                            failed_records.append([name, mobile, err])
                            failed_count += 1
                    except Exception as e:
                        status, msg_id, err = "Error", "", str(e)
                        failed_records.append([name, mobile, err])
                        failed_count += 1

                    # ✅ Log to DB
                    await sync_to_async(SmsWhatsAppLog2.objects.create)(
                        customer_name=name,
                        mobile=mobile,
                        template_name=template_choice,
                        sent_text_message=rendered_text,
                        status=status,
                        message_id=msg_id,
                        error_message=err,
                    )

                # ✅ Update job progress incrementally
                job.sent_count += len(batch)
                job.success_count = success_count
                job.failed_count = failed_count
                await sync_to_async(job.save)(
                    update_fields=["sent_count", "success_count", "failed_count"]
                )

                await asyncio.sleep(1)  # prevent API throttling

        # ✅ Ensure report directories exist
        reports_dir = os.path.join(settings.MEDIA_ROOT, "reports2")
        os.makedirs(reports_dir, exist_ok=True)

        success_path = os.path.join(reports_dir, f"success_report_{job_id}.xlsx")
        failed_path = os.path.join(reports_dir, f"failed_report_{job_id}.xlsx")

        # ✅ Write reports
        if success_records:
            pd.DataFrame(success_records, columns=["Name", "Mobile", "MessageID"]).to_excel(success_path, index=False)
        if failed_records:
            pd.DataFrame(failed_records, columns=["Name", "Mobile", "Error"]).to_excel(failed_path, index=False)

        # ✅ Update final job
        job.success_report = success_path.replace(settings.MEDIA_ROOT + "/", "")
        job.failed_report = failed_path.replace(settings.MEDIA_ROOT + "/", "")
        job.status = "Completed"
        job.completed_at = timezone.now()
        await sync_to_async(job.save)(
            update_fields=["status", "completed_at", "success_report", "failed_report"]
        )

    asyncio.run(run_sends())
