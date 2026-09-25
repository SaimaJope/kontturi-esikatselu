from django import template

from config.auth import demo_password_login_enabled

register = template.Library()


@register.simple_tag
def admin_mfa_required():
    return not demo_password_login_enabled()


@register.simple_tag
def localize_dashboard_search(search_form):
    """Supply Finnish copy where the upstream dashboard translation is missing."""
    field = search_form.fields.get("q")
    if field is not None:
        field.label = "Hae sivuja"
        field.widget.attrs["placeholder"] = "Hae kaikilta sivuilta…"
    return ""
