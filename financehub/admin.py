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

@admin.register(UploadHistory)
class UploadHistoryAdmin(admin.ModelAdmin):
    list_display = ("filename", "uploaded_by", "uploaded_at", "rows_in_file", "rows_inserted")
    readonly_fields = ("uploaded_at",)
    ordering = ("-uploaded_at",)
