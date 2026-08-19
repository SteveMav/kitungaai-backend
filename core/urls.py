from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

from . import health


urlpatterns = [
    path("comptes/", include("django.contrib.auth.urls")),
    path("", include("apps.ui.urls")),
    path("admin/", admin.site.urls),
    path("health/live", health.live, name="health-live"),
    path("health/ready", health.ready, name="health-ready"),
    path("api/v1/", include("apps.api_v1.urls")),
    path("api/iot/", include("apps.wallets.iot_urls")),
    path("api/", include("api.urls")),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
