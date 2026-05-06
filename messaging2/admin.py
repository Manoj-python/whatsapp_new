from django.contrib import admin
from .models import SmsWhatsAppLog2, BulkJob2

@admin.register(SmsWhatsAppLog2)
class SmsWhatsAppLog2Admin(admin.ModelAdmin):
    list_display = ("mobile", "message_type", "status", "sent_at")
    search_fields = ("mobile", "sent_text_message")

@admin.register(BulkJob2)
class BulkJob2Admin(admin.ModelAdmin):
    list_display = ("job_id", "template_name", "status", "total_customers", "sent_count", "success_count", "failed_count")
    search_fields = ("job_id", "template_name")
