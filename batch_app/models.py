from django.db import models

# Create your models here.
# batch_app/models.py - COMPLETE PRODUCTION READY VERSION
# ✅ PERFECT DATE/TIME HANDLING FOR ALL SCHEDULE TYPES
# ✅ FIXED: 5-MINUTE TOLERANCE FOR SAVE METHOD
# ✅ FIXED: WEEKLY SCHEDULE PRESERVES FIRST RUN DATE

import datetime
import logging
from django.db import models
from django.utils import timezone
from datetime import timedelta
import uuid
import json

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
        ('custom_interval', 'Custom Interval (Days)'),
    ]
    
    # Basic Info
    job_id = models.CharField(max_length=100, unique=True, db_index=True)
    job_name = models.CharField(max_length=255)
    target_app = models.CharField(max_length=50, help_text="Name of the messaging app")
    
    # Template
    template_id = models.CharField(max_length=10, help_text="Template ID from forms.py (e.g., 36)", blank=True, null=True)
    template_name = models.CharField(max_length=100, help_text="Actual template name from WhatsApp (e.g., new_loans_te)")
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
    total_runs = models.IntegerField(default=0)
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
    # ✅ FIXED: Increased tolerance to 1 hour
    # ============================================================
    def save(self, *args, **kwargs):
        """
        Preserve the user's selected schedule with tolerance.

        Rules:
        - Multiple Daily : Never modify.
        - Weekly         : Never modify.
        - Daily          : Move only if more than 1 hour in the past.
        - Custom         : Move only if more than 1 hour in the past.
        """
        if self.schedule_datetime:
            now = timezone.now()

            if timezone.is_naive(self.schedule_datetime):
                self.schedule_datetime = timezone.make_aware(
                    self.schedule_datetime,
                    timezone.get_current_timezone()
                )

            if self.schedule_type == "multiple_daily":
                logger.info(f"✅ Multiple Daily - keeping original datetime: {self.schedule_datetime.strftime('%Y-%m-%d %I:%M:%S %p')}")

            elif self.schedule_type == "weekly":
                logger.info(f"✅ Weekly - keeping user selected first run: {self.schedule_datetime.strftime('%Y-%m-%d %I:%M:%S %p')}")

            else:
                time_diff = (self.schedule_datetime - now).total_seconds()
                
                # ✅ FIXED: Only move if more than 1 HOUR in the past
                if time_diff < -3600:  # -1 hour
                    if self.schedule_type == "daily":
                        self.schedule_datetime += timedelta(days=1)
                        logger.info(f"📅 Daily - time was significantly past (>1 hour), moved to tomorrow: {self.schedule_datetime.strftime('%Y-%m-%d %I:%M:%S %p')}")
                    elif self.schedule_type == "custom_interval":
                        interval = self.interval_days or 1
                        self.schedule_datetime += timedelta(days=interval)
                        logger.info(f"📅 Custom - time was significantly past (>1 hour), moved to next interval: {self.schedule_datetime.strftime('%Y-%m-%d %I:%M:%S %p')}")
                else:
                    # ✅ KEEP EXACTLY the user's selected time
                    logger.info(f"✅ Keeping user's selected time: {self.schedule_datetime.strftime('%Y-%m-%d %I:%M:%S %p')} (diff: {time_diff:.0f}s)")

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
    # ✅ FIXED NEXT RUN TIME CALCULATION - WITH TOLERANCE
    # ============================================================
    def get_next_run_time(self):
        """
        Calculate the next run time based on completed_batches.
        """
        now = timezone.now()
        
        if self.schedule_type == 'daily':
            # ✅ Daily: Add completed_batches days to schedule_datetime
            next_run = self.schedule_datetime + timedelta(days=self.completed_batches)
            
            # ✅ Ensure it's in the future
            while next_run <= now:
                next_run += timedelta(days=1)
            
            return next_run
        
        elif self.schedule_type == 'weekly':
            # ✅ Weekly: Add completed_batches * 7 days
            next_run = self.schedule_datetime + timedelta(days=7 * self.completed_batches)
            
            while next_run <= now:
                next_run += timedelta(days=7)
            
            return next_run
        
        elif self.schedule_type == 'custom_interval':
            # ✅ Custom: Add completed_batches * interval_days
            interval = self.interval_days or 1
            next_run = self.schedule_datetime + timedelta(days=interval * self.completed_batches)
            
            while next_run <= now:
                next_run += timedelta(days=interval)
            
            return next_run
        
        elif self.schedule_type == 'multiple_daily':
            # ✅ Multiple Daily: Get next time from schedule_times
            return self._get_next_multiple_time(now)
        
        return None
    # ============================================================
    # ✅ PERFECT MULTIPLE DAILY NEXT TIME CALCULATION
    # ============================================================

    def _get_next_multiple_time(self, now):
        """
        Get the next time from multiple daily schedules.
        
        Example:
            times = ['15:02', '15:05', '15:07']
            now = 15:02:17 IST
            returns: 15:05 IST (same day)
            
            now = 15:07:30 IST
            returns: 15:02 IST (tomorrow)
        """
        if not self.schedule_times:
            return None
        
        # Parse all times
        times = []
        for time_str in self.schedule_times:
            try:
                t = datetime.datetime.strptime(time_str, '%H:%M').time()
                times.append(t)
            except:
                continue
        
        if not times:
            return None
        
        # Sort times
        times.sort()
        
        # Get current time
        current_time = now.time()
        
        # Find the next time today
        for t in times:
            # ✅ Compare time parts only (avoid timezone issues)
            if t > current_time:
                # ✅ Create timezone-aware datetime
                return timezone.make_aware(
                    datetime.datetime.combine(now.date(), t),
                    timezone.get_current_timezone()
                )
        
        # All times have passed today, get the first time tomorrow
        t = times[0]
        tomorrow = now.date() + timedelta(days=1)
        return timezone.make_aware(
            datetime.datetime.combine(tomorrow, t),
            timezone.get_current_timezone()
        ) 
   
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
        """Legacy method - kept for compatibility"""
        now = timezone.now()
        hour = self.schedule_datetime.hour
        minute = self.schedule_datetime.minute
        second = self.schedule_datetime.second
        next_run = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        return next_run
    
    def get_batch_from_s3(self, start_idx):
        from .utils import get_batch_from_s3
        return get_batch_from_s3(self.excel_path, start_idx, self.batch_size)
    
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
