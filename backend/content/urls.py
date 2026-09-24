from django.urls import path
from . import demo, views

urlpatterns = [
    path("__demo/version", demo.version, name="content_demo_version"),
    path("", views.home, name="content_home"),
    path("site-data.js", views.site_data, name="content_site_data"),
    path("<slug:filename>.html", views.legacy_page, name="content_legacy_page"),
]
