import re
import requests
from django.conf import settings

PAYMENT_LINK = "https://smsquare.co.in"


def format_mobile(x: str) -> str:
    """
    Cleans and formats a mobile number to standardized international (+91XXXXXXXXXX) format.
    Handles messy inputs like '91949 100 6569', '+91-9491006569', or 9948457293.
    """
    if not x:
        return ""

    # Convert to string and remove all non-digit characters
    x = str(x).strip()
    digits = re.sub(r"\D", "", x)

    # If it's longer than 10 digits (e.g., starts with '91' or '0'), trim properly
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]

    # Ensure it's exactly 10 digits now
    if len(digits) == 10:
        return f"+91{digits}"

    # If already in correct format
    if x.startswith("+") and len(re.sub(r"\D", "", x)) >= 11:
        return x

    # Fallback: return as-is (to avoid breaking anything)
    return f"+91{digits[-10:]}" if len(digits) >= 10 else x


def get_template_text_from_whatsapp(template_name):
    """
    Fetch the template structure dynamically from WhatsApp Cloud API.
    Returns the message text pattern (e.g. "Hello {{1}}, your due is {{2}}.")
    """
    try:
        url = f"https://graph.facebook.com/v17.0/{settings.WHATSAPP_BUSINESS_ACCOUNT_ID}/message_templates?name={template_name}"

        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        }
        response = requests.get(url, headers=headers, timeout=15)
        data = response.json()

        if "data" in data and data["data"]:
            # Extract the body text
            components = data["data"][0].get("components", [])
            for comp in components:
                if comp.get("type") == "BODY":
                    return comp.get("text", "")
        return None
    except Exception as e:
        return f"[Error fetching template: {e}]"


def render_template_text(template_body, parameters):
    """
    Replace {{1}}, {{2}}, etc. in WhatsApp template body with parameter values.
    """
    if not template_body:
        return "Template body not found."

    rendered = template_body
    for i, param in enumerate(parameters, start=1):
        rendered = rendered.replace(f"{{{{{i}}}}}", str(param.get("text", "")))
    return rendered


def build_payload(choice, row):
    """
    Builds WhatsApp payload dynamically + returns full rendered message.
    Returns (payload, rendered_text)
    """

    templates = {
        "1": ("emi_reminder", "en", [
            {"type": "text", "text": str(row.get("customer_name", ""))},
            {"type": "text", "text": str(row.get("total_dues", ""))},
            {"type": "text", "text": str(row.get("loan_number", ""))},
            {"type": "text", "text": str(row.get("installment_date", ""))},
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
            {"type": "text", "text": str(row.get("registration_date", ""))},
        ]),
        "5": ("nach_bounce_payment_reminder", "en", [
            {"type": "text", "text": str(row.get("customer_name", ""))},
            {"type": "text", "text": str(row.get("due_amount", ""))},
            {"type": "text", "text": str(row.get("due_date", ""))},
            {"type": "text", "text": str(row.get("loan_number", ""))},
            {"type": "text", "text": PAYMENT_LINK},
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

    # Default to choice 8 if not found
    template_name, lang, parameters = templates.get(choice, templates["8"])

    # ✅ Fetch full template body from WhatsApp Cloud API
    template_body = get_template_text_from_whatsapp(template_name)

    # ✅ Render the full message with variable substitution
    rendered_text = render_template_text(template_body, parameters)

    # ✅ Construct WhatsApp API payload
    mobile_number = row.get("cust_mobile") or row.get("CustMobile") or ""
    payload = {
        "messaging_product": "whatsapp",
        "to": format_mobile(mobile_number),
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": lang},
            "components": [{
                "type": "body",
                "parameters": parameters,
            }],
        },
    }

    return payload, rendered_text
