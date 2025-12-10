# messaging/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Auto-join a mobile chat room
    re_path(
        r"ws/chat/(?P<mobile>[0-9\+\-\s]+)/$", 
        consumers.ChatConsumer.as_asgi()
    ),

    # General websocket for sidebar, contacts, delivery ticks, search, etc.
    re_path(
        r"ws/chat/$", 
        consumers.ChatConsumer.as_asgi()
    ),
]


