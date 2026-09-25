"""A live tunnel process must not be mistaken for a reachable demonstration."""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from django.test import SimpleTestCase


spec = importlib.util.spec_from_file_location(
    "kontturi_demo_supervisor", Path(__file__).resolve().parents[2] / "scripts" / "share_demo.py"
)
supervisor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supervisor)


class DemoSupervisorHealthTests(SimpleTestCase):
    def setUp(self):
        self.status = {
            "state": "ready", "run_id": "same-run", "host": "health-check.trycloudflare.com",
            "website": "https://health-check.trycloudflare.com/",
            "editor": "https://health-check.trycloudflare.com/admin/",
        }

    def response(self, status=200, body=b"ok"):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = status
        response.read.return_value = body
        return response

    def test_timeout_and_dns_failure_mark_live_process_unavailable(self):
        for error in (TimeoutError("timed out"), URLError("DNS unavailable")):
            with self.subTest(error=type(error).__name__):
                with patch.object(supervisor, "urlopen", side_effect=error) as request:
                    status = supervisor.check_public_status(self.status)
                self.assertEqual(status["state"], "unavailable")
                self.assertFalse(status["public_reachable"])
                self.assertEqual(request.call_args.kwargs["timeout"], 5)
                self.assertEqual(self.status["state"], "ready")

    def test_http_failure_or_unexpected_body_is_not_healthy(self):
        for response in (self.response(503), self.response(body=b"not")):
            with patch.object(supervisor, "urlopen", return_value=response):
                self.assertEqual(supervisor.check_public_status(self.status)["state"], "unavailable")

    def test_recovery_preserves_url_and_run(self):
        self.status["state"] = "unavailable"
        with patch.object(supervisor, "urlopen", return_value=self.response()):
            status = supervisor.check_public_status(self.status)
        self.assertEqual(status["state"], "ready")
        self.assertTrue(status["public_reachable"])
        self.assertEqual(status["website"], self.status["website"])
        self.assertEqual(status["run_id"], "same-run")
        self.assertIn("checked_at", status)

    def test_status_checks_saved_ready_and_unavailable_state_afresh(self):
        for saved_state, works, expected in (("ready", False, "unavailable"), ("unavailable", True, "ready")):
            with self.subTest(saved_state=saved_state):
                saved = dict(self.status, state=saved_state)
                with patch.object(supervisor, "read_status", return_value=saved), \
                     patch.object(supervisor, "running", return_value=True), \
                     patch.object(supervisor, "urlopen", return_value=self.response(200 if works else 503)) as request, \
                     patch.object(supervisor, "atomic_json") as write:
                    status = supervisor.current_status()
                self.assertEqual(status["state"], expected)
                self.assertTrue(status["running"])
                request.assert_called_once()
                write.assert_not_called()

    def test_stopped_process_never_advertises_old_url_or_checks_network(self):
        with patch.object(supervisor, "read_status", return_value=self.status), \
             patch.object(supervisor, "running", return_value=False), \
             patch.object(supervisor, "urlopen") as request:
            status = supervisor.current_status()
        self.assertEqual(status["state"], "stopped")
        self.assertNotIn("website", status)
        self.assertNotIn("editor", status)
        request.assert_not_called()

    def test_invalid_saved_host_is_not_requested(self):
        with patch.object(supervisor, "urlopen") as request:
            status = supervisor.check_public_status(dict(self.status, host="unrelated.invalid"))
        self.assertEqual(status["state"], "unavailable")
        request.assert_not_called()

    def test_periodic_refresh_records_failure_then_recovery_without_restart(self):
        demo = supervisor.Demo()
        demo.status = self.status.copy()
        with patch.object(demo, "check_children") as children, \
             patch.object(supervisor, "atomic_json") as write, \
             patch.object(supervisor.subprocess, "Popen") as process, \
             patch.object(supervisor, "urlopen", side_effect=[URLError("offline"), self.response()]):
            demo.refresh_public_health()
            self.assertEqual(demo.status["state"], "unavailable")
            demo.refresh_public_health()
        self.assertEqual(demo.status["state"], "ready")
        self.assertEqual(children.call_count, 4)
        self.assertEqual(write.call_count, 2)
        process.assert_not_called()
