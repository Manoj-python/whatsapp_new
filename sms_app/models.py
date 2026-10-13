from django.db import models
from batch_app.models import NotificationType

class SMSTemplate(models.Model):

    notification_type = models.ForeignKey(
        "batch_app.NotificationType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sms_templates"
    )

    name = models.CharField(
        max_length=100
    )

    template_id = models.CharField(
        max_length=50
    )

    content = models.TextField()

    variables = models.CharField(
        max_length=500,
        blank=True
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "SMS Template"
        verbose_name_plural = "SMS Templates"

    def __str__(self):
        return self.name


class SMSCampaign(models.Model):

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("PROCESSING", "Processing"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
    ]

    name = models.CharField(
        max_length=200,
        blank=True
    )

    template = models.ForeignKey(
        SMSTemplate,
        on_delete=models.PROTECT
    )

    excel_file = models.FileField(
        upload_to="sms_campaigns/"
    )

    # Total number of rows in Excel
    total = models.PositiveIntegerField(
        default=0
    )

    # Total rows processed
    processed = models.PositiveIntegerField(
        default=0
    )

    # Successfully sent SMS
    sent = models.PositiveIntegerField(
        default=0
    )

    # Failed SMS
    failed = models.PositiveIntegerField(
        default=0
    )

    # Skipped rows
    skipped = models.PositiveIntegerField(
        default=0
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PENDING"
    )

    error_message = models.TextField(
        blank=True,
        null=True
    )

    # Campaign processing timestamps
    started_at = models.DateTimeField(
        null=True,
        blank=True
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return f"{self.name or 'SMS Campaign'} - {self.id}"


class SMSLog(models.Model):

    campaign = models.ForeignKey(
        SMSCampaign,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs"
    )
        # Batch Job SMS fallback information
    notification_type = models.ForeignKey(
        "batch_app.NotificationType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sms_logs"
    )

    batch_job = models.ForeignKey(
        "batch_app.BatchJob",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sms_logs"
    )

    mobile = models.CharField(
        max_length=15
    )

    message = models.TextField()

    # Expected values:
    # sent
    # failed
    # skipped
    status = models.CharField(
        max_length=20
    )

    response = models.TextField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.mobile} - {self.status}"
