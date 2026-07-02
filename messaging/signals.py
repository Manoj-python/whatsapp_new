from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.apps import apps

# Import your APP_CONFIG – adjust the import path as needed
from adminpanel.views import APP_CONFIG   # or from .config import APP_CONFIG

def create_chat_contact_for_case(sender, instance, created, **kwargs):
    """Generic handler: creates a ChatContact for the app that owns the case."""
    if not created or not instance.mobile:
        return

    # Find which app this case model belongs to
    app_key = None
    contact_model = None
    for key, config in APP_CONFIG.items():
        if config.get('case_model') == sender:
            app_key = key
            contact_model = config.get('contact_model')
            break

    if not contact_model:
        # If no matching config, log a warning and skip
        import logging
        logging.warning(f"No APP_CONFIG entry for case model {sender}")
        return

    # get_or_create the contact
    contact, is_new = contact_model.objects.get_or_create(
        mobile=instance.mobile,
        defaults={
            'last_msg': f"Ticket {instance.case_id}",
            'last_time': timezone.now(),
            'last_type': 'system',
            'last_status': 'Auto‑created from case',
            'unread': 0,
        }
    )

    # Sync assignment info if available
    if hasattr(instance, 'assigned_to') and instance.assigned_to:
        contact.assigned_to = instance.assigned_to.name
        contact.current_level = instance.current_level
        contact.save(update_fields=['assigned_to', 'current_level'])

# Connect the signal to each case model dynamically
def connect_case_signals():
    for config in APP_CONFIG.values():
        case_model = config.get('case_model')
        if case_model:
            post_save.connect(
                create_chat_contact_for_case,
                sender=case_model,
                dispatch_uid=f'create_chat_contact_{case_model.__name__}'
            )