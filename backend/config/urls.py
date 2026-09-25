from django.urls import include, path, re_path
from two_factor.urls import urlpatterns as two_factor_urls
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls

from . import auth, views

# Keep the existing login URL and namespace for bookmarks and safe redirects.
account_patterns = [path("account/login/", auth.login, name="login")] + [
    pattern for pattern in two_factor_urls[0] if getattr(pattern, "name", None) != "login"
]

urlpatterns = [
    path("", include((account_patterns, "two_factor"))),
    path("admin/", include(wagtailadmin_urls)),
    path("healthz", views.health),
    path("robots.txt", views.robots),
    path("assets/<path:path>", views.source_asset),
    path("media/<path:path>", views.public_image),
    path("", include("content.urls")),
    re_path(r"^(?P<filename>[a-zA-Z0-9_-]+\.(?:css|js))$", views.root_asset),
    path("", include(wagtail_urls)),
]
