"""Local/shared demonstrations and fail-closed production settings.

Both demo servers bind to loopback; shared demos require their assigned HTTPS
hostname. Production requires explicit secrets, hosts and a PostgreSQL connection.
DEBUG is always disabled.
"""
import os
import re
import secrets
from datetime import timedelta
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
SITE_SOURCE_ROOT = PROJECT_ROOT
LOCAL_DIR = BASE_DIR / ".local"
ENVIRONMENT = os.environ.get("KONTTURI_ENV", "local")
if ENVIRONMENT not in {"local", "demo", "production"}:
    raise ImproperlyConfigured("KONTTURI_ENV must be local, demo or production")
LOCAL_DEMO = ENVIRONMENT == "local"
SHARED_DEMO = ENVIRONMENT == "demo"
CMS_DEMO_MODE = LOCAL_DEMO or SHARED_DEMO
DEMO_DIR = LOCAL_DIR / "shared-demo"
DEBUG = False

if CMS_DEMO_MODE:
    state_dir = DEMO_DIR if SHARED_DEMO else LOCAL_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    secret_file = state_dir / "secret-key"
    if not secret_file.exists():
        try:
            with secret_file.open("x", encoding="utf-8") as stream:
                stream.write(secrets.token_urlsafe(64))
        except FileExistsError:
            pass
    SECRET_KEY = secret_file.read_text(encoding="utf-8").strip()
    if SHARED_DEMO:
        demo_host = os.environ.get("KONTTURI_DEMO_HOST", "")
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.trycloudflare\.com", demo_host):
            raise ImproperlyConfigured("Shared demo requires its exact KONTTURI_DEMO_HOST on trycloudflare.com.")
        ALLOWED_HOSTS = [demo_host]
    else:
        ALLOWED_HOSTS = ["127.0.0.1", "localhost", "[::1]"]
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": state_dir / "db.sqlite3", "OPTIONS": {"timeout": 20}}}
else:
    SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
    if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 12:
        raise ImproperlyConfigured("Set a strong random DJANGO_SECRET_KEY (at least 50 characters).")
    ALLOWED_HOSTS = [value.strip() for value in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if value.strip()]
    if not ALLOWED_HOSTS or any("*" in host or host.startswith(".") for host in ALLOWED_HOSTS):
        raise ImproperlyConfigured("Production needs explicit DJANGO_ALLOWED_HOSTS without wildcards.")
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url.startswith(("postgres://", "postgresql://")):
        raise ImproperlyConfigured("Production requires a PostgreSQL DATABASE_URL.")
    DATABASES = {"default": dj_database_url.parse(database_url, conn_max_age=60, conn_health_checks=True, ssl_require=True)}

INSTALLED_APPS = [
    "config",
    "content",
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    "modelcluster",
    "taggit",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    "two_factor",
    "axes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "config.middleware.SecurityHeadersMiddleware",
    "config.middleware.LoopbackOnlyMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "config.middleware.AdminMFAMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

AUTHENTICATION_BACKENDS = ["axes.backends.AxesStandaloneBackend", "django.contrib.auth.backends.ModelBackend"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 14}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "two_factor:login"
LOGIN_REDIRECT_URL = "/admin/"
LOGOUT_REDIRECT_URL = "/account/login/"
TWO_FACTOR_PATCH_ADMIN = False
TWO_FACTOR_REMEMBER_COOKIE_AGE = 0
TWO_FACTOR_QR_FACTORY = "qrcode.image.svg.SvgPathImage"
OTP_TOTP_ISSUER = "Kontturi & Co"
OTP_TOTP_THROTTLE_FACTOR = 2
OTP_STATIC_THROTTLE_FACTOR = 2
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_CLIENT_IP_CALLABLE = "config.security.client_ip"
AXES_LOCKOUT_CALLABLE = "config.security.locked_out"

LANGUAGE_CODE = "fi"
TIME_ZONE = "Europe/Helsinki"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_ROOT = DEMO_DIR / "media" if SHARED_DEMO else Path(os.environ.get("MEDIA_ROOT", str(BASE_DIR / "media"))).resolve()
MEDIA_URL = "/media/"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

WAGTAIL_SITE_NAME = "Kontturi & Co · Sisällönhallinta"
WAGTAILADMIN_BASE_URL = ("https://" + demo_host) if SHARED_DEMO else os.environ.get("CMS_BASE_URL", "http://127.0.0.1:8000")
WAGTAIL_APPEND_SLASH = False
WAGTAIL_ENABLE_UPDATE_CHECK = False
WAGTAIL_GRAVATAR_PROVIDER_URL = None
WAGTAIL_PASSWORD_RESET_ENABLED = False
WAGTAILIMAGES_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]
WAGTAILIMAGES_MAX_UPLOAD_SIZE = 8 * 1024 * 1024
WAGTAILIMAGES_MAX_IMAGE_PIXELS = 24_000_000
WAGTAILIMAGES_CHOOSER_PAGE_SIZE = 24
WAGTAILIMAGES_IMAGE_FORM_BASE = "config.forms.ImageForm"
WAGTAIL_WORKFLOW_ENABLED = True
# No document uploads or public document-serving endpoint in this public CMS.
WAGTAILDOCS_EXTENSIONS = []
WAGTAILDOCS_MAX_UPLOAD_SIZE = 1
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 20000

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_SECURE = not LOCAL_DEMO
CSRF_COOKIE_SECURE = not LOCAL_DEMO
CSRF_COOKIE_HTTPONLY = False  # Wagtail's same-origin JavaScript sends CSRF headers.
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = [WAGTAILADMIN_BASE_URL] if SHARED_DEMO else [value.strip() for value in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if value.strip()]
SECURE_SSL_REDIRECT = not LOCAL_DEMO
SECURE_HSTS_SECONDS = 31536000 if not LOCAL_DEMO else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
# Only set this behind a proxy which strips and rewrites X-Forwarded-Proto.
if os.environ.get("TRUST_HTTPS_PROXY") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    if CMS_DEMO_MODE:
        raise ImproperlyConfigured("Do not trust proxy headers in local or shared demo mode.")

INDEX_SITE = ENVIRONMENT == "production" and os.environ.get("INDEX_SITE") == "1"
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend" if CMS_DEMO_MODE else "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "cms@localhost")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
LOGGING = {
    "version": 1, "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"django": {"handlers": ["console"], "level": "WARNING"}, "axes": {"handlers": ["console"], "level": "WARNING"}},
}
