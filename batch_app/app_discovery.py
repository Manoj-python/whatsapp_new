# batch_app/app_discovery.py - COMPLETE FIXED VERSION

import importlib
import inspect
import re
from django.apps import apps as django_apps
from django.conf import settings

# Cache for discovered apps
_DISCOVERED_APPS = None


def discover_all_messaging_apps():
    """
    Dynamically discover ALL messaging apps from INSTALLED_APPS
    """
    global _DISCOVERED_APPS
    
    if _DISCOVERED_APPS is not None:
        return _DISCOVERED_APPS
    
    _DISCOVERED_APPS = {}
    
    for app_config in django_apps.get_app_configs():
        app_name = app_config.name
        
        # Skip batch_app itself
        if app_name == 'batch_app':
            continue
        
        # ✅ Check if app has messaging-related models
        try:
            module = importlib.import_module(f'{app_name}.models')
            model_names = [name for name, obj in inspect.getmembers(module, inspect.isclass) 
                          if obj.__module__ == f'{app_name}.models']
        except ImportError:
            continue
        
        # ✅ Check for messaging-related models
        log_models = [name for name in model_names if 'SmsWhatsAppLog' in name or 'WhatsAppLog' in name]
        contact_models = [name for name in model_names if 'ChatContact' in name]
        is_messaging_app = 'messaging' in app_name.lower() or 'whatsapp' in app_name.lower()
        
        if log_models or contact_models or is_messaging_app:
            # Get app label
            app_label = app_config.verbose_name or app_name.replace('_', ' ').title()
            
            # Get WhatsApp credentials for this app
            creds = get_app_credentials(app_name)
            
            _DISCOVERED_APPS[app_name] = {
                'name': app_name,
                'label': app_label,
                'models': get_app_models(app_name),
                'utils': get_app_utils(app_name),
                'tasks': get_app_tasks(app_name),
                'forms': get_app_forms(app_name),
                'log_models': log_models,
                'contact_models': contact_models,
                'credentials': creds,
                'has_webhook': check_webhook(app_name),
                'has_chat': check_chat_routing(app_name),
            }
            
            print(f"✅ Discovered messaging app: {app_name} ({app_label})")
    
    return _DISCOVERED_APPS


def get_app_models(app_name):
    """Dynamically import models from app"""
    try:
        module = importlib.import_module(f'{app_name}.models')
        models = {}
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ == f'{app_name}.models':
                models[name] = obj
        return models
    except ImportError:
        return {}


def get_app_utils(app_name):
    """Dynamically import utils from app"""
    try:
        module = importlib.import_module(f'{app_name}.utils')
        utils = {}
        for name, obj in inspect.getmembers(module, inspect.isfunction):
            utils[name] = obj
        return utils
    except ImportError:
        return {}


def get_app_tasks(app_name):
    """Dynamically import tasks from app"""
    try:
        module = importlib.import_module(f'{app_name}.tasks')
        tasks = {}
        for name, obj in inspect.getmembers(module, inspect.isfunction):
            tasks[name] = obj
        return tasks
    except ImportError:
        return {}


def get_app_forms(app_name):
    """Dynamically import forms from app"""
    try:
        module = importlib.import_module(f'{app_name}.forms')
        forms = {}
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ == f'{app_name}.forms':
                forms[name] = obj
        return forms
    except ImportError:
        return {}


def get_app_credentials(app_name):
    """Dynamically get WhatsApp credentials from settings"""
    from django.conf import settings
    
    app_key = app_name.upper().replace('-', '_')
    creds = {}
    
    # Pattern 1: app_name_ACCESS_TOKEN
    token_key = f'{app_key}_ACCESS_TOKEN'
    phone_key = f'{app_key}_PHONE_NUMBER_ID'
    
    if hasattr(settings, token_key):
        creds['access_token'] = getattr(settings, token_key)
        creds['phone_number_id'] = getattr(settings, phone_key) if hasattr(settings, phone_key) else None
        return creds
    
    # Pattern 2: WHATSAPP_ACCESS_TOKEN, WHATSAPP2_ACCESS_TOKEN, etc.
    number = 1
    if app_name == 'messaging':
        number = 1
    elif app_name == 'messaging2':
        number = 2
    elif app_name == 'special_cases' or '3' in app_name:
        number = 3
    
    token_key = f'WHATSAPP{number}_ACCESS_TOKEN' if number > 1 else 'WHATSAPP_ACCESS_TOKEN'
    phone_key = f'WHATSAPP{number}_PHONE_NUMBER_ID' if number > 1 else 'WHATSAPP_PHONE_NUMBER_ID'
    
    if hasattr(settings, token_key):
        creds['access_token'] = getattr(settings, token_key)
        creds['phone_number_id'] = getattr(settings, phone_key) if hasattr(settings, phone_key) else None
    
    return creds


def check_webhook(app_name):
    try:
        module = importlib.import_module(f'{app_name}.urls')
        urlpatterns = getattr(module, 'urlpatterns', [])
        for pattern in urlpatterns:
            if hasattr(pattern, 'pattern') and hasattr(pattern.pattern, '_route'):
                if 'webhook' in str(pattern.pattern._route):
                    return True
    except:
        pass
    return False


def check_chat_routing(app_name):
    try:
        module = importlib.import_module(f'{app_name}.routing')
        websocket_urlpatterns = getattr(module, 'websocket_urlpatterns', [])
        return bool(websocket_urlpatterns)
    except:
        pass
    return False


def get_all_messaging_apps():
    """Get all discovered messaging apps as choices"""
    apps = discover_all_messaging_apps()
    return [(key, value['label']) for key, value in apps.items()]


def get_app_by_name(app_name):
    apps = discover_all_messaging_apps()
    return apps.get(app_name)


def extract_template_name_from_label(label):
    """
    Extract the actual WhatsApp template name from a label.
    Handles various label formats.
    
    Examples:
    - "new_loans_te (Telugu)-[36]" -> "new_loans_te"
    - "EMI Reminder (English)-[1]" -> "emi_reminder"
    - "new loans template (telugu)-[43]" -> "new_loans_te"
    - "emi_reminder (English)" -> "emi_reminder"
    """
    label_lower = label.lower()
    
    # 🔥 Special mappings for known templates
    special_mappings = {
        'new loans template': 'new_loans_te',
        'new_loans_te': 'new_loans_te',
        'emi reminder': 'emi_reminder',
        'emi tenure reminder': 'emi_tenure_reminder',
        'cibil': 'cibil',
        'cibil_report': 'cibil_report',
        'vehicle registration slot': 'vehicle_registration_slot',
        'vehicle_registration_reminder': 'vehicle_registration_reminder',
        'nach bounce payment reminder': 'nach_bounce_payment_reminder',
        'nach_balance_reminder': 'nach_balance_reminder',
        'welcome_message': 'welcome_message',
        'welcome message': 'welcome_message',
        'noc_dispatch': 'noc_dispatch',
        'noc dispatch': 'noc_dispatch',
        'whatsapp_noc': 'whatsapp_noc',
        'whatsapp noc': 'whatsapp_noc',
        'guarantor': 'guarantor',
        'tenure_reminder_garantor': 'tenure_reminder_garantor',
        'noc_address_confirmation_v2': 'noc_address_confirmation_v2',
        'customer_awareness_program': 'customer_awareness_program',
        'awareness_customer': 'awareness_customer',
        'health_insurance': 'health_insurance',
        'pending_files': 'pending_files',
        'multiple_reminders_books': 'multiple_reminders_books',
        'customer_notice': 'customer_notice',
        'guarantor_notice': 'guarantor_notice',
        'public_notice': 'public_notice',
        'lok_adalat_notice': 'lok_adalat_notice',
        'lok_adalat_notice_one': 'lok_adalat_notice_one',
        'kannada_lok': 'kannada_lok',
        'lpc': 'lpc',
        'lok_hr': 'lok_hr',
        'loss_sale': 'loss_sale',
        'loss_sale_smf': 'loss_sale_smf',
        'smf_loss_sale_guarantor': 'smf_loss_sale_guarantor',
        'psf_loss_sale_guarantor': 'psf_loss_sale_guarantor',
        'disposal': 'disposal',
        'write_off': 'write_off',
        'write_off_psf': 'write_off_psf',
        'smf_write_off': 'smf_write_off',
        'doc_noc_psf': 'doc_noc_psf',
        'emp_lok_psf': 'emp_lok_psf',
        'smf_lok_doc': 'smf_lok_doc',
        'guarantor_smf_doc_lok': 'guarantor_smf_doc_lok',
        'customer_psf_lok_doc': 'customer_psf_lok_doc',
        'psf_guarantor_lok_doc': 'psf_guarantor_lok_doc',
        'guarantor_psf_registration_notice': 'guarantor_psf_registration_notice',
        'guarantor_smf_registration_notice': 'guarantor_smf_registration_notice',
        'psf_registration_borrower_notice': 'psf_registration_borrower_notice',
        'smf_registration_borrower_notice_': 'smf_registration_borrower_notice_',
        'notice_registration_telugu_psf': 'notice_registration_telugu_psf',
        'smf_notice_registration_telugu': 'smf_notice_registration_telugu',
        'gur_telugu_registration_psf_notice': 'gur_telugu_registration_psf_notice',
        'cust_registration_notice_smf': 'cust_registration_notice_smf',
        'gur_psf_writeoff': 'gur_psf_writeoff',
        'due_notice_borrower_psf': 'due_notice_borrower_psf',
        'due_notice_smf_borrower': 'due_notice_smf_borrower',
        'legal_notice_borrower': 'legal_notice_borrower',
        'legal_notice_guarantor': 'legal_notice_guarantor',
        'welcome_message_pdf': 'welcome_message_pdf',
        'apologize': 'apologize',
        'new_loans_te': 'new_loans_te',
        'books_pending_second': 'books_pending_second',
    }
    
    # Check for special mappings first (exact or partial match)
    for key, value in special_mappings.items():
        if key in label_lower:
            print(f"   🔄 Special mapping: '{key}' -> '{value}' from label: {label}")
            return value
    
    # Try to extract from pattern like "new_loans_te (Telugu)-[36]"
    # or "emi_reminder (English)"
    match = re.match(r'^([a-zA-Z0-9_]+)', label)
    if match:
        template_name = match.group(1)
        # If template_name is just "new" and label contains "new_loans", use "new_loans_te"
        if template_name == 'new' and 'new_loans' in label_lower:
            return 'new_loans_te'
        if template_name == 'emi' and ('emi reminder' in label_lower or 'tenure' in label_lower):
            if 'tenure' in label_lower:
                return 'emi_tenure_reminder'
            return 'emi_reminder'
        # If template_name is "cibil" and label contains "cibil_report", use "cibil_report"
        if template_name == 'cibil' and 'report' in label_lower:
            return 'cibil_report'
        # If template_name is "noc" and label contains "noc_dispatch"
        if template_name == 'noc' and 'dispatch' in label_lower:
            return 'noc_dispatch'
        # If template_name is "lok" and label contains "kannada_lok"
        if template_name == 'lok' and 'kannada' in label_lower:
            return 'kannada_lok'
        return template_name
    
    # Fallback: clean the label
    template_name = label_lower.replace(' ', '_')
    template_name = re.sub(r'[^a-z0-9_]', '', template_name)
    template_name = re.sub(r'\[.*?\]', '', template_name)
    template_name = re.sub(r'\(.*?\)', '', template_name)
    template_name = template_name.strip('_')
    
    return template_name


def extract_language_from_label(label):
    """Extract language code from label"""
    lang_match = re.search(r'\(([^)]+)\)', label)
    if lang_match:
        lang = lang_match.group(1).lower()
        lang_map = {
            'english': 'en',
            'telugu': 'te',
            'hindi': 'hi',
            'kannada': 'kn',
        }
        # Check if language is in the map
        for key, value in lang_map.items():
            if key in lang:
                return value
        # If language is one of the codes directly
        if lang in ['en', 'te', 'hi', 'kn']:
            return lang
    return 'en'


def get_templates_from_app(app_name):
    """
    Get templates from the selected app's forms.py
    ✅ FIXED: Correctly extracts TEMPLATE_CHOICES with proper template names
    """
    app = get_app_by_name(app_name)
    if not app:
        return []
    
    templates = []
    
    # ✅ Get forms from the app
    forms = app.get('forms', {})
    
    # Debug: Print what we found
    print(f"🔍 Looking for TEMPLATE_CHOICES in {app_name}")
    print(f"   Forms keys: {list(forms.keys())}")
    
    template_choices = None
    
    # Check if TEMPLATE_CHOICES exists in the forms dict
    if 'TEMPLATE_CHOICES' in forms:
        template_choices = forms['TEMPLATE_CHOICES']
        print(f"   Found TEMPLATE_CHOICES in {app_name}, type: {type(template_choices)}")
    
    # If not found, try direct import
    if template_choices is None:
        print(f"⚠️ No TEMPLATE_CHOICES found in forms dict, trying direct import...")
        try:
            # Try to import directly from the app's forms module
            if app_name == 'messaging':
                from messaging.forms import TEMPLATE_CHOICES as MESSAGING_TEMPLATES
                template_choices = MESSAGING_TEMPLATES
            elif app_name == 'messaging2':
                from messaging2.forms import TEMPLATE_CHOICES as MESSAGING2_TEMPLATES
                template_choices = MESSAGING2_TEMPLATES
            else:
                # Try dynamic import
                try:
                    forms_module = importlib.import_module(f'{app_name}.forms')
                    template_choices = getattr(forms_module, 'TEMPLATE_CHOICES', [])
                except:
                    template_choices = []
            print(f"   Direct import found {len(template_choices)} templates")
        except ImportError as e:
            print(f"   Direct import failed: {e}")
            template_choices = []
    
    # Process the templates
    if isinstance(template_choices, (list, tuple)):
        for choice in template_choices:
            if isinstance(choice, (list, tuple)):
                if len(choice) >= 3:
                    # New format: (id, template_name, label)
                    choice_id = str(choice[0])
                    template_name = str(choice[1])
                    choice_label = str(choice[2])
                    print(f"   🔹 3-tuple format: ID={choice_id}, Name={template_name}, Label={choice_label}")
                elif len(choice) >= 2:
                    # Old format: (id, label)
                    choice_id = str(choice[0])
                    choice_label = str(choice[1])
                    # Extract template name from label using the improved function
                    template_name = extract_template_name_from_label(choice_label)
                    print(f"   🔸 2-tuple format: ID={choice_id}, Extracted Name={template_name}, Label={choice_label}")
                else:
                    continue
                
                template_language = extract_language_from_label(choice_label)
                
                templates.append({
                    'id': choice_id,
                    'label': choice_label,
                    'name': template_name,
                    'language': template_language,
                })
    
    print(f"✅ Total templates found for {app_name}: {len(templates)}")
    if templates:
        print("   📋 Template details:")
        for t in templates[:5]:  # Show first 5
            print(f"      ID: {t['id']}, Name: {t['name']}, Lang: {t['language']}")
        if len(templates) > 5:
            print(f"      ... and {len(templates) - 5} more")
    
    return templates


def get_app_log_model(app_name):
    app = get_app_by_name(app_name)
    if not app:
        return None
    
    models = app.get('models', {})
    for name, model in models.items():
        if 'SmsWhatsAppLog' in name or 'WhatsAppLog' in name:
            return model
    return None


def get_app_contact_model(app_name):
    app = get_app_by_name(app_name)
    if not app:
        return None
    
    models = app.get('models', {})
    for name, model in models.items():
        if 'ChatContact' in name:
            return model
    return None


def get_template_name_for_id(app_name, template_id):
    """Get the actual WhatsApp template name for a given ID"""
    templates = get_templates_from_app(app_name)
    for template in templates:
        if template['id'] == str(template_id):
            return template['name']
    return None
