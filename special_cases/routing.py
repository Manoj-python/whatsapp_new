from django.urls import re_path
from .consumers import ChatConsumer3

websocket_urlpatterns = [
    re_path(r"ws/chat_spl/$", ChatConsumer3.as_asgi()),
    re_path(r"ws/chat_spl/(?P<mobile>\+?\d+)/$", ChatConsumer3.as_asgi()),
]
