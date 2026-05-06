from django.urls import re_path
from .consumers import ChatConsumer2

websocket_urlpatterns = [
    re_path(r"ws/chat2/$", ChatConsumer2.as_asgi()),  # ✅ ADD THIS
    re_path(r"ws/chat2/(?P<mobile>[^/]+)/$", ChatConsumer2.as_asgi()),
]
