import re
import requests
from datetime import datetime
from django.conf import settings
from typing import Tuple, Dict, Any, Optional,List
from pathlib import Path
import requests
import mimetypes
from django.core.files.uploadedfile import UploadedFile
from django.conf import settings
from .models import *

PAYMENT_LINK2 = "https://smsquare.co.in/pay2"

# -----------------------------------------------------
# Upload media to WhatsApp Cloud
# -----------------------------------------------------
# def upload_whatsapp_media2(file_obj):
#     """
#     Upload media to WhatsApp Cloud API
#     Returns media ID
#     """
#     access_token = settings.WHATSAPP2_ACCESS_TOKEN
#     phone_number_id = settings.WHATSAPP2_PHONE_NUMBER_ID
#     url = f"https://graph.facebook.com/v22.0/{phone_number_id}/media"
#     headers = {"Authorization": f"Bearer {access_token}"}

#     # Reset file pointer to beginning
#     if hasattr(file_obj, 'seek'):
#         file_obj.seek(0)

#     # Get file name and content type
#     if hasattr(file_obj, 'name'):
#         filename = file_obj.name
#     else:
#         filename = "media_file"

#     content_type = getattr(file_obj, 'content_type', None)
#     if not content_type:
#         content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

#     files = {
#         'file': (filename, file_obj.read(), content_type)
#     }
#     data = {'messaging_product': 'whatsapp'}

#     try:
#         resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)
#         resp.raise_for_status()
#         result = resp.json()
#         print(f"Media uploaded successfully. ID: {result.get('id')}")
#         return result
#     except Exception as e:
#         print(f"Media upload error: {e}")
#         print(f"Response: {resp.text if 'resp' in locals() else 'No response'}")
#         raise

def upload_whatsapp_media2(file_obj):
    """
    Upload media to WhatsApp Cloud API
    Returns media ID
    """
    import mimetypes

    access_token = settings.WHATSAPP2_ACCESS_TOKEN
    phone_number_id = settings.WHATSAPP2_PHONE_NUMBER_ID
    url = f"https://graph.facebook.com/v22.0/{phone_number_id}/media"
    headers = {"Authorization": f"Bearer {access_token}"}

    # ✅ Handle bytes input
    if isinstance(file_obj, bytes):
        from io import BytesIO
        file_obj = BytesIO(file_obj)
        file_obj.name = "document.pdf"

    # Reset file pointer to beginning
    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)

    # Get file name and content type
    if hasattr(file_obj, 'name'):
        filename = file_obj.name
    else:
        filename = "media_file"

    content_type = getattr(file_obj, 'content_type', None)
    if not content_type:
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

    # ✅ Read content properly
    content = file_obj.read() if hasattr(file_obj, 'read') else file_obj

    files = {
        'file': (filename, content, content_type)
    }
    data = {'messaging_product': 'whatsapp'}

    try:
        resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)
        resp.raise_for_status()
        result = resp.json()
        print(f"Media uploaded successfully. ID: {result.get('id')}")
        return result
    except Exception as e:
        print(f"Media upload error: {e}")
        print(f"Response: {resp.text if 'resp' in locals() else 'No response'}")
        raise

# -----------------------------------------------------
# Send media (image/video/audio/document)
# -----------------------------------------------------
def send_whatsapp_media2(to_number, media_id, media_type, caption="", filename=None):
    """
    Send media message using WhatsApp Cloud API
    media_type: image, video, audio, document
    """
    url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP2_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP2_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    # Build payload based on media type
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": media_type,
        media_type: {"id": media_id}
    }

    # CRITICAL FIX: Add filename for documents
    if media_type == "document" and filename:
        payload["document"]["filename"] = filename
        print(f"📄 Sending document with filename: {filename}")

    # Add caption for image, video, and document
    if caption and media_type in ("image", "video", "document"):
        payload[media_type]["caption"] = caption

    # For audio, no caption is allowed
    if media_type == "audio":
        payload["audio"] = {"id": media_id}

    print(f"Sending {media_type} to {to_number}")
    if media_type == "document":
        print(f"Filename: {filename}")

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        print(f"Media sent successfully. Message ID: {result.get('messages', [{}])[0].get('id')}")
        return result
    except Exception as e:
        print(f"Send media error: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"Response: {e.response.text}")
        raise


# --------------------------------------------------
# WhatsApp template text sanitizer
# --------------------------------------------------

def send_whatsapp_text2(to_number, text_body):
    """Send text message via WhatsApp API"""
    url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP2_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP2_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    text_body = text_body[:4096]

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text_body}
    }

    print(f"Sending text to {to_number}: {text_body[:50]}...")

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        print(f"Text sent successfully. Message ID: {result.get('messages', [{}])[0].get('id')}")
        return result
    except Exception as e:
        print(f"Send text error: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"Response: {e.response.text}")
        raise


def sanitize_template_text2(text: str) -> str:
    """
    WhatsApp template rules:
    - No tabs
    - No multiple newlines
    - No more than 1 consecutive space
    """
    text = text.replace("\t", " ")
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def split_text_into_chunks2(text: str, max_len: int = 1000) -> list[str]:
    """
    Split text into WhatsApp-safe chunks without breaking logical separators.
    """
    chunks = []
    while len(text) > max_len:
        split_at = text.rfind(" || ", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at].strip())
        text = text[split_at:].lstrip(" |")
    if text:
        chunks.append(text.strip())
    return chunks


# ---------------------------
# Mobile normalization
# ---------------------------
def format_mobile2(x: str) -> str:
    if not x:
        return ""
    s = str(x).strip()
    digits = re.sub(r"\D", "", s)
    if digits.startswith("91") and len(digits) >= 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) >= 10:
        digits = digits[-10:]
    return f"+91{digits}" if len(digits) == 10 else x


# ---------------------------
# Date formatting (DD-MM-YYYY)
# ---------------------------
def format_whatsapp_date2(value) -> str:
    if not value:
        return ""
    s = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%d-%m-%Y")
        except Exception:
            continue
    try:
        dt = datetime.fromisoformat(s)
        return dt.strftime("%d-%m-%Y")
    except Exception:
        return s


# ==================================================
# OPEN LEGAL PDF (S3 FIRST + FOLDER SUPPORT)
# ==================================================
def open_legal_pdf2(filename, folder):
    filename = Path(str(filename)).name.strip()

    # ==================================================
    # 🔥 ALWAYS TRY S3 FIRST
    # ==================================================
    import boto3
    from botocore.exceptions import ClientError

    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
    )

    key = f"{folder}/{filename}"

    print("DEBUG S3 KEY:", key)

    try:
        obj = s3.get_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=key,
        )
        print("✅ Loaded from S3")
        # ✅ Return bytes
        return obj["Body"].read()

    except ClientError as e:
        print("⚠️ S3 fetch failed:", e)

    # ==================================================
    # 🔽 FALLBACK TO LOCAL (ONLY IF NEEDED)
    # ==================================================
    if settings.DEBUG:
        if folder == "welcome_pdfs":
            base_dir = Path(settings.WELCOME_PDF_DIR)
        elif folder == "legal_pdfs":
            base_dir = Path(settings.LEGAL_PDF_DIR)
        elif folder == "noc_pdfs":
            base_dir = Path(settings.NOC_PDF_DIR)
        else:
            raise ValueError(f"Unknown folder: {folder}")

        file_path = base_dir / filename

        print("DEBUG LOCAL PATH:", file_path)

        if file_path.exists():
            print("✅ Loaded from LOCAL")
            # ✅ Return bytes, not file object
            with open(file_path, "rb") as f:
                return f.read()

        raise FileNotFoundError(
            f"PDF not found in S3 AND locally: {key} | {file_path}"
        )

    # ==================================================
    # ❌ FINAL FAIL (production)
    # ==================================================
    raise FileNotFoundError(
        f"PDF not found in S3: {key}"
    )


# ---------------------------
# WhatsApp number pre-check
# ---------------------------

# ---------------------------
# WhatsApp number pre-check
# ---------------------------
def check_whatsapp_number2(mobile: str) -> Dict[str, Any]:
    try:
        url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP2_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP2_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {"messaging_product": "whatsapp", "to": mobile, "type": "contacts"}
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        data = resp.json()

        contacts = data.get("contacts", [])
        if contacts:
            status = contacts[0].get("status")
            if status == "valid":
                return {"valid": True, "blocked": False, "reason": "Valid WhatsApp user"}
            if status == "invalid":
                return {"valid": False, "blocked": False, "reason": "Not a WhatsApp user"}

        err = data.get("error") or {}
        code = err.get("code")
        msg = err.get("message", "")
        if code:
            icode = int(code)
            if icode == 131011:
                return {"valid": False, "blocked": True, "reason": "User blocked business"}
            if icode in (131009, 131045, 131000):
                return {"valid": False, "blocked": False, "reason": msg}

        return {"valid": True, "blocked": False, "reason": "Unknown (assumed valid)"}
    except Exception as e:
        return {"valid": True, "blocked": False, "reason": f"Validation error (assume valid): {e}"}

def render_template_text2(template_body: str, parameters: list) -> str:
    """
    Replace {{1}}, {{2}} placeholders with Excel values.
    """
    if not template_body:
        return ""
    out = template_body
    for i, p in enumerate(parameters, start=1):
        out = out.replace(f"{{{{{i}}}}}", str(p.get("text", "")))
    return out


# ---------------------------
# Build payload (template) - FIXED VERSION
# ---------------------------
from io import BytesIO

def build_payload2(choice: str, row: dict, media_id: Optional[str] = None) -> Tuple[dict, str]:
    templates = {
        "1": ("emi_reminder", "en", [
            {"type": "text", "text": str(row.get("customer_name", ""))},
            {"type": "text", "text": str(row.get("total_dues", ""))},
            {"type": "text", "text": str(row.get("loan_number", ""))},
            {"type": "text", "text": format_whatsapp_date2(row.get("installment_date", ""))},
            {"type": "text", "text": PAYMENT_LINK2},
        ]),
        "2": ("emi_tenure_reminder", "te", [
            {"type": "text", "text": str(row.get("CustomerName", ""))},
            {"type": "text", "text": str(row.get("VehicleNo", ""))},
        ]),
        "3": ("cibil_report", "en", [
            {"type": "text", "text": str(row.get("customer_name", ""))},
        ]),
        "4": ("vehicle_registration_slot", "te", [
            {"type": "text", "text": str(row.get("CustomerName", ""))},
            {"type": "text", "text": format_whatsapp_date2(row.get("registration_date", ""))},
        ]),
        "5": ("nach_bounce_payment_reminder", "en", [
            {"type": "text", "text": str(row.get("customer_name", ""))},
            {"type": "text", "text": str(row.get("due_amount", ""))},
            {"type": "text", "text": format_whatsapp_date2(row.get("due_date", ""))},
            {"type": "text", "text": str(row.get("loan_number", ""))},
            {"type": "text", "text": PAYMENT_LINK2},
        ]),
        "6": ("nach_balance_reminder", "en", [
            {"type": "text", "text": str(row.get("customer_name", ""))},
            {"type": "text", "text": str(row.get("balance_amount", ""))},
            {"type": "text", "text": str(row.get("loan_number", ""))},
            {"type": "text", "text": str(row.get("urm_number", ""))},
            {"type": "text", "text": format_whatsapp_date2(row.get("due_date", ""))},
            {"type": "text", "text": str(row.get("bank_account_number", ""))},
        ]),
        "7": ("vehicle_registration_reminder", "en", [
            {"type": "text", "text": str(row.get("CustomerName", ""))},
            {"type": "text", "text": str(row.get("Vehicle_No", ""))},
            {"type": "text", "text": str(row.get("Loan_number", ""))},
        ]),
        "8": ("welcome_message", "en", [
            {"type": "text", "text": str(row.get("customer_name", ""))},
        ]),
        "9": ("noc_dispatch", "en", [
            {"type": "text", "text": str(row.get("Customer Name", ""))},
            {"type": "text", "text": str(row.get("Agreement No", ""))},
            {"type": "text", "text": str(row.get("Vehicle No", ""))},
            {"type": "text", "text": str(row.get("Couirer Status", ""))},
            {"type": "text", "text": str(row.get("PODS", ""))},
            {"type": "text", "text": format_whatsapp_date2(row.get("Couirer Date", ""))},
            {"type": "text", "text": "7"},
        ]),
        "10": ("whatsapp_noc", "en", [
            {"type": "text", "text": str(row.get("customer_name", ""))},
            {"type": "text", "text": str(row.get("loan_number", ""))},
            {"type": "text", "text": str(row.get("vehicle_number", ""))},
            {"type": "text", "text": format_mobile2(row.get("cust_mobile", ""))},
        ]),
        "11": ("guarantor", "te", [
            {"type": "text", "text": str(row.get("customer_name", ""))},
            {"type": "text", "text": str(row.get("loan_number", ""))},
            {"type": "text", "text": str(row.get("vehicle_number", ""))},
            {"type": "text", "text": str(row.get("pending_emis", ""))},
        ]),
        "12": ("noc_address_confirmation_v2", "en", [
            {"type": "text", "text": str(row.get("customer_name", ""))},
            {"type": "text", "text": str(row.get("loan_number", ""))},
            {"type": "text", "text": str(row.get("vehicle_number", ""))},
            {"type": "text", "text": str(row.get("customer_address", ""))}
        ]),
        "13": (
            "customer_notice",
            "en",
            [
                {"type": "text", "text": str(row.get("customer_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("vehicle_number", ""))},
                {"type": "text", "text": str(row.get("amount", ""))},
                {"type": "text", "text": format_whatsapp_date2(row.get("timeline", ""))},
            ],
        ),
        "14": (
            "guarantor_notice",
            "en",
            [
                {"type": "text", "text": str(row.get("guarantor_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("vehicle_number", ""))},
                {"type": "text", "text": str(row.get("amount", ""))},
                {"type": "text", "text": format_whatsapp_date2(row.get("timeline", ""))},
            ],
        ),
        "15": (
            "public_notice",
            "en",
            [
                {"type": "text", "text": str(row.get("branch_name", ""))},
                {"type": "text", "text": str(row.get("employee_name", ""))},
            ],
        ),
        "16": (
            "lok_adalat_notice",
            "te",
            [
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("vehicle_number", ""))},
            ],
        ),
        "17": (
            "disposal",
            "en",
            [
                {"type": "text", "text": str(row.get("customer_name", ""))},
                {"type": "text", "text": str(row.get("amount", ""))},
                {"type": "text", "text": str(row.get("vechile_number", ""))},
            ],
        ),
        "18": (
            "kannada_lok",
            "kn",
            [
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("vehicle_number", ""))},
                {"type": "text", "text": format_whatsapp_date2(row.get("hearing_date", ""))},
            ],
        ),
        "19": (
            "lok_hr",
            "en",
            [
                {"type": "text", "text": str(row.get("emp_name", ""))},
            ],
        ),
        "20": (
            "loss_sale",
            "en",
            [
                {"type": "text", "text": str(row.get("customer_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("vehicle_number", ""))},
                {"type": "text", "text": str(row.get("amount", ""))},
            ],
        ),
        "21": (
            "smf_lok_doc",
            "en",
            [
                {"type": "text", "text": str(row.get("customer_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("vehicle_number", ""))},
                {"type": "text", "text": format_whatsapp_date2(row.get("hearing_date", ""))},
            ],
        ),
        "22": (
            "guarantor_smf_doc_lok",
            "en",
            [
                {"type": "text", "text": str(row.get("guarantor_name", ""))},
                {"type": "text", "text": str(row.get("customer_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("vehicle_number", ""))},
                {"type": "text", "text": format_whatsapp_date2(row.get("hearing_date", ""))},
            ],
        ),
        "23": (
            "customer_psf_lok_doc",
            "en",
            [
                {"type": "text", "text": str(row.get("customer_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("vehicle_number", ""))},
                {"type": "text", "text": format_whatsapp_date2(row.get("hearing_date", ""))},
            ],
        ),
        "24": (
            "psf_guarantor_lok_doc",
            "en",
            [
                {"type": "text", "text": str(row.get("guarantor_name", ""))},
                {"type": "text", "text": str(row.get("customer_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("vehicle_number", ""))},
                {"type": "text", "text": format_whatsapp_date2(row.get("hearing_date", ""))},
            ],
        ),
        "25": (
            "loss_sale_smf",
            "en",
            [
                {"type": "text", "text": str(row.get("customer_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("vehicle_number", ""))},
                {"type": "text", "text": str(row.get("amount", ""))},
            ],
        ),
        "26": (
            "smf_loss_sale_guarantor",
            "en",
            [
                {"type": "text", "text": str(row.get("guarantor_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("vehicle_number", ""))},
                {"type": "text", "text": str(row.get("customer_name", ""))},
                {"type": "text", "text": str(row.get("amount", ""))},
            ],
        ),
        "27": (
            "psf_loss_sale_guarantor",
            "en",
            [
                {"type": "text", "text": str(row.get("guarantor_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("vehicle_number", ""))},
                {"type": "text", "text": str(row.get("customer_name", ""))},
                {"type": "text", "text": str(row.get("amount", ""))},
            ],
        ),
        "28": (
            "emp_lok_psf",
            "en",
            [
                {"type": "text", "text": str(row.get("emp_name", ""))},
                {"type": "text", "text": str(row.get("amount", ""))},
            ],
        ),
        "29": (
            "smf_write_off",
            "en",
            [
                {"type": "text", "text": str(row.get("customer_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("vehicle_number", ""))},
                {"type": "text", "text": str(row.get("amount", ""))},
            ],
        ),
        "30": (
            "write_off_psf",
            "en",
            [
                {"type": "text", "text": str(row.get("customer_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("vehicle_number", ""))},
                {"type": "text", "text": str(row.get("amount", ""))},
            ],
        ),
        "30": (
            "write_off_psf",
            "en",
            [
                {"type": "text", "text": str(row.get("customer_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("vehicle_number", ""))},
                {"type": "text", "text": str(row.get("amount", ""))},
            ],
        ),
        "31": (
            "doc_noc_psf",
            "en",
            [
                {"type": "text", "text": str(row.get("customer_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("vehicle_number", ""))},
            ],
        ),
        "32": (
            "guarantor_psf_registration_notice",
            "en",
            [
                {"type": "text", "text": str(row.get("guarantor_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("customer_name", ""))},
            ],
        ),
        "33": (
            "guarantor_smf_registration_notice",
            "en",
            [
                {"type": "text", "text": str(row.get("guarantor_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("customer_name", ""))},
            ],
        ),
        "34": (
            "psf_registration_borrower_notice",
            "en",
            [
                {"type": "text", "text": str(row.get("customer_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
            ],
        ),
        "35": (
            "smf_registration_borrower_notice_",
            "en",
            [
                {"type": "text", "text": str(row.get("customer_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
            ],
        ),
        "36": (
            "notice_registration_telugu_psf",
            "te",
            [
                {"type": "text", "text": str(row.get("customer_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
            ],
        ),
        "37": (
            "smf_notice_registration_telugu",
            "te",
            [
                {"type": "text", "text": str(row.get("customer_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
            ],
        ),
        "38": (
            "gur_telugu_registration_psf_notice",
            "te",
            [
                {"type": "text", "text": str(row.get("guarantor_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("customer_name", ""))},
            ],
        ),
        "39": (
            "cust_registration_notice_smf",
            "te",
            [
                {"type": "text", "text": str(row.get("guarantor_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("customer_name", ""))},
            ],
        ),
        "40": (
            "gur_psf_writeoff",
            "en",
            [
                {"type": "text", "text": str(row.get("guarantor_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("vehicle_number", ""))},
                {"type": "text", "text": str(row.get("amount", ""))},
            ],
        ),
        "41": (
            "due_notice_borrower_psf",
            "en",
            [
                {"type": "text", "text": str(row.get("customer_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("vehicle_number", ""))},
            
            ],
        ),
         "42": (
            "due_notice_smf_borrower",
            "en",
            [
                {"type": "text", "text": str(row.get("customer_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("vehicle_number", ""))},
            
            ],
        ),
    }

    template_name, lang, parameters = templates.get(choice, templates["8"])
    mobile = format_mobile2(
    row.get("cust_mobile") or row.get("CustMobile") or ""
)

    if not mobile:
        raise ValueError("Mobile number missing")

    # --------------------------------------------------
    # TEMPLATES WITH DOCUMENT HEADER (FIXED - UPLOADS PDF HERE)
    # --------------------------------------------------
    if choice in (
        "13","14","21","22","23","24","30","31","32","33","34","35","36","37","38","39","40","41","42"
    ):
        # ==================================================
        # 📄 SELECT PDF FILE
        # ==================================================
        pdf_filename = None
        folder = "legal_pdfs"

        if choice == "13":
            pdf_filename = row.get("customer_pdf_file")
        elif choice == "14":
            pdf_filename = row.get("guarantor_pdf_file")
        elif choice == "21":
            pdf_filename = row.get("smf_lok_doc_file")
        elif choice == "22":
            pdf_filename = row.get("smf_guarantor_pdf_file")
        elif choice == "23":
            pdf_filename = row.get("psf_customer_pdf_file")
        elif choice == "24":
            pdf_filename = row.get("psf_guarantor_pdf_file")
        elif choice == "30":
            pdf_filename=row.get("writeoff_pdf_file")
        elif choice == "31":
            pdf_filename = row.get("doc_noc_pdf_file")
            folder = "noc_pdfs"
        elif choice in ("32", "33", "38", "39"):
            pdf_filename = row.get("guarantor_pdf_file")
        elif choice in ("34", "35", "36", "37"):
            pdf_filename = row.get("customer_pdf_file")
        elif choice == "40":
            pdf_filename = row.get("writeoff_pdf_file")
        elif choice in ("41", "42"):
            pdf_filename = row.get("due_notice_pdf_file")

        if not pdf_filename:
            raise ValueError(f"PDF filename missing for template {choice}")

        original_filename = Path(pdf_filename).name

        # ==================================================
        # 📤 UPLOAD PDF TO WHATSAPP (CRITICAL FIX)
        # ==================================================
        pdf_bytes = open_legal_pdf2(pdf_filename, folder)
        if not pdf_bytes:
            raise ValueError(f"Empty PDF: {pdf_filename}")

        file_obj = BytesIO(pdf_bytes)
        file_obj.name = original_filename
        file_obj.content_type = "application/pdf"

        upload_result = upload_whatsapp_media2(file_obj)
        media_id = upload_result.get("id")

        print(f"✅ PDF uploaded to WhatsApp with ID: {media_id}, Filename: {original_filename}")

        payload = {
            "messaging_product": "whatsapp",
            "to": mobile,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "policy": "deterministic",
                    "code": lang
                },
                "components": [
                    {
                        "type": "header",
                        "parameters": [
                            {
                                "type": "document",
                                "document": {
                                    "id": media_id,
                                    "filename": original_filename
                                }
                            }
                        ],
                    },
                    {
                        "type": "body",
                        "parameters": parameters,
                    },
                ],
            },
        }

    # --------------------------------------------------
    # NORMAL TEMPLATES (NO HEADER)
    # --------------------------------------------------
    else:
        payload = {
            "messaging_product": "whatsapp",
            "to": mobile,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "policy": "deterministic",
                    "code": lang
                },
                "components": [
                    {
                        "type": "body",
                        "parameters": parameters,
                    }
                ],
            },
        }

    # --------------------------------------------------
    # PREVIEW TEXT (SANITIZED)
    # --------------------------------------------------
    try:
        template_body = get_template_text_from_whatsapp2(template_name)
        rendered_text = sanitize_template_text2(
            render_template_text2(template_body, parameters)
        )
    except Exception:
        rendered_text = template_name

    return payload, rendered_text


def send_second_message_for_mobile2(all_rows, mobile):

    lines = []

    for row in all_rows:
        row_mobile = format_mobile2(
            row.get("cust_mobile") or row.get("CustMobile") or ""
        )

        if row_mobile != mobile:
            continue

        loan_no = str(row.get("Loan Number") or row.get("loan_number") or "").strip()
        cust_name = str(row.get("Customer Name") or row.get("customer_name") or "").strip()
        loan_date = format_whatsapp_date2(
            row.get("Loan Date") or row.get("loan_date")
        )

        if not loan_no and not cust_name:
            continue

        # 🚨 SINGLE LINE FORMAT (NO \n, NO | )
        lines.append(
            f"Loan Number: {loan_no}, "
            f"Customer Name: {cust_name}, "
            f"Loan Date: {loan_date}|"
        )

    if not lines:
        raise ValueError(f"Template 17 empty for {mobile}")

    # 🚨 JOIN INTO ONE SAFE PARAGRAPH
    final_text = " ".join(lines)
    final_text = sanitize_template_text2(final_text)

    payload = {
        "messaging_product": "whatsapp",
        "to": mobile,
        "type": "template",
        "template": {
            "name": "books_pending_second",
            "language": {"code": "en"},
            "components": [{
                "type": "body",
                "parameters": [{"type": "text", "text": final_text}],
            }],
        },
    }

    resp = requests.post(
        f"https://graph.facebook.com/v22.0/{settings.WHATSAPP2_PHONE_NUMBER_ID}/messages",
        headers={
            "Authorization": f"Bearer {settings.WHATSAPP2_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    if not resp.ok:
        raise ValueError(resp.text)

    SmsWhatsAppLog2.objects.create(
        customer_name="",
        mobile=mobile,
        template_name="books_pending_second",
        sent_text_message=final_text,
        status="Sent",
        message_type="Sent",
        content_type="text",
    )


