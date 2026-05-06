from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import SmsWhatsAppLog
from .documents import MessageDocument


@receiver(post_save, sender=SmsWhatsAppLog)
def update_document(sender, instance, **kwargs):
    MessageDocument().update(instance)