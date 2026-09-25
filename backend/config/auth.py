"""Use a simple password login in demonstrations; retain production MFA."""

from django.conf import settings
from django.contrib.auth.views import LoginView as PasswordLoginView
from two_factor.views import LoginView as TwoFactorLoginView


def demo_password_login_enabled():
    # Production cannot opt out of MFA through a separate feature flag.
    return settings.CMS_DEMO_MODE and settings.ENVIRONMENT in {"local", "demo"}


def login(request, *args, **kwargs):
    if demo_password_login_enabled():
        view = PasswordLoginView.as_view(
            template_name="registration/demo_login.html",
            redirect_authenticated_user=True,
        )
    else:
        view = TwoFactorLoginView.as_view()
    return view(request, *args, **kwargs)
