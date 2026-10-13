from rest_framework import viewsets
from ..models import SMSTemplate
from batch_app.models import NotificationType
from ..serializers import SMSTemplateSerializer,NotificationTypeSerializer


class TemplateViewSet(viewsets.ModelViewSet):

    serializer_class = SMSTemplateSerializer
    permission_classes = []
    authentication_classes = []

    def get_queryset(self):
        return SMSTemplate.objects.all()


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class=NotificationTypeSerializer
    permission_classes=[]
    authentication_classes=[]
    queryset=NotificationType.objects.all()
