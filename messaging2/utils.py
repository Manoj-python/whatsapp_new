import re
import requests
from django.conf import settings

# ✅ Ensure App2 payment link variable matches your config
PAYMENT_LINK2 = "https://smsquare.co.in/pay2"


# ----------------------------------------------------------
# Helper: Format mobile numbers cleanly (App2)
# ----------------------------------------------------------
def format_mobile2(x: str) -> str:
    """
    Cleans and formats a mobile number to standardized international format (+91XXXXXXXXXX).
    Handles inputs like '919491006569', '+91-9491006569', or '09491006569'.
    """
    if not x:
        return ""

    x = str(x).strip()
    digits = re.sub(r"\D", "", x)

    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]

    if len(digits) == 10:
        return f"+91{digits}"
    if x.startswith("+") and len(re.sub(r"\D", "", x)) >= 11:
        return x

    return f"+91{digits[-10:]}" if len(digits) >= 10 else x


# ----------------------------------------------------------
# Fetch template structure from WhatsApp Cloud API (App2)
# ----------------------------------------------------------
def get_template_text_from_whatsapp2(template_name):
    """
    Fetch the template structure dynamically from WhatsApp Cloud API (App2).
    Returns message text like "Hello {{1}}, your due is {{2}}."
    """
    try:
        url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP2_BUSINESS_ACCOUNT_ID}/message_templates?name={template_name}"
        headers = {"Authorization": f"Bearer {settings.WHATSAPP2_ACCESS_TOKEN}"}
        response = requests.get(url, headers=headers, timeout=15)
        data = response.json()

        if "data" in data and data["data"]:
            components = data["data"][0].get("components", [])
            for comp in components:
                if comp.get("type") == "BODY":
                    return comp.get("text", "")
        return None
    except Exception as e:
        return f"[Error fetching template: {e}]"


# ----------------------------------------------------------
# Render text dynamically using placeholders {{1}}, {{2}}, etc.
# ----------------------------------------------------------
def render_template_text2(template_body, parameters):
    """
    Replace {{1}}, {{2}}, etc. with given parameter text values.
    """
    if not template_body:
        return "Template body not found."

    rendered = template_body
    for i, param in enumerate(parameters, start=1):
        rendered = rendered.replace(f"{{{{{i}}}}}", str(param.get("text", "")))
    return rendered


# ----------------------------------------------------------
# Build payload + rendered message for App2 WhatsApp API
# ----------------------------------------------------------
def build_payload2(choice, row):
    """
    Build WhatsApp payload dynamically for App2 and return (payload, rendered_text).
    Supports multiple templates based on dropdown choice.
    """
    templates = {
        "1": ("emi_reminder", "en", [
            {"type": "text", "text": str(row.get("customer_name", ""))},
            {"type": "text", "text": str(row.get("total_dues", ""))},
            {"type": "text", "text": str(row.get("loan_number", ""))},
            {"type": "text", "text": str(row.get("installment_date", ""))},
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
            {"type": "text", "text": str(row.get("registration_date", ""))},
        ]),
        "5": ("nach_bounce_payment_reminder", "en", [
            {"type": "text", "text": str(row.get("customer_name", ""))},
            {"type": "text", "text": str(row.get("due_amount", ""))},
            {"type": "text", "text": str(row.get("due_date", ""))},
            {"type": "text", "text": str(row.get("loan_number", ""))},
            {"type": "text", "text": PAYMENT_LINK2},
        ]),
        "6": ("nach_balance_reminder", "en", [
            {"type": "text", "text": str(row.get("customer_name", ""))},
            {"type": "text", "text": str(row.get("balance_amount", ""))},
            {"type": "text", "text": str(row.get("loan_number", ""))},
            {"type": "text", "text": str(row.get("urm_number", ""))},
            {"type": "text", "text": str(row.get("due_date", ""))},
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
    }

    # ✅ Default fallback to template 4
    template_name, lang, parameters = templates.get(choice, templates["4"])

    # ✅ Fetch template text and render
    template_body = get_template_text_from_whatsapp2(template_name)
    rendered_text = render_template_text2(template_body, parameters)

    # ✅ Construct payload
    mobile_number = row.get("cust_mobile") or row.get("CustMobile") or ""
    payload = {
        "messaging_product": "whatsapp",
        "to": format_mobile2(mobile_number),
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": lang},
            "components": [
                {"type": "body", "parameters": parameters},
            ],
        },
    }

    return payload, rendered_text
