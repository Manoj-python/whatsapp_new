# messaging/models.py
from django.db import models
from django.utils import timezone

class SmsWhatsAppLog2(models.Model):
    job_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    customer_name = models.CharField(max_length=255, blank=True, default='')
    mobile = models.CharField(max_length=20, db_index=True)
    template_name = models.CharField(max_length=100, blank=True, default='')
    sent_text_message = models.TextField(blank=True, default='')
    status = models.CharField(max_length=50, blank=True, default='', db_index=True)
    message_id = models.CharField(max_length=255, blank=True, default='', db_index=True)
    message_type = models.CharField(max_length=50, blank=True, default='', db_index=True)
    content_type = models.CharField(max_length=50, blank=True, default='text')
    media_file = models.FileField(upload_to='chat_media2/', blank=True, null=True)
    sent_at = models.DateTimeField(default=timezone.now, db_index=True)
    error_message = models.TextField(blank=True, default='')
    
    class Meta:
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['mobile', '-sent_at']),
            models.Index(fields=['-sent_at']),
            models.Index(fields=['message_type', 'status']),
            models.Index(fields=['job_id']),
            models.Index(fields=['message_id']),
        ]
    
    def __str__(self):
        return f"{self.mobile} - {self.message_type} - {self.sent_at}"

class ChatContact2(models.Model):
    mobile = models.CharField(max_length=20, unique=True, db_index=True)
    last_msg = models.TextField(blank=True, default='')
    last_time = models.DateTimeField(default=timezone.now, db_index=True)
    last_type = models.CharField(max_length=20, blank=True, default='')
    last_status = models.CharField(max_length=20, blank=True, default='')
    unread = models.IntegerField(default=0, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-last_time']
        indexes = [
            models.Index(fields=['-last_time', 'unread']),
            models.Index(fields=['mobile']),
        ]
    
    def to_dict(self):
        return {
            'mobile': self.mobile,
            'last_msg': self.last_msg or '',
            'last_type': self.last_type,
            'last_status': self.last_status,
            'unread': self.unread,
            'last_time': self.last_time.isoformat() if self.last_time else None,
        }
    
    def __str__(self):
        return f"{self.mobile} - {self.last_msg[:30]}"

class BulkJob2(models.Model):
    job_id = models.CharField(max_length=100, unique=True, db_index=True)
    template_name = models.CharField(max_length=100)
    total_customers = models.IntegerField(default=0)
    sent_count = models.IntegerField(default=0)
    success_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    status = models.CharField(max_length=50, default='Pending', db_index=True)
    excel_file = models.CharField(max_length=500, blank=True, default='')
    success_report = models.FileField(upload_to="reports/", blank=True, null=True, max_length=500)
    failed_report = models.FileField(upload_to="reports/", blank=True, null=True, max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True,default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
