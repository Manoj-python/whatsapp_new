# messaging2/api/customer_serializers.py

from rest_framework import serializers
from messaging2.models import Case, CaseComment
import os

# ─── File Size Limits ──────────────────────────────────────────

MAX_FILE_SIZE = {
    'image': 5 * 1024 * 1024,       # 5 MB
    'video': 16 * 1024 * 1024,      # 16 MB
    'audio': 16 * 1024 * 1024,      # 16 MB
    'document': 100 * 1024 * 1024,  # 100 MB
}

def validate_file_size(file_obj):
    ext = os.path.splitext(file_obj.name)[1].lower()
    if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        limit = MAX_FILE_SIZE['image']
    elif ext in ['.mp4', '.mov', '.avi', '.mkv', '.3gp']:
        limit = MAX_FILE_SIZE['video']
    elif ext in ['.mp3', '.wav', '.ogg', '.m4a', '.webm', '.mpga', '.aac']:
        limit = MAX_FILE_SIZE['audio']
    else:
        limit = MAX_FILE_SIZE['document']

    if file_obj.size > limit:
        raise serializers.ValidationError(
            f"File too large. Max {limit // (1024*1024)}MB for this file type."
        )
    return file_obj


# ─── Create Ticket ─────────────────────────────────────────────

class CustomerTicketCreateSerializer(serializers.ModelSerializer):
    attachment = serializers.FileField(write_only=True, required=False)

    class Meta:
        model = Case
        fields = [
            'customer_name', 'mobile', 'email',
            'loan_number', 'vehicle_number',
            'issue_description', 'attachment',
            'group', 'subgroup', 'category'
        ]
        extra_kwargs = {
            'group': {'required': True},
            'category': {'required': True},
            'issue_description': {'required': True},
            'loan_number': {'required': False, 'allow_null': True, 'allow_blank': True},
            'vehicle_number': {'required': False, 'allow_null': True, 'allow_blank': True},
        }

    def validate(self, data):
        if not data.get('mobile') and not data.get('email'):
            raise serializers.ValidationError("Mobile or Email is required.")
        return data

    def create(self, validated_data):
        from django.utils import timezone
        import uuid

        attachment = validated_data.pop('attachment', None)

        # Auto‑generate case ID
        case_id = f"CASE-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        validated_data['case_id'] = case_id
        validated_data['source'] = 'Customer Portal'
        validated_data['status'] = 'Open'
        validated_data['current_level'] = 'ESC1'
        validated_data['priority'] = 'Medium'
        validated_data['created_by'] = 'Customer Portal'
        app = self.context.get('app', 'sms')
        validated_data['source_app'] = app

        case = super().create(validated_data)

        if attachment:
            validate_file_size(attachment)
            from django.core.files.storage import default_storage
            from django.core.files.base import ContentFile
            saved_path = default_storage.save(
                f"customer_attachments/{case.case_id}_{attachment.name}",
                ContentFile(attachment.read())
            )
            CaseComment.objects.create(
                case=case,
                agent_name="Customer",
                comment=f"📎 Attachment: {attachment.name}",
                is_internal=False,
            )
            case.issue_description += f"\n\n📎 Attachment: {attachment.name}"
            case.save(update_fields=['issue_description'])

        # 🔔 Send WhatsApp open ticket message (async)
        from messaging2.tasks import send_ticket_open_message
        send_ticket_open_message.delay('psf', case.id)

        return case


# ─── Customer Comment ──────────────────────────────────────────

class CustomerCommentSerializer(serializers.ModelSerializer):
    attachment = serializers.FileField(write_only=True, required=False)

    class Meta:
        model = CaseComment
        fields = ['comment', 'attachment']

    def create(self, validated_data):
        attachment = validated_data.pop('attachment', None)
        comment = validated_data.get('comment', '')

        if attachment:
            validate_file_size(attachment)
            from django.core.files.storage import default_storage
            from django.core.files.base import ContentFile
            saved_path = default_storage.save(
                f"customer_comments/{self.context['case'].case_id}_{attachment.name}",
                ContentFile(attachment.read())
            )
            comment = (comment + f"\n\n📎 Attachment: {attachment.name}") if comment else f"📎 Attachment: {attachment.name}"

        return CaseComment.objects.create(
            case=self.context['case'],
            agent_name="Customer",
            comment=comment,
            is_internal=False,
        )


# ─── Ticket Detail (for customer view) ────────────────────────

class CustomerTicketDetailSerializer(serializers.ModelSerializer):
    comments = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()

    class Meta:
        model = Case
        fields = [
            'case_id', 'customer_name', 'mobile', 'email',
            'loan_number', 'vehicle_number',
            'issue_description', 'status', 'priority',
            'current_level', 'created_at', 'updated_at', 'resolved_at',
            'resolution_notes', 'reopen_count', 'comments',
            'status_display', 'customer_token'
        ]

    def get_comments(self, obj):
        qs = obj.comments.filter(is_internal=False).order_by('created_at')
        return [
            {
                'comment': c.comment,
                'agent_name': c.agent_name,
                'created_at': c.created_at.isoformat()
            }
            for c in qs
        ]

    def get_status_display(self, obj):
        mapping = {
            'Open': '🟢 Open',
            'In Progress': '🟡 In Progress',
            'Resolved': '✅ Resolved',
            'Closed': '🔒 Closed',
            'Reopened': '🔄 Reopened'
        }
        return mapping.get(obj.status, obj.status)


# ─── Ticket List (for customer dashboard) ─────────────────────

class CustomerTicketListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Case
        fields = [
            'case_id', 'customer_name', 'mobile', 'status',
            'priority', 'created_at', 'customer_token'
        ]
