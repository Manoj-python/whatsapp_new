# adminpanel/utils.py

import requests
from django.conf import settings
from datetime import timedelta
from django.utils import timezone

def send_whatsapp_template4(to_number, template_name, parameters=None, 
                            phone_number_id=None, access_token=None, language_code="en"):
    """
    Send a template message using provided WhatsApp credentials.
    If phone_number_id/access_token are None, fallback to global settings.
    """
    if parameters is None:
        parameters = []

    # Use provided credentials or fallback to global settings
    phone_number_id = phone_number_id or settings.WHATSAPP2_PHONE_NUMBER_ID
    access_token = access_token or settings.WHATSAPP2_ACCESS_TOKEN

    url = f"https://graph.facebook.com/v22.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": [
                {"type": "body", "parameters": parameters}
            ]
        }
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def send_whatsapp_text4(to_number, text, phone_number_id, access_token):
    """
    Send a plain text message via WhatsApp Cloud API.
    """
    url = f"https://graph.facebook.com/v18.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text}
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

def send_message_based_on_window(
    mobile,
    template_name,
    template_params,
    free_text,
    whatsapp_creds,
    LogModel  # <-- added as explicit parameter
):
    """
    Checks if the last inbound message is within 24h.
    If yes → send free_text as plain text.
    If no  → send the template with template_params.

    Returns: (msg_id, status, error, used_template)
    """
    # Find the most recent incoming message for this number
    last_inbound = LogModel.objects.filter(
        mobile=mobile,
        message_type="Received"
    ).order_by('-sent_at').first()

    window_open = False
    if last_inbound and last_inbound.sent_at >= timezone.now() - timedelta(hours=24):
        window_open = True

    if window_open:
        try:
            resp = send_whatsapp_text4(
                to_number=mobile,
                text=free_text,
                phone_number_id=whatsapp_creds.get('phone_number_id'),
                access_token=whatsapp_creds.get('access_token')
            )
            msg_id = resp.get("messages", [{}])[0].get("id", "")
            status = "Sent"
            error = ""
            used_template = False
        except Exception as e:
            msg_id = ""
            status = "Failed"
            error = str(e)
            used_template = False
    else:
        try:
            resp = send_whatsapp_template4(
                to_number=mobile,
                template_name=template_name,
                parameters=template_params,
                phone_number_id=whatsapp_creds.get('phone_number_id'),
                access_token=whatsapp_creds.get('access_token')
            )
            msg_id = resp.get("messages", [{}])[0].get("id", "")
            status = "Sent"
            error = ""
            used_template = True
        except Exception as e:
            msg_id = ""
            status = "Failed"
            error = str(e)
            used_template = False

    return msg_id, status, error, used_template

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
