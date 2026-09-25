"""Start the existing CMS behind Render's HTTPS ingress, with durable storage."""
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def configure_render(environment):
    if environment.get("KONTTURI_ENV") not in {"staging", "production"}:
        raise RuntimeError("Hosted deployment requires staging or production settings.")
    hostname = environment.get("RENDER_EXTERNAL_HOSTNAME", "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.onrender\.com", hostname):
        raise RuntimeError("Render must supply its exact service hostname.")
    environment.setdefault("DJANGO_ALLOWED_HOSTS", hostname)
    environment.setdefault("CMS_BASE_URL", "https://" + hostname)
    origin = urlsplit(environment["CMS_BASE_URL"])
    allowed = environment["DJANGO_ALLOWED_HOSTS"].split(",")
    if (origin.scheme != "https" or origin.hostname not in allowed or origin.path not in {"", "/"}
            or origin.username or origin.password or origin.query or origin.fragment or origin.port):
        raise RuntimeError("CMS_BASE_URL must be an allowed HTTPS origin.")
    environment.setdefault("CSRF_TRUSTED_ORIGINS", environment["CMS_BASE_URL"].rstrip("/"))
    # Render redirects HTTP at its ingress. Waitress sets the secure scheme
    # directly; client-supplied forwarded headers are never trusted.
    environment["TRUST_HTTPS_PROXY"] = "0"


def maintenance_application(environ, start_response):
    healthy = environ.get("PATH_INFO") == "/healthz"
    body = b"ok" if healthy else "Sivustoa valmistellaan. Palaa hetken kuluttua.".encode("utf-8")
    start_response("200 OK" if healthy else "503 Service Unavailable", [
        ("Content-Type", "text/plain; charset=utf-8"), ("Cache-Control", "no-store"),
        ("X-Robots-Tag", "noindex, nofollow"), ("X-Content-Type-Options", "nosniff"),
        ("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"),
    ])
    return [body]


def main():
    configure_render(os.environ)
    if os.environ.get("MEDIA_STORAGE") != "s3":
        raise RuntimeError("This free Render deployment requires persistent object storage.")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    sys.path.insert(0, str(ROOT / "backend"))
    subprocess.run([sys.executable, str(ROOT / "backend/manage.py"), "migrate", "--noinput"], check=True)
    from waitress import serve
    if os.environ.get("KONTTURI_MIGRATION_PENDING", "1") == "1":
        print("Maintenance mode: import the snapshot and verify accounts before opening the site.", flush=True)
        application = maintenance_application
    else:
        from config.wsgi import application
        from content.models import LegacyPage
        if not LegacyPage.objects.filter(source_file="index.html").exists():
            raise RuntimeError("Content is missing. Import the snapshot before opening the site.")
        from wagtail.models import Site
        origin = urlsplit(os.environ["CMS_BASE_URL"])
        Site.objects.filter(is_default_site=True).update(hostname=origin.hostname, port=443)
    serve(application, listen="0.0.0.0:" + os.environ.get("PORT", "8000"),
          threads=4, url_scheme="https", clear_untrusted_proxy_headers=True,
          max_request_body_size=12582912, ident="")


if __name__ == "__main__":
    main()
