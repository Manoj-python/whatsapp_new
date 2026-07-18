"""Root URL configuration for the SMSquare Customer Portal."""

from django.conf import settings
from django.urls import include, path
from django.views.static import serve

urlpatterns = [
    path("", include("portal.urls")),
]

if settings.DEBUG:
    # Dev convenience only — in prod, static/ is served by the
    # TLS-terminating proxy in front of the app, not Django.
    urlpatterns += [
        path("static/<path:path>", serve, {"document_root": settings.STATICFILES_DIRS[0]}),
    ]

# The Django equivalent of the FastAPI version's @app.exception_handler(403)
# for the IDOR PermissionDenied case.
handler403 = "portal.views.errors.forbidden"
