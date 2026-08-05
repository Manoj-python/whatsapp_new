# batch_app/tasks.py - COMPLETE PRODUCTION READY VERSION WITH NEW ARCHITECTURE
# ✅ PERFECT DATE/TIME HANDLING FOR ALL SCHEDULE TYPES
# ✅ MULTIPLE DAILY - EACH RUN MOVES TO NEXT BATCH
# ✅ DAILY/WEEKLY/CUSTOM - DAY-BY-DAY BATCH PROCESSING
# ✅ CUSTOM BATCH - One batch per day (100/day for 10 days)
# ✅ FULL BATCH - All customers every day (1000/day every day)
# ✅ FIXED: job.save() REPLACED WITH update_fields TO PREVENT schedule_datetime MODIFICATION
# ✅ ADDED: API CHECK FOR PAID/UNPAID CUSTOMERS
# ✅ ADDED: SKIPPED COUNT TRACKING
# ✅ NEW: process_batch_scheduler() - Creates ONE batch at a time
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
# 🚀 SCHEDULER TASK - Creates ONE batch at a time
# ============================================================
@shared_task(queue="batch_scheduler")
def process_batch_scheduler(job_id):
    """
    SCHEDULER TASK - Creates only ONE batch execution per run
    
    ALL SCHEDULE TYPES (Daily, Multiple Daily, Weekly, Custom Interval):
    
    Full Batch: All customers per schedule → Continues forever
    Custom Batch: One batch per schedule → Continues until all batches complete
    
    Multiple Daily Special Cases:
    - Full Batch: Runs all customers at each scheduled time, completes after last time
    - Custom Batch: One batch per scheduled time, continues next day if more batches
    """
    logger.info(f"🚀 process_batch_scheduler STARTED for {job_id}")
    
    try:
        job = BatchJob.objects.get(job_id=job_id)
        logger.info(f"📊 Job found: {job.job_id}, status: {job.status}, schedule_type: {job.schedule_type}")
    except BatchJob.DoesNotExist:
        logger.error(f"❌ Job {job_id} not found")
        return

    # Skip if cancelled
    if job.status == 'cancelled':
        logger.info(f"ℹ️ Job {job_id} is cancelled, skipping")
        return

    # Skip if already running
    if job.status == 'running':
        logger.info(f"ℹ️ Job {job_id} is already running, skipping")
        return

    # Check for pending or running executions
    pending_running = BatchExecution.objects.filter(
        job=job,
        status__in=['pending', 'running']
    ).count()
    
    if pending_running > 0:
        logger.info(f"ℹ️ Job {job_id} has {pending_running} pending/running executions, skipping")
        return

    # ============================================================
    # 📊 CALCULATE BATCH INFORMATION
    # ============================================================
    
    total_customers = job.total_customers
    
    if total_customers == 0:
        logger.warning(f"⚠️ Job {job_id} has 0 customers")
        job.status = 'completed'
        job.save(update_fields=['status'])
        return
    
    # Calculate batch size
    if job.batch_size_type == 'full':
        batch_size = total_customers
        logger.info(f"📊 FULL BATCH: {batch_size} customers per run")
    else:
        batch_size = job.batch_size
        logger.info(f"📊 CUSTOM BATCH: {batch_size} customers per run")

    # Calculate total batches
    total_batches = (total_customers + batch_size - 1) // batch_size if total_customers > 0 else 1
    logger.info(f"📊 Total customers: {total_customers}, Batch size: {batch_size}, Total batches: {total_batches}")

    # ============================================================
    # 🔥 FIND THE NEXT BATCH TO PROCESS
    # ============================================================
    
    # Get all completed batch numbers
    completed_batch_numbers = BatchExecution.objects.filter(
        job=job,
        status='completed'
    ).values_list('batch_number', flat=True)
    
    completed_batch_numbers = set(completed_batch_numbers)
    logger.info(f"📊 Completed batches: {sorted(completed_batch_numbers)}")
    
    # Find the next batch number (smallest missing number)
    next_batch_number = None
    for i in range(1, total_batches + 1):
        if i not in completed_batch_numbers:
            next_batch_number = i
            break
    
    # Check if all batches are completed
    if next_batch_number is None:
        logger.info(f"✅ ALL BATCHES COMPLETED for {job_id}")
        
        # ============================================================
        # 🔥 HANDLE BASED ON SCHEDULE TYPE AND BATCH SIZE
        # ============================================================
        
        # For FULL BATCH: Keep running (restart)
        if job.batch_size_type == 'full':
            logger.info(f"🔄 FULL BATCH: Restarting from batch 1 for next schedule")
            # Delete all completed executions to start fresh
            BatchExecution.objects.filter(job=job).delete()
            job.status = 'scheduled'
            job.completed_batches = 0
            job.sent_count = 0
            job.failed_count = 0
            job.skipped_count = 0
            job.save(update_fields=['status', 'completed_batches', 'sent_count', 'failed_count', 'skipped_count'])
            # Recursively call to create batch 1
            return process_batch_scheduler(job_id)
        
        # For CUSTOM BATCH: Check if we need to continue
        else:
            # Special check for Multiple Daily - might have more times today
            if job.schedule_type == 'multiple_daily':
                now = timezone.now()
                today_times = []
                
                if hasattr(job, 'get_today_times'):
                    today_times = job.get_today_times(now)
                
                if today_times and len(today_times) > 0:
                    # Count completed runs today
                    today_completed = BatchExecution.objects.filter(
                        job=job,
                        status='completed',
                        completed_at__date=now.date()
                    ).count()
                    
                    if today_completed < len(today_times):
                        # Still have more times today, continue
                        job.status = 'scheduled'
                        job.save(update_fields=['status'])
                        logger.info(f"📊 Multiple Daily: {today_completed}/{len(today_times)} times done, continuing today")
                        return
            
            # For all other schedule types, mark as completed
            job.status = 'completed'
            job.completed_at = timezone.now()
            job.next_run_time = None
            job.save(update_fields=['status', 'completed_at', 'next_run_time'])
            logger.info(f"✅ ALL BATCHES COMPLETED for {job.job_id}")
            return
    
    logger.info(f"📊 Next batch to process: {next_batch_number}/{total_batches}")

    # ============================================================
    # 🚀 CREATE THE NEXT BATCH EXECUTION
    # ============================================================
    
    # Calculate start and end rows for this batch
    start_row = (next_batch_number - 1) * batch_size
    end_row = min(start_row + batch_size, total_customers)
    
    # Mark job as running
    job.status = 'running'
    job.started_at = timezone.now()
    job.completed_batches = len(completed_batch_numbers)
    job.save(update_fields=['status', 'started_at', 'completed_batches'])
    
    logger.info(f"✅ Job {job_id} marked as running")
    logger.info(f"📊 Creating batch {next_batch_number}: rows {start_row} to {end_row}")

    # Create execution record for this batch
    execution = BatchExecution.objects.create(
        job=job,
        batch_number=next_batch_number,
        start_row=start_row,
        end_row=end_row,
        total_customers=end_row - start_row,
        status='pending'
    )
    logger.info(f"✅ Created execution {execution.id} for batch {next_batch_number}")

    # Update job total batches
    job.total_batches = total_batches
    job.save(update_fields=['total_batches'])

    # Determine queue based on target app
    queue_name = 'messaging' if job.target_app == 'messaging' else 'messaging2'
    logger.info(f"📊 Using queue: {queue_name}")

    # Dispatch the batch execution
    execute_batch.apply_async(
        args=(job_id, execution.id),
        queue=queue_name
    )
    logger.info(f"✅ Dispatched batch {next_batch_number} to {queue_name} queue")

    return 1
# batch_app/tasks.py - COMPLETE FIXED VERSION WITH UI UPDATES

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
# 🚀 SCHEDULER TASK - Creates ONE batch at a time
# ============================================================
@shared_task(queue="batch_scheduler")
def process_batch_scheduler(job_id):
    """
    SCHEDULER TASK - Creates only ONE batch execution per run
    """
    logger.info(f"🚀 process_batch_scheduler STARTED for {job_id}")
    
    try:
        job = BatchJob.objects.get(job_id=job_id)
        logger.info(f"📊 Job found: {job.job_id}, status: {job.status}, schedule_type: {job.schedule_type}")
    except BatchJob.DoesNotExist:
        logger.error(f"❌ Job {job_id} not found")
        return

    # Skip if cancelled
    if job.status == 'cancelled':
        logger.info(f"ℹ️ Job {job_id} is cancelled, skipping")
        return

    # Skip if already running
    if job.status == 'running':
        logger.info(f"ℹ️ Job {job_id} is already running, skipping")
        return

    # Check for pending or running executions
    pending_running = BatchExecution.objects.filter(
        job=job,
        status__in=['pending', 'running']
    ).count()
    
    if pending_running > 0:
        logger.info(f"ℹ️ Job {job_id} has {pending_running} pending/running executions, skipping")
        return

    # ============================================================
    # 📊 CALCULATE BATCH INFORMATION
    # ============================================================
    
    total_customers = job.total_customers
    
    if total_customers == 0:
        logger.warning(f"⚠️ Job {job_id} has 0 customers")
        job.status = 'completed'
        job.save(update_fields=['status'])
        return
    
    # Calculate batch size
    if job.batch_size_type == 'full':
        batch_size = total_customers
        logger.info(f"📊 FULL BATCH: {batch_size} customers per run")
    else:
        batch_size = job.batch_size
        logger.info(f"📊 CUSTOM BATCH: {batch_size} customers per run")

    # Calculate total batches
    total_batches = (total_customers + batch_size - 1) // batch_size if total_customers > 0 else 1
    logger.info(f"📊 Total customers: {total_customers}, Batch size: {batch_size}, Total batches: {total_batches}")

    # ============================================================
    # 🔥 FIND THE NEXT BATCH TO PROCESS
    # ============================================================
    
    # Get all completed batch numbers
    completed_batch_numbers = BatchExecution.objects.filter(
        job=job,
        status='completed'
    ).values_list('batch_number', flat=True)
    
    completed_batch_numbers = set(completed_batch_numbers)
    logger.info(f"📊 Completed batches: {sorted(completed_batch_numbers)}")
    
    # Find the next batch number (smallest missing number)
    next_batch_number = None
    for i in range(1, total_batches + 1):
        if i not in completed_batch_numbers:
            next_batch_number = i
            break
    
    # Check if all batches are completed
    if next_batch_number is None:
        logger.info(f"✅ ALL BATCHES COMPLETED for {job_id}")
        
        # For FULL BATCH: Keep running (restart)
        if job.batch_size_type == 'full':
            logger.info(f"🔄 FULL BATCH: Restarting from batch 1 for next schedule")
            # Delete all completed executions to start fresh
            BatchExecution.objects.filter(job=job).delete()
            job.status = 'scheduled'
            job.completed_batches = 0
            job.sent_count = 0
            job.failed_count = 0
            job.skipped_count = 0
            job.save(update_fields=['status', 'completed_batches', 'sent_count', 'failed_count', 'skipped_count'])
            # Recursively call to create batch 1
            return process_batch_scheduler(job_id)
        
        # For CUSTOM BATCH: Job is done
        job.status = 'completed'
        job.completed_at = timezone.now()
        job.next_run_time = None
        job.save(update_fields=['status', 'completed_at', 'next_run_time'])
        logger.info(f"✅ ALL BATCHES COMPLETED for {job.job_id}")
        return
    
    logger.info(f"📊 Next batch to process: {next_batch_number}/{total_batches}")

    # ============================================================
    # 🚀 CREATE THE NEXT BATCH EXECUTION
    # ============================================================
    
    # Calculate start and end rows for this batch
    start_row = (next_batch_number - 1) * batch_size
    end_row = min(start_row + batch_size, total_customers)
    
    # Mark job as running
    job.status = 'running'
    job.started_at = timezone.now()
    job.completed_batches = len(completed_batch_numbers)
    job.save(update_fields=['status', 'started_at', 'completed_batches'])
    
    logger.info(f"✅ Job {job_id} marked as running")
    logger.info(f"📊 Creating batch {next_batch_number}: rows {start_row} to {end_row}")

    # Create execution record for this batch
    execution = BatchExecution.objects.create(
        job=job,
        batch_number=next_batch_number,
        start_row=start_row,
        end_row=end_row,
        total_customers=end_row - start_row,
        status='pending'
    )
    logger.info(f"✅ Created execution {execution.id} for batch {next_batch_number}")

    # Update job total batches
    job.total_batches = total_batches
    job.save(update_fields=['total_batches'])

    # Determine queue based on target app
    queue_name = 'messaging' if job.target_app == 'messaging' else 'messaging2'
    logger.info(f"📊 Using queue: {queue_name}")

    # Dispatch the batch execution
    execute_batch.apply_async(
        args=(job_id, execution.id),
        queue=queue_name
    )
    logger.info(f"✅ Dispatched batch {next_batch_number} to {queue_name} queue")

    return 1
# ============================================================
# 🚀 BATCH EXECUTION TASK - One task per batch
# ============================================================
@shared_task(bind=True, queue="batch_app", max_retries=2)
def execute_batch(self, job_id, execution_id):
    """
    EXECUTION TASK - Does the actual message sending for ONE batch
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

    logger.info(f"🚀 Starting batch {execution.batch_number} for job {job_id}")

    try:
        # ============================================================
        # 1. GET BATCH OF CUSTOMERS FROM S3
        # ============================================================
        batch_customers, batch_count = job.get_batch_from_s3(execution.start_row)

        if not batch_customers or batch_count == 0:
            execution.status = 'completed'
            execution.completed_at = timezone.now()
            execution.save(update_fields=['status', 'completed_at'])
            
            # Update job status
            job.status = 'scheduled'
            job.save(update_fields=['status'])
            
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

        # 🔥 NEW: Increment total_runs counter
        job.total_runs += 1  # ← NEW: Increment run counter for UI
        
        # Update all job stats for UI
        job.completed_batches = completed_batches
        job.sent_count = aggregate_stats['total_sent'] or 0
        job.failed_count = aggregate_stats['total_failed'] or 0
        job.skipped_count = aggregate_stats['total_skipped'] or 0

        # ============================================================
        # 7. CHECK IF ALL BATCHES ARE COMPLETED
        # ============================================================
        # Calculate total batches based on customers and batch size
        if job.batch_size_type == 'full':
            total_batches = 1
        else:
            total_batches = (job.total_customers + job.batch_size - 1) // job.batch_size
        
        # Also get existing executions count
        existing_executions = BatchExecution.objects.filter(job=job).count()
        
        # Use the larger value
        total_batches = max(total_batches, existing_executions)
        
        logger.info(f"📊 Total batches: {total_batches}, Completed: {completed_batches}, Total Runs: {job.total_runs}")

        if completed_batches >= total_batches:
            # ✅ ALL BATCHES COMPLETED
            job.completed_at = timezone.now()
            
            # Check if this is a recurring job
            if job.schedule_type in ['daily', 'weekly', 'custom_interval', 'multiple_daily']:
                # For recurring jobs, reset for next schedule
                if job.batch_size_type == 'full':
                    # 🔥 FIX: Full batch - Keep stats for UI, schedule next run
                    logger.info(f"🔄 FULL BATCH: Completed run #{job.total_runs}, scheduling next run")
                    
                    # Calculate next run time
                    if job.schedule_type == 'daily':
                        next_run = job.schedule_datetime + timedelta(days=1)
                    elif job.schedule_type == 'weekly':
                        next_run = job.schedule_datetime + timedelta(days=7)
                    elif job.schedule_type == 'custom_interval':
                        next_run = job.schedule_datetime + timedelta(days=job.interval_days or 1)
                    else:
                        next_run = job.schedule_datetime + timedelta(days=1)
                    
                    # Keep the stats visible on UI
                    job.status = 'scheduled'
                    job.next_run_time = next_run
                    # 🔥 NEW: Save total_runs with other fields
                    job.save(update_fields=[
                        'completed_batches', 'sent_count', 'failed_count', 
                        'skipped_count', 'status', 'completed_at', 'next_run_time', 'total_runs'
                    ])
                    
                    # Delete executions AFTER saving stats to UI
                    BatchExecution.objects.filter(job=job).delete()
                    
                    # Reset completed batches for next run
                    job.completed_batches = 0
                    job.save(update_fields=['completed_batches'])
                    
                    # Schedule next run
                    schedule_batch_job.delay(job.job_id)
                    logger.info(f"📅 Next run #{job.total_runs + 1} scheduled for {next_run}")
                    logger.info(f"📊 Run #{job.total_runs} stats - Sent: {job.sent_count}, Skipped: {job.skipped_count}")
                    return
                else:
                    # Custom batch: Check if end_date reached
                    if job.end_date and timezone.now() >= job.end_date:
                        job.status = 'completed'
                        job.next_run_time = None
                        # 🔥 NEW: Save total_runs with other fields
                        job.save(update_fields=['completed_batches', 'sent_count', 'failed_count', 
                                               'skipped_count', 'status', 'completed_at', 'next_run_time', 'total_runs'])
                        logger.info(f"✅ Job ended (end_date reached) after {job.total_runs} runs")
                    else:
                        # Reset for next day
                        logger.info(f"🔄 CUSTOM BATCH: Resetting for next schedule")
                        
                        # Keep stats for UI before resetting
                        last_sent = job.sent_count
                        last_skipped = job.skipped_count
                        last_failed = job.failed_count
                        current_runs = job.total_runs
                        
                        # Delete completed executions to start fresh
                        BatchExecution.objects.filter(job=job).delete()
                        
                        job.status = 'scheduled'
                        job.completed_batches = 0
                        job.sent_count = 0
                        job.failed_count = 0
                        job.skipped_count = 0
                        # 🔥 NEW: Keep total_runs for history
                        
                        # Calculate next run time
                        if job.schedule_type == 'daily':
                            next_run = job.schedule_datetime + timedelta(days=1)
                        elif job.schedule_type == 'weekly':
                            next_run = job.schedule_datetime + timedelta(days=7)
                        elif job.schedule_type == 'custom_interval':
                            next_run = job.schedule_datetime + timedelta(days=job.interval_days or 1)
                        else:
                            next_run = job.schedule_datetime + timedelta(days=1)
                        
                        job.next_run_time = next_run
                        # 🔥 NEW: Save total_runs with other fields
                        job.save(update_fields=['completed_batches', 'sent_count', 'failed_count', 
                                               'skipped_count', 'status', 'completed_at', 'next_run_time', 'total_runs'])
                        
                        # Schedule next run
                        schedule_batch_job.delay(job.job_id)
                        logger.info(f"📅 Next run #{job.total_runs + 1} scheduled for {next_run}")
                        logger.info(f"📊 Run #{job.total_runs} stats - Sent: {last_sent}, Skipped: {last_skipped}")
                    return
            else:
                # One-time job: Mark as completed
                job.status = 'completed'
                job.next_run_time = None
                # 🔥 NEW: Save total_runs with other fields
                job.save(update_fields=['completed_batches', 'sent_count', 'failed_count', 
                                       'skipped_count', 'status', 'completed_at', 'next_run_time', 'total_runs'])
                logger.info(f"✅ ALL BATCHES COMPLETED for {job.job_id} after {job.total_runs} runs")
                logger.info(f"📊 Final stats - Sent: {job.sent_count}, Skipped: {job.skipped_count}")
        else:
            # More batches to process - update UI stats
            job.status = 'scheduled'
            
            # Calculate next run time for UI
            if job.schedule_type == 'daily':
                now = timezone.now()
                next_run = job.schedule_datetime
                while next_run <= now:
                    next_run += timedelta(days=1)
                job.next_run_time = next_run
            elif job.schedule_type == 'weekly':
                now = timezone.now()
                next_run = job.schedule_datetime
                while next_run <= now:
                    next_run += timedelta(days=7)
                job.next_run_time = next_run
            elif job.schedule_type == 'custom_interval':
                now = timezone.now()
                interval = job.interval_days or 1
                next_run = job.schedule_datetime
                while next_run <= now:
                    next_run += timedelta(days=interval)
                job.next_run_time = next_run
            elif job.schedule_type == 'multiple_daily':
                pass
            
            # 🔥 NEW: Save total_runs with other fields
            job.save(update_fields=['completed_batches', 'sent_count', 'failed_count', 
                                   'skipped_count', 'status', 'next_run_time', 'total_runs'])
            
            logger.info(f"📊 Progress: {completed_batches}/{total_batches} batches completed")
            logger.info(f"📊 Run #{job.total_runs} stats - Sent: {job.sent_count}, Skipped: {job.skipped_count}, Failed: {job.failed_count}")
            if job.next_run_time:
                logger.info(f"📅 Next run: {job.next_run_time}")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Batch {execution.batch_number} failed: {error_msg}")
        logger.error(traceback.format_exc())

        execution.status = 'failed'
        execution.error_message = error_msg[:500]
        execution.save(update_fields=['status', 'error_message'])

        # Set job status to scheduled
        try:
            job.status = 'scheduled'
            job.save(update_fields=['status'])
        except Exception as save_error:
            logger.error(f"❌ Failed to update job status: {save_error}")

        # Retry the batch
        try:
            self.retry(exc=e, countdown=60, max_retries=3)
        except Exception as retry_error:
            logger.error(f"❌ Failed to retry batch: {retry_error}")

# ============================================================
# LEGACY: process_batch_job - Kept for compatibility
# ============================================================
@shared_task(bind=True, queue="batch_app", max_retries=2)
def process_batch_job(self, job_id):
    """
    ⚠️ LEGACY TASK - DEPRECATED
    """
    logger.warning(f"⚠️ process_batch_job is deprecated. Use process_batch_scheduler + execute_batch instead.")
    return process_batch_scheduler(job_id)


# ============================================================
# 🔄 CHECK PENDING BATCH JOBS
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
    ).exclude(
        status__in=['running', 'completed', 'cancelled']
    )

    logger.info(f"🔍 Found {jobs.count()} pending batch jobs")

    for job in jobs:
        # Check if job already has pending executions
        pending_running = BatchExecution.objects.filter(
            job=job,
            status__in=['pending', 'running']
        ).count()
        
        if pending_running > 0:
            logger.info(f"ℹ️ Job {job.job_id} has {pending_running} pending/running executions, skipping")
            continue
        
        logger.info(f"🚀 Processing pending job: {job.job_id}")
        schedule_batch_job.delay(job.job_id)


# ============================================================
# ⛔ CANCEL SCHEDULE
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
# 📅 SCHEDULER - PERFECT TIME HANDLING FOR ALL SCHEDULE TYPES
# ============================================================
@shared_task(queue="batch_scheduler", max_retries=2)
def schedule_batch_job(job_id):
    """
    Schedule the job based on its schedule type
    """
    try:
        job = BatchJob.objects.get(job_id=job_id)
    except BatchJob.DoesNotExist:
        logger.error(f"❌ Job {job_id} not found")
        return

    # Skip only if cancelled
    if job.status == 'cancelled':
        logger.info(f"ℹ️ Job {job_id} is cancelled, skipping scheduling")
        return
    
    # For one-time jobs that are completed, don't schedule again
    if job.schedule_type == 'one_time' and job.status == 'completed':
        logger.info(f"ℹ️ One-time job {job_id} is completed, skipping scheduling")
        return
    
    # If recurring job is completed, reset to scheduled
    if job.status == 'completed' and job.schedule_type != 'one_time':
        logger.info(f"🔄 Recurring job {job_id} was marked completed, resetting to scheduled")
        job.status = 'scheduled'
        job.save(update_fields=['status'])

    try:
        # Check if end_date is reached
        if job.end_date and timezone.now() >= job.end_date:
            job.status = 'completed'
            job.next_run_time = None
            job.save(update_fields=['status', 'next_run_time'])
            logger.info(f"📅 Job {job_id} ended (end_date reached)")
            return

        now = timezone.now()

        # ===== MULTIPLE DAILY SCHEDULE =====
        if job.schedule_type == 'multiple_daily':
            # Check if job has pending/running executions
            pending_running = BatchExecution.objects.filter(
                job=job,
                status__in=['pending', 'running']
            ).count()
            
            if pending_running > 0:
                logger.info(f"ℹ️ Job {job_id} has {pending_running} pending/running executions, skipping scheduling")
                schedule_batch_job.apply_async(
                    args=(job_id,),
                    countdown=3600,
                    queue="batch_scheduler"
                )
                return

            # Calculate next run time
            if job.next_run_time and job.next_run_time > now:
                next_run = job.next_run_time
            else:
                if hasattr(job, '_get_next_multiple_time'):
                    next_run = job._get_next_multiple_time(now)
                else:
                    next_run = now + timedelta(days=1)
                
                if not next_run:
                    job.status = 'failed'
                    job.error_message = "No times could be scheduled"
                    job.save(update_fields=['status', 'error_message'])
                    return
                
                job.next_run_time = next_run
                job.status = 'scheduled'
                job.save(update_fields=['next_run_time', 'status'])

            seconds_until = int((next_run - now).total_seconds())
            logger.info(f"📅 Multiple daily: Next run at {next_run.strftime('%Y-%m-%d %I:%M %p')} (in {seconds_until}s)")

            process_batch_scheduler.apply_async(
                args=(job_id,),
                countdown=seconds_until,
                queue="batch_scheduler"
            )

            schedule_batch_job.apply_async(
                args=(job_id,),
                countdown=86400,
                queue="batch_scheduler"
            )
            return

        # ===== DAILY SCHEDULE =====
        if job.schedule_type == 'daily':
            # Check if job has pending/running executions
            pending_running = BatchExecution.objects.filter(
                job=job,
                status__in=['pending', 'running']
            ).count()
            
            if pending_running > 0:
                logger.info(f"ℹ️ Job {job_id} has {pending_running} pending/running executions, skipping scheduling")
                schedule_batch_job.apply_async(
                    args=(job_id,),
                    countdown=3600,
                    queue="batch_scheduler"
                )
                return

            # Check if all batches completed for custom batch
            if job.batch_size_type != 'full':
                total_batches = (job.total_customers + job.batch_size - 1) // job.batch_size
                completed_batches = BatchExecution.objects.filter(job=job, status='completed').count()
                
                if completed_batches >= total_batches and completed_batches > 0:
                    # All batches completed, reset for next cycle
                    logger.info(f"🔄 All {total_batches} batches completed, resetting for next day")
                    BatchExecution.objects.filter(job=job).delete()
                    job.completed_batches = 0
                    job.sent_count = 0
                    job.failed_count = 0
                    job.skipped_count = 0
                    job.save(update_fields=['completed_batches', 'sent_count', 'failed_count', 'skipped_count'])

            # Calculate next run time for UI
            if job.next_run_time and job.next_run_time > now:
                next_run = job.next_run_time
            else:
                if job.schedule_datetime > now:
                    next_run = job.schedule_datetime
                else:
                    next_run = job.schedule_datetime
                    while next_run <= now:
                        next_run += timedelta(days=1)
                
                job.next_run_time = next_run
                job.status = 'scheduled'
                job.save(update_fields=['next_run_time', 'status'])

            seconds_until = int((next_run - now).total_seconds())
            logger.info(f"📅 Daily job: Next run at {next_run.strftime('%Y-%m-%d %I:%M %p')}")

            process_batch_scheduler.apply_async(
                args=(job_id,),
                countdown=seconds_until,
                queue="batch_scheduler"
            )

            schedule_batch_job.apply_async(
                args=(job_id,),
                countdown=86400,
                queue="batch_scheduler"
            )
            return

        # ===== WEEKLY SCHEDULE =====
        if job.schedule_type == 'weekly':
            # Check if job has pending/running executions
            pending_running = BatchExecution.objects.filter(
                job=job,
                status__in=['pending', 'running']
            ).count()
            
            if pending_running > 0:
                logger.info(f"ℹ️ Job {job_id} has {pending_running} pending/running executions, skipping scheduling")
                schedule_batch_job.apply_async(
                    args=(job_id,),
                    countdown=3600,
                    queue="batch_scheduler"
                )
                return

            # Check if all batches completed for custom batch
            if job.batch_size_type != 'full':
                total_batches = (job.total_customers + job.batch_size - 1) // job.batch_size
                completed_batches = BatchExecution.objects.filter(job=job, status='completed').count()
                
                if completed_batches >= total_batches and completed_batches > 0:
                    # All batches completed, reset for next cycle
                    logger.info(f"🔄 All {total_batches} batches completed, resetting for next week")
                    BatchExecution.objects.filter(job=job).delete()
                    job.completed_batches = 0
                    job.sent_count = 0
                    job.failed_count = 0
                    job.skipped_count = 0
                    job.save(update_fields=['completed_batches', 'sent_count', 'failed_count', 'skipped_count'])

            # Calculate next run time for UI
            if job.next_run_time and job.next_run_time > now:
                next_run = job.next_run_time
            else:
                if job.schedule_datetime > now:
                    next_run = job.schedule_datetime
                else:
                    next_run = job.schedule_datetime
                    while next_run <= now:
                        next_run += timedelta(days=7)
                
                job.next_run_time = next_run
                job.status = 'scheduled'
                job.save(update_fields=['next_run_time', 'status'])

            seconds_until = int((next_run - now).total_seconds())
            logger.info(f"📅 Weekly job: Next run at {next_run.strftime('%Y-%m-%d %I:%M %p')}")

            process_batch_scheduler.apply_async(
                args=(job_id,),
                countdown=seconds_until,
                queue="batch_scheduler"
            )

            schedule_batch_job.apply_async(
                args=(job_id,),
                countdown=604800,
                queue="batch_scheduler"
            )
            return

        # ===== CUSTOM INTERVAL =====
        if job.schedule_type == 'custom_interval':
            if not job.interval_days:
                job.status = 'failed'
                job.error_message = "Interval days not configured"
                job.save(update_fields=['status', 'error_message'])
                return

            # Check if job has pending/running executions
            pending_running = BatchExecution.objects.filter(
                job=job,
                status__in=['pending', 'running']
            ).count()
            
            if pending_running > 0:
                logger.info(f"ℹ️ Job {job_id} has {pending_running} pending/running executions, skipping scheduling")
                schedule_batch_job.apply_async(
                    args=(job_id,),
                    countdown=3600,
                    queue="batch_scheduler"
                )
                return

            # Check if all batches completed for custom batch
            if job.batch_size_type != 'full':
                total_batches = (job.total_customers + job.batch_size - 1) // job.batch_size
                completed_batches = BatchExecution.objects.filter(job=job, status='completed').count()
                
                if completed_batches >= total_batches and completed_batches > 0:
                    # All batches completed, reset for next cycle
                    logger.info(f"🔄 All {total_batches} batches completed, resetting for next interval")
                    BatchExecution.objects.filter(job=job).delete()
                    job.completed_batches = 0
                    job.sent_count = 0
                    job.failed_count = 0
                    job.skipped_count = 0
                    job.save(update_fields=['completed_batches', 'sent_count', 'failed_count', 'skipped_count'])

            # Calculate next run time for UI
            interval = job.interval_days
            
            if job.next_run_time and job.next_run_time > now:
                next_run = job.next_run_time
            else:
                next_run = job.schedule_datetime
                while next_run <= now:
                    next_run += timedelta(days=interval)
                
                job.next_run_time = next_run
                job.status = 'scheduled'
                job.save(update_fields=['next_run_time', 'status'])

            seconds_until = int((next_run - now).total_seconds())
            logger.info(f"📅 Custom job: Next run at {next_run.strftime('%Y-%m-%d %I:%M %p')}")

            process_batch_scheduler.apply_async(
                args=(job_id,),
                countdown=seconds_until,
                queue="batch_scheduler"
            )

            schedule_batch_job.apply_async(
                args=(job_id,),
                countdown=interval * 86400,
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

# ============================================================
# LEGACY: process_batch_job - Kept for compatibility
# ⚠️ DEPRECATED: Use process_batch_scheduler + execute_batch instead
# ============================================================
@shared_task(bind=True, queue="batch_app", max_retries=2)
def process_batch_job(self, job_id):
    """
    ⚠️ LEGACY TASK - DEPRECATED
    Use process_batch_scheduler() + execute_batch() instead
    """
    logger.warning(f"⚠️ process_batch_job is deprecated. Use process_batch_scheduler + execute_batch instead.")
    return process_batch_scheduler(job_id)


# ============================================================
# 🔄 CHECK PENDING BATCH JOBS
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
    ).exclude(
        status__in=['running', 'completed', 'cancelled']
    )

    logger.info(f"🔍 Found {jobs.count()} pending batch jobs")

    for job in jobs:
        # Check if job already has pending executions
        pending_running = BatchExecution.objects.filter(
            job=job,
            status__in=['pending', 'running']
        ).count()
        
        if pending_running > 0:
            logger.info(f"ℹ️ Job {job.job_id} has {pending_running} pending/running executions, skipping")
            continue
        
        logger.info(f"🚀 Processing pending job: {job.job_id}")
        schedule_batch_job.delay(job.job_id)


# ============================================================
# ⛔ CANCEL SCHEDULE - WITH ERROR HANDLING
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
# 📅 SCHEDULER - PERFECT TIME HANDLING FOR ALL SCHEDULE TYPES
# ============================================================
@shared_task(queue="batch_scheduler", max_retries=2)
def schedule_batch_job(job_id):
    """
    Schedule the job based on its schedule type
    """
    try:
        job = BatchJob.objects.get(job_id=job_id)
    except BatchJob.DoesNotExist:
        logger.error(f"❌ Job {job_id} not found")
        return

    # Skip only if cancelled
    if job.status == 'cancelled':
        logger.info(f"ℹ️ Job {job_id} is cancelled, skipping scheduling")
        return
    
    # For one-time jobs that are completed, don't schedule again
    if job.schedule_type == 'one_time' and job.status == 'completed':
        logger.info(f"ℹ️ One-time job {job_id} is completed, skipping scheduling")
        return
    
    # 🔥 FIX: If recurring job is completed, reset to scheduled
    if job.status == 'completed' and job.schedule_type != 'one_time':
        # Check if it's a FULL BATCH (should never be completed)
        if job.batch_size_type == 'full':
            logger.info(f"🔄 FULL BATCH was marked completed, resetting to scheduled")
            job.status = 'scheduled'
            job.save(update_fields=['status'])
        else:
            logger.info(f"🔄 Recurring job {job_id} was marked completed, resetting to scheduled")
            job.status = 'scheduled'
            job.save(update_fields=['status'])

    try:
        # Check if end_date is reached
        if job.end_date and timezone.now() >= job.end_date:
            job.status = 'completed'
            job.next_run_time = None
            job.save(update_fields=['status', 'next_run_time'])
            logger.info(f"📅 Job {job_id} ended (end_date reached)")
            return

        now = timezone.now()

        # ===== MULTIPLE DAILY SCHEDULE =====
        if job.schedule_type == 'multiple_daily':
            # Check if job has pending/running executions
            pending_running = BatchExecution.objects.filter(
                job=job,
                status__in=['pending', 'running']
            ).count()
            
            if pending_running > 0:
                logger.info(f"ℹ️ Job {job_id} has {pending_running} pending/running executions, skipping scheduling")
                schedule_batch_job.apply_async(
                    args=(job_id,),
                    countdown=3600,
                    queue="batch_scheduler"
                )
                return

            # Calculate next run time
            if job.next_run_time and job.next_run_time > now:
                next_run = job.next_run_time
            else:
                if hasattr(job, '_get_next_multiple_time'):
                    next_run = job._get_next_multiple_time(now)
                else:
                    next_run = now + timedelta(days=1)
                
                if not next_run:
                    job.status = 'failed'
                    job.error_message = "No times could be scheduled"
                    job.save(update_fields=['status', 'error_message'])
                    return
                
                job.next_run_time = next_run
                job.status = 'scheduled'
                job.save(update_fields=['next_run_time', 'status'])

            seconds_until = int((next_run - now).total_seconds())
            logger.info(f"📅 Multiple daily: Next run at {next_run.strftime('%Y-%m-%d %I:%M %p')} (in {seconds_until}s)")

            process_batch_scheduler.apply_async(
                args=(job_id,),
                countdown=seconds_until,
                queue="batch_scheduler"
            )

            schedule_batch_job.apply_async(
                args=(job_id,),
                countdown=86400,
                queue="batch_scheduler"
            )
            return

        # ===== DAILY SCHEDULE =====
        if job.schedule_type == 'daily':
            # Check if job has pending/running executions
            pending_running = BatchExecution.objects.filter(
                job=job,
                status__in=['pending', 'running']
            ).count()
            
            if pending_running > 0:
                logger.info(f"ℹ️ Job {job_id} has {pending_running} pending/running executions, skipping scheduling")
                schedule_batch_job.apply_async(
                    args=(job_id,),
                    countdown=3600,
                    queue="batch_scheduler"
                )
                return

            # Check if all batches completed for custom batch
            if job.batch_size_type != 'full':
                total_batches = (job.total_customers + job.batch_size - 1) // job.batch_size
                completed_batches = BatchExecution.objects.filter(job=job, status='completed').count()
                
                if completed_batches >= total_batches and completed_batches > 0:
                    # All batches completed, reset for next cycle
                    logger.info(f"🔄 All {total_batches} batches completed, resetting for next day")
                    BatchExecution.objects.filter(job=job).delete()
                    job.completed_batches = 0
                    job.sent_count = 0
                    job.failed_count = 0
                    job.skipped_count = 0
                    job.save(update_fields=['completed_batches', 'sent_count', 'failed_count', 'skipped_count'])

            # Calculate next run time
            if job.next_run_time and job.next_run_time > now:
                next_run = job.next_run_time
            else:
                if job.schedule_datetime > now:
                    next_run = job.schedule_datetime
                else:
                    next_run = job.schedule_datetime
                    while next_run <= now:
                        next_run += timedelta(days=1)
                
                job.next_run_time = next_run
                job.status = 'scheduled'
                job.save(update_fields=['next_run_time', 'status'])

            seconds_until = int((next_run - now).total_seconds())
            logger.info(f"📅 Daily job: Next run at {next_run.strftime('%Y-%m-%d %I:%M %p')}")

            process_batch_scheduler.apply_async(
                args=(job_id,),
                countdown=seconds_until,
                queue="batch_scheduler"
            )

            schedule_batch_job.apply_async(
                args=(job_id,),
                countdown=86400,
                queue="batch_scheduler"
            )
            return

        # ===== WEEKLY SCHEDULE =====
        if job.schedule_type == 'weekly':
            # Check if job has pending/running executions
            pending_running = BatchExecution.objects.filter(
                job=job,
                status__in=['pending', 'running']
            ).count()
            
            if pending_running > 0:
                logger.info(f"ℹ️ Job {job_id} has {pending_running} pending/running executions, skipping scheduling")
                schedule_batch_job.apply_async(
                    args=(job_id,),
                    countdown=3600,
                    queue="batch_scheduler"
                )
                return

            # Check if all batches completed for custom batch
            if job.batch_size_type != 'full':
                total_batches = (job.total_customers + job.batch_size - 1) // job.batch_size
                completed_batches = BatchExecution.objects.filter(job=job, status='completed').count()
                
                if completed_batches >= total_batches and completed_batches > 0:
                    # All batches completed, reset for next cycle
                    logger.info(f"🔄 All {total_batches} batches completed, resetting for next week")
                    BatchExecution.objects.filter(job=job).delete()
                    job.completed_batches = 0
                    job.sent_count = 0
                    job.failed_count = 0
                    job.skipped_count = 0
                    job.save(update_fields=['completed_batches', 'sent_count', 'failed_count', 'skipped_count'])

            # Calculate next run time
            if job.next_run_time and job.next_run_time > now:
                next_run = job.next_run_time
            else:
                if job.schedule_datetime > now:
                    next_run = job.schedule_datetime
                else:
                    next_run = job.schedule_datetime
                    while next_run <= now:
                        next_run += timedelta(days=7)
                
                job.next_run_time = next_run
                job.status = 'scheduled'
                job.save(update_fields=['next_run_time', 'status'])

            seconds_until = int((next_run - now).total_seconds())
            logger.info(f"📅 Weekly job: Next run at {next_run.strftime('%Y-%m-%d %I:%M %p')}")

            process_batch_scheduler.apply_async(
                args=(job_id,),
                countdown=seconds_until,
                queue="batch_scheduler"
            )

            schedule_batch_job.apply_async(
                args=(job_id,),
                countdown=604800,
                queue="batch_scheduler"
            )
            return

        # ===== CUSTOM INTERVAL =====
        if job.schedule_type == 'custom_interval':
            if not job.interval_days:
                job.status = 'failed'
                job.error_message = "Interval days not configured"
                job.save(update_fields=['status', 'error_message'])
                return

            # Check if job has pending/running executions
            pending_running = BatchExecution.objects.filter(
                job=job,
                status__in=['pending', 'running']
            ).count()
            
            if pending_running > 0:
                logger.info(f"ℹ️ Job {job_id} has {pending_running} pending/running executions, skipping scheduling")
                schedule_batch_job.apply_async(
                    args=(job_id,),
                    countdown=3600,
                    queue="batch_scheduler"
                )
                return

            # Check if all batches completed for custom batch
            if job.batch_size_type != 'full':
                total_batches = (job.total_customers + job.batch_size - 1) // job.batch_size
                completed_batches = BatchExecution.objects.filter(job=job, status='completed').count()
                
                if completed_batches >= total_batches and completed_batches > 0:
                    # All batches completed, reset for next cycle
                    logger.info(f"🔄 All {total_batches} batches completed, resetting for next interval")
                    BatchExecution.objects.filter(job=job).delete()
                    job.completed_batches = 0
                    job.sent_count = 0
                    job.failed_count = 0
                    job.skipped_count = 0
                    job.save(update_fields=['completed_batches', 'sent_count', 'failed_count', 'skipped_count'])

            # Calculate next run time
            interval = job.interval_days
            
            if job.next_run_time and job.next_run_time > now:
                next_run = job.next_run_time
            else:
                next_run = job.schedule_datetime
                while next_run <= now:
                    next_run += timedelta(days=interval)
                
                job.next_run_time = next_run
                job.status = 'scheduled'
                job.save(update_fields=['next_run_time', 'status'])

            seconds_until = int((next_run - now).total_seconds())
            logger.info(f"📅 Custom job: Next run at {next_run.strftime('%Y-%m-%d %I:%M %p')}")

            process_batch_scheduler.apply_async(
                args=(job_id,),
                countdown=seconds_until,
                queue="batch_scheduler"
            )

            schedule_batch_job.apply_async(
                args=(job_id,),
                countdown=interval * 86400,
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
