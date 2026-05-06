from django_elasticsearch_dsl import Document, fields
from django_elasticsearch_dsl.registries import registry
from .models import SmsWhatsAppLog


@registry.register_document
class MessageDocument(Document):

    sent_text_message = fields.TextField(
        fields={
            "raw": fields.KeywordField()  # 🔥 exact match support
        }
    )

    mobile = fields.KeywordField()
    sent_at = fields.DateField()

    class Index:
        name = "messages"

    class Django:
        model = SmsWhatsAppLog
        fields = []
