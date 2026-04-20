# messaging2/utils.py
import re
import requests
from datetime import datetime
from django.conf import settings
from typing import Tuple, Dict, Any, Optional, List
from pathlib import Path

PAYMENT_LINK2 = "https://padmasai.co.in/pay2"


# -----------------------------------------------------
# Upload media to WhatsApp Cloud
# -----------------------------------------------------
def upload_whatsapp_media2(file_obj):
    access_token = settings.WHATSAPP2_ACCESS_TOKEN
    phone_number_id = settings.WHATSAPP2_PHONE_NUMBER_ID
    url = f"https://graph.facebook.com/v22.0/{phone_number_id}/media"
    headers = {"Authorization": f"Bearer {access_token}"}

    file_obj.seek(0)
    files = {'file': (file_obj.name, file_obj.read(), 'application/pdf')}
    data = {'messaging_product': 'whatsapp'}

    resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)
    resp.raise_for_status()
    return resp.json()


# -----------------------------------------------------
# Send media (image/video/audio/document)
# -----------------------------------------------------
def send_whatsapp_media2(to_number, media_id, media_type, caption=""):
    url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP2_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {settings.WHATSAPP2_ACCESS_TOKEN}",
               "Content-Type": "application/json"}

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": media_type,
        media_type: {"id": media_id},
    }
    if caption and media_type in ("image", "video"):
        payload[media_type]["caption"] = caption

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


# --------------------------------------------------
# WhatsApp template text sanitizer
# --------------------------------------------------
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
        return obj["Body"]

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
            return open(file_path, "rb")

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
def build_payload2(choice: str, row: dict) -> Tuple[dict, str]:
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
            "en",
            [
                {"type": "text", "text": str(row.get("guarantor_name", ""))},
                {"type": "text", "text": str(row.get("loan_number", ""))},
                {"type": "text", "text": str(row.get("customer_name", ""))},
            ],
        ),
    }

    template_name, lang, parameters = templates.get(choice, templates["8"])
    mobile = format_mobile2(row.get("cust_mobile", ""))

    # --------------------------------------------------
    # TEMPLATES WITH DOCUMENT HEADER (FIXED - UPLOADS PDF HERE)
    # --------------------------------------------------
    if choice in (
        "13","14","21","22","23","24","31","32","33","34","35","36","37","38","39"
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
        elif choice == "31":
            pdf_filename = row.get("doc_noc_pdf_file")
            folder = "noc_pdfs"
        elif choice in ("32", "33", "38", "39"):
            pdf_filename = row.get("guarantor_pdf_file")
        elif choice in ("34", "35", "36", "37"):
            pdf_filename = row.get("customer_pdf_file")

        if not pdf_filename:
            raise ValueError(f"PDF filename missing for template {choice}")

        filename = Path(pdf_filename).name
        
        # ==================================================
        # 📤 UPLOAD PDF TO WHATSAPP (CRITICAL FIX)
        # ==================================================
        file_stream = open_legal_pdf2(pdf_filename, folder)
        
        class WhatsAppFile:
            name = filename
            content_type = "application/pdf"
            def read(self):
                return file_stream.read()
            def seek(self, pos):
                pass
        
        upload_result = upload_whatsapp_media2(WhatsAppFile())
        media_id = upload_result.get("id")
        
        print(f"✅ PDF uploaded to WhatsApp with ID: {media_id}")

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
                                    "filename": filename
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
