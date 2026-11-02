
import csv

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_protect

from batch_app.models import NotificationType
from .models import EmailTemplate, EmailCampaign, EmailLog
from .tasks import process_email_campaign


# @login_required
def email_templates(request):
    templates = EmailTemplate.objects.all().order_by("-created_at")
    notification_types = NotificationType.objects.filter(
        is_active=True
    ).order_by("name")

    return render(
        request,
        "add_email_template.html",
        {
            "templates": templates,
            "notification_types": notification_types,
        },
    )




# @login_required
@require_POST
@csrf_protect
def upload_email_campaign(request):
    name = request.POST.get("name", "").strip()
    template_id = request.POST.get("template_id")
    excel_file = request.FILES.get("excel_file")

    if not template_id or not excel_file:
        return JsonResponse(
            {"error": "Select a template and upload an Excel file."},
            status=400,
        )

    if not excel_file.name.lower().endswith(".xlsx"):
        return JsonResponse(
            {"error": "Upload an .xlsx Excel file."},
            status=400,
        )

    if excel_file.size == 0:
        return JsonResponse(
            {"error": "Uploaded Excel file is empty."},
            status=400,
        )

    template = get_object_or_404(
        EmailTemplate,
        id=template_id,
        is_active=True,
    )

    campaign = EmailCampaign.objects.create(
        name=name or f"Email Campaign - {template.name}",
        template=template,
        excel_file=excel_file,
        status="PENDING",
    )

    try:
        task = process_email_campaign.delay(campaign.id)
    except Exception as exc:
        campaign.status = "FAILED"
        campaign.error_message = f"Could not enqueue Celery task: {exc}"
        campaign.completed_at = __import__(
            "django.utils.timezone", fromlist=["now"]
        ).now()
        campaign.save(
            update_fields=[
                "status",
                "error_message",
                "completed_at",
                "updated_at",
            ]
        )
        return JsonResponse(
            {
                "error": "Campaign created, but Celery task could not start.",
                "campaign_id": campaign.id,
            },
            status=503,
        )

    return JsonResponse(
        {
            "message": "Campaign queued successfully.",
            "campaign_id": campaign.id,
            "progress_url": reverse(
                "email_campaign_progress",
                args=[campaign.id],
            ),
            "report_url": reverse(
                "email_campaign_report",
                args=[campaign.id],
            ),
            "failed_report_url": reverse(
                "email_campaign_failed_report",
                args=[campaign.id],
            ),
        },
        status=201,
    )


# @login_required
@require_GET
def email_campaign_progress(request, campaign_id):
    campaign = get_object_or_404(
        EmailCampaign,
        id=campaign_id,
    )

    progress = (
        round(campaign.processed * 100 / campaign.total, 2)
        if campaign.total
        else (100 if campaign.status in ("COMPLETED", "FAILED") else 0)
    )

    return JsonResponse(
        {
            "id": campaign.id,
            "name": campaign.name,
            "status": campaign.status,
            "total": campaign.total,
            "processed": campaign.processed,
            "sent": campaign.sent,
            "failed": campaign.failed,
            "skipped": campaign.skipped,
            "progress": progress,
            "error_message": campaign.error_message or "",
            "completed": campaign.status in ("COMPLETED", "FAILED"),
        }
    )


def _email_csv_response(campaign, failed_only=False):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response.write("\ufeff")

    suffix = "failed" if failed_only else "all"
    response["Content-Disposition"] = (
        f'attachment; filename="email_campaign_{campaign.id}_{suffix}.csv"'
    )

    writer = csv.writer(response)
    writer.writerow(
        [
            "Excel Row",
            "Email",
            "Subject",
            "Status",
            "Reason / Response",
            "Created At",
        ]
    )

    logs = EmailLog.objects.filter(
        campaign=campaign,
    ).order_by("id")

    if failed_only:
        logs = logs.filter(status="FAILED")

    for log in logs.iterator(chunk_size=1000):
        writer.writerow(
            [
                log.row_number or "",
                log.email,
                log.subject,
                log.status,
                log.response or "",
                log.created_at.isoformat() if log.created_at else "",
            ]
        )

    return response


# @login_required
@require_GET
def email_campaign_report(request, campaign_id):
    campaign = get_object_or_404(
        EmailCampaign,
        id=campaign_id,
    )
    return _email_csv_response(campaign)


# @login_required
@require_GET
def email_campaign_failed_report(request, campaign_id):
    campaign = get_object_or_404(
        EmailCampaign,
        id=campaign_id,
    )
    return _email_csv_response(campaign, failed_only=True)

def email_campaigns(request):
    campaigns = EmailCampaign.objects.select_related(
        "template"
    ).order_by("-created_at")

    templates = EmailTemplate.objects.filter(
        is_active=True
    ).order_by("name")

    return render(
        request,
        "email_upload.html",
        {
            "campaigns": campaigns,
            "templates": templates,
        },
    )


# @login_required
@require_POST
@csrf_protect
def delete_email_campaign(request, campaign_id):
    campaign = get_object_or_404(EmailCampaign, id=campaign_id)

    # Optional: prevent deleting a campaign that's still processing
    if campaign.status == "PROCESSING":
        return JsonResponse(
            {"error": "Cannot delete a campaign that is still processing."},
            status=400,
        )

    # Delete the associated Excel file from storage if present
    if campaign.excel_file:
        campaign.excel_file.delete(save=False)

    # Delete related email logs first (or rely on on_delete=CASCADE)
    EmailLog.objects.filter(campaign=campaign).delete()

    campaign.delete()

    return JsonResponse({"message": "Campaign deleted successfully."})