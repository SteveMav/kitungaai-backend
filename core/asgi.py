import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from django.core.asgi import get_asgi_application  # noqa: E402

# Initialize Django before importing websocket routing. The routing modules import
# consumers, and consumers import Django models.
django_asgi_application = get_asgi_application()

from apps.realtime_routing import websocket_urlpatterns as v1_websocket_urlpatterns  # noqa: E402
from api.routing import websocket_urlpatterns as legacy_websocket_urlpatterns  # noqa: E402


application = ProtocolTypeRouter(
    {
        "http": django_asgi_application,
        "websocket": AuthMiddlewareStack(
            URLRouter(v1_websocket_urlpatterns + legacy_websocket_urlpatterns)
        ),
    }
)
