from rest_framework import serializers
from .models import SMSTemplate


class SMSTemplateSerializer(serializers.ModelSerializer):

    class Meta:
        model = SMSTemplate
        fields = [
            'id',
            'name',
            'template_id',
            'notification_type',   #s_ms
            'content',
            'variables',
            'created_at',
            'updated_at',
            'is_active',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
        ]

    def validate_template_id(self, value):
        # Check duplicate template_id
        queryset = SMSTemplate.objects.filter(template_id=value)

        # During update, exclude the current object
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError(
                f"Template ID '{value}' already exists."
            )

        return value

from batch_app.models import NotificationType
class NotificationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model=NotificationType
        fields=['id','code','name','description','is_active']
        read_only_fields=['id','created_at']
        

    
