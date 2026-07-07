# messaging2/utils.py
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

PAYMENT_LINK = "https://smsquare.co.in/pay2"
from financehub.models import Lcc

def lcc_details(mobile):
    """
    Fetch customer details from LCC table using mobile number.
    Returns dict with customer_name, loan_number, vehicle_no or None if not found.
    """
    if not mobile:
        return None

    # Normalize: remove '+', spaces, etc.
    clean = mobile.lstrip('+').strip()

    # Try both with and without country code '91'
    possible_numbers = [clean]
    if clean.startswith('91'):
        possible_numbers.append(clean[2:])
    else:
        possible_numbers.append('91' + clean)

    for num in possible_numbers:
        record = Lcc.objects.filter(cust_mobile=num).first()
        if record:
            return {
                'customer_name': record.customer_name or '',
                'loan_number': record.loan_number or '',
                'vehicle_no': record.vehicle_no or '',
            }
    return None
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



def upload_whatsapp_media(file_obj):
    """
    Upload media to WhatsApp Cloud API - WebM direct (NO ffmpeg)
    """
    import mimetypes
    import requests

    access_token = settings.WHATSAPP_ACCESS_TOKEN
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID

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
def send_whatsapp_media(to_number, media_id, media_type, caption="", filename=None):
    """
    Send media message using WhatsApp Cloud API
    media_type: image, video, audio, document
    """
    url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
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

def send_whatsapp_text(to_number, text_body):
    """Send text message via WhatsApp API"""
    url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
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


def sanitize_template_text(text: str) -> str:
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


def split_text_into_chunks(text: str, max_len: int = 1000) -> list[str]:
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
def format_mobile(x: str) -> str:
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
def format_whatsapp_date(value) -> str:
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
def open_legal_pdf(filename, folder):
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
def check_whatsapp_number(mobile: str) -> Dict[str, Any]:
    try:
        url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
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
            
            # Map each error code to specific status (matching tasks.py ERROR_MAP)
            if icode == 131047:
                return {"valid": False, "blocked": False, "reason": "24H_WINDOW_EXPIRED - Template window expired"}
            elif icode == 131026:
                return {"valid": False, "blocked": False, "reason": "NOT_ON_WHATSAPP - Number not on WhatsApp"}
            elif icode == 131051:
                return {"valid": False, "blocked": False, "reason": "UNSUPPORTED_MESSAGE_TYPE"}
            elif icode == 131011:
                return {"valid": False, "blocked": True, "reason": "BLOCKED_BY_USER - User blocked business"}
            elif icode == 130403:
                return {"valid": False, "blocked": True, "reason": "BLOCKED_BY_BUSINESS - Business blocked user"}
            elif icode == 131050:
                return {"valid": False, "blocked": True, "reason": "OPTED_OUT - User opted out"}
            elif icode == 190:
                return {"valid": False, "blocked": False, "reason": "TOKEN_ERROR - Invalid access token"}
            elif icode == 131009:
                return {"valid": False, "blocked": False, "reason": "INVALID_PARAMETER"}
            elif icode == 131000:
                return {"valid": False, "blocked": False, "reason": "UNKNOWN_ERROR"}
            elif icode == 131045:
                return {"valid": False, "blocked": False, "reason": "REGISTRATION_ERROR"}
            elif icode == 132000:
                return {"valid": False, "blocked": False, "reason": "TEMPLATE_PARAM_ERROR"}
            elif icode == 132001:
                return {"valid": False, "blocked": False, "reason": "TEMPLATE_NOT_FOUND"}
            elif icode == 132015:
                return {"valid": False, "blocked": False, "reason": "TEMPLATE_PAUSED"}
            elif icode == 132016:
                return {"valid": False, "blocked": False, "reason": "TEMPLATE_DISABLED"}
            elif icode == 130429:
                return {"valid": False, "blocked": False, "reason": "RATE_LIMIT - Too many requests"}
            elif icode == 131056:
                return {"valid": False, "blocked": False, "reason": "TOO_MANY_MESSAGES"}
            elif icode in [10, 200]:
                return {"valid": False, "blocked": False, "reason": "AUTH_FAILED"}
            else:
                return {"valid": False, "blocked": False, "reason": f"Failed_{icode}: {msg}"}

        return {"valid": True, "blocked": False, "reason": "Unknown (assumed valid)"}
    except Exception as e:
        return {"valid": True, "blocked": False, "reason": f"Validation error (assume valid): {e}"}

# ---------------------------
# Template fetch & render
# ---------------------------
def get_template_text_from_whatsapp(template_name: str) -> str:
    """
    Fetch BODY text of a WhatsApp template (for DB preview).
    """
    try:
        url = (
            f"https://graph.facebook.com/v22.0/"
            f"{settings.WHATSAPP_BUSINESS_ACCOUNT_ID}/message_templates"
            f"?name={template_name}"
        )
        headers = {"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"}
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json()

        if "data" in data and data["data"]:
            for comp in data["data"][0].get("components", []):
                if comp.get("type") == "BODY":
                    return comp.get("text", "")

        return "Template body not found."
    except Exception as e:
        return f"[Template fetch error: {e}]"


def render_template_text(template_body: str, parameters: list) -> str:
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



def send_second_message_for_mobile(all_rows, mobile):

    lines = []

    for row in all_rows:
        row_mobile = format_mobile(
            row.get("cust_mobile") or row.get("CustMobile") or ""
        )

        if row_mobile != mobile:
            continue

        loan_no = str(row.get("Loan Number") or row.get("loan_number") or "").strip()
        cust_name = str(row.get("Customer Name") or row.get("customer_name") or "").strip()
        loan_date = format_whatsapp_date(
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
    final_text = sanitize_template_text(final_text)

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
        f"https://graph.facebook.com/v22.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages",
        headers={
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    if not resp.ok:
        raise ValueError(resp.text)

    SmsWhatsAppLog.objects.create(
        customer_name="",
        mobile=mobile,
        template_name="books_pending_second",
        sent_text_message=final_text,
        status="Sent",
        message_type="Sent",
        content_type="text",
    )


# ---------------------------
# Build payload (template)
# ---------------------------
def build_payload(choice: str, row: dict, media_id: Optional[str] = None) -> Tuple[dict, str]:

    """
    Returns (payload_dict, rendered_text_preview)
    choice: template key (string). row: data dict with fields used below.
    """
    templates = {
        "1": ("emi_reminder", "en", [
            {"type": "text", "text": str(row.get("customer_name", ""))},
            {"type": "text", "text": str(row.get("total_dues", ""))},
            {"type": "text", "text": str(row.get("loan_number", ""))},
            {"type": "text", "text": format_whatsapp_date(row.get("installment_date", ""))},
            {"type": "text", "text": PAYMENT_LINK},
        ]),
        "2": ("emi_tenure_reminder", "te", [
            {"type": "text", "text": str(row.get("CustomerName", ""))},
            {"type": "text", "text": str(row.get("VehicleNo", ""))},
        ]),
        "3": ("cibil", "en", [
            {"type": "text", "text": str(row.get("customer_name", ""))},
        ]),
        "4": ("vehicle_registration_slot", "te", [
            {"type": "text", "text": str(row.get("CustomerName", ""))},
            {"type": "text", "text": format_whatsapp_date(row.get("registration_date", ""))},
        ]),
        "5": ("nach_bounce_payment_reminder", "en", [
            {"type": "text", "text": str(row.get("customer_name", ""))},
            {"type": "text", "text": str(row.get("due_amount", ""))},
            {"type": "text", "text": format_whatsapp_date(row.get("due_date", ""))},
            {"type": "text", "text": str(row.get("loan_number", ""))},
            {"type": "text", "text": PAYMENT_LINK},
        ]),
        "6": ("nach_balance_reminder", "en", [
            {"type": "text", "text": str(row.get("customer_name", ""))},
            {"type": "text", "text": str(row.get("balance_amount", ""))},
            {"type": "text", "text": str(row.get("loan_number", ""))},
            {"type": "text", "text": str(row.get("urm_number", ""))},
            {"type": "text", "text": format_whatsapp_date(row.get("due_date", ""))},
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
               {"type": "text", "text": str(row.get("Customer Name", ""))},     # {{1}}
               {"type": "text", "text": str(row.get("Agreement No", ""))},      # {{2}}
               {"type": "text", "text": str(row.get("Vehicle No", ""))},        # {{3}}
               {"type": "text", "text": str(row.get("Couirer Status", ""))},    # {{4}}
               {"type": "text", "text": str(row.get("PODS", ""))},              # {{5}}
               {"type": "text", "text": format_whatsapp_date(row.get("Couirer Date", ""))}, # {{6}}
               {"type": "text", "text": "7"},                                   # {{7}}
    ]),

     "10": ("noc_address_confirmation_v2", "en", [
            {"type": "text", "text": str(row.get("customer_name", ""))},
            {"type": "text", "text": str(row.get("loan_number", ""))},
            {"type": "text", "text": str(row.get("vehicle_number", ""))},
            {"type": "text", "text": str(row.get("customer_address", ""))},
        ]),

        "11": ("tenure_reminder_garantor", "te", [
            {"type": "text", "text": str(row.get("customer_name", ""))},   # {{1}}
            {"type": "text", "text": str(row.get("loan_number", ""))},     # {{2}}
            {"type": "text", "text": str(row.get("vehicle_number", ""))},  # {{3}}
            {"type": "text", "text": str(row.get("pending_emis", ""))},    # {{4}}
         ]),

        "12": ("customer_awareness_program", "en", [
            {"type": "text", "text": str(row.get("customer_name", ""))},   # {{1}}
            {"type": "text", "text": str(row.get("loan_number", ""))},     # {{2}}
            {"type": "text", "text": str(row.get("vehicle_number", ""))},  # {{3}}

        ]),
        "13": ("awareness_customer", "te", [
            {"type": "text", "text": str(row.get("customer_name", ""))},   # {{1}}
            {"type": "text", "text": str(row.get("loan_number", ""))},     # {{2}}
            {"type": "text", "text": str(row.get("vehicle_number", ""))},  # {{3}}

        ]),

        "14": ("health_insurance", "en", []),

        "15": ("pending_files", "en", [
            {"type": "text", "text": str(row.get("executive_name", ""))},   # {{1}}
        ]),
        "16": ("multiple_reminders_books", "en", [
            {"type": "text", "text": str(row.get("executive_name", ""))},   # {{1}}
            {"type": "text", "text": str(row.get("Employe id", ""))},     # {{2}}
            {"type": "text", "text": format_whatsapp_date(row.get("Last Date", ""))},  # {{3}}
        ]),
          "18": ("noc_address_confirmation_v2", "en", [
                {"type": "text", "text": str(row.get("customer_name", ""))},       # {{1}}
                {"type": "text", "text": str(row.get("loan_number", ""))},        # {{2}}
                {"type": "text", "text": str(row.get("vehicle_number", ""))},     # {{3}}
                {"type": "text", "text": str(row.get("customer_address", ""))}
        ]),
          "19": (
            "legal_notice_borrower",
            "en",
            [
                {"type": "text", "text": str(row.get("customer_name", ""))},      # {{1}}
                {"type": "text", "text": str(row.get("loan_number", ""))},        # {{2}}
                {"type": "text", "text": str(row.get("vehicle_number", ""))},     # {{3}}
                {
                    "type": "text",
                    "text": re.sub(r"[^\d]", "", str(row.get("amount", ""))),     # {{4}} digits only
                },
                {
                    "type": "text",
                    "text": format_whatsapp_date(row.get("timeline", "")),        # {{5}}
                },
            ],
        ),


              "20": (
                "legal_notice_guarantor",
                "en",
                [
                    {"type": "text", "text": str(row.get("guarantor_name", ""))},     # {{1}}
                    {"type": "text", "text": str(row.get("loan_number", ""))},        # {{2}}
                    {"type": "text", "text": str(row.get("vehicle_number", ""))},     # {{3}}
                    {
                        "type": "text",
                        "text": re.sub(r"[^\d]", "", str(row.get("amount", ""))),      # {{4}}
                    },
                    {
                        "type": "text",
                        "text": format_whatsapp_date(row.get("timeline", "")),         # {{5}}
                    },
                ],
            ),
            "21": (
                "welcome_message_pdf",  # EXACT name from WhatsApp Manager
                "en",
                [
                    {"type": "text", "text": str(row.get("customer_name", ""))},  # {{1}}
                    {"type": "text", "text": str(row.get("loan_number", ""))},    # {{2}}
                ],
            ),


             "22": (
                "public_notice",  # EXACT name from WhatsApp Manager
                "en",
                [
                    {"type": "text", "text": str(row.get("branch_name", ""))},  # {{1}}
                    {"type": "text", "text": str(row.get("employee_name", ""))},    # {{2}}
                ],
            ),
              "23": (
                "lok_adalat_notice_one",
                "en",
                [
                    {"type": "text", "text": str(row.get("loan_number", ""))},     # {{1}}
                    {"type": "text", "text": str(row.get("vehicle_number", ""))},  # {{2}}
                ],
            ),

            "24": (
                "lok_adalat",
                "te",
                [
                    {"type": "text", "text": str(row.get("loan_number", ""))},     # {{1}}
                    {"type": "text", "text": str(row.get("vehicle_number", ""))},  # {{2}}
                ],
            ),
             "25": (
                "lpc",
                "en",
                [
                    {"type": "text", "text": str(row.get("customer_name", ""))},  # {{1}}
                    {"type": "text", "text": format_whatsapp_date(row.get("effective_date", ""))},  # {{2}}
                ],
            ),
             "26": (
                "kannada_lok",
                "kn",
                [
                    {"type": "text", "text": str(row.get("loan_number", ""))},       # {{1}}
                    {"type": "text", "text": str(row.get("vehicle_number", ""))},    # {{2}}
                    {"type": "text", "text": format_whatsapp_date(row.get("hearing_date", ""))},  # {{3}}
                ],
            ),
             "27": (
                "loss_sale",
                "en",
                [
                    {"type": "text", "text": str(row.get("customer_name", ""))},   # {{1}}
                    {"type": "text", "text": str(row.get("loan_number", ""))},     # {{2}}
                    {"type": "text", "text": str(row.get("vehicle_number", ""))},  # {{3}}
                    {
                        "type": "text",
                        "text": re.sub(r"[^\d]", "", str(row.get("amount", ""))),  # {{4}}
                    },
                ],
            ),

              "28": (
                "write_off",
                "en",
                [  {"type": "text", "text": str(row.get("customer_name", ""))},  # {{1}}
                   {"type": "text", "text": str(row.get("loan_number", ""))},  # {{1}}
                   {"type": "text", "text": str(row.get("vehicle_number", ""))},
                   {"type": "text", "text": str(row.get("amount", ""))},  # {{1}}

                ],
            ),
               "29": (
                "guarantor_loss_sale",
                "en",
                [  {"type": "text", "text": str(row.get("guarantor_name", ""))},  # {{1}}
                   {"type": "text", "text": str(row.get("loan_number", ""))},  # {{1}}
                   {"type": "text", "text": str(row.get("vehicle_number", ""))},
                    {"type": "text", "text": str(row.get("customer_name", ""))},   # {{1}}
                   {"type": "text", "text": str(row.get("amount", ""))},  # {{1}}

                ],
            ),
             "30": (
                "gur_telugu_registration_notice",
                "te",
                [  {"type": "text", "text": str(row.get("guarantor_name", ""))},  # {{1}}
                   {"type": "text", "text": str(row.get("loan_number", ""))},  # {{1}}
                    {"type": "text", "text": str(row.get("customer_name", ""))},   # {{1}}

                ],
             ),
             "31": (
                "cust_telugu_registration_notice",
                "te",
                [  {"type": "text", "text": str(row.get("customer_name", ""))},  # {{1}}
                   {"type": "text", "text": str(row.get("loan_number", ""))},  # {{1}}

                ],
             ),
            "32": (
                "guarantor_registration_notice",
                "en",
                [  {"type": "text", "text": str(row.get("guarantor_name", ""))},  # {{1}}
                   {"type": "text", "text": str(row.get("loan_number", ""))},  # {{1}}
                       {"type": "text", "text": str(row.get("customer_name", ""))},   # {{1}}
                ],
             ),
             "33": (
                "registration_notice_borrower",
                "en", [  {"type": "text", "text": str(row.get("customer_name", ""))},  # {{1}}
                   {"type": "text", "text": str(row.get("loan_number", ""))},  # {{1}}
                ],
             ),
               "34": (
                "apologize",
                "en",
                [
                    {"type": "text", "text": str(row.get("customer_name", ""))},       # {{1}}
                ],
               ),
               "35": (
                "due_notice_borrower",
                "en",
                [
                    {"type": "text", "text": str(row.get("customer_name", ""))},       # {{1}}
                    {"type": "text", "text": str(row.get("loan_number", ""))},              # {{2}}
                    {"type": "text", "text": format_whatsapp_date(row.get("vehicle_number", ""))},  # {{3}}
                ],
                ),

                "36": (
                "new_loans_te",
                "te",
                [    {"type": "text", "text": str(row.get("customer_name", ""))},       # {{1}}
            
                ],
                ),

                 "37": (
                "presale_notices_borrower",
                "en",
                [    {"type": "text", "text": str(row.get("customer_name", ""))},
                     {"type": "text", "text": str(row.get("vehicle_number", ""))},
                     {"type": "text", "text": str(row.get("loan_number", ""))},             
   

                ],
                ),

    }


    template_name, lang, parameters = templates.get(choice, templates["8"])
    mobile = format_mobile(
    row.get("cust_mobile") or row.get("CustMobile") or ""
)

    if not mobile:
        raise ValueError("Mobile number missing")

    # --------------------------------------------------
    # TEMPLATES WITH DOCUMENT HEADER (19, 20, 21, 25)

    # --------------------------------------------------
   # --------------------------------------------------
    if choice in ("19", "20", "21", "25","30","31","32","33","35","37"):

        if not media_id:
            raise ValueError("media_id is required for document template")

        # Determine correct filename based on template
        if choice == "21":
            pdf_source = row.get("welcome_pdf")

        elif choice == "20":
            pdf_source = row.get("guarantor_pdf_file")

        elif choice == "25":
            pdf_source = row.get("lpc_pdf")
        elif choice == "30":
            pdf_source = row.get("gur_telugu_registration_pdf")
        elif choice == "31":
            pdf_source = row.get("cust_telugu_registration_pdf")
        elif choice == "32":
            pdf_source = row.get("guarantor_registration_pdf")
        elif choice == "33":
            pdf_source = row.get("customer_registration_pdf")
        elif choice == "35":
            pdf_source = row.get("due_notice_pdf_file")
        elif choice == "37":
            pdf_source = row.get("presale_notices_borrower_pdf")

        else:  # choice == "19"
            pdf_source = (
                row.get("borrower_pdf_file")
                or row.get("customer_pdf_file")
            )

        if not pdf_source:
            raise ValueError("PDF filename missing in Excel row")

        original_filename = Path(pdf_source).name   #Anu

        payload = {
            "messaging_product": "whatsapp",
            "to": mobile,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "policy": "deterministic",   # 🔥 prevents Telugu fallback
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
                                    "filename": original_filename  # prevents 'Untitled' #Anu
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
                    "policy": "deterministic",   # 🔥 prevents language switching
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
    template_body = get_template_text_from_whatsapp(template_name)

    rendered_text = sanitize_template_text(
        render_template_text(template_body, parameters)
    )

    return payload, rendered_text

