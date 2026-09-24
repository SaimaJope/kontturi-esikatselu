import editor_branding  # noqa: F401 — registers the branded, permission-aware dashboard.

from django.http import HttpResponseForbidden
from django.templatetags.static import static
from django.utils.html import format_html
from wagtail import hooks


@hooks.register("insert_editor_js")
def synchronize_rich_text_before_save():
    return format_html('<script src="{}" defer></script>', static("content/editor-save.js"))


@hooks.register("before_delete_snippet")
def preserve_imported_records(request, instances):
    # Wagtail's bulk deletion uses Django permissions directly rather than the
    # custom snippet viewset policy. Cover that path as well, including admins.
    from .models import Office, Person, SiteProfile
    if any(isinstance(instance, (Person, Office, SiteProfile)) for instance in instances):
        return HttpResponseForbidden("Sivuston yhteisiä tietueita voi muokata, mutta ei poistaa.")
