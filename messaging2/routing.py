# messaging2/routing.py
from django.urls import re_path
from .consumers import Chat2Consumer

websocket_urlpatterns = [
    re_path(r"ws/chat2/(?P<mobile>[^/]+)/$", Chat2Consumer.as_asgi()),
]
