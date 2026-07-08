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
    Upload media to WhatsApp Cloud API - WebM direct (NO ffmpeg)
    """
    import mimetypes
    import requests

    access_token = settings.WHATSAPP2_ACCESS_TOKEN
    phone_number_id = settings.WHATSAPP2_PHONE_NUMBER_ID

    url = f"https://graph.facebook.com/v22.0/{phone_number_id}/media"

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    # Handle bytes input
    if isinstance(file_obj, bytes):
        from io import BytesIO
        temp = BytesIO(file_obj)
        temp.name = "document.pdf"
        file_obj = temp

    if hasattr(file_obj, "seek"):
        file_obj.seek(0)

    if hasattr(file_obj, "name"):
        filename = file_obj.name
    else:
        filename = "media"

    content_type = getattr(file_obj, "content_type", None)
    if not content_type:
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    # ✅ NO CONVERSION - Upload WebM directly
    print(f"📤 Uploading: {filename} ({content_type})")

    if hasattr(file_obj, "seek"):
        file_obj.seek(0)

    content = file_obj.read() if hasattr(file_obj, "read") else file_obj

    files = {
        "file": (
            filename,
            content,
            content_type,
        )
    }

    data = {
        "messaging_product": "whatsapp"
    }

    try:
        resp = requests.post(
            url,
            headers=headers,
            files=files,
            data=data,
            timeout=60
        )

        print(f"Upload Status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"Upload Error: {resp.text}")

        resp.raise_for_status()
        result = resp.json()
        print(f"✅ Media uploaded successfully. ID: {result.get('id')}")
        return result

    except Exception as e:
        print(f"❌ Media upload error: {e}")
        if 'resp' in locals():
            print(f"Response: {resp.text}")
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




# ---------------------------
# Template fetch & render
# ---------------------------
def get_template_text_from_whatsapp2(template_name: str) -> str:
    """
    Fetch BODY text of a WhatsApp template (for DB preview).
    """
    try:
        url = (
            f"https://graph.facebook.com/v22.0/"
            f"{settings.WHATSAPP2_BUSINESS_ACCOUNT_ID}/message_templates"
            f"?name={template_name}"
        )
        headers = {"Authorization": f"Bearer {settings.WHATSAPP2_ACCESS_TOKEN}"}
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json()

        if "data" in data and data["data"]:
            for comp in data["data"][0].get("components", []):
                if comp.get("type") == "BODY":
                    return comp.get("text", "")

        return "Template body not found."
    except Exception as e:
        return f"[Template fetch error: {e}]"




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
    
          
         "43": (
                "new_loans_te",
                "te",
                [    {"type": "text", "text": str(row.get("customer_name", ""))},       # {{1}}
            
                ],
            ),
          
         
        "44": (
                "presale_notices_borrower_psf",
                "en",
                [    {"type": "text", "text": str(row.get("customer_name", ""))},
                     {"type": "text", "text": str(row.get("vehicle_number", ""))},
                     {"type": "text", "text": str(row.get("loan_number", ""))},             
                ],
                ),
        "45": (
                "presale_notices_borrower_smf",
                "en",
                [    {"type": "text", "text": str(row.get("customer_name", ""))},
                     {"type": "text", "text": str(row.get("vehicle_number", ""))},
                     {"type": "text", "text": str(row.get("loan_number", ""))},             
   

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
        "13","14","21","22","23","24","30","31","32","33","34","35","36","37","38","39","40","41","42","44","45"
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
        elif choice == "44":
            pdf_filename = row.get("presale_notices_borrower_pdf")
        elif choice == "45":
            pdf_filename = row.get("presale_notices_borrower_pdf")

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



# ================================== Payment auto generate======================================================
# ========== PAYMENT GATEWAY CONFIGURATION ==========
# ========== PAYMENT CONFIGURATION ==========
PAYMENT_CONFIG = {
    'psf': {
        'app_name': 'Padma Sai Holdings Private Limited',
        'smsquare': {
            'auth_token': "amx 4d53bce03ec34c0a911182d4c228ee6c:C1PYBd0XQEW0/sv664yh6+DrKLBtpz9hnKZzUyR6kBI=:8a960f62bdf649778f474a5071a03791:13684346:38cbfcbd-c82e-48fe-ac81-090295f8bdeb",
            'base_url': "https://uat-apiv2-smsquare.allcloud.app/api",
            'get_loan_by_mobile': "/loan/GetLoanByMobileNumber",
            'get_repayment': "/Repayment/GetRepaymentForLoanByLoanId",
            'get_qr': "/paymentgateway/GetQRCode",
        },
        'whatsapp': {
            'phone_number_id': settings.WHATSAPP2_PHONE_NUMBER_ID,
            'access_token': settings.WHATSAPP2_ACCESS_TOKEN,
            'api_version': "v22.0",
        },
        'template_name': 'payment_gateway',
    },
    'sms': {
        'app_name': 'SM SQUARE CREDIT SERVICES PRIVATE LIMITED',
        'smsquare': {
            'auth_token': "amx 4d53bce03ec34c0a911182d4c228ee6c:H9LLQ6iq811dT/DTrCsi6JX+jrazDif0hOmd8ZbDGZA=:mvBBtj6rsxIljCJglNpFOFFDW7Tjg8dj:19302908:38cbfcbd-c82e-48fe-ac81-090295f8bdeb",
            'base_url': "https://uat-apiv2-smsquare.allcloud.app/api",
            'get_loan_by_mobile': "/loan/GetLoanByMobileNumber",
            'get_repayment': "/Repayment/GetRepaymentForLoanByLoanId",
            'get_qr': "/paymentgateway/GetQRCode",
        },
        'whatsapp': {
            'phone_number_id': settings.WHATSAPP_PHONE_NUMBER_ID,
            'access_token': settings.WHATSAPP_ACCESS_TOKEN,
            'api_version': "v22.0",
        },
        'template_name': 'payment_gateway',
    },
    'spl': {
        'app_name': 'Padma Sai Holdings Private Limited',
        'smsquare': {
            'auth_token': "amx 4d53bce03ec34c0a911182d4c228ee6c:6S2KpETjIY/f8EIwql/xMh3s9ks9lWOUvQexCQEcEAs=:rdICQaUzp091Y1DTEFAw5o4Qjo8wxB4u:19301462:38cbfcbd-c82e-48fe-ac81-090295f8bdeb",
            'base_url': "https://uat-apiv2-smsquare.allcloud.app/api",
            'get_loan_by_mobile': "/loan/GetLoanByMobileNumber",
            'get_repayment': "/Repayment/GetRepaymentForLoanByLoanId",
            'get_qr': "/paymentgateway/GetQRCode",
        },
        'whatsapp': {
            'phone_number_id': "your_spl_phone_id",
            'access_token': "your_spl_access_token",
            'api_version': "v18.0",
        },
        'template_name': 'payment_gateway',
    },
}

# messaging2/utils.py

import logging
import requests

logger = logging.getLogger(__name__)

def get_payment_config(app_key):
    config = PAYMENT_CONFIG.get(app_key)
    if not config:
        raise ValueError(f"Invalid app key: {app_key}")
    return config

def call_smsquare_api(app_key, endpoint, method='GET', params=None, payload=None):
    config = get_payment_config(app_key)
    sms_config = config['smsquare']
    url = sms_config['base_url'] + endpoint
    headers = {
        "Authorization": sms_config['auth_token'],
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    try:
        if method.upper() == 'GET':
            response = requests.get(url, params=params, headers=headers, timeout=10)
        elif method.upper() == 'POST':
            response = requests.post(url, json=payload, headers=headers, timeout=10)
        else:
            raise ValueError("Unsupported method")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"SMSquare API error for {app_key}: {e}")
        raise

def get_payment_details(app_key, mobile):
    config = get_payment_config(app_key)
    sms_config = config['smsquare']

    # 1. Get loans
    params = {"ContactNumber": mobile}
    loans_data = call_smsquare_api(app_key, sms_config['get_loan_by_mobile'], method='GET', params=params)
    if not loans_data:
        raise ValueError("No loans found for this mobile")

    first_loan = loans_data[0]
    finance_id = first_loan.get('FinanceId')
    agreement_no = first_loan.get('AgreementNo')
    customer_name = first_loan.get('BorrowerName', 'Customer')
    if not finance_id:
        raise ValueError("FinanceId not found")

    # 2. Get repayment details
    repayment_params = {"FinanceId": finance_id}
    repayment_data = call_smsquare_api(app_key, sms_config['get_repayment'], method='GET', params=repayment_params)

    balance_amount = float(repayment_data.get('BalanceAmount', 0.0) or 0.0)
    lpi_due = float(repayment_data.get('LPIDue', 0.0) or 0.0)
    vas_due = float(repayment_data.get('VasDue', 0.0) or 0.0)
    collection_charges = float(repayment_data.get('CollectionCharges', 0.0) or 0.0)

    return {
        'customer_name': customer_name,
        'loan_number': agreement_no,
        'vehicle_no': first_loan.get('VehicleNo', ''),
        'due_amount': balance_amount,
        'finance_id': finance_id,
        'lpi_due': lpi_due,
        'vas_due': vas_due,
        'collection_charges': collection_charges,
    }

def generate_payment_link(app_key, mobile, amount):
    config = get_payment_config(app_key)
    sms_config = config['smsquare']

    details = get_payment_details(app_key, mobile)
    finance_id = details['finance_id']
    lpi_due = details['lpi_due']
    vas_due = details['vas_due']
    collection_charges = details['collection_charges']

    due_amount = float(amount)
    total_amount = due_amount + collection_charges + lpi_due + vas_due

    qr_payload = {
        "FinanceId": finance_id,
        "DueAmount": due_amount,
        "CollectionCharges": collection_charges,
        "LPIAmount": lpi_due,
        "ShowQR": True,
        "SMSLink": False,
        "HandLoan": 0,
        "VasDue": vas_due,
        "IsAdvanceReceipt": "true",
        "CollectionType": 5,
        "TotalAmount": total_amount
    }
    qr_response = call_smsquare_api(app_key, sms_config['get_qr'], method='POST', payload=qr_payload)
    payment_url = qr_response.get('URL')
    if not payment_url:
        raise ValueError("Payment URL not generated")
    return payment_url

def send_whatsapp_payment_template(app_key, to, amount, payment_url):
    config = get_payment_config(app_key)
    wa_config = config['whatsapp']
    logger.info(f"📞 Sending payment template for {app_key}")
    logger.info(f"📱 Phone ID: {wa_config['phone_number_id']}")
    logger.info(f"🔑 Token (first 20 chars): {wa_config['access_token'][:20]}...")
    logger.info(f"Using token: {wa_config['access_token'][:20]}...")
    wa_config = config['whatsapp']
    print(wa_config,"88888")
    template_name = config.get('template_name', 'payment_gateway')

    url = f"https://graph.facebook.com/{wa_config['api_version']}/{wa_config['phone_number_id']}/messages"
    headers = {
        "Authorization": f"Bearer {wa_config['access_token']}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "en"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": payment_url},
                        {"type": "text", "text": str(amount)}
                    ]
                }
            ]
        }
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code != 200:
            logger.error(f"WhatsApp API error: {response.status_code} - {response.text}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"WhatsApp request failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(e.response.text)  # 👈 this will show the detailed error
        raise
