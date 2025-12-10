# messaging2/utils.py
import re
import requests
from datetime import datetime
from django.conf import settings
from typing import Tuple, Dict, Any

PAYMENT_LINK2 = "https://padmasai.co.in/pay2"

# ---------------------------
# Mobile normalization (app2)
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

# ---------------------------
# WhatsApp number pre-check (app2)
# ---------------------------
def check_whatsapp_number2(mobile: str) -> Dict[str, Any]:
    out = {"valid": None, "blocked": False, "reason": ""}
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
                out.update({"valid": True, "reason": "Valid WhatsApp user"})
                return out
            if status == "invalid":
                out.update({"valid": False, "reason": "Not a WhatsApp user"})
                return out
        err = data.get("error") or {}
        code = err.get("code")
        msg = err.get("message", "")
        if code:
            try:
                icode = int(code)
                if icode == 131011:
                    out.update({"valid": False, "blocked": True, "reason": "User blocked business"})
                    return out
                if icode in (131009, 131045, 131000):
                    out.update({"valid": False, "reason": msg})
                    return out
            except Exception:
                pass
        out.update({"valid": True, "reason": "Unknown (assumed valid)"})
        return out
    except Exception as e:
        out.update({"valid": True, "reason": f"Validation error (assume valid): {e}"})
        return out

# ---------------------------
# Template helpers (app2)
# ---------------------------
def get_template_text_from_whatsapp2(template_name: str) -> str:
    try:
        url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP2_BUSINESS_ACCOUNT_ID}/message_templates?name={template_name}"
        headers = {"Authorization": f"Bearer {settings.WHATSAPP2_ACCESS_TOKEN}"}
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json()
        if "data" in data and data["data"]:
            for comp in data["data"][0].get("components", []):
                if comp.get("type") == "BODY":
                    return comp.get("text", "")
        return None
    except Exception as e:
        return f"[Error fetching template: {e}]"

def render_template_text2(template_body: str, parameters: list) -> str:
    if not template_body:
        return "Template body not found."
    out = template_body
    for i, p in enumerate(parameters, start=1):
        out = out.replace(f"{{{{{i}}}}}", str(p.get("text", "")))
    return out

# ---------------------------
# Build payload (app2)
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
            {"type": "text", "text": str(row.get("Customer Name", ""))},           # {{1}}
            {"type": "text", "text": str(row.get("Agreement No", ""))},           # {{2}}
            {"type": "text", "text": str(row.get("Vehicle No", ""))},             # {{3}}
            {"type": "text", "text": str(row.get("Couirer Status", ""))},         # {{4}}
            {"type": "text", "text": str(row.get("PODS", ""))},                   # {{5}}
            {"type": "text", "text": format_whatsapp_date2(row.get("Couirer Date", ""))},  # {{6}}
            {"type": "text", "text": "7"},                                        # {{7}}
        ]), 

    }

    template_name, lang, parameters = templates.get(choice, templates["8"])
    template_body = get_template_text_from_whatsapp2(template_name)
    rendered_text = render_template_text2(template_body, parameters)
    mobile_number = row.get("cust_mobile") or row.get("CustMobile") or ""
    payload = {
        "messaging_product": "whatsapp",
        "to": format_mobile2(mobile_number),
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": lang},
            "components": [{"type": "body", "parameters": parameters}],
        },
    }
    return payload, rendered_text
