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

PAYMENT_LINK2 = "https://smsquare.info/"

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

        "46": (
            "pay_now_link",
            "en",
            [
                {
                    "type": "text",
                    "text": str(row.get("customer_name", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("amount", ""))
                },
            ],
        ),

                "47": (
            "rc_noc_dispatched",
            "en",
            [
                {
                    "type": "text",
                    "text": str(row.get("loan_number", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("vehicle_number", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("courier_service", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("tracking_number", ""))
                },
                {
                    "type": "text",
                    "text": format_whatsapp_date2(row.get("dispatch_date", ""))
                },
            ],
        ),
        "48": (
            "hpt_completed",
            "en",
            [
                {
                    "type": "text",
                    "text": str(row.get("loan_number", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("vehicle_number", ""))
                },
            ],
        ),
        "49": (
            "hpt_pending__financier_id_mapping_required",
            "en",
            [
                {
                    "type": "text",
                    "text": str(row.get("loan_number", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("vehicle_number", ""))
                },
            ],
        ),
        "50": (
            "rcnoc_returned__address_confirmation_required",
            "en",
            [
                {
                    "type": "text",
                    "text": str(row.get("loan_number", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("vehicle_number", ""))
                },
            ],
        ),

        "51": (
            "smsquare_info",
            "en",
            [
                {
                    "type": "text",
                    "text": str(row.get("customer_name", ""))
                },

            ],
        ),
        "52": (
            "bucket_one_psf",
            "en",
            [
                {
                    "type": "text",
                    "text": str(row.get("customer_name", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("due_amount", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("loan_number", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("vehicle_number", ""))
                },
            ],
        ),
        "53": (
            "smf_bucket_one",
            "en",
            [
                {
                    "type": "text",
                    "text": str(row.get("customer_name", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("due_amount", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("loan_number", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("vehicle_number", ""))
                },
            ],
        ),
        "54": (
            "bucket_two_psf",
            "en",
            [
                {
                    "type": "text",
                    "text": str(row.get("customer_name", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("due_amount", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("loan_number", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("vehicle_number", ""))
                },
            ],
        ),
        "55": (
            "smf_bucket_two",
            "en",
            [
                {
                    "type": "text",
                    "text": str(row.get("customer_name", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("due_amount", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("loan_number", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("vehicle_number", ""))
                },
            ],
        ),

        "56": (
            "psf_cust_three_bucket",
            "en",
            [
                {
                    "type": "text",
                    "text": str(row.get("customer_name", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("due_amount", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("loan_number", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("vehicle_number", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("legal_number", ""))
                }
            ],
        ),
        "57": (
            "smf_cust_three_bucket",
            "en",
            [
                {
                    "type": "text",
                    "text": str(row.get("customer_name", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("due_amount", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("loan_number", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("vehicle_number", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("legal_number", ""))
                }
            ],
        ),
        "58": (
            "gur_psf_three_bucket",
            "en",
            [ 
                {
                    "type": "text",
                    "text": str(row.get("guarantor_name", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("customer_name", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("mobile_number", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("loan_number", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("vehicle_number", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("due_amount", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("legal_number", ""))
                }
            ],
        ),
        "59": (
            "smf_gur_three_bucket",
            "en",
            [ 
                {
                    "type": "text",
                    "text": str(row.get("guarantor_name", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("customer_name", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("mobile_number", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("loan_number", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("vehicle_number", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("due_amount", ""))
                },
                {
                    "type": "text",
                    "text": str(row.get("legal_number", ""))
                }
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
        "13","14","21","22","23","24","30","31","32","33","34","35","36","37","38","39","40","41","42","44","45","49"
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
        elif choice == "49":
            pdf_filename = row.get("hpt_pending_pdf")
            folder = "noc_pdfs"

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
    # PAY NOW LINK TEMPLATE (46)
    # --------------------------------------------------

    elif choice == "46":

        payment_link = str(row.get("payment_link", "")).strip()

        if not payment_link:
            raise ValueError("payment_link column missing in Excel")

        # Example:
        # https://alcd.in/ABC123
        # becomes:
        # ABC123
        short_code = payment_link.rstrip("/").split("/")[-1]

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
                        "parameters": parameters
                    },
                    {
                        "type": "button",
                        "sub_type": "url",
                        "index": "0",
                        "parameters": [
                            {
                                "type": "text",
                                "text": short_code
                            }
                        ]
                    }
                ]
            }
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
        'lcc_api': {
            'auth_token': "amx 4d53bce03ec34c0a911182d4c228ee6c:CYDfFMxLo52bbKrD68MknG8zyFNozrYVBIGi6Htle00=:7db2c6c008f647178e60039de9e52835:13689192:e52a26ed-9f27-11e8-8cbc-025baaa4258e",
            'base_url': "https://prod-api-padmasai.allcloud.app/api",
           'endpoint':'/voicecall/GetLccDetailsByAgreementNo'
        },
         'loan_api': {
            'base_url': 'https://prod-apiv2-padmasai.allcloud.app/api',
            'endpoint': '/loan/GetLoanAgreementNoAsync',
            'auth_token': 'amx 4d53bce03ec34c0a911182d4c228ee6c:CYDfFMxLo52bbKrD68MknG8zyFNozrYVBIGi6Htle00=:7db2c6c008f647178e60039de9e52835:13689192:e52a26ed-9f27-11e8-8cbc-025baaa4258e',
        },
        'qr_api': {
            'base_url': 'https://smsquare.info/api',
            'endpoint': '/payment-link',
            'api_key': 'uSZPjPUREaJMt8D3dtdz8jq23lFDDT3VLdTD-KvuNXerCK4c1cAkc6qlY1rnvliE',
            "financier_name":"padmasai"
        },
      

        'whatsapp': {
            'phone_number_id': settings.WHATSAPP2_PHONE_NUMBER_ID,
            'access_token': settings.WHATSAPP2_ACCESS_TOKEN,
            'api_version': "v22.0",
        },
        'template_name': 'pay_link',
    },
    'sms': {   # or whatever app_key you use, e.g. 'psf'
        'app_name': 'SM SQUARE CREDIT SERVICES PRIVATE LIMITED',
        # ----- LCC API (to fetch loan details) -----
        'lcc_api': {
            'base_url': 'https://prod-api-smsquare.allcloud.app/api',
            'endpoint': '/VoiceCall/GetLccDetailsByAgreementNo',
            'auth_token': 'amx 4d53bce03ec34c0a911182d4c228ee6c:C1PYBd0XQEW0/sv664yh6+DrKLBtpz9hnKZzUyR6kBI=:8a960f62bdf649778f474a5071a03791:13684346:38cbfcbd-c82e-48fe-ac81-090295f8bdeb',
        },
        'loan_api': {
            'base_url': 'https://prod-apiv2-smsquare.allcloud.app/api',
            'endpoint': '/loan/GetLoanAgreementNoAsync',
            'auth_token': 'amx 4d53bce03ec34c0a911182d4c228ee6c:C1PYBd0XQEW0/sv664yh6+DrKLBtpz9hnKZzUyR6kBI=:8a960f62bdf649778f474a5071a03791:13684346:38cbfcbd-c82e-48fe-ac81-090295f8bdeb',
        },
        # ----- QR Code API (to generate payment link) -----

        'qr_api': {
            'base_url': 'https://smsquare.info/api',
            'endpoint': '/payment-link',
            'api_key': 'uSZPjPUREaJMt8D3dtdz8jq23lFDDT3VLdTD-KvuNXerCK4c1cAkc6qlY1rnvliE',
            "financier_name":"smsquare"
        },

        # ----- WhatsApp config (unchanged) -----
        'whatsapp': {
            'phone_number_id': settings.WHATSAPP_PHONE_NUMBER_ID,
            'access_token': settings.WHATSAPP_ACCESS_TOKEN,
            'api_version': 'v22.0',
        },
        'template_name': 'pay_link',
    },

    # 'spl': {
    #     'app_name': 'Padma Sai Holdings Private Limited',
    #     'smsquare': {
    #         'auth_token': "amx 4d53bce03ec34c0a911182d4c228ee6c:6S2KpETjIY/f8EIwql/xMh3s9ks9lWOUvQexCQEcEAs=:rdICQaUzp091Y1DTEFAw5o4Qjo8wxB4u:19301462:38cbfcbd-c82e-48fe-ac81-090295f8bdeb",
    #         'base_url': "https://uat-apiv2-smsquare.allcloud.app/api",
    #         'get_loan_by_mobile': "/loan/GetLoanByMobileNumber",
    #         'get_repayment': "/Repayment/GetRepaymentForLoanByLoanId",
    #         'get_qr': "/paymentgateway/GetQRCode",
    #     },
    #     'whatsapp': {
    #         'phone_number_id': "your_spl_phone_id",
    #         'access_token': "your_spl_access_token",
    #         'api_version': "v18.0",
    #     },
    #     'template_name': 'payment_gateway',
    # },
}



import logging
import requests
import json

logger = logging.getLogger(__name__)

def call_allcloud_api(app_key, api_type, method='POST', params=None, payload=None):
    """
    Generic AllCloud API caller.
    api_type: 'lcc_api', 'loan_api', 'qr_api'
    """
    config = get_payment_config(app_key)
    api_config = config.get(api_type)
    if not api_config:
        raise ValueError(f"API type '{api_type}' not configured for app key '{app_key}'")

    url = api_config['base_url'] + api_config['endpoint']
    headers = {
        "Authorization": api_config['auth_token'],
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    try:
        if method.upper() == 'GET':
            resp = requests.get(url, params=params, headers=headers, timeout=10)
        else:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        # Some APIs return double-encoded JSON
        data = resp.json()
        if isinstance(data, str):
            data = json.loads(data)
        return data
    except requests.exceptions.RequestException as e:
        logger.error(f"AllCloud API error for {app_key}/{api_type}: {e}")
        raise

# messaging2/utils.py

import logging
import requests

logger = logging.getLogger(__name__)

def get_payment_config(app_key):
    config = PAYMENT_CONFIG.get(app_key)
    if not config:
        raise ValueError(f"Invalid app key: {app_key}")
    return config

from financehub.models import Lcc   # adjust import to your actual model

def get_agreement_no_from_mobile(mobile):
    mobile_clean = ''.join(filter(str.isdigit, mobile))
    if len(mobile_clean) > 10:
        mobile_clean = mobile_clean[-10:]

    # Try exact match
    lccs = Lcc.objects.filter(cust_mobile=mobile_clean)
    if lccs.exists():
        # If multiple, pick the first (maybe order by loan_date descending?)
        return lccs.first().loan_number

    # Fallback: endswith (for numbers with country code)
    lccs = Lcc.objects.filter(cust_mobile__endswith=mobile_clean)
    if lccs.exists():
        return lccs.first().loan_number

    raise ValueError("No loan found for this mobile number")

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

import logging
logger = logging.getLogger(__name__)

import json

from django.conf import settings

# The cap value (product decision)
LATE_CHARGES_CAP = 50000.0

# ------------------------------------------------------------------
# Optional: Manual EMI override for specific agreements
# If the system data is wrong, you can force a specific EMI here.
# ------------------------------------------------------------------
EMI_OVERRIDE = {
    # 'L2WNAPANP-250410598': 4990.00,   # Uncomment if needed
    # 'L3WNTSNLA-230303625': 8060.00,
}

# The cap for late charges (product decision)
LATE_CHARGES_CAP = 50000.0

def get_payment_details(app_key, mobile):
    """
    Fetch loan details from AllCloud and apply business rules:
    - Late charges capped at ₹50,000
    - Total due = overdue + capped_lpi + vas
    - Minimum EMI = 1.5*EMI if due_count<3 else 2*EMI, capped at total due
    - Max part payment = 2 * loan amount

    EMI is extracted from the Repayment Schedules:
        1. Manual override (dictionary)
        2. First PAID installment after the 1st (regular EMI)
        3. Any PAID installment (fallback)
        4. First PENDING installment (fallback)
        5. LCC CurrentMonthTBC (if available)
        6. Loan API top-level EMI (last resort)
    """
    agreement_no = get_agreement_no_from_mobile(mobile)

    # 1. LCC API (Current Dues – for overdue, LPI, VAS, due count)
    lcc_payload = {"AgreementNo": agreement_no, "FinanceId": 0}
    lcc_data = call_allcloud_api(app_key, 'lcc_api', payload=lcc_payload)

    # 2. Loan API (Loan Amount & Repayment Schedules)
    loan_params = {"strAgreementNo": agreement_no}
    loan_data = call_allcloud_api(app_key, 'loan_api', method='GET', params=loan_params)

    # 3. Extract LCC values (these are the most accurate for current dues)
    overdue = float(lcc_data.get('TotalDues', 0.0) or 0.0)
    lpi = float(lcc_data.get('LPCDue', 0.0) or 0.0)
    vas = float(lcc_data.get('VasDueAmount', 0.0) or 0.0)
    emi_due_count = float(lcc_data.get('EMIDueCount', 0.0) or 0.0)

    # 4. 🔥 Determine the Regular EMI (Priority order)
    emi = 0.0
    repayment_schedules = loan_data.get('RepaymentSchedules', [])

    # Option 0: Manual override (if defined for this agreement)
    emi = EMI_OVERRIDE.get(agreement_no, 0.0)

    # Option 1: First PAID installment, but skip the 1st one (which may be inflated)
    if emi <= 0:
        for schedule in sorted(repayment_schedules, key=lambda x: x.get('InstallmentNo', 0)):
            inst_no = schedule.get('InstallmentNo', 0)
            if inst_no <= 1:   # Skip 1st installment (and any non-positive)
                continue
            if schedule.get('PaymentStatus', '').upper() == 'PAID':
                emi = float(schedule.get('DueAmount', 0.0) or 0.0)
                break

    # Option 2: If still not found, take any PAID installment (including 1st)
    if emi <= 0:
        for schedule in sorted(repayment_schedules, key=lambda x: x.get('InstallmentNo', 0)):
            if schedule.get('PaymentStatus', '').upper() == 'PAID':
                emi = float(schedule.get('DueAmount', 0.0) or 0.0)
                break

    # Option 3: If no PAID found, take the first PENDING installment (fallback)
    if emi <= 0:
        for schedule in sorted(repayment_schedules, key=lambda x: x.get('InstallmentNo', 0)):
            payment_status = schedule.get('PaymentStatus', '').upper()
            pending_amount = float(schedule.get('PendingAmount', 0.0) or 0.0)
            if payment_status != 'PAID' and pending_amount > 0:
                emi = float(schedule.get('DueAmount', 0.0) or 0.0)
                break

    # Option 4: LCC CurrentMonthTBC (if available)
    if emi <= 0:
        emi = float(lcc_data.get('CurrentMonthTBC', 0.0) or 0.0)

    # Option 5: Loan API top-level EMI (last resort)
    if emi <= 0:
        emi = float(loan_data.get('EMI', 0.0) or 0.0)

    # If still zero, raise an error (shouldn't happen)
    if emi <= 0:
        raise ValueError(f"Could not determine regular EMI for agreement {agreement_no}")

    # 5. Loan Amount (for Max Part Payment)
    loan_amount = float(loan_data.get('TotalAmount', 0.0) or 0.0)

    # 6. Business Rules
    capped_lpi = min(lpi, LATE_CHARGES_CAP)   # Cap LPI at ₹50,000
    total_due = overdue + capped_lpi + vas    # Display Total Due

    # Minimum EMI (Tiered Logic)
    if emi_due_count < 3:
        floor = min(1.5 * emi, total_due)      # 1.5x EMI, but never exceed Total Due
    else:
        floor = 2 * emi                        # 2x EMI when 3+ EMIs overdue

    global_min = getattr(settings, 'MIN_PART_PAYMENT', 100.0)
    min_emi = max(floor, global_min)

    max_part = round(2 * loan_amount, 2)

    # 7. Return all necessary fields
    return {
        'customer_name': lcc_data.get('CustomerName', ''),
        'loan_number': agreement_no,
        'vehicle_no': lcc_data.get('RegistrationNo', ''),
        'finance_id': lcc_data.get('FinanceId', 0),
        'due_amount': overdue,
        'lpi_due': lpi,
        'vas_due': vas,
        'total_due': total_due,           # Capped total due
        'min_emi_amount': min_emi,        # Minimum EMI for payment
        'max_part_amount': max_part,      # Max part payment
        'collection_charges': 0.0,        # Not available from these APIs
        'emi_due_count': emi_due_count,   # For display/debug
        'regular_emi': emi,               # The EMI used for calculation
    }



def generate_payment_link(app_key, mobile, amount):
    config = get_payment_config(app_key)
    details = get_payment_details(app_key, mobile)
    finance_id = details['finance_id']

    qr_api = config['qr_api']
    url = qr_api['base_url'] + qr_api['endpoint']
    headers = {
        "x-api-key": qr_api['api_key'],
        "Content-Type": "application/json"
    }
    payload = {
        "finance_id": finance_id,
        "amount": float(amount),
        "financier_name": qr_api.get('financier_name', 'padmasai')   # ✅ dynamic
    }

    # 🔍 LOG THE REQUEST
    # logger.info(f"🔗 Payment Link Request URL: {url}")
    # logger.info(f"📦 Payment Link Payload: {payload}")

    response = requests.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()

    # 🔍 LOG THE FULL RESPONSE
    logger.info(f"✅ Payment Link Response: {json.dumps(data, indent=2)}")

    payment_url = data.get('link')
    payment_token = data.get('token')
    if not payment_url or not payment_token:
        raise ValueError("Payment link or token not generated")

    return payment_url, payment_token

def send_whatsapp_payment_template(app_key, to, customer_name, amount, short_code):
    """
    Send WhatsApp template with a payment link button.
    - short_code: the token from the payment link (e.g., '83bc07ad...')
    """
    config = get_payment_config(app_key)
    wa_config = config['whatsapp']
    template_name = config.get("template_name", "pay_link")

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
                        {"type": "text", "text": customer_name},
                        {"type": "text", "text": str(amount)}
                    ]
                },
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [
                        {"type": "text", "text": short_code}   # ✅ token directly
                    ]
                }
            ]
        }
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        logger.info(f"WhatsApp template sent to {to}")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"WhatsApp request failed: {e}")
        if e.response:
            logger.error(e.response.text)
        raise







API_CHECK_TEMPLATES = [
    "1", "2", "3", "5", "6", "7", "11", "19", "20", "35", "37", "44", "45", "46", "47"
]

def needs_api_check(template_id):
    """Check if template needs API check (PAID/UNPAID)"""
    return str(template_id) in API_CHECK_TEMPLATES


def check_smsquare_payment_status(mobile, agreement_no=None):
    """
    Check if Padma Sai (messaging2) customer has PAID or UNPAID
    
    API: https://prod-api-padmasai.allcloud.app/api/voicecall/GetLccDetailsByAgreementNo
    Auth: amx 4d53bce03ec34c0a911182d4c228ee6c:CYDfFMxLo52bbKrD68MknG8zyFNozrYVBIGi6Htle00=:7db2c6c008f647178e60039de9e52835:13689192:e52a26ed-9f27-11e8-8cbc-025baaa4258e
    
    Returns: {'is_paid': True/False, 'total_due': amount}
    """
    import json
    import requests
    from financehub.models import Lcc
    
    try:
        # Step 1: Get agreement number if not provided
        if not agreement_no:
            mobile_clean = ''.join(filter(str.isdigit, mobile))
            if len(mobile_clean) > 10:
                mobile_clean = mobile_clean[-10:]
            
            # Try to find in Lcc table
            lcc_record = Lcc.objects.filter(cust_mobile=mobile_clean).first()
            if not lcc_record:
                lcc_record = Lcc.objects.filter(guarantor_mobile=mobile_clean).first()
            
            if not lcc_record:
                # No loan found → Treat as PAID (skip)
                return {
                    'is_paid': True,
                    'total_due': 0,
                    'status': 'no_loan'
                }
            
            agreement_no = lcc_record.loan_number
        
        # Step 2: Call Padma Sai LCC API (messaging2)
        SMSQUARE_LCC_URL = "https://prod-api-padmasai.allcloud.app/api/voicecall/GetLccDetailsByAgreementNo"
        SMSQUARE_LCC_AUTH = "amx 4d53bce03ec34c0a911182d4c228ee6c:CYDfFMxLo52bbKrD68MknG8zyFNozrYVBIGi6Htle00=:7db2c6c008f647178e60039de9e52835:13689192:e52a26ed-9f27-11e8-8cbc-025baaa4258e"
        
        headers = {
            "Authorization": SMSQUARE_LCC_AUTH,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        payload = {
            "AgreementNo": agreement_no,
            "FinanceId": 0
        }
        
        response = requests.post(SMSQUARE_LCC_URL, headers=headers, json=payload, timeout=30)
        
        # Step 3: Check response status
        if response.status_code != 200:
            return {
                'is_paid': False,
                'total_due': 0,
                'status': 'api_error',
                'error': f"HTTP {response.status_code}"
            }
        
        # Step 4: Parse JSON
        try:
            data = response.json()
        except json.JSONDecodeError:
            return {
                'is_paid': False,
                'total_due': 0,
                'status': 'api_error',
                'error': 'Invalid JSON response'
            }
        
        # Step 5: If response is a string, parse again
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                return {
                    'is_paid': False,
                    'total_due': 0,
                    'status': 'api_error',
                    'error': 'String response not JSON'
                }
        
        # Step 6: Calculate total arrears from response
        # Response fields: TotalDues, LPCDue, VasDueAmount
        total_dues = float(data.get('TotalDues', 0))
        lpc_due = float(data.get('LPCDue', 0))
        vas_due = float(data.get('VasDueAmount', 0))
        total_arrears = total_dues + lpc_due + vas_due
        
        # Example response:
        # {
        #   "TotalDues": 10110.00,
        #   "LPCDue": 80.0,
        #   "VasDueAmount": 0.0,
        #   "CustomerName": "DEPILLI GOVINDA",
        #   ...
        # }
        
        return {
            'is_paid': total_arrears == 0,  # 0 = PAID, >0 = UNPAID
            'total_due': total_arrears,
            'customer_name': data.get('CustomerName', ''),
            'loan_number': agreement_no,
            'finance_id': data.get('FinanceId', 0),
            'registration_no': data.get('RegistrationNo', ''),
            'vehicle_class': data.get('VehicleClass', ''),
            'region': data.get('Region', ''),
            'branch': data.get('Branch', ''),
            'status': 'success'
        }
        
    except requests.exceptions.RequestException as e:
        # API error → Assume UNPAID (send reminder)
        return {
            'is_paid': False,
            'total_due': 0,
            'status': 'api_error',
            'error': str(e)
        }
    except Exception as e:
        # Any other error → Assume UNPAID (send reminder)
        return {
            'is_paid': False,
            'total_due': 0,
            'status': 'api_error',
            'error': str(e)
        }
