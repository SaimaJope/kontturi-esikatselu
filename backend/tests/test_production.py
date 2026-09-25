"""Import production settings in fresh processes so local defaults cannot leak in."""

import json
import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase


class ProductionConfigurationTests(SimpleTestCase):
    def load_production(self, **overrides):
        environment = os.environ.copy()
        for key in ("KONTTURI_ENV", "DJANGO_SECRET_KEY", "DJANGO_ALLOWED_HOSTS", "DATABASE_URL", "TRUST_HTTPS_PROXY"):
            environment.pop(key, None)
        environment.update(
            KONTTURI_ENV="production",
            DJANGO_SECRET_KEY="Testing-only-A1B2C3D4E5F6G7H8I9J0-kLmnOpqrStUvWxYz-123456789",
            DJANGO_ALLOWED_HOSTS="kontturi.example.invalid",
            DATABASE_URL="postgresql://cms:test-only-password@127.0.0.1/kontturi_test",
        )
        environment.update(overrides)
        script = (
            "import json; import config.settings as s; "
            "print(json.dumps({key: getattr(s, key) for key in "
            "['DEBUG','LOCAL_DEMO','CMS_DEMO_MODE','SESSION_COOKIE_SECURE','CSRF_COOKIE_SECURE',"
            "'SECURE_SSL_REDIRECT','SECURE_HSTS_SECONDS','SESSION_COOKIE_HTTPONLY']}))"
        )
        return subprocess.run([sys.executable, "-c", script], cwd=settings.BASE_DIR, env=environment, capture_output=True, text=True, timeout=15)

    def test_production_enables_transport_and_cookie_security(self):
        result = self.load_production()
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(result.stdout)
        self.assertFalse(values["DEBUG"])
        self.assertFalse(values["LOCAL_DEMO"])
        self.assertFalse(values["CMS_DEMO_MODE"])
        for key in ("SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SECURE_SSL_REDIRECT", "SESSION_COOKIE_HTTPONLY"):
            self.assertTrue(values[key], key)
        self.assertGreaterEqual(values["SECURE_HSTS_SECONDS"], 31536000)

    def test_production_refuses_missing_or_unsafe_deployment_configuration(self):
        invalid = (
            {"DJANGO_SECRET_KEY": ""},
            {"DJANGO_SECRET_KEY": "a" * 70},
            {"DJANGO_ALLOWED_HOSTS": ""},
            {"DJANGO_ALLOWED_HOSTS": "*"},
            {"DJANGO_ALLOWED_HOSTS": ".example.invalid"},
            {"DATABASE_URL": "sqlite:///db.sqlite3"},
            {"DATABASE_URL": "postgresql://cms:test@127.0.0.1/test?sslmode=disable"},
            {"KONTTURI_ENV": "typo-environment"},
        )
        for environment in invalid:
            with self.subTest(setting=next(iter(environment))):
                result = self.load_production(**environment)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ImproperlyConfigured", result.stderr)

    def test_hosted_staging_keeps_secure_transport_without_local_database_fallback(self):
        result = self.load_production(KONTTURI_ENV="staging")
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(result.stdout)
        self.assertTrue(values["CMS_DEMO_MODE"])
        self.assertFalse(values["LOCAL_DEMO"])
        self.assertFalse(values["DEBUG"])
        self.assertTrue(values["SESSION_COOKIE_SECURE"])
        self.assertTrue(values["CSRF_COOKIE_SECURE"])
        for invalid in ({"DATABASE_URL": "sqlite:///demo.sqlite3"}, {"DJANGO_SECRET_KEY": ""},
                        {"DJANGO_ALLOWED_HOSTS": "*"}):
            with self.subTest(invalid=invalid):
                result = self.load_production(KONTTURI_ENV="staging", **invalid)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ImproperlyConfigured", result.stderr)
