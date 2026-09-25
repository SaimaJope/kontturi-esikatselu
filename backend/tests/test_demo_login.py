"""Demo sign-in skips phone setup without relaxing account or production checks."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice


PASSWORD = "Test-only-demo-password-73!"


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    CMS_DEMO_MODE=True, ENVIRONMENT="demo",
)
class DemoPasswordLoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="password-demo-editor", password=PASSWORD,
        )
        cls.user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="wagtailadmin", codename="access_admin",
            )
        )

    def password_login(self, client=None, **extra):
        return (client or self.client).post(
            reverse("two_factor:login"),
            {"username": self.user.username, "password": PASSWORD, **extra},
        )

    def test_both_demo_environments_allow_password_login_without_phone_setup(self):
        for environment in ("local", "demo"):
            with self.subTest(environment=environment), override_settings(ENVIRONMENT=environment):
                self.client.logout()
                login_page = self.client.get(reverse("two_factor:login"))
                self.assertContains(login_page, 'name="username"')
                self.assertContains(login_page, 'name="password"')
                self.assertNotContains(login_page, 'name="token-otp_token"')
                response = self.password_login()
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.url, "/admin/")
                self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))
                self.assertNotIn(DEVICE_ID_SESSION_KEY, self.client.session)
                self.assertEqual(self.client.get("/admin/").status_code, 200)
                self.assertFalse(TOTPDevice.objects.filter(user=self.user).exists())

    def test_enrolled_device_is_preserved_but_not_requested_in_demo(self):
        device = TOTPDevice.objects.create(user=self.user, name="default", confirmed=True)
        original_key = device.key
        response = self.password_login()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin/")
        self.assertEqual(self.client.get("/admin/").status_code, 200)
        self.assertNotIn(DEVICE_ID_SESSION_KEY, self.client.session)
        device.refresh_from_db()
        self.assertEqual(device.key, original_key)
        self.assertTrue(device.confirmed)
        self.assertEqual(TOTPDevice.objects.filter(user=self.user).count(), 1)

    def test_wrong_password_cannot_authenticate_or_access_editor(self):
        response = self.password_login(password="incorrect-password")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get("/admin/").status_code, 302)

    def test_password_login_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("two_factor:login"))
        response = self.password_login(client=client)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("_auth_user_id", client.session)
        response = self.password_login(
            client=client, csrfmiddlewaretoken=client.cookies["csrftoken"].value,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin/")

    def test_failed_passwords_lock_demo_login_despite_spoofed_forwarded_ips(self):
        for attempt in range(5):
            response = self.client.post(
                reverse("two_factor:login"),
                {"username": self.user.username, "password": "incorrect-password"},
                HTTP_X_FORWARDED_FOR=f"198.51.100.{attempt + 1}",
            )
        self.assertEqual(response.status_code, 429)
        response = self.client.post(
            reverse("two_factor:login"),
            {"username": self.user.username, "password": PASSWORD},
            HTTP_X_FORWARDED_FOR="203.0.113.1",
        )
        self.assertEqual(response.status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_account_without_editor_permission_cannot_enter_admin(self):
        self.user.user_permissions.clear()
        self.password_login()
        for path in ("/admin/", "/admin/pages/", "/admin/images/add/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)

    def test_inactive_account_cannot_login(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.password_login()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get("/admin/").status_code, 302)

    def test_stale_authenticator_urls_redirect_without_changing_devices(self):
        device = TOTPDevice.objects.create(user=self.user, name="default", confirmed=True)
        paths = [reverse("two_factor:" + name) for name in (
            "setup", "qr", "setup_complete", "backup_tokens", "profile", "disable",
        )]
        for path in paths:
            with self.subTest(path=path, authenticated=False):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(reverse("two_factor:login")))
        self.password_login()
        for path in paths:
            for method in (self.client.get, self.client.post):
                with self.subTest(path=path, method=method.__name__):
                    response = method(path)
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response.url, "/admin/")
        self.assertTrue(TOTPDevice.objects.filter(pk=device.pk, confirmed=True).exists())
        self.assertEqual(TOTPDevice.objects.filter(user=self.user).count(), 1)
        self.assertNotIn("django_two_factor-qr_secret_key", self.client.session)

    def test_external_next_cannot_redirect_login_off_site(self):
        response = self.password_login(next="https://attacker.invalid/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin/")

    def test_demo_login_keeps_document_uploads_blocked(self):
        self.password_login()
        self.assertEqual(self.client.get("/admin/documents/").status_code, 403)

    @override_settings(ENVIRONMENT="production", CMS_DEMO_MODE=True)
    def test_demo_flag_alone_cannot_bypass_production_authenticator(self):
        TOTPDevice.objects.create(user=self.user, name="default", confirmed=True)
        url = reverse("two_factor:login")
        self.client.get(url)
        response = self.client.post(url, {
            "login_view-current_step": "auth",
            "auth-username": self.user.username,
            "auth-password": PASSWORD,
        })
        self.assertContains(response, 'name="token-otp_token"')
        self.assertNotIn("_auth_user_id", self.client.session)
        self.client.force_login(self.user)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(url))

    @override_settings(ENVIRONMENT="local", CMS_DEMO_MODE=False)
    def test_disabled_demo_mode_requires_enrollment(self):
        self.client.force_login(self.user)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("two_factor:setup"))
