import importlib.util
from pathlib import Path
from unittest.mock import Mock
from django.test import SimpleTestCase

spec = importlib.util.spec_from_file_location("kontturi_render", Path(__file__).resolve().parents[2] / "scripts/start_render.py")
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)


class RenderConfigurationTests(SimpleTestCase):
    def test_exact_platform_host_and_https_without_forwarded_header_trust(self):
        environment = {"KONTTURI_ENV": "staging", "RENDER_EXTERNAL_HOSTNAME": "kontturi.onrender.com",
                       "TRUST_HTTPS_PROXY": "1"}
        render.configure_render(environment)
        self.assertEqual(environment["DJANGO_ALLOWED_HOSTS"], "kontturi.onrender.com")
        self.assertEqual(environment["CMS_BASE_URL"], "https://kontturi.onrender.com")
        self.assertEqual(environment["CSRF_TRUSTED_ORIGINS"], "https://kontturi.onrender.com")
        self.assertEqual(environment["TRUST_HTTPS_PROXY"], "0")

    def test_local_mode_and_untrusted_host_configuration_are_rejected(self):
        for override in ({"KONTTURI_ENV": "demo"}, {"RENDER_EXTERNAL_HOSTNAME": "attacker.example"},
                         {"CMS_BASE_URL": "http://kontturi.onrender.com"},
                         {"CMS_BASE_URL": "https://other.onrender.com"},
                         {"CMS_BASE_URL": "https://user:password@kontturi.onrender.com"},
                         {"CMS_BASE_URL": "https://kontturi.onrender.com/admin/"}):
            environment = {"KONTTURI_ENV": "staging", "RENDER_EXTERNAL_HOSTNAME": "kontturi.onrender.com", **override}
            with self.subTest(override=override), self.assertRaises(RuntimeError):
                render.configure_render(environment)

    def test_maintenance_does_not_expose_empty_editor_or_content(self):
        for path, status in (("/healthz", "200 OK"), ("/", "503 Service Unavailable"), ("/admin/", "503 Service Unavailable")):
            start = Mock()
            body = render.maintenance_application({"PATH_INFO": path}, start)
            self.assertEqual(start.call_args.args[0], status)
            self.assertIn(("Cache-Control", "no-store"), start.call_args.args[1])
            self.assertTrue(body[0])
