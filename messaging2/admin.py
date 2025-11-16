from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import SmsWhatsAppLog2, BulkJob2


@admin.register(SmsWhatsAppLog2)
class SmsWhatsAppLog2Admin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer_name",
        "mobile",
        "message_type",
        "content_type",
        "template_name",
        "status",
        "sent_at",
    )
    list_filter = (
        "message_type",
        "content_type",
        "status",
        "sent_at",
    )
    search_fields = (
        "customer_name",
        "mobile",
        "template_name",
        "status",
        "message_id",
        "sent_text_message",
    )
    readonly_fields = ("sent_at",)
    date_hierarchy = "sent_at"
    ordering = ("-sent_at",)


@admin.register(BulkJob2)
class BulkJob2Admin(admin.ModelAdmin):
    list_display = (
        "job_id",
        "template_name",
        "total_customers",
        "sent_count",
        "success_count",
        "failed_count",
        "status",
        "started_at",
        "completed_at",
    )
    list_filter = (
        "status",
        "started_at",
        "completed_at",
    )
    search_fields = (
        "job_id",
        "template_name",
    )
    readonly_fields = (
        "started_at",
        "completed_at",
    )
    date_hierarchy = "started_at"
    ordering = ("-started_at",)


# Optional: if you prefer not to use decorators
# admin.site.register(SmsWhatsAppLog2, SmsWhatsAppLog2Admin)
# admin.site.register(BulkJob2, BulkJob2Admin)
