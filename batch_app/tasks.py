# batch_app/tasks.py - COMPLETE PRODUCTION READY VERSION
# ✅ DUPLICATE PREVENTION WITH REDIS CLAIMS
# ✅ JOB INDEPENDENCE WITH PER-JOB LOCKS
# ✅ IST TIMEZONE (12-HOUR FORMAT)
# ✅ PARALLEL PROCESSING (FAST)
# ✅ NO STUCK JOBS - PROPER CLEANUP
# ✅ MONTHLY SCHEDULE SUPPORT
# ✅ ACCURATE COUNTS & REPORTS

import time
import logging
import re
import threading
import calendar
from datetime import datetime, timedelta
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django.db import close_old_connections, DatabaseError, transaction
from django.db.models import Sum
from django.core.cache import cache
import requests
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dateutil.relativedelta import relativedelta

from .models import BatchJob, BatchLog, BatchExecution
from .utils import format_mobile, get_batch_from_s3, read_excel_from_s3
from .app_discovery import get_app_by_name, get_app_log_model, get_app_contact_model, get_app_utils

logger = logging.getLogger(__name__)

# ============================================================
# ⚙️ PRODUCTION CONFIGURATION
# ============================================================
MAX_WORKERS = 10                      # Parallel workers per batch
MAX_API_CALLS_PER_SECOND = 8          # WhatsApp API rate limit
API_TIMEOUT_CONNECT = 5               # Connection timeout
API_TIMEOUT_READ = 20                 # Read timeout
HEARTBEAT_INTERVAL = 25               # Progress update every 25 customers
EXECUTION_HEARTBEAT_TTL = 15 * 60       # Redis heartbeat TTL; refreshed while task is alive
STUCK_EXECUTION_AFTER = 60 * 60         # Only auto-fail if no heartbeat for 1 hour
JOB_LOCK_TIMEOUT = 60 * 60 * 24       # 24 hours per job
CUSTOMER_CLAIM_TIMEOUT = 60 * 60 * 24 * 730 # 2 years; supports long monthly/custom campaigns


# ============================================================
# 🕒 IST TIMEZONE HELPERS
# ============================================================
def get_ist_time():
    """Get current time in IST"""
    return timezone.localtime(timezone.now())

def format_ist_datetime(dt):
    """Format datetime in IST 12-hour format"""
    if not dt:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return timezone.localtime(dt)

def format_ist_12hr(dt):
    """Format datetime in 12-hour IST format"""
    ist_dt = format_ist_datetime(dt)
    if not ist_dt:
        return '-'
    return ist_dt.strftime('%Y-%m-%d %I:%M:%S %p')


# ============================================================
# 🔒 REDIS LOCKS FOR DUPLICATE PREVENTION
# ============================================================
def acquire_job_lock(job_id, timeout=JOB_LOCK_TIMEOUT):
    """Atomic Redis lock per job - prevents overlapping scheduler runs."""
    key = f"batch_job_lock:{job_id}"
    try:
        return bool(cache.add(key, "1", timeout))
    except Exception as e:
        logger.error(f"❌ Job lock failed for {job_id}: {e}")
        return False


def release_job_lock(job_id):
    """Release scheduler lock for a job."""
    try:
        cache.delete(f"batch_job_lock:{job_id}")
    except Exception as e:
        logger.warning(f"⚠️ Could not release lock for {job_id}: {e}")


def is_job_locked(job_id):
    """Check whether a job scheduler lock exists."""
    try:
        return cache.get(f"batch_job_lock:{job_id}") is not None
    except Exception:
        # Fail closed: never dispatch when duplicate protection is unavailable.
        return True


def get_occurrence_token(job):
    """
    Stable token for one scheduled occurrence.

    IMPORTANT:
    This intentionally does NOT use execution_id.
    If an execution is retried/recreated after a worker crash, the same
    occurrence must still be blocked from sending the same customer twice.

    total_runs is incremented only after the complete occurrence finishes,
    so all batches belonging to one occurrence share the same token.
    """
    return str(int(job.total_runs or 0))


def get_customer_claim_key(job_id, occurrence_token, mobile):
    safe_mobile = re.sub(r"[^0-9A-Za-z_.-]", "_", str(mobile))
    return f"wa_send_claim:{job_id}:{occurrence_token}:{safe_mobile}"


def claim_customer_send(job_id, occurrence_token, mobile):
    """
    Atomically claim a customer for ONE job occurrence.

    The claim is execution-independent. Therefore:
      - duplicate rows in the same batch are blocked;
      - duplicate rows across batches in the same occurrence are blocked;
      - a retry/new execution of the same occurrence is blocked;
      - the next scheduled occurrence is allowed because total_runs changes.
    """
    key = get_customer_claim_key(job_id, occurrence_token, mobile)
    try:
        return bool(cache.add(key, "claimed", CUSTOMER_CLAIM_TIMEOUT))
    except Exception as e:
        logger.error(
            f"❌ Customer claim unavailable for job={job_id}, "
            f"occurrence={occurrence_token}, mobile={mobile}: {e}"
        )
        # Fail closed. A Redis outage must never turn into duplicate sends.
        return False


def release_customer_send_claim(job_id, occurrence_token, mobile):
    """Release a claim only when the WhatsApp request definitely was NOT sent."""
    try:
        cache.delete(get_customer_claim_key(job_id, occurrence_token, mobile))
    except Exception:
        pass


def set_execution_heartbeat(execution_id):
    """Refresh DB + Redis liveness for a long-running execution."""
    heartbeat_now = timezone.now()

    # DB heartbeat is the authoritative fallback. This means cleanup can still
    # identify a dead worker even if the Redis heartbeat key disappears.
    try:
        BatchExecution.objects.filter(id=execution_id).update(
            last_heartbeat=heartbeat_now
        )
    except Exception as e:
        logger.warning(f"⚠️ DB heartbeat failed for execution {execution_id}: {e}")

    try:
        cache.set(
            f"batch_execution_heartbeat:{execution_id}",
            "alive",
            EXECUTION_HEARTBEAT_TTL,
        )
        # Prevent the execution lock from expiring on unusually large batches.
        cache.set(
            f"batch_execution_lock:{execution_id}",
            "1",
            JOB_LOCK_TIMEOUT,
        )
    except Exception as e:
        logger.warning(
            f"⚠️ Redis heartbeat/lock refresh failed for execution "
            f"{execution_id}: {e}"
        )


def clear_execution_heartbeat(execution_id):
    try:
        cache.delete(f"batch_execution_heartbeat:{execution_id}")
    except Exception:
        pass


def execution_has_heartbeat(execution_id):
    """Return True if the execution has a recent DB or Redis heartbeat."""
    try:
        db_value = BatchExecution.objects.filter(
            id=execution_id,
            last_heartbeat__gte=timezone.now() - timedelta(seconds=STUCK_EXECUTION_AFTER),
        ).exists()
        if db_value:
            return True
    except Exception as e:
        logger.warning(f"⚠️ DB heartbeat check failed for execution {execution_id}: {e}")

    try:
        return cache.get(f"batch_execution_heartbeat:{execution_id}") is not None
    except Exception:
        # If both checks are unavailable, fail closed: never auto-fail a job
        # merely because Redis/DB connectivity is temporarily unavailable.
        return True


# ============================================================
# 🚦 API RATE LIMITER
# ============================================================
class RateLimiter:
    def __init__(self, max_calls_per_second=MAX_API_CALLS_PER_SECOND):
        self.max_calls = max_calls_per_second
        self.calls = []
        self.lock = threading.Lock()

    def wait(self):
        while True:
            with self.lock:
                now = time.monotonic()
                self.calls = [t for t in self.calls if now - t < 1.0]
                if len(self.calls) < self.max_calls:
                    self.calls.append(now)
                    return
                sleep_time = max(0.01, 1.0 - (now - self.calls[0]) + 0.01)
            time.sleep(sleep_time)

_rate_limiters = {}
_rate_limiters_lock = threading.Lock()

def get_rate_limiter(app_name):
    """One limiter per WhatsApp app so unrelated apps do not throttle each other."""
    key = str(app_name or "default")
    with _rate_limiters_lock:
        limiter = _rate_limiters.get(key)
        if limiter is None:
            limiter = RateLimiter()
            _rate_limiters[key] = limiter
        return limiter


# ============================================================
# 🌐 HTTP SESSION WITH CONNECTION POOLING
# ============================================================
_thread_local = threading.local()

def get_session():
    """Thread-local HTTP session with connection pooling"""
    if not hasattr(_thread_local, "session"):
        session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=MAX_WORKERS,
            pool_maxsize=MAX_WORKERS,
            max_retries=Retry(
                total=2,
                backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET"],
                raise_on_status=False,
            ),
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        _thread_local.session = session
    return _thread_local.session


# ============================================================
# 🕒 SCHEDULE CALCULATOR - CORRECT NEXT RUN TIME
# ============================================================
def get_multiple_daily_times(job):
    """Get multiple daily times from job"""
    times = getattr(job, "schedule_times", [])
    if isinstance(times, str):
        try:
            import json
            times = json.loads(times)
        except Exception:
            times = [t.strip() for t in times.split(",") if t.strip()]
    if not times:
        return []
    return sorted(str(t) for t in times)

def calculate_next_run_time(job, from_time=None):
    """
    Calculate the next scheduled run time for a job.
    Supports: one_time, daily, weekly, custom_interval, monthly, multiple_daily
    """
    if not from_time:
        from_time = timezone.now()
    
    now = from_time
    if timezone.is_naive(now):
        now = timezone.make_aware(now, timezone.get_current_timezone())
    
    base = job.schedule_datetime
    if timezone.is_naive(base):
        base = timezone.make_aware(base, timezone.get_current_timezone())
    
    now_local = timezone.localtime(now)
    base_local = timezone.localtime(base)
    
    # ONE TIME
    if job.schedule_type == "one_time":
        if base > now:
            return base
        return None
    
    # DAILY
    if job.schedule_type == "daily":
        candidate = timezone.make_aware(
            datetime.combine(now_local.date(), base_local.time()),
            timezone.get_current_timezone()
        )
        if candidate <= now_local:
            candidate += timedelta(days=1)
        return candidate
    
    # WEEKLY
    if job.schedule_type == "weekly":
        target_weekday = (
            job.weekly_day
            if job.weekly_day is not None
            else base_local.weekday()
        )
        days_ahead = (target_weekday - now_local.weekday()) % 7
        candidate = timezone.make_aware(
            datetime.combine(
                now_local.date() + timedelta(days=days_ahead),
                base_local.time(),
            ),
            timezone.get_current_timezone(),
        )
        if candidate <= now_local:
            candidate += timedelta(days=7)
        return candidate
    
    # CUSTOM INTERVAL - anchored to the original schedule_datetime
    if job.schedule_type == "custom_interval":
        interval = max(int(job.interval_days or 1), 1)
        candidate = base
        while candidate <= now:
            candidate += timedelta(days=interval)
        return candidate
    
    # MONTHLY
    if job.schedule_type == "monthly":
        target_day = base_local.day
        year, month = now_local.year, now_local.month
        day = min(target_day, calendar.monthrange(year, month)[1])
        candidate = timezone.make_aware(
            datetime(year, month, day, base_local.hour, base_local.minute, base_local.second),
            timezone.get_current_timezone()
        )
        if candidate <= now_local:
            if month == 12:
                year, month = year + 1, 1
            else:
                month += 1
            day = min(target_day, calendar.monthrange(year, month)[1])
            candidate = timezone.make_aware(
                datetime(year, month, day, base_local.hour, base_local.minute, base_local.second),
                timezone.get_current_timezone()
            )
        return candidate
    
    # MULTIPLE DAILY
    if job.schedule_type == "multiple_daily":
        times = get_multiple_daily_times(job)
        if times:
            for time_str in times:
                try:
                    hour, minute = map(int, time_str.split(":")[:2])
                    candidate = timezone.make_aware(
                        datetime.combine(now_local.date(), datetime.min.time().replace(hour=hour, minute=minute)),
                        timezone.get_current_timezone()
                    )
                    if candidate > now_local:
                        return candidate
                except Exception:
                    continue
            # All times passed, use tomorrow's first time
            first = times[0]
            hour, minute = map(int, first.split(":")[:2])
            tomorrow = now_local.date() + timedelta(days=1)
            return timezone.make_aware(
                datetime.combine(tomorrow, datetime.min.time().replace(hour=hour, minute=minute)),
                timezone.get_current_timezone()
            )
    
    # Fallback: daily at base time
    candidate = timezone.make_aware(
        datetime.combine(now_local.date(), base_local.time()),
        timezone.get_current_timezone()
    )
    if candidate <= now_local:
        candidate += timedelta(days=1)
    return candidate


# ============================================================
# 🎯 DYNAMIC TEMPLATE SELECTION (SAME AS YOUR OLD CODE)
# ============================================================
def get_dynamic_template_id(target_app, job_template_id, emi_due_count):
    """Dynamic template selection based on EMI count"""
    target_app = str(target_app)
    job_template_id = str(job_template_id)
    
    # APP 1: messaging (SMSquare)
    if target_app == "messaging":
        if job_template_id in {"44", "45", "46"}:
            if emi_due_count < 0.2:
                return None
            if emi_due_count < 2:
                return "44"
            elif emi_due_count < 3:
                return "45"
            else:
                return "46"
        if job_template_id == "47":
            return "47"
    
    # APP 2: messaging2 (Padma Sai)
    elif target_app == "messaging2":
        if job_template_id in {"52", "54", "56"}:
            if emi_due_count < 0.2:
                return None
            if emi_due_count < 2:
                return "52"
            elif emi_due_count < 3:
                return "54"
            else:
                return "56"
        if job_template_id in {"53", "55", "57"}:
            if emi_due_count < 0.2:
                return None
            if emi_due_count < 2:
                return "53"
            elif emi_due_count < 3:
                return "55"
            else:
                return "57"
        if job_template_id in {"58", "59"}:
            return job_template_id
    
    # Non-bucket jobs
    return job_template_id


# ============================================================
# 🔥 HELPER FUNCTIONS FOR APP DISCOVERY
# ============================================================
def get_build_payload_function(app_name):
    """Get build_payload function from app"""
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
    except Exception as e:
        logger.error(f"❌ Failed to import build_payload for {app_name}: {e}")
    return None

def get_app_schedule_function(app_name):
    """Get schedule function from app"""
    try:
        utils = get_app_utils(app_name)
        if 'get_total_overdue_from_schedule' in utils:
            return utils['get_total_overdue_from_schedule']
        elif 'get_total_overdue_from_schedule2' in utils:
            return utils['get_total_overdue_from_schedule2']
        else:
            if app_name == 'messaging':
                from messaging.utils import get_total_overdue_from_schedule
                return get_total_overdue_from_schedule
            elif app_name == 'messaging2':
                from messaging2.utils import get_total_overdue_from_schedule2
                return get_total_overdue_from_schedule2
    except Exception as e:
        logger.error(f"❌ Failed to import schedule function for {app_name}: {e}")
    return None

def get_app_needs_api_check_function(app_name):
    """Get needs_api_check function from app"""
    try:
        utils = get_app_utils(app_name)
        if 'needs_api_check' in utils:
            return utils['needs_api_check']
        elif 'needs_api_check2' in utils:
            return utils['needs_api_check2']
        else:
            if app_name == 'messaging':
                from messaging.utils import needs_api_check
                return needs_api_check
            elif app_name == 'messaging2':
                from messaging2.utils import needs_api_check
                return needs_api_check
    except Exception as e:
        logger.error(f"❌ Failed to import needs_api_check for {app_name}: {e}")
    return None

def get_app_seize_check_function(app_name):
    """Get seize check function from app"""
    try:
        utils = get_app_utils(app_name)
        if 'check_smsquare_payment_status' in utils:
            return utils['check_smsquare_payment_status']
        elif 'check_smsquare_payment_status2' in utils:
            return utils['check_smsquare_payment_status2']
        elif 'check_payment_status' in utils:
            return utils['check_payment_status']
        else:
            if app_name == 'messaging':
                from messaging.utils import check_smsquare_payment_status
                return check_smsquare_payment_status
            elif app_name == 'messaging2':
                from messaging2.utils import check_smsquare_payment_status2
                return check_smsquare_payment_status2
    except Exception as e:
        logger.error(f"❌ Failed to import seize check function for {app_name}: {e}")
    return None

def get_actual_template_name(target_app, template_id):
    """Get template name from template ID"""
    if template_id is None:
        return ""
    try:
        from .app_discovery import get_template_name_for_id
        return get_template_name_for_id(target_app, template_id) or str(template_id)
    except Exception:
        return str(template_id)


# ============================================================
# 👤 SINGLE CUSTOMER PROCESSOR - WITH DUPLICATE PREVENTION
# ============================================================
# ============================================================
# 👤 SINGLE CUSTOMER PROCESSOR - WITH DUPLICATE PREVENTION
# ============================================================
def process_single_customer(
    row, job, execution_id, LogModel, ContactModel, url, headers,
    build_payload, needs_api_check_func, schedule_func, seize_check_func
):
    """
    Process ONE customer.

    IMPORTANT:
    - Existing business/template logic is preserved.
    - Template 36 with needs_api_check=False will NOT enter
      EMI / PAID / due_amount logic.
    - Duplicate prevention is preserved.
    - Every duplicate skip is now written to LogModel.
    - Every send/API failure remains FAILED.
    """

    result = {
        "sent": 0,
        "failed": 0,
        "skipped": 0,
        "mobile": "",
        "error": None,
    }

    mobile = ""
    claim_owned = False
    send_attempted = False
    actual_template_id = job.template_id
    occurrence_token = get_occurrence_token(job)

    customer_name = ""
    loan_number = ""
    excel_amount = "0"
    vehicle_number = ""
    actual_template_name = ""

    try:
        # ========================================================
        # 1. EXTRACT CUSTOMER DATA
        # ========================================================
        mobile = format_mobile(
            row.get("CustMobile")
            or row.get("cust_mobile")
            or ""
        )

        customer_name = (
            row.get("CustomerName")
            or row.get("customer_name")
            or ""
        )

        loan_number = (
            row.get("loan_number")
            or row.get("LoanNumber")
            or row.get("agreement_no")
            or row.get("AgreementNo")
            or ""
        )

        excel_amount = (
            row.get("due_amount")
            or row.get("DueAmount")
            or "0"
        )

        vehicle_number = (
            row.get("vehicle_number")
            or row.get("VehicleNumber")
            or row.get("VehicleNo")
            or row.get("vehicle_no")
            or ""
        )

        result["mobile"] = mobile

        # ========================================================
        # 2. INVALID MOBILE
        # ========================================================
        if not mobile:
            result["failed"] = 1
            result["error"] = "Invalid mobile number"

            try:
                LogModel.objects.create(
                    job_id=job,
                    customer_name=customer_name,
                    mobile="",
                    template_name=job.template_name or str(job.template_id or ""),
                    sent_text_message="",
                    status="Failed",
                    message_type="Sent",
                    error_message="Invalid mobile number",
                    sent_at=timezone.now(),
                )
            except Exception:
                logger.exception(
                    f"❌ Failed to save invalid-mobile report "
                    f"for job={job.job_id}"
                )

            return result

        # ========================================================
        # 3. SEIZE DATE CHECK
        # ========================================================
        if seize_check_func:
            try:
                seize_result = seize_check_func(
                    mobile,
                    loan_number
                ) or {}

                seize_date = seize_result.get("seize_date")

                if seize_date:
                    result["skipped"] = 1

                    try:
                        LogModel.objects.create(
                            job_id=job,
                            customer_name=customer_name,
                            mobile=mobile,
                            template_name="SEIZED",
                            sent_text_message="Vehicle seized",
                            status="SEIZED",
                            message_type="Skipped",
                            error_message=(
                                f"Vehicle seized on {seize_date}"
                            ),
                            sent_at=timezone.now(),
                        )
                    except Exception:
                        logger.exception(
                            f"❌ Failed to save seized report "
                            f"for {mobile}"
                        )

                    logger.info(
                        f"⛔ {mobile} - Vehicle seized on {seize_date}"
                    )

                    return result

            except Exception as e:
                # IMPORTANT:
                # Seize API failure must NOT automatically skip customer.
                logger.warning(
                    f"⚠️ Seize check failed for {mobile}: {e}"
                )

        # ========================================================
        # 4. API CHECK / DYNAMIC TEMPLATE
        # ========================================================
        actual_template_id = job.template_id
        real_time_due = None
        emi_due_count = 0
        is_paid = False

        needs_check = False

        if needs_api_check_func:
            try:
                needs_check = bool(
                    needs_api_check_func(job.template_id)
                )
            except Exception as e:
                logger.warning(
                    f"⚠️ needs_api_check failed for "
                    f"{job.target_app}/{job.template_id}: {e}"
                )

        logger.info(
            f"📋 Job={job.job_id} | "
            f"Template={job.template_id} | "
            f"API Check={'YES' if needs_check else 'NO'} | "
            f"Mobile={mobile}"
        )

        # IMPORTANT:
        # Template 36 -> needs_check=False
        # Therefore EMI / PAID / due_amount logic is skipped.
        if needs_check and schedule_func:
            try:
                get_rate_limiter(job.target_app).wait()

                schedule_data = schedule_func(
                    mobile,
                    loan_number,
                    include_upcoming=True
                ) or {}

                real_time_due = schedule_data.get(
                    "total_due",
                    0
                )

                is_paid = schedule_data.get(
                    "is_paid",
                    False
                )

                emi_due_count = schedule_data.get(
                    "emi_due_count",
                    0
                )

                actual_template_id = get_dynamic_template_id(
                    job.target_app,
                    job.template_id,
                    emi_due_count,
                )

                logger.info(
                    f"🎯 {mobile} | "
                    f"JobTemplate={job.template_id} | "
                    f"EMI={emi_due_count} | "
                    f"ActualTemplate={actual_template_id} | "
                    f"Due=₹{real_time_due}"
                )

                # ====================================================
                # NO APPLICABLE BUCKET / EMI < 0.2
                # ====================================================
                if (
                    actual_template_id is None
                    or emi_due_count < 0.2
                ):
                    result["skipped"] = 1

                    try:
                        LogModel.objects.create(
                            job_id=job,
                            customer_name=customer_name,
                            mobile=mobile,
                            template_name="SKIPPED",
                            sent_text_message=(
                                f"SKIPPED: EMI count "
                                f"{emi_due_count}"
                            ),
                            status="SKIPPED",
                            message_type="Skipped",
                            error_message=(
                                "No applicable bucket / "
                                f"EMI count={emi_due_count}"
                            ),
                            sent_at=timezone.now(),
                        )
                    except Exception:
                        logger.exception(
                            f"❌ Failed to save EMI skip report "
                            f"for {mobile}"
                        )

                    return result

                # ====================================================
                # PAID
                # ====================================================
                if is_paid:
                    result["skipped"] = 1

                    try:
                        LogModel.objects.create(
                            job_id=job,
                            customer_name=customer_name,
                            mobile=mobile,
                            template_name="PAID",
                            sent_text_message=(
                                f"PAID: ₹{real_time_due}"
                            ),
                            status="PAID",
                            message_type="Skipped",
                            error_message=(
                                "Customer is PAID "
                                f"(Total Due: ₹{real_time_due})"
                            ),
                            sent_at=timezone.now(),
                        )
                    except Exception:
                        logger.exception(
                            f"❌ Failed to save PAID report "
                            f"for {mobile}"
                        )

                    return result

                # ====================================================
                # REAL-TIME AMOUNT
                # ====================================================
                if (
                    real_time_due is not None
                    and real_time_due > 0
                ):
                    row["due_amount"] = str(real_time_due)

            except Exception as e:
                # IMPORTANT:
                # API error must NOT become SKIPPED.
                # Preserve old fallback -> continue using Excel data.
                logger.warning(
                    f"⚠️ API check error for {mobile}: {e}"
                )

        # ========================================================
        # 5. DUPLICATE PREVENTION
        # ========================================================
        if not claim_customer_send(
            job.job_id,
            occurrence_token,
            mobile
        ):
            result["skipped"] = 1
            result["error"] = (
                "Duplicate customer prevented "
                "for this scheduled occurrence"
            )

            # IMPORTANT FIX:
            # Previously duplicate was counted as skipped but
            # NO customer-level report was created.
            try:
                duplicate_template_name = (
                    get_actual_template_name(
                        job.target_app,
                        actual_template_id
                    )
                    or str(
                        actual_template_id
                        or job.template_id
                        or ""
                    )
                )

                LogModel.objects.create(
                    job_id=job,
                    customer_name=customer_name,
                    mobile=mobile,
                    template_name=duplicate_template_name,
                    sent_text_message=(
                        "SKIPPED - Duplicate customer prevented"
                    ),
                    status="SKIPPED",
                    message_type="Skipped",
                    error_message=(
                        "Duplicate prevented: customer already "
                        "claimed for this scheduled occurrence"
                    ),
                    sent_at=timezone.now(),
                )

            except Exception:
                logger.exception(
                    f"❌ Failed to save duplicate-skip report "
                    f"for {mobile}"
                )

            logger.warning(
                f"⏭️ DUPLICATE PREVENTED: "
                f"job={job.job_id}, "
                f"occurrence={occurrence_token}, "
                f"mobile={mobile}"
            )

            return result

        claim_owned = True

        # ========================================================
        # 6. GET ACTUAL TEMPLATE NAME
        # ========================================================
        actual_template_name = get_actual_template_name(
            job.target_app,
            actual_template_id
        )

        # ========================================================
        # 7. BUILD PAYLOAD
        # ========================================================
        payload, rendered_text = build_payload(
            actual_template_id,
            row,
            None
        )

        payload["to"] = mobile

        # ========================================================
        # 8. RATE LIMIT + HTTP SEND
        # ========================================================
        get_rate_limiter(job.target_app).wait()

        session = get_session()

        # IMPORTANT:
        # From this point claim is never released automatically.
        # Timeout can mean WhatsApp accepted the message.
        send_attempted = True

        try:
            resp = session.post(
                url,
                headers=headers,
                json=payload,
                timeout=(
                    API_TIMEOUT_CONNECT,
                    API_TIMEOUT_READ,
                ),
            )

        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
        ) as e:

            result["failed"] = 1
            result["error"] = str(e)[:500]

            try:
                LogModel.objects.create(
                    job_id=job,
                    customer_name=customer_name,
                    mobile=mobile,
                    template_name=(
                        actual_template_name
                        or str(actual_template_id)
                    ),
                    sent_text_message="",
                    status="Failed",
                    message_type="Sent",
                    error_message=(
                        f"AMBIGUOUS SEND: {str(e)[:450]}"
                    ),
                    sent_at=timezone.now(),
                )
            except Exception:
                logger.exception(
                    f"❌ Failed to save timeout/connection "
                    f"failure report for {mobile}"
                )

            logger.error(
                f"⚠️ Ambiguous API failure for {mobile}; "
                f"claim retained to prevent duplicate retry: {e}"
            )

            return result

        # ========================================================
        # 9. SUCCESS
        # ========================================================
        if resp.ok:

            try:
                body = resp.json()
                msg_id = (
                    body.get("messages", [{}])[0]
                    .get("id", "")
                )
            except Exception:
                msg_id = ""

            log_text = rendered_text

            if real_time_due:
                log_text = (
                    f"{rendered_text}\n\n"
                    f"Excel: ₹{excel_amount} | "
                    f"Actual: ₹{real_time_due}"
                )

            # Report persistence must never cause WhatsApp retry.
            try:
                LogModel.objects.create(
                    job_id=job,
                    customer_name=customer_name,
                    mobile=mobile,
                    template_name=(
                        actual_template_name
                        or str(actual_template_id)
                    ),
                    sent_text_message=(
                        log_text
                        or f"📨 Batch: {job.template_name}"
                    ),
                    status="Sent",
                    message_id=msg_id,
                    message_type="Sent",
                    content_type="text",
                    error_message=(
                        f"Job Template: {job.template_id} | "
                        f"Actual Template: {actual_template_id} | "
                        f"EMI Count: {emi_due_count} | "
                        f"Excel Due: ₹{excel_amount} | "
                        f"API Due: ₹{real_time_due} | "
                        f"Loan: {loan_number} | "
                        f"Vehicle: {vehicle_number}"
                    ),
                    sent_at=timezone.now(),
                )

            except Exception as e:
                logger.exception(
                    f"⚠️ WhatsApp sent to {mobile}, "
                    f"but success report save failed: {e}"
                )

            # ====================================================
            # CONTACT UPDATE
            # ====================================================
            if ContactModel:
                try:
                    ContactModel.objects.update_or_create(
                        mobile=mobile,
                        defaults={
                            "last_msg": (
                                log_text
                                or f"📨 Batch: {job.template_name}"
                            ),
                            "last_time": timezone.now(),
                            "last_type": "Sent",
                            "last_status": "Sent",
                            "unread": 0,
                        }
                    )

                except Exception as e:
                    logger.warning(
                        f"⚠️ Contact update failed after "
                        f"successful send to {mobile}: {e}"
                    )

            result["sent"] = 1

            logger.info(
                f"✅ [{job.target_app}] Sent to {mobile} | "
                f"job={job.job_id} | "
                f"occurrence={occurrence_token}"
            )

            return result

        # ========================================================
        # 10. HTTP FAILURE
        # ========================================================
        definite_rejection = (
            400 <= resp.status_code < 500
            and resp.status_code not in (408, 429)
        )

        if definite_rejection:
            release_customer_send_claim(
                job.job_id,
                occurrence_token,
                mobile
            )
            claim_owned = False

        else:
            # 408 / 429 / 5xx are ambiguous.
            # Keep claim to prevent duplicate sends.
            logger.error(
                f"⚠️ Ambiguous HTTP {resp.status_code} "
                f"for {mobile}; claim retained"
            )

        result["failed"] = 1

        error_msg = (
            resp.text
            or f"HTTP {resp.status_code}"
        )[:500]

        try:
            LogModel.objects.create(
                job_id=job,
                customer_name=customer_name,
                mobile=mobile,
                template_name=(
                    actual_template_name
                    or str(actual_template_id)
                ),
                sent_text_message="",
                status="Failed",
                message_type="Sent",
                error_message=error_msg,
                sent_at=timezone.now(),
            )

        except Exception:
            logger.exception(
                f"❌ Failed to save HTTP failure report "
                f"for {mobile}"
            )

        logger.error(
            f"❌ [{job.target_app}] Failed to send "
            f"{mobile}: {resp.status_code}"
        )

        return result

    # ============================================================
    # 11. UNEXPECTED CUSTOMER ERROR
    # ============================================================
    except Exception as e:

        # Release only when HTTP request was NOT started.
        if (
            claim_owned
            and mobile
            and not send_attempted
        ):
            try:
                release_customer_send_claim(
                    job.job_id,
                    occurrence_token,
                    mobile
                )
            except Exception:
                logger.exception(
                    f"❌ Failed to release claim for {mobile}"
                )

        result["failed"] = 1
        result["error"] = str(e)[:500]

        logger.error(
            f"❌ Error for {mobile or 'Unknown'}: {e}"
        )
        logger.error(traceback.format_exc())

        # IMPORTANT:
        # Unexpected error must also appear in Failed report.
        try:
            unexpected_template_name = ""

            try:
                if actual_template_id is not None:
                    unexpected_template_name = (
                        get_actual_template_name(
                            job.target_app,
                            actual_template_id
                        )
                        or str(actual_template_id)
                    )
            except Exception:
                unexpected_template_name = (
                    str(actual_template_id or "")
                )

            LogModel.objects.create(
                job_id=job,
                customer_name=customer_name,
                mobile=mobile,
                template_name=unexpected_template_name,
                sent_text_message="",
                status="Failed",
                message_type="Sent",
                error_message=str(e)[:500],
                sent_at=timezone.now(),
            )

        except Exception:
            logger.exception(
                f"❌ Could not save unexpected FAILED "
                f"report for {mobile or 'Unknown'}"
            )

        return result

# ============================================================
# 🚀 SCHEDULER TASK - CREATE EXACTLY ONE SCHEDULED BATCH
# ============================================================
@shared_task(queue="batch_scheduler")
def process_batch_scheduler(job_id):
    """
    Create exactly ONE BatchExecution for the current due schedule.

    IMPORTANT BUSINESS RULE:
    - CUSTOM SIZE = batch_size customers per scheduled occurrence.
      Example: 10,000 customers + 1,000/day => 1,000 today, next 1,000
      tomorrow, and so on until all 10,000 are completed.
    - FULL = all customers in one batch for each scheduled occurrence.
      Therefore FULL + Daily can repeat the complete customer list daily.
    - Never start the next CUSTOM batch immediately after the previous one.
      The next batch waits for next_run_time.
    """
    logger.info(f"🚀 process_batch_scheduler STARTED: {job_id}")

    if not acquire_job_lock(job_id):
        logger.info(f"⏳ {job_id}: scheduler lock already held")
        return None

    try:
        with transaction.atomic():
            job = BatchJob.objects.select_for_update().get(job_id=job_id)
            now = timezone.now()

            if job.status in ["cancelled", "completed"]:
                return None

            # Never create two active executions for the same job.
            if BatchExecution.objects.filter(
                job=job,
                status__in=["pending", "running"],
            ).exists():
                logger.info(f"⏭️ {job_id}: active execution already exists")
                return None

            # If a due time has not been established yet, establish the first
            # schedule from the user's selected schedule_datetime.
            if job.next_run_time is None:
                if job.schedule_datetime and job.schedule_datetime > now:
                    job.next_run_time = job.schedule_datetime
                elif job.schedule_type == "one_time":
                    job.next_run_time = job.schedule_datetime
                else:
                    job.next_run_time = calculate_next_run_time(job, now)
                job.status = "scheduled"
                job.save(update_fields=["next_run_time", "status"])

            # This task is only allowed to create a batch when its schedule is due.
            if job.next_run_time and job.next_run_time > now:
                return None

            total_customers = int(job.total_customers or 0)
            if total_customers <= 0:
                job.status = "completed"
                job.next_run_time = None
                job.completed_at = now
                job.save(update_fields=["status", "next_run_time", "completed_at"])
                return None

            if job.batch_size_type == "full":
                batch_size = total_customers
            else:
                batch_size = max(int(job.batch_size or 1), 1)

            total_batches = max(
                1,
                (total_customers + batch_size - 1) // batch_size,
            )

            # One occurrence token covers all CUSTOM batches belonging to the
            # same campaign run. For FULL, one execution is one occurrence.
            occurrence_token = get_occurrence_token(job)

            current_occurrence = BatchExecution.objects.filter(
                job=job,
                occurrence_token=occurrence_token,
            )

            completed_numbers = set(
                current_occurrence.filter(status="completed")
                .values_list("batch_number", flat=True)
            )

            next_batch = next(
                (n for n in range(1, total_batches + 1) if n not in completed_numbers),
                None,
            )

            # CUSTOM SIZE campaign is finished once all customer ranges have
            # been delivered. It must NOT restart from customer #1.
            if next_batch is None and job.batch_size_type != "full":
                job.status = "completed"
                job.next_run_time = None
                job.completed_at = job.completed_at or now
                job.completed_batches = total_batches
                job.save(update_fields=[
                    "status", "next_run_time", "completed_at", "completed_batches"
                ])
                logger.info(f"✅ {job_id}: all custom batches already completed")
                return None

            # FULL has exactly one batch per occurrence. If its old occurrence
            # is complete, the next scheduled occurrence uses a new token.
            if next_batch is None:
                next_batch = 1
                # This is only reachable if an old FULL execution used the same
                # token. Move to the next occurrence before creating a new one.
                job.total_runs = int(job.total_runs or 0) + 1
                occurrence_token = get_occurrence_token(job)
                completed_numbers = set()

            start_row = (next_batch - 1) * batch_size
            end_row = min(start_row + batch_size, total_customers)

            job.status = "running"
            job.started_at = now
            job.total_batches = total_batches
            job.current_batch = next_batch
            job.completed_batches = len(completed_numbers)
            job.save(update_fields=[
                "status", "started_at", "total_batches",
                "current_batch", "completed_batches", "total_runs"
            ])

            execution = BatchExecution.objects.create(
                job=job,
                occurrence_token=occurrence_token,
                batch_number=next_batch,
                start_row=start_row,
                end_row=end_row,
                total_customers=end_row - start_row,
                status="pending",
            )

            queue_name = "messaging" if job.target_app == "messaging" else "messaging2"

            logger.info(
                f"📦 {job_id}: {job.batch_size_type.upper()} "
                f"batch {next_batch}/{total_batches}, "
                f"rows {start_row}:{end_row}, occurrence={occurrence_token}, "
                f"scheduled={format_ist_12hr(job.next_run_time)}, queue={queue_name}"
            )

        # Publish only after the DB transaction commits.
        try:
            async_result = execute_batch.apply_async(
                args=(job_id, execution.id),
                queue=queue_name,
                countdown=0,
            )
            BatchExecution.objects.filter(id=execution.id).update(
                task_id=async_result.id
            )
        except Exception as dispatch_error:
            logger.exception(
                f"❌ Celery dispatch failed for job={job_id}, execution={execution.id}"
            )
            with transaction.atomic():
                failed_execution = BatchExecution.objects.select_for_update().get(
                    id=execution.id
                )
                failed_execution.status = "failed"
                failed_execution.error_message = (
                    f"Celery dispatch failed: {str(dispatch_error)[:450]}"
                )
                failed_execution.completed_at = timezone.now()
                failed_execution.save(update_fields=[
                    "status", "error_message", "completed_at"
                ])

                failed_job = BatchJob.objects.select_for_update().get(job_id=job_id)
                if failed_job.status == "running":
                    failed_job.status = "scheduled"
                    failed_job.next_run_time = timezone.now() + timedelta(seconds=30)
                    failed_job.save(update_fields=["status", "next_run_time"])
            return None

        return execution.id

    except BatchJob.DoesNotExist:
        logger.warning(f"⚠️ Job {job_id} not found")
        return None
    except Exception as e:
        logger.exception(f"❌ Scheduler failed for {job_id}: {e}")
        return None
    finally:
        release_job_lock(job_id)


# ============================================================
# 🚀 BATCH EXECUTION TASK - PARALLEL PROCESSING
# ============================================================
@shared_task(bind=True, queue="batch_app")
def execute_batch(self, job_id, execution_id):
    """
    Execute exactly one BatchExecution.

    - Per-execution Redis lock prevents duplicate task delivery.
    - Redis heartbeat proves the worker is alive even for 100k-customer jobs.
    - Customer claims are occurrence-based, so crash/retry cannot resend.
    - Every customer is processed independently; one customer failure does
      not stop the whole batch.
    """
    close_old_connections()
    heartbeat_stop = None
    heartbeat_thread = None

    execution_lock_key = f"batch_execution_lock:{execution_id}"
    acquired_execution_lock = False

    try:
        if not cache.add(execution_lock_key, "1", JOB_LOCK_TIMEOUT):
            logger.info(
                f"⏭️ Execution {execution_id} already running/claimed"
            )
            return
        acquired_execution_lock = True
    except Exception as e:
        logger.error(
            f"❌ Execution lock unavailable for {execution_id}: {e}"
        )
        return

    try:
        execution = (
            BatchExecution.objects.select_related("job")
            .get(id=execution_id)
        )
        job = execution.job

        if job.status == "cancelled":
            execution.status = "cancelled"
            execution.completed_at = timezone.now()
            execution.save(update_fields=["status", "completed_at"])
            return

        if execution.status == "completed":
            logger.info(f"⏭️ Execution {execution_id} already completed")
            return

        execution.status = "running"
        execution.started_at = execution.started_at or timezone.now()
        execution.save(update_fields=["status", "started_at"])

        set_execution_heartbeat(execution_id)

        logger.info(
            f"🚀 Starting job={job.job_id}, "
            f"batch={execution.batch_number}, execution={execution_id}, "
            f"occurrence={get_occurrence_token(job)}"
        )

        batch_customers, batch_count = job.get_batch_from_s3(execution.start_row)

        if not batch_customers or batch_count == 0:
            execution.status = "completed"
            execution.completed_at = timezone.now()
            execution.sent_count = 0
            execution.failed_count = 0
            execution.skipped_count = 0
            execution.save(
                update_fields=[
                    "status", "completed_at",
                    "sent_count", "failed_count", "skipped_count",
                ]
            )
            _finish_or_schedule_job(job)
            logger.info(f"✅ Batch {execution.batch_number}: No customers")
            return

        app = get_app_by_name(job.target_app)
        if not app:
            raise RuntimeError(f"App {job.target_app} not found")

        LogModel = get_app_log_model(job.target_app)
        ContactModel = get_app_contact_model(job.target_app)
        if not LogModel:
            raise RuntimeError(f"No log model found for {job.target_app}")

        creds = app.get("credentials", {})
        if (
            not creds
            or "access_token" not in creds
            or "phone_number_id" not in creds
        ):
            raise RuntimeError(f"No credentials found for {job.target_app}")

        build_payload = get_build_payload_function(job.target_app)
        if not build_payload:
            raise RuntimeError(
                f"No build_payload function for {job.target_app}"
            )

        needs_api_check_func = get_app_needs_api_check_function(
            job.target_app
        )
        schedule_func = get_app_schedule_function(job.target_app)
        seize_check_func = get_app_seize_check_function(job.target_app)

        url = (
            f"https://graph.facebook.com/v22.0/"
            f"{creds['phone_number_id']}/messages"
        )
        headers = {
            "Authorization": f"Bearer {creds['access_token']}",
            "Content-Type": "application/json",
        }

        total_customers = len(batch_customers)
        sent = failed = skipped = 0
        start_time = time.monotonic()

        # Keep liveness independent of customer completion.
        heartbeat_stop = threading.Event()

        def _heartbeat_loop():
            while not heartbeat_stop.wait(30):
                set_execution_heartbeat(execution_id)

        heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            name=f"batch-heartbeat-{execution_id}",
            daemon=True,
        )
        set_execution_heartbeat(execution_id)
        heartbeat_thread.start()

        iterator = iter(batch_customers)
        pending = {}

        with ThreadPoolExecutor(
            max_workers=MAX_WORKERS,
            thread_name_prefix=f"batch-{execution_id}",
        ) as executor:
            # Keep a bounded number of futures in memory.
            for _ in range(min(MAX_WORKERS, total_customers)):
                try:
                    row = next(iterator)
                except StopIteration:
                    break

                future = executor.submit(
                    process_single_customer,
                    row, job, execution_id, LogModel, ContactModel,
                    url, headers, build_payload, needs_api_check_func,
                    schedule_func, seize_check_func,
                )
                pending[future] = True

            completed_count = 0

            while pending:
                done = next(as_completed(list(pending)))
                pending.pop(done, None)

                try:
                    result = done.result()
                    sent += result.get("sent", 0)
                    failed += result.get("failed", 0)
                    skipped += result.get("skipped", 0)
                except Exception as e:
                    failed += 1
                    logger.error(
                        f"❌ Customer worker error in execution "
                        f"{execution_id}: {e}"
                    )
                    logger.error(traceback.format_exc())

                completed_count += 1

                try:
                    row = next(iterator)
                    future = executor.submit(
                        process_single_customer,
                        row, job, execution_id, LogModel, ContactModel,
                        url, headers, build_payload, needs_api_check_func,
                        schedule_func, seize_check_func,
                    )
                    pending[future] = True
                except StopIteration:
                    pass

                if (
                    completed_count % HEARTBEAT_INTERVAL == 0
                    or completed_count == total_customers
                ):
                    execution.sent_count = sent
                    execution.failed_count = failed
                    execution.skipped_count = skipped
                    execution.save(
                        update_fields=[
                            "sent_count",
                            "failed_count",
                            "skipped_count",
                        ]
                    )
                    set_execution_heartbeat(execution_id)

                    self.update_state(
                        state="PROGRESS",
                        meta={
                            "current": completed_count,
                            "total": total_customers,
                            "sent": sent,
                            "failed": failed,
                            "skipped": skipped,
                            "elapsed": int(time.monotonic() - start_time),
                        },
                    )

        if heartbeat_stop is not None:
            heartbeat_stop.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=2)

        # Final stats are authoritative.
        execution.sent_count = sent
        execution.failed_count = failed
        execution.skipped_count = skipped
        execution.status = "completed"
        execution.completed_at = timezone.now()
        execution.save(
            update_fields=[
                "sent_count",
                "failed_count",
                "skipped_count",
                "status",
                "completed_at",
            ]
        )

        logger.info(
            f"✅ Batch {execution.batch_number} completed: "
            f"Sent={sent}, Skipped={skipped}, Failed={failed}"
        )

        # If scheduling the next occurrence fails, _finish_or_schedule_job
        # itself repairs the job state so it cannot remain 'running' forever.
        _finish_or_schedule_job(job)

    except BatchExecution.DoesNotExist:
        logger.error(f"❌ Execution {execution_id} not found")
        return

    except Exception as e:
        error_msg = str(e)[:500]
        logger.error(
            f"❌ Batch execution failed job={job_id}, "
            f"execution={execution_id}: {error_msg}"
        )
        logger.error(traceback.format_exc())

        try:
            execution.status = "failed"
            execution.error_message = error_msg
            execution.completed_at = timezone.now()
            execution.save(
                update_fields=[
                    "status", "error_message", "completed_at"
                ]
            )

            # Make the job immediately eligible for scheduler recovery.
            job.status = "scheduled"
            job.next_run_time = timezone.now()
            job.save(update_fields=["status", "next_run_time"])

        except Exception:
            logger.exception("Failed saving failed execution")

    finally:
        if heartbeat_stop is not None:
            heartbeat_stop.set()
        if heartbeat_thread is not None and heartbeat_thread.is_alive():
            heartbeat_thread.join(timeout=2)
        clear_execution_heartbeat(execution_id)
        if acquired_execution_lock:
            try:
                cache.delete(execution_lock_key)
            except Exception:
                pass
        close_old_connections()


# ============================================================
# 🔄 FINISH CURRENT BATCH / SCHEDULE NEXT
# ============================================================
def _finish_or_schedule_job(job):
    """
    Finalize one batch and schedule the next batch according to the UI rule.

    CUSTOM SIZE:
        10K customers + 1K + Daily
        Day 1 -> rows 0:1000
        Day 2 -> rows 1000:2000
        ...
        Final day -> rows 9000:10000 -> job COMPLETED

        The next batch NEVER starts immediately.

    FULL:
        All customers are one batch. If the schedule is recurring, the next
        complete run is scheduled according to daily/weekly/monthly/etc.
    """
    job_id = job.job_id

    try:
        with transaction.atomic():
            locked_job = BatchJob.objects.select_for_update().get(job_id=job_id)
            now = timezone.now()
            occurrence_token = get_occurrence_token(locked_job)

            occurrence_qs = BatchExecution.objects.filter(
                job=locked_job,
                occurrence_token=occurrence_token,
            )

            if locked_job.batch_size_type == "full":
                total_batches = 1
            else:
                batch_size = max(int(locked_job.batch_size or 1), 1)
                total_batches = max(
                    1,
                    (int(locked_job.total_customers or 0) + batch_size - 1)
                    // batch_size,
                )

            completed_batches = occurrence_qs.filter(status="completed").count()
            stats = occurrence_qs.aggregate(
                total_sent=Sum("sent_count"),
                total_failed=Sum("failed_count"),
                total_skipped=Sum("skipped_count"),
            )

            occurrence_sent = stats["total_sent"] or 0
            occurrence_failed = stats["total_failed"] or 0
            occurrence_skipped = stats["total_skipped"] or 0

            locked_job.completed_batches = completed_batches
            locked_job.current_batch = min(completed_batches + 1, total_batches)

            # ========================================================
            # CUSTOM SIZE: MORE RANGES REMAIN
            # ========================================================
            if locked_job.batch_size_type != "full" and completed_batches < total_batches:
                # IMPORTANT: wait for the next scheduled occurrence.
                next_run = calculate_next_run_time(locked_job, now)
                if not next_run:
                    next_run = now + timedelta(days=1)

                locked_job.status = "scheduled"
                locked_job.next_run_time = next_run

                # For CUSTOM campaigns these are campaign totals, so keep them.
                all_stats = BatchExecution.objects.filter(job=locked_job).aggregate(
                    total_sent=Sum("sent_count"),
                    total_failed=Sum("failed_count"),
                    total_skipped=Sum("skipped_count"),
                )
                locked_job.sent_count = all_stats["total_sent"] or 0
                locked_job.failed_count = all_stats["total_failed"] or 0
                locked_job.skipped_count = all_stats["total_skipped"] or 0

                locked_job.save(update_fields=[
                    "completed_batches", "current_batch", "sent_count",
                    "failed_count", "skipped_count", "status", "next_run_time"
                ])

                logger.info(
                    f"📅 {job_id}: batch {completed_batches}/{total_batches} complete. "
                    f"NEXT batch will wait until {format_ist_12hr(next_run)}"
                )
                return

            # ========================================================
            # FULL: ONE BATCH COMPLETES ONE SCHEDULED OCCURRENCE
            # ========================================================
            locked_job.total_runs = int(locked_job.total_runs or 0) + 1
            locked_job.completed_at = now
            locked_job.completed_batches = total_batches
            locked_job.current_batch = total_batches
            locked_job.sent_count = occurrence_sent
            locked_job.failed_count = occurrence_failed
            locked_job.skipped_count = occurrence_skipped

            if locked_job.end_date and now >= locked_job.end_date:
                locked_job.status = "completed"
                locked_job.next_run_time = None
                locked_job.save(update_fields=[
                    "total_runs", "completed_at", "completed_batches", "current_batch",
                    "sent_count", "failed_count", "skipped_count",
                    "status", "next_run_time"
                ])
                logger.info(f"✅ {job_id}: end_date reached")
                return

            # CUSTOM SIZE reaching the final range is a completed campaign.
            if locked_job.batch_size_type != "full":
                locked_job.status = "completed"
                locked_job.next_run_time = None
                locked_job.save(update_fields=[
                    "total_runs", "completed_at", "completed_batches", "current_batch",
                    "sent_count", "failed_count", "skipped_count",
                    "status", "next_run_time"
                ])
                logger.info(
                    f"✅ {job_id}: ALL {locked_job.total_customers} customers completed "
                    f"in {total_batches} scheduled batches"
                )
                return

            # FULL recurring run: next occurrence uses the incremented token.
            next_run = calculate_next_run_time(locked_job, now)
            if not next_run:
                locked_job.status = "completed"
                locked_job.next_run_time = None
                locked_job.save(update_fields=[
                    "total_runs", "completed_at", "completed_batches", "current_batch",
                    "sent_count", "failed_count", "skipped_count",
                    "status", "next_run_time"
                ])
                return

            locked_job.status = "scheduled"
            locked_job.next_run_time = next_run
            locked_job.completed_batches = 0
            locked_job.current_batch = 0
            # Reset visible counts for the NEXT FULL occurrence.
            locked_job.sent_count = 0
            locked_job.failed_count = 0
            locked_job.skipped_count = 0

            locked_job.save(update_fields=[
                "total_runs", "completed_at", "completed_batches", "current_batch",
                "sent_count", "failed_count", "skipped_count",
                "status", "next_run_time"
            ])

            logger.info(
                f"📅 {job_id}: FULL occurrence #{locked_job.total_runs} complete; "
                f"next full run={format_ist_12hr(next_run)}"
            )

    except Exception as e:
        logger.exception(f"❌ Finish/schedule failed for {job_id}: {e}")
        # Do not leave the job permanently running. A retryable scheduler pass
        # will recover the failed batch without changing the customer range.
        try:
            BatchJob.objects.filter(
                job_id=job_id,
                status="running",
            ).update(
                status="scheduled",
                next_run_time=timezone.now() + timedelta(seconds=30),
                error_message=f"Finish/schedule error: {str(e)[:450]}",
            )
        except Exception:
            logger.exception(f"❌ Could not repair job state for {job_id}")


# ============================================================
# 🔄 CHECK DUE JOBS - SINGLE SOURCE OF TRUTH
# ============================================================
@shared_task(queue="batch_scheduler")
def check_pending_batch_jobs():
    """
    Run from Celery Beat every 10 seconds.
    This is the ONLY periodic dispatcher.
    """
    now = timezone.now()
    
    jobs = BatchJob.objects.filter(
        status="scheduled",
        next_run_time__lte=now,
    ).order_by("next_run_time")
    
    due_count = jobs.count()
    logger.info(f"🔍 Scheduler: {due_count} due jobs at {format_ist_12hr(now)}")
    
    for job in jobs.iterator(chunk_size=100):
        try:
            # Check end date
            if job.end_date and now >= job.end_date:
                BatchJob.objects.filter(
                    job_id=job.job_id,
                    status="scheduled"
                ).update(
                    status="completed",
                    next_run_time=None,
                )
                logger.info(f"⏹️ {job.job_id}: end_date reached")
                continue
            
            # Fast duplicate checks
            if is_job_locked(job.job_id):
                continue
            
            if BatchExecution.objects.filter(
                job=job,
                status__in=["pending", "running"],
            ).exists():
                continue
            
            # Dispatch the job
            process_batch_scheduler.delay(job.job_id)
            logger.info(
                f"🚀 Triggered due job={job.job_id} "
                f"scheduled={format_ist_12hr(job.next_run_time)}"
            )
            
        except Exception as e:
            logger.error(f"❌ Failed dispatching {job.job_id}: {e}")
            release_job_lock(job.job_id)


# ============================================================
# 🧹 CLEANUP STUCK EXECUTIONS
# ============================================================
@shared_task(queue="batch_scheduler")
def cleanup_stuck_executions():
    """
    Recover genuinely dead executions without killing healthy large jobs.

    A 100k-customer batch can legitimately take several hours. Therefore
    started_at alone is NOT used as proof of a stuck job. The worker refreshes
    a Redis heartbeat while processing; cleanup only fails a running execution
    when its heartbeat is gone and it is older than STUCK_EXECUTION_AFTER.

    Pending executions are also recovered if they were orphaned before Celery
    could start them.
    """
    now = timezone.now()
    pending_threshold = now - timedelta(minutes=30)
    running_threshold = now - timedelta(seconds=STUCK_EXECUTION_AFTER)
    updated = 0

    # Orphaned pending executions: dispatch/startup never happened.
    pending_executions = BatchExecution.objects.filter(
        status="pending",
        created_at__lte=pending_threshold,
    ).select_related("job")

    for execution in pending_executions.iterator(chunk_size=100):
        try:
            with transaction.atomic():
                locked = BatchExecution.objects.select_for_update().get(
                    id=execution.id
                )

                if locked.status != "pending":
                    continue

                locked.status = "failed"
                locked.error_message = (
                    "Auto-recovered: pending execution orphaned for > 30 minutes"
                )
                locked.completed_at = now
                locked.save(
                    update_fields=[
                        "status", "error_message", "completed_at"
                    ]
                )

                job = locked.job
                if job.status in ["running", "scheduled"]:
                    job.status = "scheduled"
                    job.next_run_time = now
                    job.save(update_fields=["status", "next_run_time"])

                updated += 1
                logger.warning(
                    f"🧹 Recovered orphaned pending execution "
                    f"{locked.id} for job {job.job_id}"
                )

        except Exception:
            logger.exception(
                f"❌ Failed to cleanup pending execution {execution.id}"
            )

    # Dead running executions.
    running_executions = BatchExecution.objects.filter(
        status="running",
        started_at__lte=running_threshold,
    ).select_related("job")

    for execution in running_executions.iterator(chunk_size=100):
        try:
            # Healthy workers refresh this marker every HEARTBEAT_INTERVAL.
            if execution_has_heartbeat(execution.id):
                continue

            with transaction.atomic():
                locked = BatchExecution.objects.select_for_update().get(
                    id=execution.id
                )

                if locked.status != "running":
                    continue

                # Re-check after locking to avoid racing with a live worker.
                if execution_has_heartbeat(locked.id):
                    continue

                locked.status = "failed"
                locked.error_message = (
                    "Auto-failed: no worker heartbeat for > "
                    f"{STUCK_EXECUTION_AFTER / 60:.0f} minutes"
                )
                locked.completed_at = now
                locked.save(
                    update_fields=[
                        "status", "error_message", "completed_at"
                    ]
                )

                job = locked.job
                if job.status == "running":
                    job.status = "scheduled"
                    job.next_run_time = now
                    job.save(update_fields=["status", "next_run_time"])

                updated += 1
                logger.warning(
                    f"🧹 Cleaned dead execution {locked.id} "
                    f"for job {job.job_id}"
                )

        except Exception:
            logger.exception(
                f"❌ Failed to cleanup execution {execution.id}"
            )

    if updated:
        logger.info(f"🧹 Cleaned/recovered {updated} stuck executions")

    return updated


# ============================================================
# ⛔ CANCEL SCHEDULE
# ============================================================
@shared_task(queue="batch_scheduler")
def cancel_daily_schedule(job_id):
    """Cancel all future schedules for a job"""
    try:
        with transaction.atomic():
            job = BatchJob.objects.select_for_update().get(job_id=job_id)
            if job.status in ["cancelled", "completed"]:
                return
            
            # Cancel pending executions
            BatchExecution.objects.filter(
                job=job,
                status="pending"
            ).update(status="cancelled")
            
            # Update job
            job.status = "cancelled"
            job.next_run_time = None
            job.save(update_fields=["status", "next_run_time"])
        
        release_job_lock(job_id)
        logger.info(f"⛔ Schedule cancelled for {job_id}")
        
    except BatchJob.DoesNotExist:
        logger.warning(f"⚠️ Job {job_id} not found for cancellation")
    except Exception as e:
        logger.error(f"❌ Failed to cancel {job_id}: {e}")
        logger.error(traceback.format_exc())
        release_job_lock(job_id)


# ============================================================
# 📅 LEGACY COMPATIBILITY TASK
# ============================================================
@shared_task(queue="batch_scheduler")
def schedule_batch_job(job_id):
    """
    Compatibility entry point for old code/admin actions.
    Updates next_run_time without creating countdown chains.
    """
    try:
        with transaction.atomic():
            job = BatchJob.objects.select_for_update().get(job_id=job_id)
            
            if job.status in ["cancelled", "completed"]:
                return
            
            now = timezone.now()
            if not job.next_run_time or job.next_run_time <= now:
                job.next_run_time = calculate_next_run_time(job, now)
                job.status = "scheduled"
                job.save(update_fields=["next_run_time", "status"])
        
        logger.info(
            f"📅 Compatibility schedule updated: {job_id} -> "
            f"{format_ist_12hr(job.next_run_time)}"
        )
        return job.next_run_time
        
    except BatchJob.DoesNotExist:
        logger.warning(f"⚠️ Job {job_id} not found")
        return None
    except Exception as e:
        logger.error(f"❌ schedule_batch_job failed for {job_id}: {e}")
        logger.error(traceback.format_exc())
        return None


# ============================================================
# LEGACY PROCESS BATCH JOB (Deprecated)
# ============================================================
@shared_task(queue="batch_app")
def process_batch_job(job_id):
    """Deprecated: use check_pending_batch_jobs instead"""
    logger.warning("⚠️ process_batch_job is deprecated; use check_pending_batch_jobs")
    return process_batch_scheduler(job_id)
