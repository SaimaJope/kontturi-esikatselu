"""Exercise the boundaries needed when the demonstration is shared over HTTPS."""

import json
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice
from wagtail.models import Site


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    ENVIRONMENT="production", CMS_DEMO_MODE=False,
)
class SharedDemoEnrollmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="shared-demo-security", password="Test-only-strong-password-27!"
        )
        cls.device = TOTPDevice.objects.create(user=cls.user, name="default", confirmed=True)

    def test_unverified_session_cannot_restart_enrollment_with_post(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("two_factor:setup"), {"setup_view-current_step": "welcome"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("two_factor:login")))
        self.assertNotIn(DEVICE_ID_SESSION_KEY, self.client.session)
        self.assertNotIn("django_two_factor-qr_secret_key", self.client.session)
        self.assertEqual(TOTPDevice.objects.filter(user=self.user).count(), 1)

    def test_unverified_session_cannot_access_existing_enrollment_qr(self):
        self.client.force_login(self.user)
        session = self.client.session
        session["django_two_factor-qr_secret_key"] = "JBSWY3DPEHPK3PXP"
        session.save()
        response = self.client.get(reverse("two_factor:qr"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("two_factor:login")))

    def test_new_account_can_still_begin_first_enrollment(self):
        first_login_user = get_user_model().objects.create_user(
            username="shared-first-login", password="Test-only-password-first-login-93!"
        )
        self.client.force_login(first_login_user)
        response = self.client.post(
            reverse("two_factor:setup"), {"setup_view-current_step": "welcome"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="generator-token"')


class SharedDemoConfigurationTests(SimpleTestCase):
    def load_demo(self, **overrides):
        environment = os.environ.copy()
        for key in (
            "KONTTURI_ENV", "KONTTURI_DEMO_HOST", "DJANGO_SECRET_KEY",
            "DJANGO_ALLOWED_HOSTS", "DATABASE_URL", "TRUST_HTTPS_PROXY",
            "CSRF_TRUSTED_ORIGINS", "CMS_BASE_URL", "MEDIA_ROOT", "INDEX_SITE",
        ):
            environment.pop(key, None)
        environment.update(KONTTURI_ENV="demo", KONTTURI_DEMO_HOST="security-test.trycloudflare.com")
        environment.update(overrides)
        script = (
            "import json; import config.settings as s; "
            "values = {key: getattr(s, key) for key in "
            "['DEBUG','LOCAL_DEMO','SHARED_DEMO','CMS_DEMO_MODE',"
            "'SESSION_COOKIE_SECURE','CSRF_COOKIE_SECURE','SECURE_SSL_REDIRECT',"
            "'ALLOWED_HOSTS','CSRF_TRUSTED_ORIGINS','INDEX_SITE','WAGTAILADMIN_BASE_URL']}; "
            "values.update(database=str(s.DATABASES['default']['NAME']), "
            "media=str(s.MEDIA_ROOT), demo_dir=str(s.DEMO_DIR)); "
            "print(json.dumps(values))"
        )
        return subprocess.run(
            [sys.executable, "-c", script], cwd=settings.BASE_DIR, env=environment,
            capture_output=True, text=True, timeout=15,
        )

    def test_shared_demo_isolated_from_local_state_with_https_and_exact_host(self):
        result = self.load_demo(
            INDEX_SITE="1", DJANGO_ALLOWED_HOSTS="*", MEDIA_ROOT="C:/not-demo-media",
            CSRF_TRUSTED_ORIGINS="https://attacker.invalid", CMS_BASE_URL="http://attacker.invalid",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(result.stdout)
        self.assertFalse(values["DEBUG"])
        self.assertFalse(values["LOCAL_DEMO"])
        self.assertFalse(values["INDEX_SITE"])
        for key in ("SHARED_DEMO", "CMS_DEMO_MODE", "SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SECURE_SSL_REDIRECT"):
            self.assertTrue(values[key], key)
        host = "security-test.trycloudflare.com"
        self.assertEqual(values["ALLOWED_HOSTS"], [host])
        self.assertEqual(values["CSRF_TRUSTED_ORIGINS"], ["https://" + host])
        self.assertEqual(values["WAGTAILADMIN_BASE_URL"], "https://" + host)
        self.assertEqual(values["database"], str(settings.LOCAL_DIR / "shared-demo" / "db.sqlite3"))
        self.assertEqual(values["media"], str(settings.LOCAL_DIR / "shared-demo" / "media"))

    def test_shared_demo_rejects_missing_wildcard_or_unrelated_host_and_proxy_trust(self):
        for host in ("", "*", ".trycloudflare.com", "*.trycloudflare.com", "trycloudflare.com", "attacker.invalid", "https://example.trycloudflare.com", "example.trycloudflare.com:8000"):
            with self.subTest(host=host):
                result = self.load_demo(KONTTURI_DEMO_HOST=host)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ImproperlyConfigured", result.stderr)
        result = self.load_demo(TRUST_HTTPS_PROXY="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ImproperlyConfigured", result.stderr)


@override_settings(
    LOCAL_DEMO=False, SHARED_DEMO=True, INDEX_SITE=False,
    ALLOWED_HOSTS=["security-test.trycloudflare.com"], SECURE_SSL_REDIRECT=True,
    SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True,
)
class SharedDemoRequestBoundaryTests(TestCase):
    def test_demo_rejects_nonloopback_origin_and_spoofed_forwarding(self):
        response = self.client.get(
            "/healthz", secure=True, HTTP_HOST="security-test.trycloudflare.com",
            REMOTE_ADDR="198.51.100.20", HTTP_X_FORWARDED_FOR="127.0.0.1",
            HTTP_X_FORWARDED_PROTO="https",
        )
        self.assertEqual(response.status_code, 403)

    def test_health_and_asset_requests_reject_untrusted_host(self):
        for path in ("/healthz", "/robots.txt", "/app.js"):
            with self.subTest(path=path):
                response = self.client.get(path, secure=True, HTTP_HOST="attacker.invalid")
                self.assertEqual(response.status_code, 400)

    def test_static_files_cannot_bypass_exact_host_check(self):
        with TemporaryDirectory() as temporary:
            (Path(temporary) / "shared-probe.css").write_text("body{color:black}", encoding="utf-8")
            with override_settings(STATIC_ROOT=temporary):
                client = Client()
                trusted = client.get(
                    "/static/shared-probe.css", secure=True,
                    HTTP_HOST="security-test.trycloudflare.com",
                )
                try:
                    self.assertEqual(trusted.status_code, 200)
                finally:
                    trusted.close()
                untrusted = client.get(
                    "/static/shared-probe.css", secure=True, HTTP_HOST="attacker.invalid"
                )
                try:
                    self.assertEqual(untrusted.status_code, 400)
                finally:
                    untrusted.close()

    def test_demo_https_has_noindex_and_secure_csrf_cookie(self):
        response = self.client.get(
            reverse("two_factor:login"), secure=True,
            HTTP_HOST="security-test.trycloudflare.com",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("noindex", response.headers["X-Robots-Tag"])
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertTrue(response.cookies[settings.CSRF_COOKIE_NAME]["secure"])


class SharedDemoAccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.publisher_group = Group.objects.create(name="Julkaisijat")

    def test_shared_account_creation_and_restart_preserve_limited_access_and_mfa(self):
        with TemporaryDirectory() as temporary:
            demo_dir = Path(temporary)
            with override_settings(
                SHARED_DEMO=True, DEMO_DIR=demo_dir,
                ALLOWED_HOSTS=["account-test.trycloudflare.com"],
                WAGTAILADMIN_BASE_URL="https://account-test.trycloudflare.com",
            ):
                output = StringIO()
                call_command("bootstrap_shared_demo", stdout=output)
                credentials = json.loads((demo_dir / "credentials.json").read_text(encoding="utf-8"))
                user = get_user_model().objects.get(username="kontturi-demo")
                self.assertFalse(user.is_superuser)
                self.assertFalse(user.is_staff)
                self.assertFalse(user.user_permissions.exists())
                self.assertEqual(list(user.groups.all()), [self.publisher_group])
                self.assertTrue(user.check_password(credentials["password"]))
                self.assertNotIn(credentials["password"], output.getvalue())
                device = TOTPDevice.objects.create(user=user, name="default", confirmed=True)
                recipient_copy = (
                    "Website: https://expired-link.trycloudflare.com/\n"
                    "Editor: https://expired-link.trycloudflare.com/admin/\n"
                    "Username: tatu-demo\nPassword: unchanged-recipient-password\n"
                    "Current site: https://kontturi.fi/\n"
                )
                recipient_copies = {
                    filename: recipient_copy.replace("tatu-demo", f"{recipient}-demo")
                    for recipient in ("tatu", "niina")
                    for filename in (f"{recipient}-access.txt", f"email-{recipient}.fi.txt")
                }
                for filename, contents in recipient_copies.items():
                    (demo_dir / filename).write_text(contents, encoding="utf-8")
                call_command("bootstrap_shared_demo", stdout=output)
                for filename, contents in recipient_copies.items():
                    self.assertEqual(
                        (demo_dir / filename).read_text(encoding="utf-8"),
                        contents.replace("expired-link.trycloudflare.com", "account-test.trycloudflare.com"),
                    )
                self.assertNotIn("unchanged-recipient-password", output.getvalue())
                user.refresh_from_db()
                self.assertTrue(user.check_password(credentials["password"]))
                self.assertTrue(TOTPDevice.objects.filter(pk=device.pk, confirmed=True).exists())
                site = Site.objects.get(is_default_site=True)
                self.assertEqual(site.hostname, "account-test.trycloudflare.com")
                self.assertEqual(site.port, 443)

    def test_shared_bootstrap_refuses_existing_account_with_admin_privileges(self):
        get_user_model().objects.create_superuser(
            username="kontturi-demo", password="Test-only-privileged-password-47!"
        )
        with TemporaryDirectory() as temporary:
            with override_settings(SHARED_DEMO=True, DEMO_DIR=Path(temporary)):
                with self.assertRaises(CommandError):
                    call_command("bootstrap_shared_demo", stdout=StringIO())
                self.assertFalse((Path(temporary) / "access.txt").exists())

    def test_shared_bootstrap_cannot_create_account_outside_shared_demo(self):
        with override_settings(SHARED_DEMO=False):
            with self.assertRaises(CommandError):
                call_command("bootstrap_shared_demo", stdout=StringIO())
        self.assertFalse(get_user_model().objects.filter(username="kontturi-demo").exists())
