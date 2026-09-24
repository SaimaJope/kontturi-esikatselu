from django.urls import include, path, re_path
from two_factor.urls import urlpatterns as two_factor_urls
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls

from . import views

urlpatterns = [
    path("", include(two_factor_urls)),
    path("admin/", include(wagtailadmin_urls)),
    path("healthz", views.health),
    path("robots.txt", views.robots),
    path("assets/<path:path>", views.source_asset),
    path("media/<path:path>", views.public_image),
    path("", include("content.urls")),
    re_path(r"^(?P<filename>[a-zA-Z0-9_-]+\.(?:css|js))$", views.root_asset),
    path("", include(wagtail_urls)),
]
