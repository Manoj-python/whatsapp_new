# messaging2/signals.py

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from adminpanel.views import APP_CONFIG
from .tasks import send_ticket_open_message, send_ticket_close_message

# Map source_app values to app_key
SOURCE_APP_TO_APP_KEY = {
    'app1': 'sms',
    'app2': 'psf',
    'app3': 'spl',
}

def get_app_key_from_instance(instance):
    # Try using source_app first
    source = getattr(instance, 'source_app', None)
    if source and source in SOURCE_APP_TO_APP_KEY:
        return SOURCE_APP_TO_APP_KEY[source]
    
    # Fallback: match by model class
    for key, cfg in APP_CONFIG.items():
        if isinstance(instance, cfg['case_model']):
            return key
    return None

@receiver(pre_save)
def store_old_status(sender, **kwargs):
    # Only process if sender is one of the Case models
    app_key = None
    for key, cfg in APP_CONFIG.items():
        if sender == cfg['case_model']:
            app_key = key
            break
    if not app_key:
        return

    instance = kwargs.get('instance')
    if instance.pk:
        try:
            instance._old_status = sender.objects.get(pk=instance.pk).status
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None

@receiver(post_save)
def handle_case_messages(sender, instance, created, **kwargs):
    # Only process if sender is one of the Case models
    app_key = None
    for key, cfg in APP_CONFIG.items():
        if sender == cfg['case_model']:
            app_key = key
            break
    if not app_key:
        return

    # Determine the actual app_key from the instance (using source_app)
    actual_app_key = get_app_key_from_instance(instance)
    if not actual_app_key:
        # Fallback to the matched app_key (should not happen)
        actual_app_key = app_key

    # New case → send open message
    if created and not instance.ticket_open_message_sent:
        send_ticket_open_message.delay(actual_app_key, instance.id)

    # Status changed to 'Closed' → send close message
    if not created:
        old_status = getattr(instance, '_old_status', None)
        if instance.status == 'Resolved' and old_status != 'Resolved' and not instance.ticket_close_message_sent:
            send_ticket_close_message.delay(actual_app_key, instance.id)
