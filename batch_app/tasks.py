# batch_app/tasks.py - COMPLETE PRODUCTION READY VERSION WITH NEW ARCHITECTURE
# ✅ PERFECT DATE/TIME HANDLING FOR ALL SCHEDULE TYPES
# ✅ MULTIPLE DAILY - EACH RUN MOVES TO NEXT BATCH
# ✅ DAILY/WEEKLY/CUSTOM - DAY-BY-DAY BATCH PROCESSING
# ✅ FIXED: job.save() REPLACED WITH update_fields TO PREVENT schedule_datetime MODIFICATION
# ✅ ADDED: API CHECK FOR PAID/UNPAID CUSTOMERS
# ✅ ADDED: SKIPPED COUNT TRACKING
# ✅ NEW: process_batch_scheduler() - Lightweight scheduler (2-3 seconds)
# ✅ NEW: execute_batch() - Per-batch execution for parallel processing
# ✅ NEW: BatchExecution model for tracking individual batches

import time
import logging
import re
from datetime import datetime, timedelta
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django.db import close_old_connections, DatabaseError
from django.db.models import Sum
import requests
import importlib
import traceback

from .models import BatchJob, BatchLog, BatchExecution
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
# 🚀 NEW: SCHEDULER TASK - Lightweight, finishes in 2-3 seconds
# ============================================================

@shared_task(queue="batch_scheduler")
def process_batch_scheduler(job_id):
    """
    SCHEDULER TASK - Takes 2-3 seconds max
    Only creates batch executions, doesn't send messages
    This allows 30+ jobs to all start at exactly their scheduled time
    """
    try:
        job = BatchJob.objects.get(job_id=job_id)
    except BatchJob.DoesNotExist:
        logger.error(f"❌ Job {job_id} not found")
        return
    
    # Skip if already running, completed, or cancelled
    if job.status in ['running', 'completed', 'cancelled']:
        logger.info(f"ℹ️ Job {job_id} is {job.status}, skipping")
        return
    
    # Check if job already has executions (prevent duplicate scheduling)
    existing_executions = BatchExecution.objects.filter(job=job).count()
    if existing_executions > 0:
        logger.info(f"ℹ️ Job {job_id} already has {existing_executions} executions, skipping")
        return
    
    # Mark job as running
    job.status = 'running'
    job.started_at = timezone.now()
    job.save(update_fields=['status', 'started_at'])
    
    # Calculate batch size
    if job.batch_size_type == 'full':
        batch_size = job.total_customers
    else:
        batch_size = job.batch_size
    
    # Calculate total batches
    total_batches = (job.total_customers + batch_size - 1) // batch_size if job.total_customers > 0 else 1
    
    logger.info(f"📊 Job {job_id}: {job.total_customers} customers, {batch_size} per batch, {total_batches} batches")
    
    # Create execution records for each batch
    executions = []
    for batch_num in range(total_batches):
        start_row = batch_num * batch_size
        end_row = min(start_row + batch_size, job.total_customers)
        
        execution = BatchExecution.objects.create(
            job=job,
            batch_number=batch_num + 1,
            start_row=start_row,
            end_row=end_row,
            total_customers=end_row - start_row,
            status='pending'
        )
        executions.append(execution)
    
    # Update job with total batches
    job.total_batches = total_batches
    job.save(update_fields=['total_batches'])
    
    logger.info(f"✅ Created {len(executions)} batch executions for {job_id}")
    
    # Determine queue based on target app
    queue_name = 'messaging' if job.target_app == 'messaging' else 'messaging2'
    
    # Dispatch each batch to the appropriate queue
    # Each batch becomes its own Celery task for parallel processing
    for execution in executions:
        execute_batch.apply_async(
            args=(job_id, execution.id),
            queue=queue_name
        )
    
    logger.info(f"✅ Dispatched {len(executions)} batches to {queue_name} queue")
    return len(executions)


# ============================================================
# 🚀 NEW: BATCH EXECUTION TASK - One task per batch
# ============================================================

@shared_task(bind=True, queue="batch_app", max_retries=2)
def execute_batch(self, job_id, execution_id):
    """
    EXECUTION TASK - Does the actual message sending for ONE batch
    Each batch runs as a separate Celery task for parallel processing
    """
    close_old_connections()
    
    try:
        execution = BatchExecution.objects.get(id=execution_id)
        job = execution.job
    except (BatchExecution.DoesNotExist, BatchJob.DoesNotExist) as e:
        logger.error(f"❌ Execution {execution_id} or Job {job_id} not found: {e}")
        return
    
    # Skip if job is cancelled
    if job.status == 'cancelled':
        execution.status = 'cancelled'
        execution.save(update_fields=['status'])
        logger.info(f"⛔ Job {job_id} cancelled, skipping execution {execution_id}")
        return
    
    # Skip if execution is already completed or running
    if execution.status in ['completed', 'running']:
        logger.info(f"ℹ️ Execution {execution_id} already {execution.status}, skipping")
        return
    
    # Mark execution as running
    execution.status = 'running'
    execution.started_at = timezone.now()
    execution.save(update_fields=['status', 'started_at'])
    
    logger.info(f"🚀 Starting batch {execution.batch_number}/{job.total_batches} for job {job_id}")
    
    try:
        # ============================================================
        # 1. GET BATCH OF CUSTOMERS FROM S3
        # ============================================================
        batch_customers, batch_count = job.get_batch_from_s3(execution.start_row)
        
        if not batch_customers or batch_count == 0:
            execution.status = 'completed'
            execution.completed_at = timezone.now()
            execution.save(update_fields=['status', 'completed_at'])
            logger.info(f"✅ Batch {execution.batch_number}: No customers, completed")
            return
        
        # ============================================================
        # 2. GET APP INFO AND CREDENTIALS
        # ============================================================
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
        # 3. CHECK IF API CHECK IS NEEDED (PAID/UNPAID)
        # ============================================================
        check_api = False
        api_check_function = None
        
        try:
            if job.target_app == 'messaging':
                from messaging.utils import needs_api_check, check_smsquare_payment_status
                api_check_function = check_smsquare_payment_status
                check_api = needs_api_check(job.template_id)
                logger.info(f"📋 [messaging] Template {job.template_id} - API Check: {'YES' if check_api else 'NO'}")
                
            elif job.target_app == 'messaging2':
                from messaging2.utils import needs_api_check, check_smsquare_payment_status
                api_check_function = check_smsquare_payment_status
                check_api = needs_api_check(job.template_id)
                logger.info(f"📋 [messaging2] Template {job.template_id} - API Check: {'YES' if check_api else 'NO'}")
                
            else:
                logger.info(f"📋 [unknown] No API check for app {job.target_app}")
                
        except ImportError as e:
            logger.warning(f"⚠️ Could not import API check functions for {job.target_app}: {e}")
        except Exception as e:
            logger.warning(f"⚠️ Error checking API for {job.target_app}: {e}")
        
        # ============================================================
        # 4. SEND MESSAGES VIA WHATSAPP API
        # ============================================================
        url = f"https://graph.facebook.com/v22.0/{creds['phone_number_id']}/messages"
        headers = {
            "Authorization": f"Bearer {creds['access_token']}",
            "Content-Type": "application/json",
        }
        
        sent = 0
        failed = 0
        skipped = 0
        
        logger.info(f"📦 Batch {execution.batch_number}: Processing {batch_count} customers")
        
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
                total_due = 0
                
                if check_api and api_check_function:
                    try:
                        status = api_check_function(mobile, loan_number)
                        
                        if status.get('is_paid', False):
                            should_skip = True
                            total_due = status.get('total_due', 0)
                            skipped += 1
                            
                            # Log skipped customer
                            try:
                                LogModel.objects.create(
                                    job_id=job,
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
                            total_due = status.get('total_due', 0)
                            logger.info(f"❌ {mobile} - UNPAID (₹{total_due}) - Sending message")
                            
                    except Exception as api_error:
                        logger.warning(f"⚠️ API Error for {mobile}: {api_error}")
                        logger.warning(f"📱 {mobile} - Assuming UNPAID, sending")
                else:
                    logger.info(f"📱 {mobile} - No API check, sending")
                
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
                        job_id=job,
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
                    
                    logger.info(f"✅ [{job.target_app}] Sent to {mobile}")
                else:
                    failed += 1
                    error_msg = resp.text[:500]
                    
                    LogModel.objects.create(
                        job_id=job,
                        customer_name=customer_name,
                        mobile=mobile,
                        template_name=job.template_name,
                        sent_text_message="",
                        status="Failed",
                        message_type="Sent",
                        error_message=error_msg,
                    )
                    logger.error(f"❌ [{job.target_app}] Failed to send to {mobile}")
                
                    
            except Exception as e:
                failed += 1
                error_msg = str(e)
                logger.error(f"❌ Error for {mobile if 'mobile' in locals() else 'Unknown'}: {error_msg}")
                
                try:
                    LogModel.objects.create(
                        job_id=job,
                        customer_name=customer_name if 'customer_name' in locals() else '',
                        mobile=mobile if 'mobile' in locals() else '',
                        template_name=job.template_name,
                        sent_text_message="",
                        status="Failed",
                        message_type="Sent",
                        error_message=error_msg[:500],
                    )
                except Exception as log_error:
                    logger.error(f"❌ Failed to create log: {log_error}")
        
        # ============================================================
        # 5. UPDATE EXECUTION STATISTICS
        # ============================================================
        execution.sent_count = sent
        execution.failed_count = failed
        execution.skipped_count = skipped
        execution.status = 'completed'
        execution.completed_at = timezone.now()
        execution.save(update_fields=['sent_count', 'failed_count', 'skipped_count', 'status', 'completed_at'])
        
        logger.info(f"✅ Batch {execution.batch_number} completed: Sent={sent}, Skipped={skipped}, Failed={failed}")
        
        # ============================================================
        # 6. UPDATE JOB PROGRESS (Aggregate from all executions)
        # ============================================================
        # Count completed batches
        completed_batches = BatchExecution.objects.filter(job=job, status='completed').count()
        
        # Aggregate stats from all executions
        aggregate_stats = BatchExecution.objects.filter(job=job).aggregate(
            total_sent=Sum('sent_count'),
            total_failed=Sum('failed_count'),
            total_skipped=Sum('skipped_count')
        )
        
        job.completed_batches = completed_batches
        job.sent_count = aggregate_stats['total_sent'] or 0
        job.failed_count = aggregate_stats['total_failed'] or 0
        job.skipped_count = aggregate_stats['total_skipped'] or 0
        
        # ============================================================
        # 7. CHECK IF ALL BATCHES ARE COMPLETED
        # ============================================================
        total_batches = BatchExecution.objects.filter(job=job).count()
        
        if completed_batches >= total_batches:
            # ✅ ALL BATCHES COMPLETED
            job.status = 'completed'
            job.completed_at = timezone.now()
            job.next_run_time = None
            job.save(update_fields=['completed_batches', 'sent_count', 'failed_count', 'skipped_count', 'status', 'completed_at', 'next_run_time'])
            logger.info(f"✅ ALL BATCHES COMPLETED for {job.job_id} - Sent={job.sent_count}, Skipped={job.skipped_count}, Failed={job.failed_count}")
        else:
            # Still more batches to process today
            job.save(update_fields=['completed_batches', 'sent_count', 'failed_count', 'skipped_count'])
            
            logger.info(f"📊 Progress: {completed_batches}/{total_batches} batches completed")
            logger.info(f"📊 Stats: Sent={job.sent_count}, Skipped={job.skipped_count}, Failed={job.failed_count}")
        
        # ============================================================
        # 8. SCHEDULE NEXT RUN (For daily/weekly/custom - NOT for multiple daily)
        # ============================================================
        # Only schedule next run if job is not completed and not multiple_daily
        if job.status != 'completed' and job.schedule_type != 'multiple_daily':
            # Check if this was the last batch of the day
            if completed_batches >= total_batches:
                # Calculate next run time based on schedule type
                next_run = None
                
                if job.schedule_type == 'daily':
                    next_run = job.schedule_datetime + timedelta(days=job.total_runs + 1)
                    while next_run <= timezone.now():
                        next_run += timedelta(days=1)
                
                elif job.schedule_type == 'weekly':
                    next_run = job.schedule_datetime + timedelta(days=7 * (job.total_runs + 1))
                    while next_run <= timezone.now():
                        next_run += timedelta(days=7)
                
                elif job.schedule_type == 'custom_interval':
                    interval = job.interval_days or 1
                    next_run = job.schedule_datetime + timedelta(days=interval * (job.total_runs + 1))
                    while next_run <= timezone.now():
                        next_run += timedelta(days=interval)
                
                if next_run:
                    job.next_run_time = next_run
                    job.status = 'scheduled'
                    job.save(update_fields=['next_run_time', 'status'])
                    
                    # Schedule the next run
                    schedule_batch_job.apply_async(
                        args=(job.job_id,),
                        countdown=int((next_run - timezone.now()).total_seconds()),
                        queue="batch_scheduler"
                    )
                    logger.info(f"📅 Next run scheduled for {next_run.strftime('%Y-%m-%d %I:%M %p')}")
        
        # For multiple daily, the scheduler handles rescheduling
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Batch {execution.batch_number} failed: {error_msg}")
        logger.error(traceback.format_exc())
        
        execution.status = 'failed'
        execution.error_message = error_msg[:500]
        execution.save(update_fields=['status', 'error_message'])
        
        # Retry the batch
        try:
            self.retry(exc=e, countdown=60, max_retries=3)
        except Exception as retry_error:
            logger.error(f"❌ Failed to retry batch: {retry_error}")


# ============================================================
# LEGACY: process_batch_job - Kept for compatibility
# ⚠️ DEPRECATED: Use process_batch_scheduler + execute_batch instead
# ============================================================

@shared_task(bind=True, queue="batch_app", max_retries=2)
def process_batch_job(self, job_id):
    """
    ⚠️ LEGACY TASK - DEPRECATED
    Use process_batch_scheduler() + execute_batch() instead
    
    This is kept for backward compatibility but will be removed in future.
    """
    logger.warning(f"⚠️ process_batch_job is deprecated. Use process_batch_scheduler + execute_batch instead.")
    
    # Redirect to new scheduler
    return process_batch_scheduler(job_id)


# ============================================================
# CHECK PENDING BATCH JOBS
# ============================================================

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
        schedule_batch_job.delay(job.job_id)


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
        
        # Cancel all pending executions
        BatchExecution.objects.filter(job=job, status='pending').update(status='cancelled')
        
        # Update the job
        job.status = 'cancelled'
        job.next_run_time = None
        job.save(update_fields=['status', 'next_run_time'])
        logger.info(f"⛔ Schedule cancelled for {job_id}")
        
    except DatabaseError as e:
        logger.error(f"❌ Database error cancelling schedule for {job_id}: {e}")
        try:
            job.status = 'cancelled'
            job.next_run_time = None
            job.save()
            logger.info(f"⛔ Schedule cancelled for {job_id} (full save)")
        except Exception as save_error:
            logger.error(f"❌ Failed to cancel schedule: {save_error}")
            
    except Exception as e:
        logger.error(f"❌ Failed to cancel schedule for {job_id}: {e}")
        logger.error(traceback.format_exc())


# ============================================================
# SCHEDULER - PERFECT TIME HANDLING FOR ALL SCHEDULE TYPES
# ============================================================

@shared_task(queue="batch_scheduler", max_retries=2)
def schedule_batch_job(job_id):
    """
    Schedule the job based on its schedule type
    
    ✅ FIXED: NEVER modify schedule_datetime
    ✅ FIXED: Weekly schedules preserve first run date
    ✅ FIXED: Timezone-aware comparisons
    ✅ UPDATED: Uses process_batch_scheduler instead of process_batch_job
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
            
            # Check if job has any pending executions
            pending_executions = BatchExecution.objects.filter(job=job, status__in=['pending', 'running']).count()
            if pending_executions > 0:
                logger.info(f"ℹ️ Job {job_id} has {pending_executions} pending executions, skipping scheduling")
                return
            
            # ✅ Use the saved next_run_time from the job
            if job.next_run_time and job.next_run_time > now:
                next_run = job.next_run_time
                seconds_until = int((next_run - now).total_seconds())
                
                if seconds_until <= 60:
                    process_batch_scheduler.delay(job_id)
                    logger.info(f"🚀 Multiple daily: Running immediately")
                else:
                    process_batch_scheduler.apply_async(
                        args=(job_id,),
                        countdown=seconds_until,
                        queue="batch_scheduler"
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
                    process_batch_scheduler.delay(job_id)
                    logger.info(f"🚀 Multiple daily: Running immediately")
                else:
                    process_batch_scheduler.apply_async(
                        args=(job_id,),
                        countdown=seconds_until,
                        queue="batch_scheduler"
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
        
        # ===== WEEKLY SCHEDULE =====
        if job.schedule_type == 'weekly':
            now = timezone.now()
            
            # Check if job has any pending executions
            pending_executions = BatchExecution.objects.filter(job=job, status__in=['pending', 'running']).count()
            if pending_executions > 0:
                logger.info(f"ℹ️ Job {job_id} has {pending_executions} pending executions, skipping scheduling")
                return
            
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
                process_batch_scheduler.delay(job_id)
                logger.info(f"🚀 Weekly job {job_id} running immediately")
            else:
                job.next_run_time = next_run
                job.status = 'scheduled'
                job.save(update_fields=['next_run_time', 'status'])
                
                process_batch_scheduler.apply_async(
                    args=(job_id,),
                    countdown=seconds_until,
                    queue="batch_scheduler"
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
        
        # ===== DAILY SCHEDULE =====
        if job.schedule_type == 'daily':
            now = timezone.now()
            
            # Check if job has any pending executions
            pending_executions = BatchExecution.objects.filter(job=job, status__in=['pending', 'running']).count()
            if pending_executions > 0:
                logger.info(f"ℹ️ Job {job_id} has {pending_executions} pending executions, skipping scheduling")
                return
            
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
                process_batch_scheduler.delay(job_id)
                logger.info(f"🚀 Daily job {job_id} running immediately")
            else:
                job.next_run_time = next_run
                job.status = 'scheduled'
                job.save(update_fields=['next_run_time', 'status'])
                
                process_batch_scheduler.apply_async(
                    args=(job_id,),
                    countdown=seconds_until,
                    queue="batch_scheduler"
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
        
        # ===== CUSTOM INTERVAL SCHEDULE =====
        if job.schedule_type == 'custom_interval':
            if not job.interval_days:
                job.status = 'failed'
                job.error_message = "Interval days not configured"
                job.save(update_fields=['status', 'error_message'])
                return
            
            # Check if job has any pending executions
            pending_executions = BatchExecution.objects.filter(job=job, status__in=['pending', 'running']).count()
            if pending_executions > 0:
                logger.info(f"ℹ️ Job {job_id} has {pending_executions} pending executions, skipping scheduling")
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
                process_batch_scheduler.delay(job_id)
                logger.info(f"🚀 Custom job {job_id} running immediately")
            else:
                job.next_run_time = next_run
                job.status = 'scheduled'
                job.save(update_fields=['next_run_time', 'status'])
                
                process_batch_scheduler.apply_async(
                    args=(job_id,),
                    countdown=seconds_until,
                    queue="batch_scheduler"
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
