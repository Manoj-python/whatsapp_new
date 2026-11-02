from django.db import models

class EmailTemplate(models.Model):
    notification_type = models.ForeignKey(
        "batch_app.NotificationType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="email_templates",
    )

    name = models.CharField(max_length=100)
    subject = models.CharField(max_length=255)
    content = models.TextField()

    # Example: customer_name, loan_id, amount
    variables = models.CharField(
        max_length=500,
        blank=True,
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Email Template"
        verbose_name_plural = "Email Templates"

    def __str__(self):
        return self.name


class EmailCampaign(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("PROCESSING", "Processing"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
    ]

    name = models.CharField(max_length=200, blank=True)

    template = models.ForeignKey(
        EmailTemplate,
        on_delete=models.PROTECT,
        related_name="campaigns",
    )

    excel_file = models.FileField(
        upload_to="email_campaigns/",
    )

    # Total rows in Excel
    total = models.PositiveIntegerField(default=0)

    # Total rows processed
    processed = models.PositiveIntegerField(default=0)

    # Successfully submitted emails
    sent = models.PositiveIntegerField(default=0)

    # Failed emails
    failed = models.PositiveIntegerField(default=0)

    # Skipped rows
    skipped = models.PositiveIntegerField(default=0)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PENDING",
        db_index=True,
    )

    error_message = models.TextField(
        blank=True,
        null=True,
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name or 'Email Campaign'} - {self.id}"


class EmailLog(models.Model):
    STATUS_CHOICES = [
        ("SENT", "Sent"),
        ("FAILED", "Failed"),
        ("SKIPPED", "Skipped"),
    ]

    campaign = models.ForeignKey(
        EmailCampaign,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
    )

    notification_type = models.ForeignKey(
        "batch_app.NotificationType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="email_logs",
    )

    # For email fallback in existing batch jobs
    batch_job = models.ForeignKey(
        "batch_app.BatchJob",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_logs",
    )
    row_number = models.PositiveIntegerField(
    null=True,
    blank=True,
)

    email = models.EmailField(max_length=254)
    subject = models.CharField(max_length=255)
    message = models.TextField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        db_index=True,
    )

    response = models.TextField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} - {self.status}"
