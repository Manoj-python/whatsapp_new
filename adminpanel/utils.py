# adminpanel/utils.py

import requests
from django.conf import settings

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
