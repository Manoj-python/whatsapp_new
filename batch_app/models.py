# batch_app/models.py - COMPLETE PRODUCTION READY VERSION
# ✅ PERFECT DATE/TIME HANDLING FOR ALL SCHEDULE TYPES
# ✅ FIXED: 5-MINUTE TOLERANCE FOR SAVE METHOD
# ✅ FIXED: WEEKLY SCHEDULE PRESERVES FIRST RUN DATE

import datetime
import calendar
import logging
from django.db import models
from django.utils import timezone
from datetime import timedelta
import uuid
import json

class NotificationType(models.Model):
    code = models.CharField(
        max_length=100,
        unique=True,
        db_index=True
    )

    name = models.CharField(
        max_length=200
    )

    description = models.TextField(
        blank=True,
        null=True
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.code} - {self.name}"

logger = logging.getLogger(__name__)


class BatchJob(models.Model):
    """Batch job - Dynamically works with ALL messaging apps"""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('scheduled', 'Scheduled'),
        ('running', 'Running'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    BATCH_SIZE_CHOICES = [
        ('custom', 'Custom Size'),
        ('full', 'Full (All Customers)'),
    ]

    SCHEDULE_TYPE_CHOICES = [
        ('daily', 'Daily'),
        ('multiple_daily', 'Multiple Times Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('custom_interval', 'Custom Interval (Days)'),
        ('one_time', 'One Time'),
    ]

    # Basic Info
    job_id = models.CharField(max_length=100, unique=True, db_index=True)
    job_name = models.CharField(max_length=255)
    target_app = models.CharField(max_length=50, help_text="Name of the messaging app")

    # Template
    template_id = models.CharField(max_length=10, help_text="Template ID from forms.py (e.g., 36)", blank=True, null=True)
    template_name = models.CharField(max_length=100, help_text="Actual template name from WhatsApp (e.g., new_loans_te)", blank=True, null=True)
    template_language = models.CharField(max_length=10, default='en', help_text="Language code (en, te, hi, kn)")

    # Excel File Path
    excel_path = models.CharField(max_length=500)

    # Batch Size
    batch_size_type = models.CharField(max_length=10, choices=BATCH_SIZE_CHOICES, default='custom')
    batch_size = models.IntegerField(default=1000)

    # Schedule
    schedule_type = models.CharField(max_length=20, choices=SCHEDULE_TYPE_CHOICES, default='daily')
    schedule_datetime = models.DateTimeField(help_text="First run date and time, continues daily at same time")
    schedule_times = models.JSONField(default=list, blank=True, help_text='List of times for multiple daily schedules')
    weekly_day = models.IntegerField(null=True, blank=True, help_text='Day of week (0=Monday, 6=Sunday)')
    interval_days = models.IntegerField(null=True, blank=True, help_text='Number of days between runs')
    end_date = models.DateTimeField(null=True, blank=True, help_text='Stop scheduling after this date')

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Progress
    total_customers = models.IntegerField(default=0)
    total_batches = models.IntegerField(default=0)
    completed_batches = models.IntegerField(default=0)
    current_batch = models.IntegerField(default=0)

    # Stats
    sent_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    skipped_count = models.IntegerField(default=0)
    # Run Tracking
    # Number of fully completed scheduled occurrences.
    total_runs = models.IntegerField(default=0, help_text="Total number of fully completed scheduled occurrences")
    completed_runs = models.IntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    next_run_time = models.DateTimeField(null=True, blank=True)

    # Metadata
    created_by = models.CharField(max_length=150, blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    report_file = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        db_table = 'batch_jobs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'next_run_time']),
            models.Index(fields=['target_app']),
            models.Index(fields=['template_id']),
            models.Index(fields=['schedule_type']),
        ]

    def __str__(self):
        return f"{self.job_id} - {self.job_name}"

    # ============================================================
    # 🕒 SCHEDULE BASE TIME - NEVER AUTO-SHIFT USER INPUT
    # ============================================================
    def save(self, *args, **kwargs):
        """
        Save the job without silently changing the user's selected schedule.

        IMPORTANT:
        schedule_datetime is the immutable BASE schedule selected in the UI.
        next_run_time is the field that moves from day to day/week to week/etc.
        The old implementation modified schedule_datetime during ordinary saves,
        which could shift a 5:52 PM schedule and cause incorrect future runs.
        """
        if self.schedule_datetime and timezone.is_naive(self.schedule_datetime):
            self.schedule_datetime = timezone.make_aware(
                self.schedule_datetime,
                timezone.get_current_timezone(),
            )

        if self.end_date and timezone.is_naive(self.end_date):
            self.end_date = timezone.make_aware(
                self.end_date,
                timezone.get_current_timezone(),
            )

        super().save(*args, **kwargs)

    def progress_percentage(self):
        if self.total_batches == 0:
            return 0
        try:
            return int((self.completed_batches / self.total_batches) * 100)
        except:
            return 0

    def get_actual_batch_size(self):
        if self.batch_size_type == 'full':
            return self.total_customers
        return self.batch_size

    # batch_app/models.py - FIXED get_schedule_info()
    def get_schedule_info(self):
        """Get human-readable schedule description with IST time"""
        try:
            # ✅ Convert schedule_datetime to IST
            if self.schedule_datetime:
                ist_dt = timezone.localtime(self.schedule_datetime)
                ist_time_str = ist_dt.strftime('%I:%M %p')
            else:
                ist_time_str = "Unknown"

            if self.schedule_type == 'daily':
                return f"Daily at {ist_time_str}"

            elif self.schedule_type == 'multiple_daily':
                times = ', '.join(self.schedule_times or [])
                return f"Multiple times daily: {times}"

            elif self.schedule_type == 'monthly':
                return f"Monthly on day {self.schedule_datetime.day} at {ist_time_str}"

            elif self.schedule_type == 'weekly':
                days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                if self.weekly_day is not None and 0 <= self.weekly_day < len(days):
                    day_name = days[self.weekly_day]
                else:
                    day_name = 'Unknown'
                return f"Weekly on {day_name} at {ist_time_str}"

            elif self.schedule_type == 'custom_interval':
                return f"Every {self.interval_days} day(s) at {ist_time_str}"

            return "Unknown schedule"

        except Exception as e:
            logger.error(f"❌ Error in get_schedule_info: {e}")
            return "Schedule info unavailable"

    # ============================================================
    # 📅 NEXT RUN TIME - ANCHORED TO USER'S ORIGINAL SCHEDULE
    # ============================================================
    def get_next_run_time(self):
        """Return the next scheduled occurrence in the configured timezone."""
        now = timezone.now()
        base = self.schedule_datetime

        if not base:
            return None

        if timezone.is_naive(base):
            base = timezone.make_aware(base, timezone.get_current_timezone())

        local_now = timezone.localtime(now)
        local_base = timezone.localtime(base)
        tz = timezone.get_current_timezone()

        if self.schedule_type == 'one_time':
            return base if base > now else None

        if self.schedule_type == 'daily':
            candidate = timezone.make_aware(
                datetime.datetime.combine(
                    local_now.date(),
                    local_base.time(),
                ),
                tz,
            )
            if candidate <= local_now:
                candidate += timedelta(days=1)
            return candidate

        if self.schedule_type == 'weekly':
            target_weekday = (
                self.weekly_day
                if self.weekly_day is not None
                else local_base.weekday()
            )
            days_ahead = (target_weekday - local_now.weekday()) % 7
            candidate = timezone.make_aware(
                datetime.datetime.combine(
                    local_now.date() + timedelta(days=days_ahead),
                    local_base.time(),
                ),
                tz,
            )
            if candidate <= local_now:
                candidate += timedelta(days=7)
            return candidate

        if self.schedule_type == 'custom_interval':
            interval = max(int(self.interval_days or 1), 1)
            candidate = base
            while candidate <= now:
                candidate += timedelta(days=interval)
            return candidate

        if self.schedule_type == 'monthly':
            target_day = local_base.day
            year = local_now.year
            month = local_now.month
            while True:
                day = min(target_day, calendar.monthrange(year, month)[1])
                candidate = timezone.make_aware(
                    datetime.datetime(
                        year, month, day,
                        local_base.hour,
                        local_base.minute,
                        local_base.second,
                    ),
                    tz,
                )
                if candidate > local_now:
                    return candidate
                if month == 12:
                    year += 1
                    month = 1
                else:
                    month += 1

        if self.schedule_type == 'multiple_daily':
            times = []
            for time_str in (self.schedule_times or []):
                try:
                    parsed = datetime.datetime.strptime(
                        str(time_str), '%H:%M'
                    ).time()
                    times.append(parsed)
                except (TypeError, ValueError):
                    continue

            for parsed in sorted(times):
                candidate = timezone.make_aware(
                    datetime.datetime.combine(local_now.date(), parsed),
                    tz,
                )
                if candidate > local_now:
                    return candidate

            if times:
                tomorrow = local_now.date() + timedelta(days=1)
                return timezone.make_aware(
                    datetime.datetime.combine(tomorrow, sorted(times)[0]),
                    tz,
                )

        return None

    def get_all_run_times(self):
        """Get all scheduled times for the day (for multiple daily)"""
        if self.schedule_type != 'multiple_daily':
            return [self.schedule_datetime]

        now = timezone.now()
        run_times = []
        for time_str in self.schedule_times:
            try:
                t = datetime.datetime.strptime(time_str, '%H:%M').time()
                dt = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
                run_times.append(dt)
            except:
                continue
        return run_times

    def get_log_model(self):
        from .app_discovery import get_app_log_model
        return get_app_log_model(self.target_app)

    def get_contact_model(self):
        from .app_discovery import get_app_contact_model
        return get_app_contact_model(self.target_app)

    def get_credentials(self):
        from .app_discovery import get_app_by_name
        app = get_app_by_name(self.target_app)
        if app:
            return app.get('credentials', {})
        return {}

    def get_template_info(self):
        from .app_discovery import get_templates_from_app
        templates = get_templates_from_app(self.target_app)
        for template in templates:
            if template['id'] == self.template_id:
                return template
        return {
            'id': self.template_id,
            'label': self.template_name,
            'name': self.template_name,
            'language': self.template_language,
        }

    def get_next_run(self):
        """Legacy compatibility method; use the configured schedule rules."""
        return self.get_next_run_time()

    def get_batch_from_s3(self, start_idx):
        """Read exactly one configured batch from S3. FULL means all customers."""
        from .utils import get_batch_from_s3
        batch_size = self.get_actual_batch_size()
        return get_batch_from_s3(self.excel_path, start_idx, batch_size)

    def get_all_customers_from_s3(self):
        from .utils import read_excel_from_s3
        df = read_excel_from_s3(self.excel_path)
        if df is None:
            return [], 0
        return df.to_dict('records'), len(df)


class BatchLog(models.Model):
    """Log for batch job - separate from app logs"""
    job = models.ForeignKey(BatchJob, on_delete=models.CASCADE, related_name='logs')
    mobile = models.CharField(max_length=20, db_index=True)
    customer_name = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=50, db_index=True)
    message_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'batch_logs'
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['job', 'status']),
            models.Index(fields=['mobile']),
        ]

    def __str__(self):
        return f"{self.mobile} - {self.status}"





# batch_app/models.py - Add this new model

class BatchExecution(models.Model):
    """Individual batch execution - each batch gets its own Celery task"""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    job = models.ForeignKey(BatchJob, on_delete=models.CASCADE, related_name='executions')
    # Same token for every batch in one scheduled occurrence.
    # Nullable so existing historical rows can be migrated safely.
    occurrence_token = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    batch_number = models.IntegerField()
    start_row = models.IntegerField()
    end_row = models.IntegerField()
    total_customers = models.IntegerField(default=0)

    sent_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    skipped_count = models.IntegerField(default=0)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True, null=True)

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    task_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,  # ✅ Add index for faster lookups
        help_text="Celery task ID for this execution"
    )

    # Last heartbeat - to detect stuck executions
    last_heartbeat = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,  # ✅ Add index for faster lookups
        help_text="Last time this execution reported progress"
    )

    # Progress - how many customers processed
    progress = models.IntegerField(
        default=0,
        help_text="Number of customers processed in this batch"
    )




    class Meta:
        db_table = 'batch_executions'
        indexes = [
            models.Index(fields=['job', 'status']),
            models.Index(fields=['batch_number']),
            models.Index(fields=['status', 'started_at']),
            models.Index(fields=['job', 'occurrence_token', 'batch_number']),
        ]
        ordering = ['batch_number']
