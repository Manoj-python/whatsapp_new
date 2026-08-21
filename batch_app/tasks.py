# batch_app/tasks.py - COMPLETE PRODUCTION READY VERSION WITH API CHECK
# ✅ API CHECK INTEGRATED FOR PAID/UNPAID CUSTOMERS
# ✅ DYNAMIC APP FUNCTION DISCOVERY
# ✅ CLEAN AND ORGANIZED

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

# ============================================================
# 🎯 DYNAMIC TEMPLATE SELECTION
# ============================================================

def get_dynamic_template_id(target_app, job_template_id, emi_due_count):
    """
    Decide the actual WhatsApp template for this customer.
    
    The Batch Job template remains the user's manually selected
    base template. We only change the template actually sent
    when the selected job is a bucket campaign.
    
    Rules:
    - emi_due_count < 0.2 → Skip (No message)
    - emi_due_count < 2   → Bucket 1 (Template 44/52/53)
    - emi_due_count < 3   → Bucket 2 (Template 45/54/55)
    - emi_due_count >= 3  → Bucket 3 (Template 46/56/57)
    """
    
    target_app = str(target_app)
    job_template_id = str(job_template_id)
    
    # ============================================================
    # APP 1: messaging (SMSquare)
    # ============================================================
    if target_app == "messaging":
        
        # Customer bucket campaigns
        if job_template_id in {"44", "45", "46"}:
            
            if emi_due_count < 0.2:
                return None  # Skip
            
            if emi_due_count < 2:
                return "44"  # One Bucket Customer
            elif emi_due_count < 3:
                return "45"  # Two Buckets Customer
            else:
                return "46"  # Three+ Buckets Customer
        
        # Guarantor bucket - always send as is
        if job_template_id == "47":
            return "47"
    
    # ============================================================
    # APP 2: messaging2 (Padma Sai)
    # ============================================================
    elif target_app == "messaging2":
        
        # PSF customer bucket campaigns
        if job_template_id in {"52", "54", "56"}:
            
            if emi_due_count < 0.2:
                return None  # Skip
            
            if emi_due_count < 2:
                return "52"  # One Bucket PSF Customer
            elif emi_due_count < 3:
                return "54"  # Two Buckets PSF Customer
            else:
                return "56"  # Three+ PSF Customer
        
        # SMF customer bucket campaigns
        if job_template_id in {"53", "55", "57"}:
            
            if emi_due_count < 0.2:
                return None  # Skip
            
            if emi_due_count < 2:
                return "53"  # One Bucket SMF Customer
            elif emi_due_count < 3:
                return "55"  # Two Buckets SMF Customer
            else:
                return "57"  # Three+ SMF Customer
        
        # Guarantor bucket templates - always send as is
        if job_template_id in {"58", "59"}:
            return job_template_id
    
    # ============================================================
    # Non-bucket jobs (keep original template)
    # ============================================================
    return job_template_id
# ============================================================
# 🔥 HELPER FUNCTIONS FOR DYNAMIC APP DISCOVERY
# ============================================================

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


def get_app_schedule_function(app_name):
    """
    Get the schedule function from the app's utils
    Returns: function or None
    """
    try:
        utils = get_app_utils(app_name)
        
        if 'get_total_overdue_from_schedule' in utils:
            return utils['get_total_overdue_from_schedule']
        elif 'get_total_overdue_from_schedule2' in utils:
            return utils['get_total_overdue_from_schedule2']
        else:
            # Direct import for known apps
            if app_name == 'messaging':
                from messaging.utils import get_total_overdue_from_schedule
                return get_total_overdue_from_schedule
            elif app_name == 'messaging2':
                from messaging2.utils import get_total_overdue_from_schedule2
                return get_total_overdue_from_schedule2
            else:
                return None
    except Exception as e:
        logger.error(f"❌ Failed to import schedule function for {app_name}: {e}")
        return None


def get_app_needs_api_check_function(app_name):
    """
    Get the needs_api_check function from the app's utils
    Returns: function or None
    """
    try:
        utils = get_app_utils(app_name)
        
        if 'needs_api_check' in utils:
            return utils['needs_api_check']
        elif 'needs_api_check2' in utils:
            return utils['needs_api_check2']
        else:
            # Direct import for known apps
            if app_name == 'messaging':
                from messaging.utils import needs_api_check
                return needs_api_check
            elif app_name == 'messaging2':
                from messaging2.utils import needs_api_check
                return needs_api_check
            else:
                return None
    except Exception as e:
        logger.error(f"❌ Failed to import needs_api_check for {app_name}: {e}")
        return None


def check_payment_status_for_app(app_name, mobile, loan_number=None):
    """
    Check payment status using the app's check_smsquare_payment_status function
    Returns: {'is_paid': True/False, 'total_due': amount, 'customer_name': str}
    """
    try:
        # Try to get the function from app's utils
        utils = get_app_utils(app_name)
        
        if 'check_smsquare_payment_status' in utils:
            result = utils['check_smsquare_payment_status'](mobile, loan_number)
        elif 'check_payment_status' in utils:
            result = utils['check_payment_status'](mobile, loan_number)
        else:
            # Direct import for known apps
            if app_name == 'messaging':
                from messaging.utils import check_smsquare_payment_status
                result = check_smsquare_payment_status(mobile, loan_number)
            elif app_name == 'messaging2':
                from messaging2.utils import check_smsquare_payment_status
                result = check_smsquare_payment_status(mobile, loan_number)
            else:
                # No check function - assume UNPAID (send)
                return {
                    'is_paid': False,
                    'total_due': 0,
                    'customer_name': '',
                    'status': 'no_check'
                }
        
        # Ensure consistent format
        return {
            'is_paid': result.get('is_paid', False),
            'total_due': result.get('total_due', 0),
            'customer_name': result.get('customer_name', ''),
            'status': result.get('status', 'success')
        }
        
    except Exception as e:
        logger.warning(f"⚠️ API check failed for {app_name}/{mobile}: {e}")
        # On error, assume UNPAID (send reminder)
        return {
            'is_paid': False,
            'total_due': 0,
            'customer_name': '',
            'status': 'api_error'
        }


def get_app_seize_check_function(app_name):
    """
    Get the SeizeDate check function from the app's utils
    Returns: function or None
    """
    try:
        utils = get_app_utils(app_name)
        
        if 'check_smsquare_payment_status' in utils:
            return utils['check_smsquare_payment_status']
        elif 'check_smsquare_payment_status2' in utils:
            return utils['check_smsquare_payment_status2']
        elif 'check_payment_status' in utils:
            return utils['check_payment_status']
        else:
            # Direct import for known apps
            if app_name == 'messaging':
                from messaging.utils import check_smsquare_payment_status
                return check_smsquare_payment_status
            elif app_name == 'messaging2':
                from messaging2.utils import check_smsquare_payment_status2
                return check_smsquare_payment_status2
            else:
                return None
    except Exception as e:
        logger.error(f"❌ Failed to import seize check function for {app_name}: {e}")
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
            BatchExecution.objects.filter(job=job).delete()
            job.status = 'scheduled'
            job.completed_batches = 0
            job.sent_count = 0
            job.failed_count = 0
            job.skipped_count = 0
            job.save(update_fields=['status', 'completed_batches', 'sent_count', 'failed_count', 'skipped_count'])
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

    start_row = (next_batch_number - 1) * batch_size
    end_row = min(start_row + batch_size, total_customers)

    job.status = 'running'
    job.started_at = timezone.now()
    job.completed_batches = len(completed_batch_numbers)
    job.save(update_fields=['status', 'started_at', 'completed_batches'])

    logger.info(f"✅ Job {job_id} marked as running")
    logger.info(f"📊 Creating batch {next_batch_number}: rows {start_row} to {end_row}")

    execution = BatchExecution.objects.create(
        job=job,
        batch_number=next_batch_number,
        start_row=start_row,
        end_row=end_row,
        total_customers=end_row - start_row,
        status='pending'
    )
    logger.info(f"✅ Created execution {execution.id} for batch {next_batch_number}")

    job.total_batches = total_batches
    job.save(update_fields=['total_batches'])

    queue_name = 'messaging' if job.target_app == 'messaging' else 'messaging2'
    logger.info(f"📊 Using queue: {queue_name}")

    execute_batch.apply_async(
        args=(job_id, execution.id),
        queue=queue_name
    )
    logger.info(f"✅ Dispatched batch {next_batch_number} to {queue_name} queue")

    return 1


# ============================================================
# 🚀 BATCH EXECUTION TASK - One task per batch (WITH API CHECK & SEIZE DATE)
# ============================================================
@shared_task(bind=True, queue="batch_app", max_retries=2)
def execute_batch(self, job_id, execution_id):
    """
    EXECUTION TASK - Does the actual message sending for ONE batch
    ✅ FIXED: Dynamic API check using app's utility functions
    ✅ SKIPS PAID customers
    ✅ SKIPS SEIZED vehicles
    ✅ APPLIES 0.2 tolerance
    ✅ OVERRIDES Excel amount with real-time amount
    """
    close_old_connections()

    try:
        execution = BatchExecution.objects.get(id=execution_id)
        job = execution.job
    except (BatchExecution.DoesNotExist, BatchJob.DoesNotExist) as e:
        logger.error(f"❌ Execution {execution_id} or Job {job_id} not found: {e}")
        return

    if job.status == 'cancelled':
        execution.status = 'cancelled'
        execution.save(update_fields=['status'])
        logger.info(f"⛔ Job {job_id} cancelled, skipping execution {execution_id}")
        return

    if execution.status in ['completed', 'running']:
        logger.info(f"ℹ️ Execution {execution_id} already {execution.status}, skipping")
        return

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
        # 🔥 GET APP FUNCTIONS FOR API CHECK
        # ============================================================
        needs_api_check_func = get_app_needs_api_check_function(job.target_app)
        schedule_func = get_app_schedule_function(job.target_app)
        seize_check_func = get_app_seize_check_function(job.target_app)

        # ============================================================
        # 3. SEND MESSAGES VIA WHATSAPP API
        # ============================================================
        url = f"https://graph.facebook.com/v22.0/{creds['phone_number_id']}/messages"
        headers = {
            "Authorization": f"Bearer {creds['access_token']}",
            "Content-Type": "application/json",
        }

        sent = 0
        failed = 0
        skipped = 0
        seized_count = 0

        logger.info(f"📦 Batch {execution.batch_number}: Processing {batch_count} customers")

        for idx, row in enumerate(batch_customers):
            try:
                mobile = format_mobile(row.get('CustMobile') or row.get('cust_mobile') or '')
                customer_name = row.get('CustomerName') or row.get('customer_name') or ''
                loan_number = row.get('loan_number') or row.get('LoanNumber') or row.get('agreement_no') or row.get('AgreementNo')
                excel_amount = row.get('due_amount') or row.get('DueAmount') or '0'

                if not mobile:
                    failed += 1
                    continue

                # ============================================================
                # 🔍 SEIZE DATE CHECK - Skip seized vehicles (BEFORE API check)
                # ============================================================
                
                if seize_check_func:
                    try:
                        seize_result = seize_check_func(mobile, loan_number)
                        seize_date = seize_result.get('seize_date')
                        
                        if seize_date:
                            logger.info(f"⛔ {mobile} - Vehicle seized on {seize_date}, skipping")
                            seized_count += 1
                            
                            LogModel.objects.create(
                                job_id=job,
                                customer_name=customer_name,
                                mobile=mobile,
                                template_name=job.template_name,
                                sent_text_message=f"SEIZED - Vehicle seized on {seize_date}",
                                status='SEIZED',
                                message_type='Skipped',
                                error_message=f"Vehicle seized on {seize_date}",
                            )
                            continue
                    except Exception as e:
                        logger.warning(f"⚠️ SeizeDate check failed for {mobile}: {e}")
                        # Continue with normal flow

                # ============================================================
                # 🔍 API CHECK - Using app's utility functions
                # ============================================================
                real_time_due = None
                is_paid = False
                emi_due_count = 0
                should_skip = False

                # ✅ Check if template needs API check
                needs_check = False
                if needs_api_check_func:
                    try:
                        needs_check = needs_api_check_func(job.template_id)
                    except Exception as e:
                        logger.warning(f"⚠️ Error checking needs_api_check: {e}")

                logger.info(f"📋 Template {job.template_id} - API Check: {'YES' if needs_check else 'NO'}")

                if needs_check and schedule_func:
                    try:
                        # ✅ Call with include_upcoming=True for bucket templates
                        # For bucket templates (44-47 in messaging, 52-59 in messaging2)
                        # we want to INCLUDE current month
                        schedule_data = schedule_func(mobile, loan_number, include_upcoming=True)

                        real_time_due = schedule_data.get('total_due', 0)
                        is_paid = schedule_data.get('is_paid', False)
                        emi_due_count = schedule_data.get('emi_due_count', 0)

                        logger.info(f"📊 EMI Due Count: {emi_due_count}")
                        logger.info(f"📊 Total Due: ₹{real_time_due}")
                        logger.info(f"📊 Is Paid: {is_paid}")

                        # ============================================================
                        # 🎯 DETERMINE ACTUAL TEMPLATE FOR THIS CUSTOMER
                        # ============================================================

                        actual_template_id = get_dynamic_template_id(
                            job.target_app,
                            job.template_id,
                            emi_due_count,
                        )
        
                        logger.info(
                            f"🎯 {mobile} | "
                            f"App={job.target_app} | "
                            f"Job Template={job.template_id} | "
                            f"EMI Count={emi_due_count} | "
                            f"Actual Template={actual_template_id} | "
                            f"Current Due=₹{real_time_due}"
                        )
                      

                        # Skip if no applicable bucket
                        if actual_template_id is None:
                            logger.info(f"⏭️ {mobile} - Skipping (EMI count {emi_due_count} < 0.2)")
                            skipped += 1
                            
                            LogModel.objects.create(
                                job_id=job,
                                customer_name=customer_name,
                                mobile=mobile,
                                template_name=job.template_name,
                                sent_text_message=f"SKIPPED - EMI Due Count: {emi_due_count}",
                                status="SKIPPED",
                                message_type="Skipped",
                                error_message=f"No applicable bucket. EMI Due Count={emi_due_count}",
                            )
                            continue

                        # ✅ Step 1: Apply 0.2 tolerance
                        if emi_due_count < 0.2:
                            logger.info(f"✅ {mobile} - Skipping (only {emi_due_count} EMI overdue)")
                            should_skip = True
                            skipped += 1

                            LogModel.objects.create(
                                job_id=job,
                                customer_name=customer_name,
                                mobile=mobile,
                                template_name=job.template_name,
                                sent_text_message=f"SKIPPED - Only {emi_due_count} EMI overdue",
                                status='SKIPPED',
                                message_type='Skipped',
                                error_message=f"Only {emi_due_count} EMI overdue - skipped",
                            )
                            continue

                        # ✅ Step 2: Check if PAID
                        if is_paid:
                            logger.info(f"✅ {mobile} - PAID (₹{real_time_due}), skipping")
                            should_skip = True
                            skipped += 1

                            LogModel.objects.create(
                                job_id=job,
                                customer_name=customer_name,
                                mobile=mobile,
                                template_name=job.template_name,
                                sent_text_message=f"PAID - No message sent (Total Due: ₹{real_time_due})",
                                status='PAID',
                                message_type='Skipped',
                                error_message=f"Customer is PAID (Excel: ₹{excel_amount} | Actual: ₹{real_time_due})",
                            )
                            continue

                        # ✅ Step 3: Override Excel amount with real-time amount
                        if real_time_due is not None and real_time_due > 0:
                            row['due_amount'] = str(real_time_due)
                            logger.info(f"🔄 {mobile} - UNPAID (Excel: ₹{excel_amount} → Actual: ₹{real_time_due})")

                            # Update customer name if available
                            if schedule_data.get('customer_name'):
                                row['customer_name'] = schedule_data.get('customer_name')

                    except Exception as api_error:
                        logger.warning(f"⚠️ API Error for {mobile}: {api_error} - Using Excel data")
                        # Continue with Excel data

                if should_skip:
                    continue

                # ============================================================
                # 📤 SEND MESSAGE (With updated real-time amount)
                # ============================================================
                payload, rendered_text = build_payload(actual_template_id, row, None)
                payload['to'] = mobile

                resp = requests.post(url, headers=headers, json=payload, timeout=30)

                if resp.ok:
                    msg_id = resp.json()['messages'][0]['id']
                    sent += 1

                    # Log with real-time amount if available
                    log_text = rendered_text
                    if real_time_due:
                        log_text = f"{rendered_text}\n\n📊 Excel: ₹{excel_amount} | Actual: ₹{real_time_due}"

                    # Get actual template name for logging
                    from .app_discovery import get_template_name_for_id
                    actual_template_name = get_template_name_for_id(job.target_app, actual_template_id)

                    LogModel.objects.create(
                        job_id=job,
                        customer_name=customer_name,
                        mobile=mobile,
                        template_name=actual_template_name or str(actual_template_id),  # ✅ NEW - Log actual template
                        sent_text_message=log_text or f"📨 Batch: {job.template_name}",
                        status="Sent",
                        message_id=msg_id,
                        message_type="Sent",
                        content_type="text",
                        error_message=(
                            f"Job Template: {job.template_id} | "
                            f"Actual Template: {actual_template_id} | "
                            f"EMI Count: {emi_due_count} | "
                            f"Actual Due: ₹{real_time_due}"
                        ),
                    )

                    if ContactModel:
                        ContactModel.objects.update_or_create(
                            mobile=mobile,
                            defaults={
                                "last_msg": log_text or f"📨 Batch: {job.template_name}",
                                "last_time": timezone.now(),
                                "last_type": "Sent",
                                "last_status": "Sent",
                                "unread": 0
                            }
                        )

                    logger.info(f"✅ [{job.target_app}] Sent to {mobile} - Amount: ₹{row.get('due_amount', 0)}")
                    print(f"===================================================================")
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
        # 4. UPDATE EXECUTION STATISTICS
        # ============================================================
        execution.sent_count = sent
        execution.failed_count = failed
        execution.skipped_count = skipped + seized_count
        execution.status = 'completed'
        execution.completed_at = timezone.now()
        execution.save(update_fields=['sent_count', 'failed_count', 'skipped_count', 'status', 'completed_at'])

        logger.info(f"✅ Batch {execution.batch_number} completed: Sent={sent}, Skipped={skipped + seized_count}, Seized={seized_count}, Failed={failed}")

        # ============================================================
        # 5. UPDATE JOB PROGRESS
        # ============================================================
        completed_batches = BatchExecution.objects.filter(job=job, status='completed').count()

        aggregate_stats = BatchExecution.objects.filter(job=job).aggregate(
            total_sent=Sum('sent_count'),
            total_failed=Sum('failed_count'),
            total_skipped=Sum('skipped_count')
        )

        job.total_runs += 1
        job.completed_batches = completed_batches
        job.sent_count = aggregate_stats['total_sent'] or 0
        job.failed_count = aggregate_stats['total_failed'] or 0
        job.skipped_count = aggregate_stats['total_skipped'] or 0

        # ============================================================
        # 6. CHECK IF ALL BATCHES ARE COMPLETED
        # ============================================================
        if job.batch_size_type == 'full':
            total_batches = 1
        else:
            total_batches = (job.total_customers + job.batch_size - 1) // job.batch_size

        existing_executions = BatchExecution.objects.filter(job=job).count()
        total_batches = max(total_batches, existing_executions)

        logger.info(f"📊 Total batches: {total_batches}, Completed: {completed_batches}, Total Runs: {job.total_runs}")

        if completed_batches >= total_batches:
            job.completed_at = timezone.now()

            if job.schedule_type in ['daily', 'weekly', 'custom_interval', 'multiple_daily']:
                if job.batch_size_type == 'full':
                    logger.info(f"🔄 FULL BATCH: Completed run #{job.total_runs}, scheduling next run")

                    if job.schedule_type == 'daily':
                        next_run = job.schedule_datetime + timedelta(days=1)
                    elif job.schedule_type == 'weekly':
                        next_run = job.schedule_datetime + timedelta(days=7)
                    elif job.schedule_type == 'custom_interval':
                        next_run = job.schedule_datetime + timedelta(days=job.interval_days or 1)
                    else:
                        next_run = job.schedule_datetime + timedelta(days=1)

                    job.status = 'scheduled'
                    job.next_run_time = next_run
                    job.save(update_fields=[
                        'completed_batches', 'sent_count', 'failed_count',
                        'skipped_count', 'status', 'completed_at', 'next_run_time', 'total_runs'
                    ])

                    BatchExecution.objects.filter(job=job).delete()
                    job.completed_batches = 0
                    job.save(update_fields=['completed_batches'])

                    schedule_batch_job.delay(job.job_id)
                    logger.info(f"📅 Next run #{job.total_runs + 1} scheduled for {next_run}")
                    return
                else:
                    if job.end_date and timezone.now() >= job.end_date:
                        job.status = 'completed'
                        job.next_run_time = None
                        job.save(update_fields=['completed_batches', 'sent_count', 'failed_count',
                                               'skipped_count', 'status', 'completed_at', 'next_run_time', 'total_runs'])
                        logger.info(f"✅ Job ended (end_date reached) after {job.total_runs} runs")
                    else:
                        logger.info(f"🔄 CUSTOM BATCH: Resetting for next schedule")

                        BatchExecution.objects.filter(job=job).delete()

                        job.status = 'scheduled'
                        job.completed_batches = 0
                        job.sent_count = 0
                        job.failed_count = 0
                        job.skipped_count = 0

                        if job.schedule_type == 'daily':
                            next_run = job.schedule_datetime + timedelta(days=1)
                        elif job.schedule_type == 'weekly':
                            next_run = job.schedule_datetime + timedelta(days=7)
                        elif job.schedule_type == 'custom_interval':
                            next_run = job.schedule_datetime + timedelta(days=job.interval_days or 1)
                        else:
                            next_run = job.schedule_datetime + timedelta(days=1)

                        job.next_run_time = next_run
                        job.save(update_fields=['completed_batches', 'sent_count', 'failed_count',
                                               'skipped_count', 'status', 'completed_at', 'next_run_time', 'total_runs'])

                        schedule_batch_job.delay(job.job_id)
                        logger.info(f"📅 Next run #{job.total_runs + 1} scheduled for {next_run}")
                    return
            else:
                job.status = 'completed'
                job.next_run_time = None
                job.save(update_fields=['completed_batches', 'sent_count', 'failed_count',
                                       'skipped_count', 'status', 'completed_at', 'next_run_time', 'total_runs'])
                logger.info(f"✅ ALL BATCHES COMPLETED for {job.job_id} after {job.total_runs} runs")
        else:
            job.status = 'scheduled'

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

            job.save(update_fields=['completed_batches', 'sent_count', 'failed_count',
                                   'skipped_count', 'status', 'next_run_time', 'total_runs'])

            logger.info(f"📊 Progress: {completed_batches}/{total_batches} batches completed")
            logger.info(f"📊 Run #{job.total_runs} stats - Sent: {job.sent_count}, Skipped: {job.skipped_count}, Failed: {job.failed_count}")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Batch {execution.batch_number} failed: {error_msg}")
        logger.error(traceback.format_exc())

        execution.status = 'failed'
        execution.error_message = error_msg[:500]
        execution.save(update_fields=['status', 'error_message'])

        try:
            job.status = 'scheduled'
            job.save(update_fields=['status'])
        except Exception as save_error:
            logger.error(f"❌ Failed to update job status: {save_error}")

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
    Use process_batch_scheduler + execute_batch instead
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

        BatchExecution.objects.filter(job=job, status='pending').update(status='cancelled')

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
# 📅 SCHEDULER - PERFECT TIME HANDLING
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

    if job.status == 'cancelled':
        logger.info(f"ℹ️ Job {job_id} is cancelled, skipping scheduling")
        return

    if job.schedule_type == 'one_time' and job.status == 'completed':
        logger.info(f"ℹ️ One-time job {job_id} is completed, skipping scheduling")
        return

    if job.status == 'completed' and job.schedule_type != 'one_time':
        logger.info(f"🔄 Recurring job {job_id} was marked completed, resetting to scheduled")
        job.status = 'scheduled'
        job.save(update_fields=['status'])

    try:
        if job.end_date and timezone.now() >= job.end_date:
            job.status = 'completed'
            job.next_run_time = None
            job.save(update_fields=['status', 'next_run_time'])
            logger.info(f"📅 Job {job_id} ended (end_date reached)")
            return

        now = timezone.now()

        # ===== MULTIPLE DAILY SCHEDULE =====
        if job.schedule_type == 'multiple_daily':
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
            return

        # ===== DAILY SCHEDULE =====
        if job.schedule_type == 'daily':
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

            if job.batch_size_type != 'full':
                total_batches = (job.total_customers + job.batch_size - 1) // job.batch_size
                completed_batches = BatchExecution.objects.filter(job=job, status='completed').count()

                if completed_batches >= total_batches and completed_batches > 0:
                    logger.info(f"🔄 All {total_batches} batches completed, resetting for next day")
                    BatchExecution.objects.filter(job=job).delete()
                    job.completed_batches = 0
                    job.sent_count = 0
                    job.failed_count = 0
                    job.skipped_count = 0
                    job.save(update_fields=['completed_batches', 'sent_count', 'failed_count', 'skipped_count'])

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
            return

        # ===== WEEKLY SCHEDULE =====
        if job.schedule_type == 'weekly':
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

            if job.batch_size_type != 'full':
                total_batches = (job.total_customers + job.batch_size - 1) // job.batch_size
                completed_batches = BatchExecution.objects.filter(job=job, status='completed').count()

                if completed_batches >= total_batches and completed_batches > 0:
                    logger.info(f"🔄 All {total_batches} batches completed, resetting for next week")
                    BatchExecution.objects.filter(job=job).delete()
                    job.completed_batches = 0
                    job.sent_count = 0
                    job.failed_count = 0
                    job.skipped_count = 0
                    job.save(update_fields=['completed_batches', 'sent_count', 'failed_count', 'skipped_count'])

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
            return

        # ===== CUSTOM INTERVAL =====
        if job.schedule_type == 'custom_interval':
            if not job.interval_days:
                job.status = 'failed'
                job.error_message = "Interval days not configured"
                job.save(update_fields=['status', 'error_message'])
                return

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

            if job.batch_size_type != 'full':
                total_batches = (job.total_customers + job.batch_size - 1) // job.batch_size
                completed_batches = BatchExecution.objects.filter(job=job, status='completed').count()

                if completed_batches >= total_batches and completed_batches > 0:
                    logger.info(f"🔄 All {total_batches} batches completed, resetting for next interval")
                    BatchExecution.objects.filter(job=job).delete()
                    job.completed_batches = 0
                    job.sent_count = 0
                    job.failed_count = 0
                    job.skipped_count = 0
                    job.save(update_fields=['completed_batches', 'sent_count', 'failed_count', 'skipped_count'])

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
            return

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
