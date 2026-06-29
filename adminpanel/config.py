from messaging.models import CaseDescriptionLog as SmsCaseDescriptionLog
from messaging2.models import CaseDescriptionLog as PsfCaseDescriptionLog
from messaging.models import *
from messaging2.models import Agent, Case as psfCase, ChatContact2, SmsWhatsAppLog2
from messaging.models import Case as smsCase, ChatContact, SmsWhatsAppLog
from special_cases.models import Case as SplCase, SmsWhatsAppLog3, ChatContact3
from messaging2.models import *
from django.conf import settings

# ============================================
# APP CONFIGURATION
# ============================================
from messaging2.utils import get_template_text_from_whatsapp2
from messaging.utils import get_template_text_from_whatsapp
from .utils import render_template_text
# ============================================
# APP CONFIGURATION
# ============================================
APP_CONFIG = {
    'psf': {
        'name': 'PSF',
        'app_name':'Padma Sai Holdings Private Limited',
        'case_model': psfCase,
        'log_model': SmsWhatsAppLog2,
        'contact_model': ChatContact2,
        'channel_group': 'global_contacts2',
        'description_log_model': PsfCaseDescriptionLog,
        'templates': {
            'open': 'ticket_open',    # Replace with actual template name for PSF
            'close': 'ticket_closed',
            'welcome':'welcome_message',
        },
        'get_template_text': get_template_text_from_whatsapp2,
        'render_template_text': render_template_text,
        'whatsapp': {
            'phone_number_id': settings.WHATSAPP2_PHONE_NUMBER_ID,   # Use PSF's
            'access_token': settings.WHATSAPP2_ACCESS_TOKEN,
        },
    },
    'sms': {
        'name': 'SMS',
        'app_name':'SM SQUARE CREDIT SERVICES PRIVATE LIMITED',
        'case_model': smsCase,
        'log_model': SmsWhatsAppLog,
        'contact_model': ChatContact,
        'channel_group': 'global_contacts',
        'description_log_model': SmsCaseDescriptionLog,
        'get_template_text': get_template_text_from_whatsapp,
        'render_template_text': render_template_text,
        'templates': {
            'open': 'ticket_open',    # Replace with actual template name for PSF
            'close': 'ticket_closed',
            'welcome':'welcome_message',
        },
        'whatsapp': {
            'phone_number_id': settings.WHATSAPP_PHONE_NUMBER_ID,   # Use PSF's
            'access_token': settings.WHATSAPP_ACCESS_TOKEN,
        },
    },
    'spl': {
        'name': 'SPL Cases',
        'case_model': SplCase,
        'log_model': SmsWhatsAppLog3,
        'contact_model': ChatContact3,
        'channel_group': 'global_contacts3',
    },
}