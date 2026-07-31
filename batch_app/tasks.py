# batch_app/tasks.py - COMPLETE PRODUCTION READY VERSION WITH API CHECK
# ✅ PERFECT DATE/TIME HANDLING FOR ALL SCHEDULE TYPES
# ✅ MULTIPLE DAILY - EACH RUN MOVES TO NEXT BATCH
# ✅ DAILY/WEEKLY/CUSTOM - DAY-BY-DAY BATCH PROCESSING
# ✅ FIXED: job.save() REPLACED WITH update_fields TO PREVENT schedule_datetime MODIFICATION
# ✅ ADDED: API CHECK FOR PAID/UNPAID CUSTOMERS
# ✅ ADDED: SKIPPED COUNT TRACKING

import time
import logging
import re
from datetime import datetime, timedelta
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django.db import close_old_connections, DatabaseError
import requests
import importlib
import traceback

from .models import BatchJob, BatchLog
from .utils import format_mobile, get_batch_from_s3, read_excel_from_s3
from .app_discovery import get_app_by_name, get_app_log_model, get_app_contact_model, get_app_utils

logger = logging.getLogger(__name__)


def get_build_payload_function(app_name):
    """Dynamically import the build_payload function from the target app's utils"""
    try:
        utils = get_app_utils(app_name)

        if 'build_payload' in utils:
            return utils['build_payload']
        elif 'build_payload2' in utils:
            return utils['build_payload2']
        else:
            if app_name == 'messaging':
                from messaging.utils import build_payload
                return build_payload
            elif app_name == 'messaging2':
                from messaging2.utils import build_payload2
                return build_payload2
            else:
                return None
    except Exception as e:
        logger.error(f"❌ Failed to import build_payload for {app_name}: {e}")
        return None


# ============================================================
# BATCH PROCESSING - PERFECT FOR ALL SCHEDULE TYPES WITH API CHECK
# ============================================================

@shared_task(bind=True, queue="batch_app", max_retries=3)
def process_batch_job(self, job_id):
    """Process a batch job - Supports FULL batch size with API CHECK"""
    close_old_connections()

    try:
        job = BatchJob.objects.get(job_id=job_id)
    except BatchJob.DoesNotExist:
        logger.error(f"❌ Job {job_id} not found")
        return

    # Skip if cancelled
    if job.status == 'cancelled':
        logger.info(f"ℹ️ Job {job_id} is cancelled, skipping")
        return

    if job.status == 'paused':
        logger.info(f"⏸️ Batch job {job_id} is paused")
        return

    # For multiple daily: check if already completed ALL times today
    if (
        job.schedule_type == 'multiple_daily'
        and job.status == 'completed'
        and job.completed_runs >= len(job.schedule_times)
    ):
        logger.info(f"ℹ️ Job {job_id} already completed for all scheduled times")
        return

    try:
        # Set status to running
        if job.status != 'running':
            job.status = 'running'
            job.started_at = timezone.now()
            job.save(update_fields=['status', 'started_at'])

        actual_batch_size = job.get_actual_batch_size()

        # Handle 'full' batch size
        if job.batch_size_type == 'full':
            batch_customers, batch_count = job.get_all_customers_from_s3()
        else:
            batch_customers, batch_count = job.get_batch_from_s3(
                job.current_batch * job.batch_size
            )

        if not batch_customers:
            job.status = 'completed'
            job.completed_at = timezone.now()
            job.next_run_time = None
            job.save(update_fields=['status', 'completed_at', 'next_run_time'])
            return

        # Get app info
        app = get_app_by_name(job.target_app)
        if not app:
            raise Exception(f"App {job.target_app} not found")

        LogModel = get_app_log_model(job.target_app)
        ContactModel = get_app_contact_model(job.target_app)

        if not LogModel:
            raise Exception(f"No log model found for app {job.target_app}")

        creds = app.get('credentials', {})
        if not creds or 'access_token' not in creds or 'phone_number_id' not in creds:
            raise Exception(f"No credentials found for app {job.target_app}")

        build_payload = get_build_payload_function(job.target_app)
        if not build_payload:
            raise Exception(f"No build_payload function found for app {job.target_app}")

        # ============================================================
        # 🔥 CHECK IF API CHECK IS NEEDED
        # ============================================================
        check_api = False
        api_check_function = None
        needs_api_check_func = None
        
        try:
            if job.target_app == 'messaging':
                from messaging.utils import needs_api_check, check_smsquare_payment_status
                needs_api_check_func = needs_api_check
                api_check_function = check_smsquare_payment_status
                check_api = needs_api_check(job.template_id)
                logger.info(f"📋 [messaging] Template {job.template_id} - API Check: {'YES' if check_api else 'NO'}")
                
            elif job.target_app == 'messaging2':
                from messaging2.utils import needs_api_check, check_smsquare_payment_status
                needs_api_check_func = needs_api_check
                api_check_function = check_smsquare_payment_status
                check_api = needs_api_check(job.template_id)
                logger.info(f"📋 [messaging2] Template {job.template_id} - API Check: {'YES' if check_api else 'NO'}")
                
            else:
                logger.info(f"📋 [unknown] No API check for app {job.target_app}")
                
        except ImportError as e:
            logger.warning(f"⚠️ Could not import API check functions for {job.target_app}: {e}")
        except Exception as e:
            logger.warning(f"⚠️ Error checking API for {job.target_app}: {e}")

        # Log info
        if job.batch_size_type == 'full':
            logger.info(f"📦 FULL BATCH - {batch_count} customers (all at once)")
        else:
            logger.info(f"📦 Batch {job.current_batch + 1}/{job.total_batches} - {batch_count} customers")

        logger.info(f"📱 Target App: {app.get('label', job.target_app)} ({job.target_app})")
        logger.info(f"📋 Template: {job.template_name} (ID: {job.template_id})")
        logger.info(f"🌐 Language: {job.template_language}")
        logger.info(f"📊 Batch Size: {actual_batch_size}")
        logger.info(f"🔍 API Check Enabled: {check_api}")

        # Send messages via WhatsApp API
        url = f"https://graph.facebook.com/v22.0/{creds['phone_number_id']}/messages"
        headers = {
            "Authorization": f"Bearer {creds['access_token']}",
            "Content-Type": "application/json",
        }

        sent = 0
        failed = 0
        skipped = 0

        for idx, row in enumerate(batch_customers):
            try:
                mobile = format_mobile(row.get('CustMobile') or row.get('cust_mobile') or '')
                customer_name = row.get('CustomerName') or row.get('customer_name') or ''
                loan_number = row.get('loan_number') or row.get('LoanNumber') or row.get('agreement_no') or row.get('AgreementNo')

                if not mobile:
                    failed += 1
                    continue

                # ============================================================
                # 🔍 API CHECK - Skip PAID customers
                # ============================================================
                should_skip = False
                skip_reason = ""
                total_due = 0

                if check_api and api_check_function:
                    try:
                        # Call the API check function
                        status = api_check_function(mobile, loan_number)
                        
                        if status.get('is_paid', False):
                            # ✅ PAID → Skip (no message)
                            should_skip = True
                            total_due = status.get('total_due', 0)
                            skip_reason = f"PAID - Total Due: ₹{total_due}"
                            logger.info(f"✅ {mobile} - PAID, skipping")
                            skipped += 1
                            
                            # ✅ LOG THE SKIPPED CUSTOMER
                            try:
                                LogModel.objects.create(
                                    job_id=job.job_id,
                                    customer_name=customer_name,
                                    mobile=mobile,
                                    template_name=job.template_name,
                                    sent_text_message=f"PAID - No message sent (Total Due: ₹{total_due})",
                                    status="Skipped",
                                    message_id="",
                                    message_type="Skipped",
                                    content_type="text",
                                    error_message=f"Customer is PAID - Total Due: ₹{total_due}",
                                )
                            except Exception as log_error:
                                logger.error(f"Failed to create skipped log: {log_error}")
                            
                            # Also log to BatchLog
                            try:
                                BatchLog.objects.create(
                                    job=job,
                                    mobile=mobile,
                                    customer_name=customer_name,
                                    status='Skipped',
                                    error_message=f"PAID - Total Due: ₹{total_due}",
                                )
                            except Exception as batch_log_error:
                                logger.error(f"Failed to create BatchLog: {batch_log_error}")
                            
                            # Update contact if exists
                            if ContactModel:
                                try:
                                    ContactModel.objects.update_or_create(
                                        mobile=mobile,
                                        defaults={
                                            "last_msg": f"[SKIPPED] PAID - No message sent",
                                            "last_time": timezone.now(),
                                            "last_type": "Skipped",
                                            "last_status": "Skipped",
                                            "unread": 0
                                        }
                                    )
                                except Exception as contact_error:
                                    logger.error(f"Failed to update contact: {contact_error}")
                            
                            continue  # ⬅️ SKIP SENDING
                            
                        else:
                            # ❌ UNPAID → Continue to send
                            total_due = status.get('total_due', 0)
                            logger.info(f"❌ {mobile} - UNPAID (₹{total_due}) - Sending message")
                            
                    except Exception as api_error:
                        # If API fails, assume UNPAID (send reminder)
                        logger.warning(f"⚠️ API Error for {mobile}: {api_error}")
                        logger.warning(f"📱 {mobile} - Assuming UNPAID, sending")
                else:
                    # ❌ No API check → Send to ALL
                    logger.info(f"📱 {mobile} - No API check, sending")

                # If skipped, continue to next customer
                if should_skip:
                    continue

                # ============================================================
                # 📤 SEND MESSAGE
                # ============================================================
                payload, rendered_text = build_payload(job.template_id, row, None)
                payload['to'] = mobile

                resp = requests.post(url, headers=headers, json=payload, timeout=30)

                if resp.ok:
                    msg_id = resp.json()['messages'][0]['id']
                    sent += 1

                    LogModel.objects.create(
                        job_id=job.job_id,
                        customer_name=customer_name,
                        mobile=mobile,
                        template_name=job.template_name,
                        sent_text_message=rendered_text or f"📨 Batch: {job.template_name}",
                        status="Sent",
                        message_id=msg_id,
                        message_type="Sent",
                        content_type="text",
                    )

                    if ContactModel:
                        ContactModel.objects.update_or_create(
                            mobile=mobile,
                            defaults={
                                "last_msg": rendered_text or f"📨 Batch: {job.template_name}",
                                "last_time": timezone.now(),
                                "last_type": "Sent",
                                "last_status": "Sent",
                                "unread": 0
                            }
                        )

                    BatchLog.objects.create(
                        job=job,
                        mobile=mobile,
                        customer_name=customer_name,
                        status='Sent',
                        message_id=msg_id,
                    )

                    logger.info(f"✅ [{job.target_app}] Sent to {mobile}")
                else:
                    failed += 1
                    error_msg = resp.text[:500]

                    LogModel.objects.create(
                        job_id=job.job_id,
                        customer_name=customer_name,
                        mobile=mobile,
                        template_name=job.template_name,
                        sent_text_message="",
                        status="Failed",
                        message_type="Sent",
                        error_message=error_msg,
                    )

                    BatchLog.objects.create(
                        job=job,
                        mobile=mobile,
                        customer_name=customer_name,
                        status='Failed',
                        error_message=error_msg,
                    )
                    logger.error(f"❌ [{job.target_app}] Failed to send to {mobile}")

                if (idx + 1) % 100 == 0:
                    time.sleep(5)

            except Exception as e:
                failed += 1
                error_msg = str(e)
                logger.error(f"❌ Error for {mobile if 'mobile' in locals() else 'Unknown'}: {error_msg}")

                try:
                    LogModel.objects.create(
                        job_id=job.job_id,
                        customer_name=customer_name if 'customer_name' in locals() else '',
                        mobile=mobile if 'mobile' in locals() else '',
                        template_name=job.template_name,
                        sent_text_message="",
                        status="Failed",
                        message_type="Sent",
                        error_message=error_msg[:500],
                    )

                    BatchLog.objects.create(
                        job=job,
                        mobile=mobile if 'mobile' in locals() else '',
                        customer_name=customer_name if 'customer_name' in locals() else '',
                        status='Failed',
                        error_message=error_msg[:500],
                    )
                except Exception as log_error:
                    logger.error(f"❌ Failed to create log: {log_error}")

        # ============================================================
        # 📊 UPDATE JOB PROGRESS - INCLUDING SKIPPED
        # ============================================================
        logger.info(f"📊 Batch Summary: Sent={sent}, Skipped={skipped}, Failed={failed}")

        # ============================================================
        # ✅ FIXED: MULTIPLE DAILY SCHEDULE - COMPLETE ONLY AFTER ALL TIMES
        # ============================================================
        if job.schedule_type == 'multiple_daily':

            # ============================================================
            # 1. UPDATE STATISTICS
            # ============================================================

            # ✅ Custom Batch: Move to next batch
            # ✅ Full Batch: Same customers every time, don't increment
            if job.batch_size_type != 'full':
                job.current_batch += 1
                job.completed_batches += 1

            # ✅ Always update these
            job.sent_count += sent
            job.failed_count += failed
            job.skipped_count += skipped  # ✅ Track skipped
            job.total_runs += 1
            job.completed_runs += 1
            job.completed_at = timezone.now()

            total_times = len(job.schedule_times)

            logger.info(f"📊 Multiple Daily Progress:")
            logger.info(f"   Runs: {job.completed_runs}/{total_times}")
            logger.info(f"   Batches: {job.completed_batches}/{job.total_batches}")
            logger.info(f"   Batch Size Type: {job.batch_size_type}")
            logger.info(f"   Sent: {job.sent_count}, Skipped: {job.skipped_count}, Failed: {job.failed_count}")

            # ============================================================
            # 2. CHECK COMPLETION - CLEAN LOGIC
            # ============================================================

            # ✅ All times today completed?
            all_times_completed = job.completed_runs >= total_times

            # ✅ All batches completed?
            all_batches_completed = job.completed_batches >= job.total_batches

            if all_times_completed and all_batches_completed:
                # ✅ COMPLETED - Everything finished
                job.status = 'completed'
                job.completed_batches = job.total_batches
                job.completed_at = timezone.now()
                job.next_run_time = None

                logger.info(f"✅ Job {job_id} COMPLETED successfully!")

            elif all_times_completed:
                # ✅ All times done today, but batches remain → Tomorrow
                job.status = 'scheduled'

                # ✅ Get tomorrow's first time
                next_run = job._get_next_multiple_time(timezone.now())
                if next_run:
                    job.next_run_time = next_run

                logger.info(
                    f"📅 All today's runs finished. Next batch scheduled at "
                    f"{next_run.strftime('%Y-%m-%d %I:%M %p') if next_run else 'N/A'}"
                )

            else:
                # ✅ More times today
                job.status = 'scheduled'

                # ✅ Get next time today
                next_run = job._get_next_multiple_time(timezone.now())
                if next_run:
                    job.next_run_time = next_run

                logger.info(
                    f"📅 Multiple Daily Progress: "
                    f"{job.completed_runs}/{total_times} runs completed today."
                )
                logger.info(
                    f"📊 Batch Progress: "
                    f"{job.completed_batches}/{job.total_batches}"
                )
                logger.info(
                    f"📅 Next run at: "
                    f"{next_run.strftime('%Y-%m-%d %I:%M %p') if next_run else 'N/A'}"
                )

            # ============================================================
            # 3. SAVE
            # ============================================================

            job.save(update_fields=[
                'current_batch',
                'completed_batches',
                'sent_count',
                'failed_count',
                'skipped_count',
                'total_runs',
                'completed_runs',
                'completed_at',
                'status',
                'next_run_time'
            ])

            logger.info(
                f"📊 Saved Multiple Daily Job: "
                f"Status={job.status}, "
                f"CompletedRuns={job.completed_runs}/{total_times}, "
                f"CompletedBatches={job.completed_batches}/{job.total_batches}, "
                f"Sent={job.sent_count}, Skipped={job.skipped_count}, Failed={job.failed_count}, "
                f"NextRun={job.next_run_time}"
            )


        # -------------------------
        # 2. FULL BATCH
        # -------------------------
        elif job.batch_size_type == 'full':
            job.current_batch = 1
            job.completed_batches = 1
            job.sent_count += sent
            job.failed_count += failed
            job.skipped_count += skipped  # ✅ Track skipped
            job.total_runs += 1
            job.completed_runs += 1

            # ✅ FIXED: Use update_fields to prevent modifying schedule_datetime
            job.save(update_fields=[
                'current_batch', 'completed_batches', 'sent_count',
                'failed_count', 'skipped_count', 'total_runs', 'completed_runs'
            ])

            job.status = 'completed'
            job.completed_at = timezone.now()
            job.next_run_time = None
            job.save(update_fields=['status', 'completed_at', 'next_run_time'])
            logger.info(f"✅ FULL BATCH COMPLETED for {job_id} - Sent={sent}, Skipped={skipped}, Failed={failed}")

         # -------------------------
        # 3. DAILY / WEEKLY / CUSTOM
        # -------------------------
        else:
            # Normal batch update
            job.current_batch += 1
            job.completed_batches += 1
            job.sent_count += sent
            job.failed_count += failed
            job.skipped_count += skipped  # ✅ Track skipped
            job.total_runs += 1
            job.completed_runs += 1

            logger.info(
                f"✅ Batch {job.current_batch}/{job.total_batches} completed"
            )
            logger.info(f"📊 Sent: {sent}, Skipped: {skipped}, Failed: {failed}")

            # ============================================================
            # ALL BATCHES COMPLETED
            # ============================================================
            if job.current_batch >= job.total_batches:

                job.status = 'completed'
                job.completed_at = timezone.now()
                job.next_run_time = None

                job.save(update_fields=[
                    'current_batch',
                    'completed_batches',
                    'sent_count',
                    'failed_count',
                    'skipped_count',
                    'total_runs',
                    'completed_runs',
                    'status',
                    'completed_at',
                    'next_run_time'
                ])

                logger.info(f"✅ ALL BATCHES COMPLETED for {job_id} - Sent={job.sent_count}, Skipped={job.skipped_count}, Failed={job.failed_count}")

            else:
                # ============================================================
                # DAILY - Next Run = Tomorrow Same Time
                # ============================================================
                if job.schedule_type == 'daily':
                    # ✅ CORRECT: Use total_runs (not completed_batches)
                    next_run = job.schedule_datetime + timedelta(days=job.total_runs)  # ✅ FIXED

                    # ✅ Ensure it's in the future
                    now = timezone.now()
                    while next_run <= now:
                        next_run += timedelta(days=1)

                    job.status = 'scheduled'
                    job.next_run_time = next_run

                    job.save(update_fields=[
                        'current_batch',
                        'completed_batches',
                        'sent_count',
                        'failed_count',
                        'skipped_count',
                        'total_runs',
                        'completed_runs',
                        'status',
                        'next_run_time'
                    ])

                    logger.info(
                        f"📅 Daily Next Run: "
                        f"{next_run.strftime('%Y-%m-%d %I:%M %p')}"
                    )

                # ============================================================
                # WEEKLY - Next Run = Next Week Same Day/Time
                # ============================================================
                elif job.schedule_type == 'weekly':
                    # ✅ Calculate next run: schedule_datetime + (completed_batches * 7 days)
                    next_run = job.schedule_datetime + timedelta(days=7 * job.completed_batches)

                    # ✅ Ensure it's in the future
                    now = timezone.now()
                    while next_run <= now:
                        next_run += timedelta(days=7)

                    job.status = 'scheduled'
                    job.next_run_time = next_run

                    job.save(update_fields=[
                        'current_batch',
                        'completed_batches',
                        'sent_count',
                        'failed_count',
                        'skipped_count',
                        'total_runs',
                        'completed_runs',
                        'status',
                        'next_run_time'
                    ])

                    logger.info(
                        f"📅 Weekly Next Run: "
                        f"{next_run.strftime('%Y-%m-%d %I:%M %p')}"
                    )

                # ============================================================
                # CUSTOM INTERVAL - Next Run = After N Days
                # ============================================================
                elif job.schedule_type == 'custom_interval':
                    # ✅ FIX: Use total_runs instead of completed_batches
                    interval = job.interval_days or 1
                    next_run = job.schedule_datetime + timedelta(days=interval * job.total_runs)

                    # ✅ Ensure it's in the future
                    now = timezone.now()
                    while next_run <= now:
                        next_run += timedelta(days=interval)

                    job.status = 'scheduled'
                    job.next_run_time = next_run

                    job.save(update_fields=[
                        'current_batch',
                        'completed_batches',
                        'sent_count',
                        'failed_count',
                        'skipped_count',
                        'total_runs',
                        'completed_runs',
                        'status',
                        'next_run_time'
                    ])

                    logger.info(
                        f"📅 Custom Interval Next Run: "
                        f"{next_run.strftime('%Y-%m-%d %I:%M %p')} "
                        f"(Every {interval} day(s))"
                    )
                else:
                    job.save(update_fields=[
                        'current_batch',
                        'completed_batches',
                        'sent_count',
                        'failed_count',
                        'skipped_count',
                        'total_runs',
                        'completed_runs'
                    ])

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Batch job {job_id} failed: {error_msg}")
        logger.error(traceback.format_exc())

        try:
            job.status = 'failed'
            job.error_message = error_msg[:500]
            job.save(update_fields=['status', 'error_message'])
        except Exception as save_error:
            logger.error(f"❌ Failed to update job status: {save_error}")

        try:
            self.retry(exc=e, countdown=60, max_retries=3)
        except Exception as retry_error:
            logger.error(f"❌ Failed to retry task: {retry_error}")


@shared_task(queue="batch_scheduler")
def check_pending_batch_jobs():
    """
    Check for pending scheduled jobs and process them
    """
    from django.utils import timezone

    now = timezone.now()

    jobs = BatchJob.objects.filter(
        status="scheduled",
        next_run_time__lte=now
    )

    logger.info(f"🔍 Found {jobs.count()} pending batch jobs")

    for job in jobs:
        logger.info(f"🚀 Processing pending job: {job.job_id}")
        process_batch_job.delay(job.job_id)


# ============================================================
# CANCEL SCHEDULE - WITH ERROR HANDLING
# ============================================================

@shared_task(queue="batch_scheduler")
def cancel_daily_schedule(job_id):
    """Cancel all future schedules for a job with error handling"""
    try:
        job = BatchJob.objects.get(job_id=job_id)
    except BatchJob.DoesNotExist:
        logger.warning(f"⚠️ Job {job_id} not found for cancellation")
        return

    try:
        # Check if job is already cancelled or completed
        if job.status in ['cancelled', 'completed']:
            logger.info(f"ℹ️ Job {job_id} already {job.status}, no action needed")
            return

        # Update the job
        job.status = 'cancelled'
        job.next_run_time = None
        job.save(update_fields=['status', 'next_run_time'])
        logger.info(f"⛔ Schedule cancelled for {job_id}")

    except DatabaseError as e:
        # Handle database errors
        logger.error(f"❌ Database error cancelling schedule for {job_id}: {e}")
        # Try a different approach - update the job without update_fields
        try:
            job.status = 'cancelled'
            job.next_run_time = None
            job.save()  # Save all fields
            logger.info(f"⛔ Schedule cancelled for {job_id} (full save)")
        except Exception as save_error:
            logger.error(f"❌ Failed to cancel schedule: {save_error}")

    except Exception as e:
        logger.error(f"❌ Failed to cancel schedule for {job_id}: {e}")
        logger.error(traceback.format_exc())


# ============================================================
# SCHEDULER - PERFECT TIME HANDLING FOR ALL SCHEDULE TYPES
# ============================================================

@shared_task(queue="batch_scheduler", max_retries=3)
def schedule_batch_job(job_id):
    """
    Schedule the job based on its schedule type

    ✅ FIXED: NEVER modify schedule_datetime
    ✅ FIXED: Weekly schedules preserve first run date
    ✅ FIXED: Timezone-aware comparisons
    """
    try:
        job = BatchJob.objects.get(job_id=job_id)
    except BatchJob.DoesNotExist:
        logger.error(f"❌ Job {job_id} not found")
        return

    if job.status in ['completed', 'cancelled']:
        logger.info(f"ℹ️ Job {job_id} is {job.status}, skipping scheduling")
        return

    try:
        # Check if end_date is reached
        if job.end_date and timezone.now() >= job.end_date:
            job.status = 'completed'
            job.save(update_fields=['status'])
            logger.info(f"📅 Job {job_id} ended (end_date reached)")
            return

        # ===== MULTIPLE DAILY SCHEDULE =====
        if job.schedule_type == 'multiple_daily':
            now = timezone.now()

            # ✅ FIX: Use the saved next_run_time from the job
            if job.next_run_time and job.next_run_time > now:
                next_run = job.next_run_time
                seconds_until = int((next_run - now).total_seconds())

                if seconds_until <= 60:
                    process_batch_job.delay(job_id)
                    logger.info(f"🚀 Multiple daily: Running immediately")
                else:
                    process_batch_job.apply_async(
                        args=(job_id,),
                        countdown=seconds_until,
                        queue="batch_app"
                    )
                    logger.info(f"📅 Multiple daily: Scheduled at {next_run.strftime('%Y-%m-%d %I:%M %p')} (in {seconds_until}s)")

                # Schedule next day's scheduler (24 hours)
                schedule_batch_job.apply_async(
                    args=(job_id,),
                    countdown=86400,
                    queue="batch_scheduler"
                )
                return

            # ✅ If no next_run_time exists (first time), calculate the next one
            next_run = job._get_next_multiple_time(now)
            if next_run:
                job.next_run_time = next_run
                job.status = 'scheduled'
                job.save(update_fields=['next_run_time', 'status'])

                seconds_until = int((next_run - now).total_seconds())

                if seconds_until <= 60:
                    process_batch_job.delay(job_id)
                    logger.info(f"🚀 Multiple daily: Running immediately")
                else:
                    process_batch_job.apply_async(
                        args=(job_id,),
                        countdown=seconds_until,
                        queue="batch_app"
                    )
                    logger.info(f"📅 Multiple daily: Scheduled at {next_run.strftime('%Y-%m-%d %I:%M %p')} (in {seconds_until}s)")
            else:
                job.status = 'failed'
                job.error_message = "No times could be scheduled"
                job.save(update_fields=['status', 'error_message'])
                logger.error(f"❌ No times scheduled for {job_id}")
                return

            # Schedule next day's scheduler (24 hours)
            schedule_batch_job.apply_async(
                args=(job_id,),
                countdown=86400,
                queue="batch_scheduler"
            )
            return

        # ===== WEEKLY SCHEDULE - FIXED =====
        if job.schedule_type == 'weekly':
            now = timezone.now()

            # ✅ FIXED: Use schedule_datetime as the anchor for all calculations
            if job.schedule_datetime > now:
                next_run = job.schedule_datetime
            else:
                next_run = job.schedule_datetime
                while next_run <= now:
                    next_run += timedelta(days=7)

            seconds_until = int((next_run - now).total_seconds())

            logger.info(f"📅 Weekly job {job_id} - schedule_datetime: {job.schedule_datetime.strftime('%Y-%m-%d %I:%M:%S %p')}")
            logger.info(f"📅 Weekly job {job_id} - next_run: {next_run.strftime('%Y-%m-%d %I:%M:%S %p')}")
            logger.info(f"📅 Weekly job {job_id} - seconds_until: {seconds_until}")

            if seconds_until <= 60:
                process_batch_job.delay(job_id)
                logger.info(f"🚀 Weekly job {job_id} running immediately")
            else:
                job.next_run_time = next_run
                job.status = 'scheduled'
                job.save(update_fields=['next_run_time', 'status'])

                process_batch_job.apply_async(
                    args=(job_id,),
                    countdown=seconds_until,
                    queue="batch_app"
                )
                logger.info(f"📅 Weekly job {job_id} scheduled for {next_run.strftime('%Y-%m-%d %I:%M %p')}")

            # Schedule next scheduler (7 days later)
            next_scheduler = next_run + timedelta(days=7)
            schedule_batch_job.apply_async(
                args=(job_id,),
                eta=next_scheduler,
                queue="batch_scheduler"
            )
            return

        # ===== DAILY SCHEDULE - FIXED =====
        if job.schedule_type == 'daily':
            now = timezone.now()

            # ✅ FIXED: Use schedule_datetime as the anchor
            if job.schedule_datetime > now:
                next_run = job.schedule_datetime
            else:
                next_run = job.schedule_datetime
                while next_run <= now:
                    next_run += timedelta(days=1)

            seconds_until = int((next_run - now).total_seconds())

            logger.info(f"📅 Daily job {job_id} - schedule_datetime: {job.schedule_datetime.strftime('%Y-%m-%d %I:%M:%S %p')}")
            logger.info(f"📅 Daily job {job_id} - next_run: {next_run.strftime('%Y-%m-%d %I:%M:%S %p')}")

            if seconds_until <= 60:
                process_batch_job.delay(job_id)
                logger.info(f"🚀 Daily job {job_id} running immediately")
            else:
                job.next_run_time = next_run
                job.status = 'scheduled'
                job.save(update_fields=['next_run_time', 'status'])

                process_batch_job.apply_async(
                    args=(job_id,),
                    countdown=seconds_until,
                    queue="batch_app"
                )
                logger.info(f"📅 Daily job {job_id} scheduled for {next_run.strftime('%Y-%m-%d %I:%M %p')}")

            # Schedule next scheduler (1 day later)
            next_scheduler = next_run + timedelta(days=1)
            schedule_batch_job.apply_async(
                args=(job_id,),
                eta=next_scheduler,
                queue="batch_scheduler"
            )
            return

        # ===== CUSTOM INTERVAL SCHEDULE - FIXED =====
        if job.schedule_type == 'custom_interval':
            if not job.interval_days:
                job.status = 'failed'
                job.error_message = "Interval days not configured"
                job.save(update_fields=['status', 'error_message'])
                return

            now = timezone.now()
            interval = job.interval_days

            if job.next_run_time and job.next_run_time > now:
                next_run = job.next_run_time
            else:
                next_run = job.schedule_datetime + timedelta(days=interval * job.total_runs)
                while next_run <= now:
                    next_run += timedelta(days=interval)

            seconds_until = int((next_run - now).total_seconds())

            logger.info(f"📅 Custom job {job_id} - schedule_datetime: {job.schedule_datetime.strftime('%Y-%m-%d %I:%M:%S %p')}")
            logger.info(f"📅 Custom job {job_id} - total_runs: {job.total_runs}")
            logger.info(f"📅 Custom job {job_id} - next_run: {next_run.strftime('%Y-%m-%d %I:%M:%S %p')}")

            if seconds_until <= 60:
                process_batch_job.delay(job_id)
                logger.info(f"🚀 Custom job {job_id} running immediately")
            else:
                job.next_run_time = next_run
                job.status = 'scheduled'
                job.save(update_fields=['next_run_time', 'status'])

                process_batch_job.apply_async(
                    args=(job_id,),
                    countdown=seconds_until,
                    queue="batch_app"
                )
                logger.info(f"📅 Custom job {job_id} scheduled for {next_run.strftime('%Y-%m-%d %I:%M %p')}")

            # Schedule next scheduler
            next_scheduler = next_run + timedelta(days=interval)
            schedule_batch_job.apply_async(
                args=(job_id,),
                eta=next_scheduler,
                queue="batch_scheduler"
            )
            return

        # Unknown schedule type
        logger.warning(f"⚠️ Unknown schedule type for {job_id}: {job.schedule_type}")
        job.status = 'failed'
        job.error_message = f"Unknown schedule type: {job.schedule_type}"
        job.save(update_fields=['status', 'error_message'])

    except Exception as e:
        logger.error(f"❌ Failed to schedule job {job_id}: {e}")
        logger.error(traceback.format_exc())

        try:
            job.status = 'failed'
            job.error_message = f"Scheduling failed: {str(e)[:500]}"
            job.save(update_fields=['status', 'error_message'])
        except Exception as save_error:
            logger.error(f"❌ Failed to update job status: {save_error}")
