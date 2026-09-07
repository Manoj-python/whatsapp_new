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
    source = getattr(instance, 'source_app', None)
    if source and source in SOURCE_APP_TO_APP_KEY:
        return SOURCE_APP_TO_APP_KEY[source]
    for key, cfg in APP_CONFIG.items():
        if isinstance(instance, cfg['case_model']):
            return key
    return None

@receiver(pre_save)
def store_old_status(sender, **kwargs):
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
    app_key = None
    for key, cfg in APP_CONFIG.items():
        if sender == cfg['case_model']:
            app_key = key
            break
    if not app_key:
        return

    actual_app_key = get_app_key_from_instance(instance)
    if not actual_app_key:
        actual_app_key = app_key

    # ─── OPEN MESSAGE (Only for non-MeghaAI) ──────────────────────
    if created and not instance.ticket_open_message_sent:
        # ✅ Skip open message for MeghaAI
        if instance.created_by == "MeghaAI":
            instance.ticket_open_message_sent = True
            instance.save(update_fields=["ticket_open_message_sent"])
            print(f"🔄 OPEN message SKIPPED for MeghaAI: {instance.case_id}")
        else:
            # Send open message for everyone else
            if hasattr(instance, '_skip_ticket_open') and instance._skip_ticket_open:
                return
            send_ticket_open_message.delay(actual_app_key, instance.id)
            print(f"📤 OPEN message SENT for: {instance.case_id}")

    # ─── CLOSE MESSAGE (Always send for everyone) ──────────────────
    if not created:
        old_status = getattr(instance, '_old_status', None)
        if instance.status in ['Resolved', 'Closed'] and old_status not in ['Resolved', 'Closed']:
            if not instance.ticket_close_message_sent:
                print(f"📤 CLOSE message SENT for: {instance.case_id} (Created by: {instance.created_by})")
                send_ticket_close_message.delay(actual_app_key, instance.id)
