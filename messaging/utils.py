import re
import requests
from datetime import datetime
from django.conf import settings
from typing import Tuple, Dict, Any, Optional,List
from pathlib import Path
PAYMENT_LINK = "https://smsquare.co.in/pay2"


# -----------------------------------------------------
# Upload media to WhatsApp Cloud (same behaviour)
# -----------------------------------------------------
def upload_whatsapp_media(file_obj):
    access_token = settings.WHATSAPP_ACCESS_TOKEN
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    url = f"https://graph.facebook.com/v22.0/{phone_number_id}/media"
    headers = {"Authorization": f"Bearer {access_token}"}

    file_obj.seek(0)
    files = {'file': (file_obj.name, file_obj.read(), file_obj.content_type)}
    data = {'messaging_product': 'whatsapp'}

    resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)
    resp.raise_for_status()
    return resp.json()


# -----------------------------------------------------
# Send media (image/video/audio/document)
# -----------------------------------------------------
def send_whatsapp_media(to_number, media_id, media_type, caption=""):
    url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
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
# WhatsApp template text sanitizer (CRITICAL)
# --------------------------------------------------
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
# OPEN LEGAL PDF (LOCAL TEST)
# ==================================================
# from django.conf import settings
# from pathlib import Path

# def open_legal_pdf(filename):
#     filename = filename.strip()
#     folder = Path(settings.LEGAL_PDF_DIR)

#     print("DEBUG LEGAL_PDF_DIR =", folder)
#     print("DEBUG FILES IN DIR =", [f.name for f in folder.glob("*")])

#     file_path = folder / filename
#     print("DEBUG LOOKING FOR =", file_path)
#     print("DEBUG EXISTS =", file_path.exists())

#     if not file_path.exists():
#         raise FileNotFoundError(f"Legal PDF not found: {file_path}")

#     return open(file_path, "rb")
from pathlib import Path
from django.conf import settings
import boto3
from botocore.exceptions import ClientError

def open_legal_pdf(filename):
    filename = Path(str(filename)).name.strip()

    # ---------- LOCAL ----------
    if settings.DEBUG:
        file_path = Path(settings.LEGAL_PDF_DIR) / filename
        if not file_path.exists():
            raise FileNotFoundError(f"Legal PDF not found locally: {file_path}")
        return open(file_path, "rb")

    # ---------- S3 (BOTO3 - RELIABLE) ----------
    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
    )

    key = f"legal_pdfs/{filename}"

    try:
        obj = s3.get_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=key,
        )
        return obj["Body"]   # file-like object ✅
    except ClientError as e:
        raise FileNotFoundError(
            f"Legal PDF not found in S3: {key} ({e})"
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
# Build payload (template)
# ---------------------------

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


    }
  

    template_name, lang, parameters = templates.get(choice, templates["8"])
    mobile = format_mobile(row.get("cust_mobile", ""))

    # --------------------------------------------------
    # TEMPLATES WITH DOCUMENT HEADER (19, 20, 21, 25)

    # --------------------------------------------------
    if choice in ("19", "20", "21", "25"):

        if not media_id:
            raise ValueError("media_id is required for document template")

        # Determine correct filename based on template
        if choice == "21":
            pdf_source = row.get("welcome_pdf")

        elif choice == "20":
            pdf_source = row.get("guarantor_pdf_file")

        elif choice == "25":
            pdf_source = row.get("lpc_pdf")

        else:  # choice == "19"
            pdf_source = (
                row.get("borrower_pdf_file")
                or row.get("customer_pdf_file")
            )

        if not pdf_source:
            raise ValueError("PDF filename missing in Excel row")

        filename = Path(pdf_source).name

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
                                    "filename": filename  # prevents 'Untitled'
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

def send_second_message_for_mobile(all_rows, mobile):

    from .models import SmsWhatsAppLog
    import requests
    from django.conf import settings
    from .utils import sanitize_template_text, format_whatsapp_date, format_mobile

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
  





