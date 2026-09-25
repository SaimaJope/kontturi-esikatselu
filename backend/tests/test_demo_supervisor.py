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
        self.status["idle_sleep_prevention_active"] = True
        with patch.object(supervisor, "read_status", return_value=self.status), \
             patch.object(supervisor, "running", return_value=False), \
             patch.object(supervisor, "urlopen") as request:
            status = supervisor.current_status()
        self.assertEqual(status["state"], "stopped")
        self.assertNotIn("website", status)
        self.assertNotIn("editor", status)
        self.assertFalse(status["idle_sleep_prevention_active"])
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


class DemoIdleSleepTests(SimpleTestCase):
    def test_acquire_prevents_only_idle_system_sleep_and_close_releases_it(self):
        guard = supervisor.IdleSleepGuard()
        with patch.object(supervisor.os, "name", "nt"), \
             patch.object(supervisor, "set_windows_execution_state", return_value=0x80000000) as execution:
            guard.start()
            self.assertTrue(guard.status()["idle_sleep_prevention_active"])
            self.assertIsNone(guard.status()["idle_sleep_warning"])
            execution.assert_called_once_with(0x80000001)
            guard.close()
            self.assertFalse(guard.active)
            self.assertEqual([call.args[0] for call in execution.call_args_list], [0x80000001, 0x80000000])
            guard.close()
            self.assertEqual(execution.call_count, 2)

    def test_failed_or_unavailable_api_warns_without_blocking_or_releasing_another_request(self):
        for result in (0, OSError("unavailable"), AttributeError("API missing")):
            with self.subTest(result=type(result).__name__):
                guard = supervisor.IdleSleepGuard()
                with patch.object(supervisor.os, "name", "nt"), \
                     patch.object(supervisor, "set_windows_execution_state", side_effect=[result]) as execution:
                    guard.start()
                    guard.close()
                self.assertFalse(guard.active)
                self.assertIn("Keep this PC awake manually", guard.warning)
                execution.assert_called_once_with(0x80000001)

    def test_other_platform_does_not_call_windows_api(self):
        guard = supervisor.IdleSleepGuard()
        with patch.object(supervisor.os, "name", "posix"), \
             patch.object(supervisor, "set_windows_execution_state") as execution:
            guard.start()
            guard.close()
        self.assertFalse(guard.active)
        self.assertIsNotNone(guard.warning)
        execution.assert_not_called()

    def test_release_failure_is_reported_without_interrupting_cleanup(self):
        guard = supervisor.IdleSleepGuard()
        with patch.object(supervisor.os, "name", "nt"), \
             patch.object(supervisor, "set_windows_execution_state", side_effect=[0x80000000, 0]):
            guard.start()
            guard.close()
        self.assertTrue(guard.active)
        self.assertIn("when the supervisor exits", guard.warning)

    def test_supervisor_releases_guard_on_stop_and_startup_failure(self):
        for error, result in ((supervisor.StopRequested(), 0), (RuntimeError("port unavailable"), 1)):
            with self.subTest(error=type(error).__name__):
                demo = supervisor.Demo()
                snapshots = []
                with patch.object(supervisor.os, "name", "nt"), \
                     patch.object(supervisor, "set_windows_execution_state", return_value=0x80000000) as execution, \
                     patch.object(supervisor, "contain_windows_process_tree"), \
                     patch.object(supervisor, "ensure_port_free", side_effect=error), \
                     patch.object(supervisor, "atomic_json", side_effect=lambda path, data: snapshots.append(data.copy())), \
                     patch.object(Path, "write_text"), \
                     patch.object(supervisor, "stop_process") as stop:
                    self.assertEqual(demo.run(), result)
                self.assertEqual([call.args[0] for call in execution.call_args_list], [0x80000001, 0x80000000])
                self.assertTrue(any(status.get("idle_sleep_prevention_active") for status in snapshots))
                self.assertFalse(snapshots[-1]["idle_sleep_prevention_active"])
                self.assertEqual(stop.call_count, 2)

    def test_supervisor_still_runs_when_guard_is_unavailable(self):
        demo = supervisor.Demo()
        with patch.object(supervisor.os, "name", "nt"), \
             patch.object(supervisor, "set_windows_execution_state", return_value=0), \
             patch.object(supervisor, "contain_windows_process_tree") as contain, \
             patch.object(supervisor, "ensure_port_free", side_effect=supervisor.StopRequested()) as port, \
             patch.object(supervisor, "atomic_json"), \
             patch.object(Path, "write_text"), \
             patch.object(supervisor, "stop_process"):
            self.assertEqual(demo.run(), 0)
        contain.assert_called_once()
        port.assert_called_once()
        self.assertFalse(demo.status["idle_sleep_prevention_active"])
        self.assertIn("Keep this PC awake manually", demo.status["idle_sleep_warning"])
