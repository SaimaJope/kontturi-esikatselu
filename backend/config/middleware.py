import ipaddress

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse

from .auth import demo_password_login_enabled


class LoopbackOnlyMiddleware:
    """A local demo cannot silently become an internet-accessible deployment."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Validate the host before WhiteNoise can return a static response.
        # CommonMiddleware runs later and only covers application requests.
        request.get_host()
        # Shared demos also run exclusively behind their loopback tunnel.
        # Never infer this address from attacker-controlled forwarded headers.
        if settings.LOCAL_DEMO or settings.SHARED_DEMO:
            try:
                allowed = ipaddress.ip_address(request.META.get("REMOTE_ADDR", "")).is_loopback
            except ValueError:
                allowed = False
            if not allowed:
                return HttpResponseForbidden("Local demonstration: loopback access only.")
        return self.get_response(request)


class AdminMFAMiddleware:
    """Protect Wagtail permissions everywhere and require MFA in production."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        password_demo = demo_password_login_enabled()
        if password_demo and request.path.startswith("/account/two_factor/"):
            if not request.user.is_authenticated:
                return redirect_to_login("/admin/", reverse("two_factor:login"))
            return HttpResponseRedirect("/admin/")
        # django-two-factor-auth's setup view checks existing devices on GET;
        # protect its POST wizard and QR endpoint as well. A password-only
        # session must verify the enrolled device before replacing it.
        if (
            not password_demo
            and request.user.is_authenticated
            and not request.user.is_verified()
            and request.path in {reverse("two_factor:setup"), reverse("two_factor:qr")}
        ):
            from django_otp.plugins.otp_totp.models import TOTPDevice
            if TOTPDevice.objects.filter(user=request.user, confirmed=True).exists():
                return redirect_to_login(request.get_full_path(), reverse("two_factor:login"))
        if request.path == "/admin" or request.path.startswith("/admin/"):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), reverse("two_factor:login"))
            if not request.user.is_active or not request.user.has_perm("wagtailadmin.access_admin"):
                return HttpResponseForbidden("Sinulla ei ole oikeutta sisällönhallintaan.")
            if not password_demo and not request.user.is_verified():
                from django_otp.plugins.otp_totp.models import TOTPDevice
                if TOTPDevice.objects.filter(user=request.user, confirmed=True).exists():
                    return redirect_to_login(request.get_full_path(), reverse("two_factor:login"))
                return HttpResponseRedirect(reverse("two_factor:setup"))
            if request.path.startswith("/admin/documents/"):
                return HttpResponseForbidden("Tässä sisällönhallinnassa käytetään vain julkisia kuvia.")
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        if match is None or not request.user.is_authenticated or request.user.is_superuser:
            return None
        delete_image = match.namespace == "wagtailimages" and match.url_name in {"delete", "delete_multiple"}
        bulk_images = match.url_name == "wagtail_bulk_action" and view_kwargs.get("app_label") == "wagtailimages" and view_kwargs.get("model_name") == "image"
        if delete_image or bulk_images:
            return HttpResponseForbidden("Kuvien poistaminen ja massamuutokset on rajattu ylläpitäjille, jotta julkaistut sivut säilyvät ehjinä.")
        return None


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        private = request.path.startswith(("/admin", "/account/"))
        # Wagtail requires inline initialization scripts/styles. Public pages do not.
        script = "'self' 'unsafe-inline'" if private else "'self'"
        frame = "'self'" if private else "'none'"
        response["Content-Security-Policy"] = (
            f"default-src 'self'; script-src {script}; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; "
            f"media-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
            f"frame-ancestors {frame}; frame-src 'self'"
        )
        response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        response["X-Content-Type-Options"] = "nosniff"
        response["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if private:
            response["Cache-Control"] = "no-store, private"
            response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
            response["X-Frame-Options"] = "SAMEORIGIN"
        elif not settings.INDEX_SITE:
            response["X-Robots-Tag"] = "noindex, nofollow"
        return response
