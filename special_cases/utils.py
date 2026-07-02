import pandas as pd
import unicodedata
import re
from django.apps import apps

# Chunk settings
PANDAS_CHUNK_SIZE = 5000
BULK_BATCH_SIZE = 2000

from .models import SmsWhatsAppLog3
# -------------------------------------------------------
# SMART HEADER MAP (FULL INCLUDING DIALER FIXES)
# -------------------------------------------------------
SMART_HEADER_MAP = {

    # ================= BASIC =================
    "company": "company",
    "branch": "branch",
    "centre": "centre",

    "loan_no": "loan_no",
    "loan no": "loan_no",

    "vehicleno": "vehicle_no",
    "vehicle no": "vehicle_no",

    "cif id": "cif_id",

    # ================= CUSTOMER =================
    "customer name": "customer_name",
    "cust number": "customer_mobile",
    "customer father name": "customer_father_name",
    "customer address": "customer_address",

    # ================= GUARANTOR =================
    "guarantor name": "guarantor_name",
    "guarantor father name": "guarantor_father_name",
    "guarantor mobile num": "guarantor_mobile",
    "guarantor address": "guarantor_address",

    # ================= CO BORROWER =================
    "co borrower name": "co_borrower_name",
    "co borrower father name": "co_borrower_father_name",
    "co borrower mobile number": "co_borrower_mobile",
    "co borrower address": "co_borrower_address",

    # ================= VEHICLE =================
    "make": "make",
    "class": "vehicle_class",
    "variant": "variant",
    "vehicle type": "vehicle_type",

    "engine no": "engine_no",
    "chassis no": "chassis_no",

    "fuel type": "fuel_type",

    # ================= LOAN =================
    "loan date": "loan_date",
    "loan amount": "loan_amount",
    "tenure": "tenure",

    "loan closure date": "loan_closure_date",
    "maturity date": "maturity_date",

    "type": "loan_type",
    "reason": "reason",
    "remarks": "remarks",

    # ================= FINANCIAL =================
    "waiver": "waiver",
    "finance amount": "finance_amount",
    "installment received amount": "installment_received_amount",
    "loan closure amount": "loan_closure_amount",
    "difference amount": "difference_amount",
    "total": "total",
    "irr": "irr",
    "amount": "amount",

    # ================= NOC =================
    "noc issued to": "noc_issued_to",
    "noc date": "noc_date",

    # ================= CLASSIFICATION =================
    "loan segment": "loan_segment",
    "scheme name": "scheme_name",
    "source name": "source_name",

    # ================= COLLECTION =================
    "received installments": "received_installments",

    "principle portion collected": "principal_collected",  # 🔥 spelling fix
    "interest portion collected": "interest_collected",
    "broken interest collected": "broken_interest_collected",

    "vas charges collected": "vas_charges_collected",

    "vas collect later received": "vas_collect_later_received",

    # ================= APPROVAL =================
    "final approval date": "final_approval_date",

    # ================= OUTSTANDING =================
    "principal outstanding": "principal_outstanding",
    "interest outstanding": "interest_outstanding",
    "broken interest outstanding": "broken_interest_outstanding",

    "foreclosure charges": "foreclosure_charges",
    "foreclosure charges tax": "foreclosure_charges_tax",

    "vas charges outstanding": "vas_charges_outstanding",
    "lpc outstanding": "lpc_outstanding",
    "vas collect later oustanding": "vas_collect_later_outstanding",  # 🔥 typo fix

    # ================= WAIVER =================
    "principal bad debt": "principal_bad_debt",

    "interest waiver": "interest_waiver",
    "broken interest waiver": "broken_interest_waiver",
    "vas charges waiver": "vas_charges_waiver",
    "lpc waiver": "lpc_waiver",
    "vas collect later waiver": "vas_collect_later_waiver",
}


# -------------------------------------------------------
# HEADER CLEANER
# -------------------------------------------------------
def clean_header(header: str):
    if not header:
        return ""

    h = str(header).strip()

    # Remove invisible characters
    INVISIBLE = ["\u200b", "\u200c", "\u200d", "\ufeff", "\t", "\n", "\r"]
    for ch in INVISIBLE:
        h = h.replace(ch, "")

    # Replace delimiters
    h = re.sub(r"[-./]", " ", h)

    # CamelCase → snake_case
    h = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", h)
    h = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", h)

    # Spaces → underscore
    h = h.replace(" ", "_")

    # Lowercase
    h = h.lower()

    # Smart map
    return SMART_HEADER_MAP.get(h, h)


# -------------------------------------------------------
# VALUE CLEANER FOR EVERY CELL
# -------------------------------------------------------
def clean_value(v):
    if not v:
        return ""
    v = str(v)
    v = unicodedata.normalize("NFKD", v)

    # Remove invisible chars
    INVISIBLE = ["\u200b", "\u200c", "\u200d", "\ufeff", "\t", "\n", "\r"]
    for ch in INVISIBLE:
        v = v.replace(ch, "")

    # Normalize hyphens
    HYPHENS = ["-", "-", "-", "—", "―"]
    for h in HYPHENS:
        v = v.replace(h, "-")

    return v.strip()


def normalize_row_values(row_dict):
    return {k: clean_value(v) for k, v in row_dict.items()}


# -------------------------------------------------------
# DATE NORMALIZER
# -------------------------------------------------------
def normalize_date(value):
    if value is None:
        return ""
    v = str(value).strip()
    if v in ["", "nan", "NaT", "None"]:
        return ""
    try:
        dt = pd.to_datetime(v, errors="coerce")
        if pd.isna(dt):
            return ""
        return dt.strftime("%Y-%m-%d")
    except:
        return ""


# -------------------------------------------------------
# MODEL RESOLVER
# -------------------------------------------------------
def get_model_by_type(file_type: str):
    mapping = {
    "write_off": "Write_Off",
    "dealer_ta_balances": "Dealer_TA_Balances",
    "auction": "Auction",
    "ledger": "Ledger"
}

    model_name = mapping.get(file_type.lower())
    if not model_name:
        return None

    return apps.get_model("special_cases", model_name)

# ======================= chat App ==========================


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

PAYMENT_LINK3 = "https://smsquare.co.in/pay2"

def format_whatsapp_date3(value) -> str:
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


def upload_whatsapp_media3(file_obj):
    """
    Upload media to WhatsApp Cloud API
    Returns media ID
    """
    import mimetypes
    
    access_token = settings.WHATSAPP3_ACCESS_TOKEN
    phone_number_id = settings.WHATSAPP3_PHONE_NUMBER_ID
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
def send_whatsapp_media3(to_number, media_id, media_type, caption=""):
    """
    Send media message using WhatsApp Cloud API
    media_type: image, video, audio, document
    """
    url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP3_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP3_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Build payload based on media type
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": media_type,
        media_type: {"id": media_id}
    }
    
    # Add caption for image and video
    if caption and media_type in ("image", "video"):
        payload[media_type]["caption"] = caption
    
    # For audio, no caption is allowed
    if media_type == "audio":
        payload["audio"] = {"id": media_id}
    
    print(f"Sending {media_type} to {to_number}")
    print(f"Payload: {payload}")
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        print(f"Media sent successfully. Message ID: {result.get('messages', [{}])[0].get('id')}")
        return result
    except Exception as e:
        print(f"Send media error: {e}")
        print(f"Response: {resp.text if 'resp' in locals() else 'No response'}")
        raise

# --------------------------------------------------
# WhatsApp template text sanitizer
# --------------------------------------------------

def send_whatsapp_text3(to_number, text_body):
    """Send text message via WhatsApp API"""
    url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP3_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP3_ACCESS_TOKEN}",
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


def sanitize_template_text3(text: str) -> str:
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


def split_text_into_chunks3(text: str, max_len: int = 1000) -> list[str]:
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
def format_mobile3(x: str) -> str:
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
def format_whatsapp_date3(value) -> str:
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
def open_legal_pdf3(filename, folder):
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
def check_whatsapp_number3(mobile: str) -> Dict[str, Any]:
    try:
        url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP3_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP3_ACCESS_TOKEN}",
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
def get_template_text_from_whatsapp3(template_name: str) -> str:
    """
    Fetch BODY text of a WhatsApp template (for DB preview).
    """
    try:
        url = (
            f"https://graph.facebook.com/v22.0/"
            f"{settings.WHATSAPP3_BUSINESS_ACCOUNT_ID}/message_templates"
            f"?name={template_name}"
        )
        headers = {"Authorization": f"Bearer {settings.WHATSAPP3_ACCESS_TOKEN}"}
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json()

        if "data" in data and data["data"]:
            for comp in data["data"][0].get("components", []):
                if comp.get("type") == "BODY":
                    return comp.get("text", "")

        return "Template body not found."
    except Exception as e:
        return f"[Template fetch error: {e}]"


def render_template_text3(template_body: str, parameters: list) -> str:
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

def build_payload3(choice: str, row: dict) -> Tuple[dict, str]:
    """
    Supports two templates:
        "1" -> wel (en, 1 param: customer_name)
        "2" -> hello_world (en_US, no params)
    """
    mobile = format_mobile3(row.get("cust_mobile") or row.get("CustMobile") or "")
    if not mobile:
        raise ValueError("Mobile number missing")

    # Define templates mapping
    templates = {
        "1": {
            "name": "wel",
            "lang": "en",
            "params": [{"type": "text", "text": str(row.get("customer_name", ""))}],
        },
        "2": {
            "name": "hello_world",
            "lang": "en_US",
            "params": [],   # no parameters
        },
    }

    # Fallback to "1" if choice not found
    template = templates.get(choice, templates["1"])
    template_name = template["name"]
    lang = template["lang"]
    parameters = template["params"]

    payload = {
        "messaging_product": "whatsapp",
        "to": mobile,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"policy": "deterministic", "code": lang},
            "components": [{"type": "body", "parameters": parameters}],
        },
    }

    # Preview text (for logs)
    try:
        template_body = get_template_text_from_whatsapp3(template_name)
        rendered_text = sanitize_template_text3(
            render_template_text3(template_body, parameters)
        )
    except Exception:
        rendered_text = template_name

    return payload, rendered_text


def send_second_message_for_mobile3(all_rows, mobile):

    lines = []

    for row in all_rows:
        row_mobile = format_mobile3(
            row.get("cust_mobile") or row.get("CustMobile") or ""
        )

        if row_mobile != mobile:
            continue

        loan_no = str(row.get("Loan Number") or row.get("loan_number") or "").strip()
        cust_name = str(row.get("Customer Name") or row.get("customer_name") or "").strip()
        loan_date = format_whatsapp_date3(
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
    final_text = sanitize_template_text3(final_text)

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
        f"https://graph.facebook.com/v22.0/{settings.WHATSAPP3_PHONE_NUMBER_ID}/messages",
        headers={
            "Authorization": f"Bearer {settings.WHATSAPP3_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    if not resp.ok:
        raise ValueError(resp.text)

    SmsWhatsAppLog3.objects.create(
        customer_name="",
        mobile=mobile,
        template_name="books_pending_second",
        sent_text_message=final_text,
        status="Sent",
        message_type="Sent",
        content_type="text",
    )

