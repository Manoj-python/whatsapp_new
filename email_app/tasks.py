
# import logging

# import openpyxl
# from celery import shared_task
# from django.conf import settings
# from django.core.mail import send_mail
# from django.core.validators import validate_email
# from django.core.exceptions import ValidationError
# from django.utils import timezone

# from .models import EmailCampaign, EmailLog

# logger = logging.getLogger(__name__)

# LOG_BATCH_SIZE = 500
# PROGRESS_BATCH_SIZE = 100


# # ============================================================
# # HELPERS
# # ============================================================

# def normalize_email(value):
#     if value is None:
#         return ""
#     return str(value).strip().lower()


# def normalize_header(value):
#     if value is None:
#         return ""
#     return str(value).strip().lower()


# def get_template_variables(template):
#     variables = [
#         value.strip().lower()
#         for value in (template.variables or "").split(",")
#         if value.strip()
#     ]

#     if len(variables) != len(set(variables)):
#         raise ValueError(
#             f"Duplicate variables configured in template: {template.name}"
#         )

#     return variables


# def render_text(text, values):
#     import re

#     return re.sub(
#         r"\{([a-zA-Z0-9_]+)\}",
#         lambda match: str(
#             values.get(match.group(1).lower(), "") or ""
#         ),
#         text or "",
#     )


# def save_logs(logs):
#     if logs:
#         EmailLog.objects.bulk_create(
#             logs,
#             batch_size=LOG_BATCH_SIZE,
#         )
#         logs.clear()


# def update_progress(campaign_id, processed, sent, failed, skipped):
#     EmailCampaign.objects.filter(id=campaign_id).update(
#         processed=processed,
#         sent=sent,
#         failed=failed,
#         skipped=skipped,
#     )


# def claim_campaign(campaign_id):
#     return (
#         EmailCampaign.objects
#         .filter(id=campaign_id, status="PENDING")
#         .update(
#             status="PROCESSING",
#             started_at=timezone.now(),
#             completed_at=None,
#             error_message="",
#         )
#         == 1
#     )


# def create_log(
#     campaign,
#     email,
#     subject,
#     message,
#     status,
#     response,
#     row_number,
# ):
#     return EmailLog(
#         campaign=campaign,
#         notification_type=campaign.template.notification_type,
#         email=email,
#         subject=subject,
#         message=message,
#         status=status,
#         response=str(response or "")[:4000],
#         row_number=row_number,
#     )


# # ============================================================
# # CELERY TASK
# # ============================================================

# @shared_task(bind=True)
# def process_email_campaign(self, campaign_id):

#     if not claim_campaign(campaign_id):
#         return {
#             "status": "SKIPPED",
#             "campaign_id": campaign_id,
#             "reason": "Campaign is not in PENDING status.",
#         }

#     workbook = None
#     excel_file = None
#     logs = []

#     processed = 0
#     sent = 0
#     failed = 0
#     skipped = 0

#     # Duplicate check within this Excel campaign.
#     processed_emails = set()

#     try:
#         # ----------------------------------------------------
#         # LOAD CAMPAIGN AND TEMPLATE
#         # ----------------------------------------------------

#         campaign = (
#             EmailCampaign.objects
#             .select_related("template", "template__notification_type")
#             .get(id=campaign_id)
#         )

#         template = campaign.template

#         if not template.is_active:
#             raise ValueError("Selected email template is inactive.")

#         if not campaign.excel_file:
#             raise ValueError("Campaign Excel file is missing.")

#         if not getattr(settings, "DEFAULT_FROM_EMAIL", ""):
#             raise ValueError("DEFAULT_FROM_EMAIL is not configured.")

#         variables = get_template_variables(template)

#         # ----------------------------------------------------
#         # OPEN EXCEL
#         # ----------------------------------------------------

#         excel_file = campaign.excel_file.open("rb")

#         workbook = openpyxl.load_workbook(
#             excel_file,
#             read_only=True,
#             data_only=True,
#         )

#         sheet = workbook.active

#         if sheet is None:
#             raise ValueError("Excel workbook has no active sheet.")

#         rows = sheet.iter_rows(values_only=True)

#         try:
#             raw_headers = next(rows)
#         except StopIteration:
#             raise ValueError("Excel file is empty.")

#         headers = [normalize_header(value) for value in raw_headers]

#         non_empty_headers = [header for header in headers if header]

#         if len(non_empty_headers) != len(set(non_empty_headers)):
#             raise ValueError("Excel contains duplicate column names.")

#         if "email" not in headers:
#             raise ValueError("Excel must contain an 'email' column.")

#         email_index = headers.index("email")

#         variable_indexes = {}

#         for variable in variables:
#             if variable not in headers:
#                 raise ValueError(
#                     f"Excel is missing required column: {variable}"
#                 )
#             variable_indexes[variable] = headers.index(variable)

#         total = max((sheet.max_row or 1) - 1, 0)

#         EmailCampaign.objects.filter(id=campaign_id).update(
#             total=total,
#             processed=0,
#             sent=0,
#             failed=0,
#             skipped=0,
#         )

#         # ----------------------------------------------------
#         # PROCESS RECIPIENTS
#         # ----------------------------------------------------

#         for row_number, row in enumerate(rows, start=2):
#             processed += 1

#             email = ""
#             subject = ""
#             body = ""

#             try:
#                 email = (
#                     normalize_email(row[email_index])
#                     if email_index < len(row)
#                     else ""
#                 )

#                 # Empty email address
#                 if not email:
#                     failed += 1

#                     logs.append(create_log(
#                         campaign, "", "", "",
#                         "FAILED",
#                         "Email address is empty.",
#                         row_number,
#                     ))
#                     continue

#                 # Validate email format
#                 try:
#                     validate_email(email)
#                 except ValidationError:
#                     failed += 1

#                     logs.append(create_log(
#                         campaign, email, "", "",
#                         "FAILED",
#                         "Invalid email address format.",
#                         row_number,
#                     ))
#                     continue

#                 # Skip duplicate email in the same Excel file
#                 if email in processed_emails:
#                     skipped += 1

#                     logs.append(create_log(
#                         campaign, email, "", "",
#                         "SKIPPED",
#                         "Duplicate email address in this Excel file.",
#                         row_number,
#                     ))
#                     continue

#                 processed_emails.add(email)

#                 # Read template variables from Excel
#                 values = {}

#                 for variable, index in variable_indexes.items():
#                     value = row[index] if index < len(row) else None
#                     values[variable] = (
#                         "" if value is None else str(value)
#                     )

#                 # Render subject and body
#                 subject = render_text(template.subject, values)
#                 body = render_text(template.content, values)

#                 if not subject.strip():
#                     raise ValueError("Rendered email subject is empty.")

#                 # Send one email to one recipient
#                 result = send_mail(
#                     subject=subject,
#                     message=body,
#                     from_email=settings.DEFAULT_FROM_EMAIL,
#                     recipient_list=[email],
#                     fail_silently=False,
#                 )

#                 if result == 1:
#                     sent += 1
#                     status = "SENT"
#                     response = (
#                         "Accepted by configured email backend; "
#                         "inbox delivery is not confirmed."
#                     )
#                 else:
#                     failed += 1
#                     status = "FAILED"
#                     response = "Email backend did not confirm sending."

#                 logs.append(create_log(
#                     campaign,
#                     email,
#                     subject,
#                     body,
#                     status,
#                     response,
#                     row_number,
#                 ))

#             except Exception as exc:
#                 failed += 1

#                 logs.append(create_log(
#                     campaign,
#                     email,
#                     subject,
#                     body,
#                     "FAILED",
#                     str(exc),
#                     row_number,
#                 ))

#                 logger.exception(
#                     "Email processing failed: campaign=%s row=%s",
#                     campaign_id,
#                     row_number,
#                 )

#             # Save logs in batches
#             if len(logs) >= LOG_BATCH_SIZE:
#                 save_logs(logs)

#             # Update progress periodically
#             if processed % PROGRESS_BATCH_SIZE == 0:
#                 save_logs(logs)

#                 update_progress(
#                     campaign_id,
#                     processed,
#                     sent,
#                     failed,
#                     skipped,
#                 )

#         # ----------------------------------------------------
#         # FINAL COUNTS
#         # ----------------------------------------------------

#         save_logs(logs)

#         EmailCampaign.objects.filter(id=campaign_id).update(
#             total=total,
#             processed=processed,
#             sent=sent,
#             failed=failed,
#             skipped=skipped,
#             status="COMPLETED",
#             error_message="",
#             completed_at=timezone.now(),
#         )

#         return {
#             "status": "COMPLETED",
#             "campaign_id": campaign_id,
#             "total": total,
#             "processed": processed,
#             "sent": sent,
#             "failed": failed,
#             "skipped": skipped,
#         }

#     except Exception as exc:
#         try:
#             save_logs(logs)
#         except Exception:
#             logger.exception("Unable to save remaining email logs.")

#         EmailCampaign.objects.filter(id=campaign_id).update(
#             status="FAILED",
#             error_message=str(exc)[:4000],
#             completed_at=timezone.now(),
#         )

#         logger.exception(
#             "Email campaign failed: campaign=%s",
#             campaign_id,
#         )
#         raise

#     finally:
#         if workbook is not None:
#             workbook.close()

#         if excel_file is not None:
#             excel_file.close()





import logging
import time
import re

import openpyxl

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import EmailCampaign, EmailLog

# IMPORTANT:
# Change this import to the actual app containing open_legal_pdf.
from messaging.utils import open_legal_pdf


logger = logging.getLogger(__name__)

LOG_BATCH_SIZE = 500
PROGRESS_BATCH_SIZE = 100

# Start conservatively below your SES maximum of 14/sec.
EMAIL_RATE_PER_SECOND = 8
EMAIL_INTERVAL = 1.0 / EMAIL_RATE_PER_SECOND

# Fixed S3 folder
S3_PDF_FOLDER = "legal_pdfs"


# ============================================================
# HELPERS
# ============================================================

def normalize_email(value):
    if value is None:
        return ""
    return str(value).strip().lower()


def normalize_header(value):
    if value is None:
        return ""
    return str(value).strip().lower()


def get_template_variables(template):

    variables = [
        value.strip().lower()
        for value in (template.variables or "").split(",")
        if value.strip()
    ]

    if len(variables) != len(set(variables)):
        raise ValueError(
            f"Duplicate variables configured in template: {template.name}"
        )

    return variables


def render_text(text, values):

    return re.sub(
        r"\{([a-zA-Z0-9_]+)\}",
        lambda match: str(
            values.get(match.group(1).lower(), "") or ""
        ),
        text or "",
    )


def save_logs(logs):

    if logs:
        EmailLog.objects.bulk_create(
            logs,
            batch_size=LOG_BATCH_SIZE,
        )
        logs.clear()


def update_progress(
    campaign_id,
    processed,
    sent,
    failed,
    skipped,
):

    EmailCampaign.objects.filter(id=campaign_id).update(
        processed=processed,
        sent=sent,
        failed=failed,
        skipped=skipped,
    )


def claim_campaign(campaign_id):

    return (
        EmailCampaign.objects
        .filter(id=campaign_id, status="PENDING")
        .update(
            status="PROCESSING",
            started_at=timezone.now(),
            completed_at=None,
            error_message="",
        )
        == 1
    )


def create_log(
    campaign,
    email,
    subject,
    message,
    status,
    response,
    row_number,
):

    return EmailLog(
        campaign=campaign,
        notification_type=campaign.template.notification_type,
        email=email,
        subject=subject,
        message=message,
        status=status,
        response=str(response or "")[:4000],
        row_number=row_number,
    )


# ============================================================
# EMAIL RATE LIMITER
# ============================================================

def wait_for_send_slot(next_send_at):

    """
    Limit this task to 8 email send attempts per second.
    Returns the next permitted send time.
    """

    now = time.monotonic()

    if next_send_at > now:
        time.sleep(next_send_at - now)

    now = time.monotonic()

    return max(next_send_at, now) + EMAIL_INTERVAL


# ============================================================
# PDF ATTACHMENT
# ============================================================

def attach_legal_pdf(email_message, filename):

    """
    Fetch customer-specific PDF from S3 legal_pdfs folder.
    Uses existing open_legal_pdf() function.
    """

    if not filename:
        raise ValueError(
            "Attachment filename is missing in Excel."
        )

    filename = str(filename).strip()

    if not filename.lower().endswith(".pdf"):
        raise ValueError(
            f"Invalid PDF filename: {filename}"
        )

    # Fetch PDF from S3
    pdf_bytes = open_legal_pdf(
        filename,
        S3_PDF_FOLDER,
    )

    if not pdf_bytes:
        raise ValueError(
            f"PDF is empty: {filename}"
        )

    # Attach PDF
    email_message.attach(
        filename,
        pdf_bytes,
        "application/pdf",
    )


# ============================================================
# CELERY EMAIL CAMPAIGN
# ============================================================

@shared_task(bind=True)
def process_email_campaign(self, campaign_id):

    if not claim_campaign(campaign_id):

        return {
            "status": "SKIPPED",
            "campaign_id": campaign_id,
            "reason": "Campaign is not in PENDING status.",
        }

    workbook = None
    excel_file = None
    email_connection = None

    logs = []

    processed = 0
    sent = 0
    failed = 0
    skipped = 0

    processed_emails = set()

    next_send_at = 0.0

    try:

        # ----------------------------------------------------
        # 1. LOAD CAMPAIGN
        # ----------------------------------------------------

        campaign = (
            EmailCampaign.objects
            .select_related(
                "template",
                "template__notification_type",
            )
            .get(id=campaign_id)
        )

        template = campaign.template

        if not template.is_active:
            raise ValueError(
                "Selected email template is inactive."
            )

        if not campaign.excel_file:
            raise ValueError(
                "Campaign Excel file is missing."
            )

        if not getattr(settings, "DEFAULT_FROM_EMAIL", ""):
            raise ValueError(
                "DEFAULT_FROM_EMAIL is not configured."
            )

        variables = get_template_variables(template)

        # ----------------------------------------------------
        # 2. OPEN EXCEL
        # ----------------------------------------------------

        excel_file = campaign.excel_file.open("rb")

        workbook = openpyxl.load_workbook(
            excel_file,
            read_only=True,
            data_only=True,
        )

        sheet = workbook.active

        if sheet is None:
            raise ValueError(
                "Excel workbook has no active sheet."
            )

        rows = sheet.iter_rows(values_only=True)

        try:
            raw_headers = next(rows)

        except StopIteration:
            raise ValueError("Excel file is empty.")

        headers = [
            normalize_header(value)
            for value in raw_headers
        ]

        non_empty_headers = [
            header for header in headers if header
        ]

        if len(non_empty_headers) != len(set(non_empty_headers)):
            raise ValueError(
                "Excel contains duplicate column names."
            )

        # ----------------------------------------------------
        # 3. VALIDATE EXCEL COLUMNS
        # ----------------------------------------------------

        if "email" not in headers:
            raise ValueError(
                "Excel must contain an 'email' column."
            )

        if "attachment_file" not in headers:
            raise ValueError(
                "Excel must contain an 'attachment_file' column."
            )

        email_index = headers.index("email")

        attachment_index = headers.index("attachment_file")

        variable_indexes = {}

        for variable in variables:

            if variable not in headers:
                raise ValueError(
                    f"Excel missing required column: {variable}"
                )

            variable_indexes[variable] = headers.index(variable)

        total = max((sheet.max_row or 1) - 1, 0)

        EmailCampaign.objects.filter(id=campaign_id).update(
            total=total,
            processed=0,
            sent=0,
            failed=0,
            skipped=0,
        )

        # ----------------------------------------------------
        # 4. OPEN ONE SMTP CONNECTION
        # ----------------------------------------------------

        email_connection = get_connection(
            fail_silently=False
        )

        email_connection.open()

        logger.info(
            "SMTP connection opened for campaign=%s",
            campaign_id,
        )

        # ----------------------------------------------------
        # 5. PROCESS EACH CUSTOMER
        # ----------------------------------------------------

        for row_number, row in enumerate(rows, start=2):

            processed += 1

            email = ""
            subject = ""
            body = ""

            try:

                # --------------------------------------------
                # GET EMAIL
                # --------------------------------------------

                email = (
                    normalize_email(row[email_index])
                    if email_index < len(row)
                    else ""
                )

                if not email:
                    raise ValueError(
                        "Email address is empty."
                    )

                # --------------------------------------------
                # VALIDATE EMAIL
                # --------------------------------------------

                try:
                    validate_email(email)

                except ValidationError:
                    raise ValueError(
                        "Invalid email address format."
                    )

                # --------------------------------------------
                # DUPLICATE CHECK
                # --------------------------------------------

                if email in processed_emails:

                    skipped += 1

                    logs.append(create_log(
                        campaign,
                        email,
                        "",
                        "",
                        "SKIPPED",
                        "Duplicate email in Excel.",
                        row_number,
                    ))

                else:

                    processed_emails.add(email)

                    # ----------------------------------------
                    # READ TEMPLATE VARIABLES
                    # ----------------------------------------

                    values = {}

                    for variable, index in variable_indexes.items():

                        value = (
                            row[index]
                            if index < len(row)
                            else None
                        )

                        values[variable] = (
                            "" if value is None
                            else str(value)
                        )

                    # ----------------------------------------
                    # RENDER EMAIL
                    # ----------------------------------------

                    subject = render_text(
                        template.subject,
                        values,
                    )

                    body = render_text(
                        template.content,
                        values,
                    )

                    if not subject.strip():
                        raise ValueError(
                            "Rendered email subject is empty."
                        )

                    # ----------------------------------------
                    # GET ATTACHMENT FILENAME
                    # ----------------------------------------

                    attachment_filename = (
                        str(row[attachment_index]).strip()
                        if (
                            attachment_index < len(row)
                            and row[attachment_index] is not None
                        )
                        else ""
                    )

                    # ----------------------------------------
                    # CREATE EMAIL
                    # ----------------------------------------

                    email_message = EmailMessage(
                        subject=subject,
                        body=body,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        to=[email],
                        connection=email_connection,
                    )

                    # ----------------------------------------
                    # FETCH PDF FROM S3
                    # ----------------------------------------

                    attach_legal_pdf(
                        email_message,
                        attachment_filename,
                    )

                    # ----------------------------------------
                    # RATE LIMIT BEFORE SENDING
                    # ----------------------------------------

                    next_send_at = wait_for_send_slot(
                        next_send_at
                    )

                    # ----------------------------------------
                    # SEND EMAIL
                    # ----------------------------------------

                    result = email_message.send(
                        fail_silently=False
                    )

                    if result == 1:

                        sent += 1
                        status = "SENT"

                        response = (
                            "Accepted by configured SMTP backend. "
                            "Inbox delivery is not confirmed."
                        )

                    else:

                        failed += 1
                        status = "FAILED"

                        response = (
                            "SMTP backend did not confirm sending."
                        )

                    logs.append(create_log(
                        campaign,
                        email,
                        subject,
                        body,
                        status,
                        response,
                        row_number,
                    ))

            except Exception as exc:

                failed += 1

                logs.append(create_log(
                    campaign,
                    email,
                    subject,
                    body,
                    "FAILED",
                    str(exc),
                    row_number,
                ))

                logger.exception(
                    "Email failed: campaign=%s row=%s email=%s",
                    campaign_id,
                    row_number,
                    email,
                )

            # ------------------------------------------------
            # 6. SAVE LOGS IN BATCHES
            # ------------------------------------------------

            if len(logs) >= LOG_BATCH_SIZE:
                save_logs(logs)

            # ------------------------------------------------
            # 7. UPDATE PROGRESS EVERY 100
            # ------------------------------------------------

            if processed % PROGRESS_BATCH_SIZE == 0:

                save_logs(logs)

                update_progress(
                    campaign_id,
                    processed,
                    sent,
                    failed,
                    skipped,
                )

                logger.info(
                    "Campaign progress: campaign=%s "
                    "processed=%s sent=%s failed=%s skipped=%s",
                    campaign_id,
                    processed,
                    sent,
                    failed,
                    skipped,
                )

        # ----------------------------------------------------
        # 8. FINAL UPDATE
        # ----------------------------------------------------

        save_logs(logs)

        EmailCampaign.objects.filter(id=campaign_id).update(
            total=total,
            processed=processed,
            sent=sent,
            failed=failed,
            skipped=skipped,
            status="COMPLETED",
            error_message="",
            completed_at=timezone.now(),
        )

        logger.info(
            "Campaign completed: campaign=%s "
            "total=%s sent=%s failed=%s skipped=%s",
            campaign_id,
            total,
            sent,
            failed,
            skipped,
        )

        return {
            "status": "COMPLETED",
            "campaign_id": campaign_id,
            "total": total,
            "processed": processed,
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
        }

    except Exception as exc:

        try:
            save_logs(logs)

        except Exception:
            logger.exception(
                "Unable to save remaining email logs."
            )

        EmailCampaign.objects.filter(id=campaign_id).update(
            processed=processed,
            sent=sent,
            failed=failed,
            skipped=skipped,
            status="FAILED",
            error_message=str(exc)[:4000],
            completed_at=timezone.now(),
        )

        logger.exception(
            "Campaign failed: campaign=%s",
            campaign_id,
        )

        raise

    finally:

        # Close SMTP connection
        if email_connection is not None:

            try:
                email_connection.close()

            except Exception:
                logger.exception(
                    "Unable to close SMTP connection."
                )

        # Close Excel
        if workbook is not None:
            workbook.close()

        if excel_file is not None:
            excel_file.close()
