import asyncio
import aiohttp
import pandas as pd
from asgiref.sync import sync_to_async
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from .models import SmsWhatsAppLog, BulkJob
from .utils import build_payload  # must return (payload, rendered_text)


async def send_whatsapp_async(session, payload):
    """
    Send WhatsApp message asynchronously using Meta Cloud API.
    """
    url = f"https://graph.facebook.com/v17.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        async with session.post(url, headers=headers, json=payload, timeout=30) as resp:
            return await resp.json()
    except Exception as e:
        return {"error": {"message": str(e)}}


@shared_task
def process_bulk_whatsapp(excel_path, template_choice, job_id):
    """
    Celery task to send bulk WhatsApp messages.
    Fetches dynamic templates, replaces variables, sends messages, and logs status.
    """

    async def run_sends():
        # ✅ Fetch job from DB
        job = await sync_to_async(BulkJob.objects.get)(job_id=job_id)
        job.status = "Running"
        await sync_to_async(job.save)(update_fields=["status"])

        # ✅ Load Excel data
        df = pd.read_excel(excel_path, dtype=str).fillna("")
        success_records, failed_records = [], []
        success_count, failed_count = 0, 0

        async with aiohttp.ClientSession() as session:
            rows = df.to_dict("records")

            for i in range(0, len(rows), 15):  # batch sending
                batch = rows[i:i + 15]
                tasks, payloads, messages = [], [], []

                for row in batch:
                    try:
                        # ✅ Build payload and rendered text
                        payload, rendered_text = build_payload(template_choice, row)
                        payloads.append(payload)
                        messages.append(rendered_text)
                        tasks.append(send_whatsapp_async(session, payload))
                    except Exception as e:
                        failed_records.append([
                            row.get("customer_name") or row.get("CustomerName"),
                            row.get("cust_mobile") or row.get("CustMobile"),
                            str(e)
                        ])
                        failed_count += 1
                        continue

                # ✅ Send all in parallel
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

                    # ✅ Log WhatsApp message
                    await sync_to_async(SmsWhatsAppLog.objects.create)(
                        customer_name=name,
                        mobile=mobile,
                        template_name=template_choice,
                        sent_text_message=rendered_text,
                        status=status,
                        message_id=msg_id,
                        error_message=err,
                    )

                # ✅ Update job progress
                job.sent_count += len(batch)
                job.success_count = success_count
                job.failed_count = failed_count
                await sync_to_async(job.save)(
                    update_fields=["sent_count", "success_count", "failed_count"]
                )

                await asyncio.sleep(1)

        # ✅ Export reports
        pd.DataFrame(success_records, columns=["Name", "Mobile", "MessageID"]).to_excel(
            "success_report.xlsx", index=False
        )
        pd.DataFrame(failed_records, columns=["Name", "Mobile", "Error"]).to_excel(
            "failed_report.xlsx", index=False
        )

        # ✅ Mark job as complete
        job.status = "Completed"
        job.completed_at = timezone.now()
        await sync_to_async(job.save)(update_fields=["status", "completed_at"])

    asyncio.run(run_sends())
