# financehub/admin.py
from django.contrib import admin
from .models import Lcc, UploadHistory

@admin.register(Lcc)
class LccAdmin(admin.ModelAdmin):
    list_display = ("loan_number", "customer_name", "cust_mobile", "branch", "centre_name", "created_at")
    search_fields = ("loan_number", "customer_name", "cust_mobile", "vehicle_no")
    list_filter = ("company", "branch", "latest_status")
    ordering = ("-created_at",)
    list_per_page = 50

from django.contrib import admin
from .models import UploadHistory

@admin.register(UploadHistory)
class UploadHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "filename",
        "file_type",
        "uploaded_by",
        "uploaded_at",
        "total_rows",
        "processed_rows",
        "status",
    )

    readonly_fields = (
        "filename",
        "file_type",
        "uploaded_by",
        "uploaded_at",
        "total_rows",
        "processed_rows",
        "status",
        "error_message",
    )
