from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # URL dynamique pour que le frontend s'abonne à un panier précis
    re_path(r'ws/basket/(?P<device_id>[\w-]+)/$', consumers.BasketConsumer.as_asgi()),
]