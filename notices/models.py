from django.db import models

class TaskStatus(models.Model):
    task_id = models.CharField(max_length=100, unique=True)
    notice_type = models.CharField(max_length=100)
    total_rows = models.IntegerField(default=0)
    processed_rows = models.IntegerField(default=0)
    status = models.CharField(max_length=20, default='pending')  # pending, processing, completed, failed
    zip_url = models.TextField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.task_id} - {self.status}"
