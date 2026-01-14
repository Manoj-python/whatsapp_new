from django.urls import re_path
from .consumers import Chat2Consumer

websocket_urlpatterns = [
    # Chat socket (per mobile)
    re_path(r"ws/chat2/(?P<mobile>[^/]+)/$", Chat2Consumer.as_asgi()),

    # Global socket (contacts refresh)
]
