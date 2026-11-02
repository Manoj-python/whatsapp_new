
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticatedOrReadOnly

from ..models import EmailTemplate
from ..serializers import EmailTemplateSerializer


class EmailTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = EmailTemplateSerializer
    permission_classes = []

    def get_queryset(self):
        return EmailTemplate.objects.all().order_by("-created_at")
