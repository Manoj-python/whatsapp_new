from django.db import models

from .utils import format_mobile2

class SmsWhatsAppLog2(models.Model):
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

    customer_name = models.CharField(max_length=100, blank=True, null=True)
    mobile = models.CharField(max_length=30, db_index=True)
    template_name = models.CharField(max_length=50, blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    message_id = models.CharField(max_length=200, blank=True, null=True)
    sent_text_message = models.TextField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    # ✅ New fields
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPE_CHOICES, default="Sent")
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES, default="text")
    media_file = models.FileField(upload_to="whatsapp2_media/", blank=True, null=True)

    def save(self, *args, **kwargs):
        """Normalize mobile before saving."""
        if self.mobile:
            self.mobile = format_mobile2(self.mobile)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.mobile} - {self.message_type} - {self.content_type}"


class BulkJob2(models.Model):
    job_id = models.CharField(max_length=100, unique=True)
    template_name = models.CharField(max_length=50)
    total_customers = models.IntegerField(default=0)
    sent_count = models.IntegerField(default=0)
    success_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    status = models.CharField(
        max_length=20,
        default="Pending",  # Pending, Running, Completed, Failed
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    excel_file = models.FileField(upload_to="uploads2/")

    # Optional: store per-job report filenames
    success_report = models.FileField(upload_to="reports2/", blank=True, null=True,max_length=500)
    failed_report = models.FileField(upload_to="reports2/", blank=True, null=True,max_length=500)

    def __str__(self):
        return f"{self.template_name} ({self.job_id})"
