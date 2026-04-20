import os
import django

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "whatsapp_sender.settings")

# 🔥 MUST BE CALLED BEFORE IMPORTING ROUTERS
django.setup()

# 🔥 Import routing AFTER django.setup()
from messaging.routing import websocket_urlpatterns as ws1
from messaging2.routing import websocket_urlpatterns as ws2
from special_cases.routing import websocket_urlpatterns as w3


application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(ws1 + ws2 + w3)
    ),
})

