from django.contrib import admin
from .models import SMSTemplate, SMSLog, SMSCampaign
from batch_app.models import NotificationType


@admin.register(NotificationType)
class NotificationTypeAdmin(admin.ModelAdmin):

    list_display = (
        "code",
        "name",
        "is_active",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "code",
        "name",
    )


@admin.register(SMSTemplate)
class SMSTemplateAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "template_id",
        "variables",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "name",
        "template_id",
       
    )

@admin.register(SMSCampaign)
class SMSCampaignAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "name",
        "template",
        "total",
        "processed",
        "sent",
        "failed",
        "status",
        "created_at",
    )

    list_filter = (
        "status",
        "created_at",
    )

    search_fields = (
        "name",
        "template__name",
        "template__template_id",
    )


@admin.register(SMSLog)
class SMSLogAdmin(admin.ModelAdmin):

    list_display = (
        "mobile",
        "status",
        "campaign",
        "created_at",
    )

    list_filter = (
        "status",
        "created_at",
    )

    search_fields = (
        "mobile",
    )