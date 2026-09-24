"""MFA is verified with real passwords, TOTP devices, and login wizard requests."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice


PASSWORD = "Strong-test-only-password-83!"


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class MultiFactorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="mfa-admin", email="mfa@example.invalid", password=PASSWORD
        )

    def make_device(self, user=None):
        return TOTPDevice.objects.create(user=user or self.user, name="default", confirmed=True)

    def password_step(self, **extra):
        url = reverse("two_factor:login")
        self.client.get(url)
        return self.client.post(
            url,
            {"login_view-current_step": "auth", "auth-username": self.user.username, "auth-password": PASSWORD, **extra},
        )

    def token_step(self, device, **extra):
        token = str(totp(device.bin_key, step=device.step, t0=device.t0, digits=device.digits, drift=device.drift)).zfill(device.digits)
        return self.client.post(
            reverse("two_factor:login"),
            {"login_view-current_step": "token", "token-otp_token": token, **extra},
        )

    def test_password_only_session_must_enroll_before_accessing_admin(self):
        self.client.force_login(self.user)
        for path in ("/admin/", "/admin/login/", "/admin/images/add/", "/admin/pages/", "/admin/users/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.url, reverse("two_factor:setup"))

    def test_existing_device_requires_verification_even_with_authenticated_session(self):
        self.make_device()
        self.client.force_login(self.user)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("two_factor:login")))

    def test_another_users_verified_device_cannot_unlock_admin(self):
        self.make_device()
        other = get_user_model().objects.create_user(username="other-user", password=PASSWORD)
        other_device = self.make_device(other)
        self.client.force_login(self.user)
        session = self.client.session
        session[DEVICE_ID_SESSION_KEY] = other_device.persistent_id
        session.save()
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("two_factor:login")))

    def test_valid_password_alone_does_not_authenticate_mfa_user(self):
        self.make_device()
        response = self.password_step()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="token-otp_token"')
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get("/admin/").status_code, 302)

    def test_invalid_totp_does_not_authenticate(self):
        self.make_device()
        self.password_step()
        response = self.client.post(reverse("two_factor:login"), {"login_view-current_step": "token", "token-otp_token": "invalid"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_real_password_and_totp_authenticate_and_reject_external_redirect(self):
        device = self.make_device()
        self.password_step(next="https://attacker.invalid/")
        response = self.token_step(device, next="https://attacker.invalid/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin/")
        self.assertEqual(self.client.session.get(DEVICE_ID_SESSION_KEY), device.persistent_id)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_failed_passwords_lock_account_and_forwarded_ip_cannot_bypass(self):
        self.make_device()
        url = reverse("two_factor:login")
        for attempt in range(5):
            self.client.get(url)
            response = self.client.post(
                url,
                {"login_view-current_step": "auth", "auth-username": self.user.username, "auth-password": "incorrect-password"},
                HTTP_X_FORWARDED_FOR=f"198.51.100.{attempt + 1}",
            )
        self.assertEqual(response.status_code, 429)
        self.client.get(url)
        response = self.client.post(
            url,
            {"login_view-current_step": "auth", "auth-username": self.user.username, "auth-password": PASSWORD},
            HTTP_X_FORWARDED_FOR="203.0.113.1",
        )
        self.assertEqual(response.status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)
