from django.db import models
from .utils import format_mobile

class SmsWhatsAppLog(models.Model):
    MESSAGE_TYPE_CHOICES = (
        ("Sent", "Sent"),
        ("Received", "Received"),
    )

    CONTENT_TYPE_CHOICES = (
        ("text", "Text"),
        ("image", "Image"),
        ("audio", "Audio"),
        ("video", "Video"),
        ("document", "Document"),
        ("interactive", "Interactive"),
        ("unknown", "Unknown"),
    )
    
    job_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    customer_name = models.CharField(max_length=100, blank=True, null=True)
    mobile = models.CharField(max_length=30, db_index=True)
    template_name = models.CharField(max_length=50, blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    message_id = models.CharField(max_length=200, blank=True, null=True, db_index=True)
    sent_text_message = models.TextField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    sent_at = models.DateTimeField(auto_now_add=True, db_index=True)
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPE_CHOICES, default="Sent")
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES, default="text")
    media_file = models.FileField(upload_to="whatsapp_media/", blank=True, null=True)

    def save(self, *args, **kwargs):
        """Normalize mobile before saving."""
        if self.mobile:
            self.mobile = format_mobile(self.mobile)
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            # For contact list queries (mobile + latest message)
            models.Index(fields=['mobile', '-sent_at', '-id'], name='idx_mobile_sent_at'),
            
            # For unread message counts
            models.Index(fields=['message_type', 'status'], name='idx_type_status'),
            
            # For sorting by sent_at
            models.Index(fields=['-sent_at'], name='idx_sent_at_desc'),
            
            # For webhook updates by message_id
            models.Index(fields=['message_id'], name='idx_message_id'),
            
            # For job-related queries
            models.Index(fields=['job_id', 'status'], name='idx_job_status'),
            
            # For searching messages
            models.Index(fields=['mobile', 'message_type', 'sent_at'], 
                        name='idx_mobile_type_sent'),
        ]

    def __str__(self):
        return f"{self.mobile} - {self.message_type} - {self.content_type}"


class BulkJob(models.Model):
    job_id = models.CharField(max_length=100, unique=True)
    template_name = models.CharField(max_length=50)
    total_customers = models.IntegerField(default=0)
    sent_count = models.IntegerField(default=0)
    success_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    status = models.CharField(max_length=20, default="Pending")
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    excel_file = models.FileField(upload_to="uploads/")
    success_report = models.FileField(upload_to="reports/", blank=True, null=True, max_length=500)
    failed_report = models.FileField(upload_to="reports/", blank=True, null=True, max_length=500)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'started_at'], name='idx_status_started'),
            models.Index(fields=['job_id'], name='idx_job_id'),
        ]

    def __str__(self):
        return f"{self.template_name} ({self.job_id})"

class ChatContact(models.Model):
    mobile = models.CharField(max_length=30, unique=True, db_index=True)
    last_time = models.DateTimeField(db_index=True)
    last_msg = models.TextField(blank=True, null=True)
    last_type = models.CharField(max_length=10, blank=True, null=True)
    last_status = models.CharField(max_length=50, blank=True, null=True)
    unread = models.IntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=['-last_time']),
            models.Index(fields=['mobile']),
            ]