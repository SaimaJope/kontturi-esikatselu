"""Public version polling for the demonstration, without exposing drafts."""

import hashlib
import json

from django.conf import settings
from django.http import Http404, JsonResponse
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from wagtail.models import Page

from .models import ArticlePage, LegacyPage, Office, Person, SiteProfile


def published_version():
    """Hash only published page revisions and immediately public shared fields.

    Never use latest_revision, draft_title, or revision creation timestamps:
    saving a private draft must have no effect on this public endpoint.
    Restrict pages to the same public/live boundary as the site's views.
    """
    state = {
        "pages": list(
            Page.objects.type(LegacyPage, ArticlePage).live().public()
            .order_by("pk").values_list("pk", "live_revision_id", "live")
        ),
        "people": list(Person.objects.order_by("pk").values_list(
            "pk", "name", "role", "phone", "tel", "email", "topic",
            "image_id", "image__file", "image__width", "image__height", "sort_order",
        )),
        "offices": list(Office.objects.order_by("pk").values_list(
            "pk", "name", "street", "postal", "phone", "tel", "hours", "hours_en",
        )),
        "profile": list(SiteProfile.objects.order_by("pk").values_list(
            "pk", "name", "email", "on_call_phone", "on_call_tel",
        )),
    }
    payload = json.dumps(state, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@never_cache
@require_GET
def version(request):
    if not getattr(settings, "CMS_DEMO_MODE", False):
        raise Http404
    return JsonResponse({"version": published_version()})


def render_version(request):
    """Sample before rendering so a concurrent publication cannot be missed."""
    if not getattr(settings, "CMS_DEMO_MODE", False) or getattr(request, "is_preview", False):
        return None
    return published_version()


def append_refresh_script(soup, version_token):
    if version_token is None or soup.body is None:
        return
    script = soup.new_tag("script", src=static("content/demo-live.js"))
    script["defer"] = ""
    script["data-version"] = version_token
    script["data-version-url"] = reverse("content_demo_version")
    soup.body.append(script)
