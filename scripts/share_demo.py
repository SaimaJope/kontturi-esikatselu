"""Supervise the temporary HTTPS CMS demonstration; all state stays out of Git.

Run through start-shareable-demo.ps1. This is a development demonstration,
not a production deployment: the link expires when this process or PC stops.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
import uuid


ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "backend" / ".local" / "shared-demo"
BIN = ROOT / "backend" / ".local" / "bin"
STATUS = STATE / "status.json"
LOCK = STATE / "supervisor.lock"
STOP = STATE / "stop.json"
PORT = 8001
HEALTH_CHECK_INTERVAL = 30
HEALTH_CHECK_TIMEOUT = 5
CREATE_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
RELEASE_API = "https://api.github.com/repos/cloudflare/cloudflared/releases/latest"
TUNNEL_HOST = re.compile(r"https://([a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com)(?=[\s/|]|$)")
_WINDOWS_JOB_HANDLE = None
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def set_windows_execution_state(flags: int) -> int:
    import ctypes
    from ctypes import wintypes

    function = ctypes.WinDLL("kernel32", use_last_error=True).SetThreadExecutionState
    function.argtypes = [wintypes.DWORD]
    function.restype = wintypes.DWORD
    return function(flags)


class IdleSleepGuard:
    """Keep only this supervisor's thread active; never change the power plan.

    Windows still honors explicit sleep and lid closure. The display may sleep.
    Windows also clears this request automatically if the thread/process exits.
    """

    def __init__(self) -> None:
        self.active = False
        self.warning = None

    def start(self) -> None:
        try:
            if os.name != "nt" or not set_windows_execution_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED):
                raise OSError("Idle-sleep prevention unavailable")
            self.active = True
        except (AttributeError, OSError):
            self.warning = "Automatic idle-sleep prevention is unavailable. Keep this PC awake manually."

    def close(self) -> None:
        if self.active:
            try:
                if not set_windows_execution_state(ES_CONTINUOUS):
                    raise OSError("Idle-sleep request was not cleared")
                self.active = False
            except (AttributeError, OSError):
                self.warning = "The idle-sleep request could not be cleared; Windows will release it when the supervisor exits."

    def status(self) -> dict:
        return {"idle_sleep_prevention_active": self.active, "idle_sleep_warning": self.warning}


def contain_windows_process_tree() -> None:
    """Kill every descendant when the supervisor exits, including venv children.

    The unnamed job handle is deliberately retained until OS process teardown.
    Closing it earlier would also kill this supervisor before status/lock cleanup.
    Children inherit job membership, not the handle, so they cannot keep it alive.
    """
    global _WINDOWS_JOB_HANDLE
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IOCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimits),
            ("IoInfo", IOCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        error = ctypes.get_last_error()
        kernel32.CloseHandle(handle)
        raise ctypes.WinError(error)
    if not kernel32.AssignProcessToJobObject(handle, kernel32.GetCurrentProcess()):
        error = ctypes.get_last_error()
        kernel32.CloseHandle(handle)
        raise ctypes.WinError(error)
    _WINDOWS_JOB_HANDLE = handle


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_status() -> dict:
    try:
        return json.loads(STATUS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"state": "stopped"}


class SupervisorLock:
    """An OS-held file lock is released automatically even after a crash."""

    def __init__(self) -> None:
        self.stream = None

    def acquire(self) -> bool:
        STATE.mkdir(parents=True, exist_ok=True)
        self.stream = LOCK.open("a+b")
        if LOCK.stat().st_size == 0:
            self.stream.write(b"0")
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            self.stream = None
            return False
        return True

    def close(self) -> None:
        if self.stream is not None:
            self.stream.close()
            self.stream = None


def running() -> bool:
    lock = SupervisorLock()
    acquired = lock.acquire()
    lock.close()
    return not acquired


def check_public_status(status: dict) -> dict:
    """A living cloudflared process can still have an expired or offline tunnel."""
    status = status.copy()
    host = status.get("host", "")
    reachable = False
    if TUNNEL_HOST.fullmatch(f"https://{host}"):
        request = Request(f"https://{host}/healthz", headers={"Cache-Control": "no-cache"})
        try:
            with urlopen(request, timeout=HEALTH_CHECK_TIMEOUT) as response:
                reachable = response.status == 200 and response.read(3) == b"ok"
        except (OSError, URLError):
            pass
    status.update(
        state="ready" if reachable else "unavailable",
        stage="Ready" if reachable else "The public HTTPS link is unavailable",
        public_reachable=reachable,
        checked_at=time.time(),
    )
    return status


def current_status() -> dict:
    """Check readiness now without racing the supervisor's status-file writes."""
    status = read_status()
    status["running"] = running()
    if not status["running"]:
        if status.get("state") in {"starting", "ready", "unavailable", "stopping"}:
            status["state"] = "stopped"
        status.pop("website", None)
        status.pop("editor", None)
        status["public_reachable"] = False
        status["idle_sleep_prevention_active"] = False
    elif status.get("state") in {"ready", "unavailable"}:
        status = check_public_status(status)
    return status


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cloudflared_binary() -> Path:
    if os.name != "nt" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("The shareable-demo launcher currently requires Windows x64.")
    BIN.mkdir(parents=True, exist_ok=True)
    executable = BIN / "cloudflared-windows-amd64.exe"
    receipt = BIN / "cloudflared-release.json"
    if executable.is_file() and receipt.is_file():
        try:
            installed = json.loads(receipt.read_text(encoding="utf-8"))
            if re.fullmatch(r"[a-f0-9]{64}", installed.get("sha256", "")) and sha256_file(executable) == installed["sha256"]:
                return executable
        except (OSError, ValueError):
            pass

    request = Request(RELEASE_API, headers={"Accept": "application/vnd.github+json", "User-Agent": "Kontturi-CMS-demo"})
    with urlopen(request, timeout=30) as response:
        release = json.loads(response.read(2 * 1024 * 1024))
    asset = next((item for item in release.get("assets", []) if item.get("name") == executable.name), None)
    if asset is None:
        raise RuntimeError("The official cloudflared release does not include its Windows x64 binary.")
    digest = asset.get("digest", "")
    download_url = asset.get("browser_download_url", "")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
        raise RuntimeError("The official release has no SHA256 digest; refusing an unverified download.")
    if not re.fullmatch(r"https://github\.com/cloudflare/cloudflared/releases/download/[A-Za-z0-9._-]+/cloudflared-windows-amd64\.exe", download_url):
        raise RuntimeError("Unexpected cloudflared download location.")
    temporary = executable.with_suffix(".download")
    try:
        download = Request(download_url, headers={"User-Agent": "Kontturi-CMS-demo"})
        count = 0
        with urlopen(download, timeout=30) as response, temporary.open("wb") as stream:
            while block := response.read(1024 * 1024):
                count += len(block)
                if count > 150 * 1024 * 1024:
                    raise RuntimeError("The cloudflared download exceeded its expected size.")
                stream.write(block)
        expected = digest.removeprefix("sha256:")
        if sha256_file(temporary) != expected:
            raise RuntimeError("cloudflared SHA256 verification failed; the download was discarded.")
        os.replace(temporary, executable)
        atomic_json(receipt, {"version": release.get("tag_name"), "sha256": expected, "source": download_url})
    finally:
        temporary.unlink(missing_ok=True)
    return executable


def ensure_port_free() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if os.name == "nt":
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(("127.0.0.1", PORT))
        except OSError as error:
            raise RuntimeError(f"Port {PORT} is already in use. The launcher will not replace that process.") from error


def stop_process(process: subprocess.Popen | None) -> None:
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


class StopRequested(Exception):
    pass


class Demo:
    def __init__(self) -> None:
        self.run_id = uuid.uuid4().hex
        self.status = {"run_id": self.run_id, "pid": os.getpid(), "state": "starting", "started_at": time.time()}
        self.tunnel = None
        self.server = None
        self.files = []
        self.sleep_guard = IdleSleepGuard()

    def update(self, **values) -> None:
        self.status.update(values)
        atomic_json(STATUS, self.status)

    def check_stop(self) -> None:
        try:
            signal = json.loads(STOP.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if signal.get("run_id") == self.run_id:
            raise StopRequested()

    def check_children(self) -> None:
        self.check_stop()
        if self.tunnel is not None and self.tunnel.poll() is not None:
            raise RuntimeError("The HTTPS tunnel stopped. See cloudflared.log, then restart the demo.")
        if self.server is not None and self.server.poll() is not None:
            raise RuntimeError("The demo web server stopped. See server.log, then restart the demo.")

    def refresh_public_health(self) -> None:
        self.check_children()
        checked = check_public_status(self.status)
        self.check_children()
        self.status = checked
        self.update()

    def open_log(self, filename: str):
        stream = (STATE / filename).open("wb")
        self.files.append(stream)
        return stream

    def manage(self, environment: dict, log, *arguments: str) -> None:
        self.update(stage="Setting up content: " + arguments[0])
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "backend" / "manage.py"), *arguments],
            cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, creationflags=CREATE_FLAGS,
        )
        try:
            while process.poll() is None:
                self.check_children()
                time.sleep(0.25)
            if process.returncode:
                raise RuntimeError(f"Content setup failed at {arguments[0]}. See setup.log.")
        finally:
            stop_process(process)

    def wait_for_host(self) -> str:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            self.check_children()
            try:
                log_text = (STATE / "cloudflared.log").read_text(encoding="utf-8", errors="replace")
            except OSError:
                log_text = ""
            match = TUNNEL_HOST.search(log_text)
            if match:
                return match.group(1)
            time.sleep(0.5)
        raise RuntimeError("Cloudflare did not assign a demo URL in time. See cloudflared.log.")

    def wait_for_http(self, url: str, host: str | None = None, timeout: int = 60) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.check_children()
            request = Request(url, headers={"Host": host} if host else {})
            try:
                with urlopen(request, timeout=5) as response:
                    if response.status == 200:
                        return
            except (OSError, URLError):
                pass
            time.sleep(1)
        raise RuntimeError("The demo URL did not become ready. See server.log and cloudflared.log.")

    def run(self) -> int:
        self.update(stage="Checking the demo server port")
        try:
            self.sleep_guard.start()
            self.update(**self.sleep_guard.status())
            contain_windows_process_tree()
            ensure_port_free()
            self.update(stage="Verifying the official cloudflared executable")
            executable = cloudflared_binary()
            self.check_stop()
            self.update(stage="Requesting a temporary HTTPS URL")
            tunnel_log = self.open_log("cloudflared.log")
            self.tunnel = subprocess.Popen(
                [str(executable), "tunnel", "--url", f"http://127.0.0.1:{PORT}", "--protocol", "http2", "--no-autoupdate"],
                cwd=STATE, stdout=tunnel_log, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, creationflags=CREATE_FLAGS,
            )
            self.update(tunnel_pid=self.tunnel.pid)
            host = self.wait_for_host()
            environment = os.environ.copy()
            environment.update({"KONTTURI_ENV": "demo", "KONTTURI_DEMO_HOST": host, "PYTHONUNBUFFERED": "1"})
            # Keep ambient proxy configuration from changing the demo's trust boundary.
            environment.pop("TRUST_HTTPS_PROXY", None)
            environment.pop("DJANGO_SETTINGS_MODULE", None)
            setup_log = self.open_log("setup.log")
            self.manage(environment, setup_log, "migrate", "--noinput")
            self.manage(environment, setup_log, "seed_site", "--hostname", host, "--port", "443")
            self.manage(environment, setup_log, "setup_roles")
            self.manage(environment, setup_log, "bootstrap_shared_demo")
            self.manage(environment, setup_log, "collectstatic", "--noinput", "--verbosity", "0")
            self.update(stage="Starting the web server")
            server_log = self.open_log("server.log")
            self.server = subprocess.Popen(
                [sys.executable, "-c", "from config.wsgi import application; from waitress import serve; serve(application, listen='127.0.0.1:8001', url_scheme='https', ident='', clear_untrusted_proxy_headers=True, max_request_body_size=12582912)"],
                cwd=ROOT / "backend", env=environment, stdout=server_log, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, creationflags=CREATE_FLAGS,
            )
            self.update(server_pid=self.server.pid, host=host)
            self.wait_for_http(f"http://127.0.0.1:{PORT}/healthz", host=host)
            self.update(stage="Checking the public HTTPS link")
            self.wait_for_http(f"https://{host}/healthz", timeout=90)
            links = f"Website: https://{host}/\nEditor: https://{host}/admin/\n\nLogin: backend/.local/shared-demo/access.txt\n\nThis temporary link works only while this PC and the demo launcher are running.\nRestarting creates a new URL and retains the demo content and login.\n"
            (STATE / "links.txt").write_text(links, encoding="utf-8")
            self.update(state="ready", stage="Ready", website=f"https://{host}/", editor=f"https://{host}/admin/")
            next_health_check = time.monotonic() + HEALTH_CHECK_INTERVAL
            while True:
                self.check_children()
                if time.monotonic() >= next_health_check:
                    self.refresh_public_health()
                    next_health_check = time.monotonic() + HEALTH_CHECK_INTERVAL
                time.sleep(1)
        except (StopRequested, KeyboardInterrupt):
            self.update(state="stopping", stage="Closing the temporary demo")
            return 0
        except Exception as error:
            # Exceptions contain setup stages or public URLs, never credentials.
            self.update(state="failed", stage="Stopped", error=str(error))
            return 1
        finally:
            self.sleep_guard.close()
            self.status.update(self.sleep_guard.status())
            stop_process(self.server)
            stop_process(self.tunnel)
            for stream in self.files:
                stream.close()
            if self.status.get("state") != "failed":
                self.update(state="stopped", stage="Stopped")
            self.status.pop("website", None)
            self.status.pop("editor", None)
            atomic_json(STATUS, self.status)
            (STATE / "links.txt").write_text("The temporary demo is stopped. Run start-shareable-demo.ps1 to obtain a new link.\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--supervise", action="store_true")
    mode.add_argument("--status", action="store_true")
    mode.add_argument("--stop", action="store_true")
    arguments = parser.parse_args()
    if arguments.status:
        print(json.dumps(current_status()))
        return 0
    if arguments.stop:
        if not running():
            print("The shared demo is already stopped.")
            return 0
        status = read_status()
        if not status.get("run_id"):
            print("The demo is still starting; retry in a moment.")
            return 1
        atomic_json(STOP, {"run_id": status["run_id"]})
        print("The shared demo is stopping.")
        return 0
    lock = SupervisorLock()
    if not lock.acquire():
        print("A shared demo is already running.")
        return 1
    try:
        return Demo().run()
    finally:
        lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
