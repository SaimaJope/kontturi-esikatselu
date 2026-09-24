"""Exercise the real authentication, middleware, and admin request pipeline."""

from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class AnonymousAccessTests(TestCase):
    def test_editor_and_account_management_require_authentication(self):
        for path in ("/admin/", "/admin/pages/", "/admin/users/", "/admin/groups/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertIn(response.status_code, (302, 303, 401, 403))
                if response.status_code in (302, 303):
                    self.assertFalse(urlsplit(response.url).netloc)

    def test_login_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(
            reverse("two_factor:login"),
            {"auth-username": "nobody", "auth-password": "invalid-password"},
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_writes_require_csrf_even_before_authentication(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post("/admin/pages/", {"title": "Cross-site request"})
        # An authentication redirect is safe, but a protected endpoint must
        # never accept the write or return a successful response.
        self.assertIn(response.status_code, (302, 303, 403, 405))

    def test_login_cannot_redirect_to_external_site(self):
        response = self.client.get(
            reverse("two_factor:login"), {"next": "https://attacker.invalid/"}
        )
        self.assertEqual(response.status_code, 200)
        # A supplied URL must never be acted on before authentication.
        self.assertNotIn("Location", response)

    def test_authentication_page_has_security_headers(self):
        response = self.client.get(reverse("two_factor:login"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertIn("Content-Security-Policy", response.headers)
        self.assertIn("frame-ancestors 'self'", response.headers["Content-Security-Policy"])
        self.assertIn("no-store", response.headers.get("Cache-Control", ""))

    def test_source_and_secret_files_are_not_served(self):
        candidates = (
            "/.env",
            "/.git/config",
            "/backend/db.sqlite3",
            "/backend/config/settings.py",
            "/assets/../backend/config/settings.py",
            "/assets/%2e%2e/backend/config/settings.py",
            "/media/../config/settings.py",
            "/static/../config/settings.py",
        )
        for path in candidates:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertIn(response.status_code, (301, 302, 400, 403, 404))
                if not response.streaming:
                    self.assertNotContains(response, settings.SECRET_KEY, status_code=response.status_code)
                    self.assertNotContains(response, "Traceback (most recent call last)", status_code=response.status_code)

    def test_untrusted_host_is_rejected(self):
        response = self.client.get(reverse("two_factor:login"), HTTP_HOST="attacker.invalid")
        self.assertEqual(response.status_code, 400)

    def test_existing_partner_gif_is_served_as_a_trusted_source_asset(self):
        response = self.client.get("/assets/partners/tieyhdistys.gif")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "image/gif")
        self.assertTrue(b"".join(response.streaming_content).startswith((b"GIF87a", b"GIF89a")))
        response.close()
        # Trusted source assets do not extend the editor's image upload types.
        self.assertNotIn("gif", settings.WAGTAILIMAGES_EXTENSIONS)

    def test_local_demo_rejects_nonloopback_connections_and_forged_proxy_headers(self):
        with override_settings(LOCAL_DEMO=True):
            response = self.client.get(
                "/healthz",
                REMOTE_ADDR="198.51.100.20",
                HTTP_X_FORWARDED_FOR="127.0.0.1",
            )
        self.assertEqual(response.status_code, 403)


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class BasicAccountIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="unprivileged-test", password="Use-only-for-tests-93!"
        )

    def test_unprivileged_account_cannot_access_editor(self):
        self.client.force_login(self.user)
        response = self.client.get("/admin/")
        self.assertIn(response.status_code, (302, 303, 403))

    def test_unprivileged_account_cannot_grant_itself_permissions(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("wagtailusers_users:edit", args=[self.user.pk]),
            {"username": self.user.username, "is_superuser": "on", "is_staff": "on"},
        )
        self.assertIn(response.status_code, (302, 303, 403, 404))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_superuser)
        self.assertFalse(self.user.is_staff)
