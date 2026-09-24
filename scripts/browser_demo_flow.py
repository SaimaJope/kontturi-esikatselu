"""Prove draft -> publish -> automatic public refresh in the running demo.

Run with the same KONTTURI_ENV/KONTTURI_DEMO_HOST as the demo server. This
creates and removes its own limited publisher account and test article. Login
uses the real authenticator enrollment flow. Credentials never enter reports.
Screenshots and the result are written only to ignored test-results/.
"""

import json
import os
import secrets
import sys
import time
import uuid
from base64 import b32decode
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

import django

django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice
from playwright.sync_api import expect, sync_playwright

from content.models import ArticlePage


if settings.ENVIRONMENT not in {"local", "demo"} or not settings.CMS_DEMO_MODE:
    raise SystemExit("Browser demo checks cannot run against production.")

BASE_URL = settings.WAGTAILADMIN_BASE_URL.rstrip("/")
origin = urlsplit(BASE_URL)
if settings.LOCAL_DEMO:
    if origin.scheme != "http" or origin.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit("Local demo checks require a loopback CMS_BASE_URL.")
elif origin.scheme != "https" or origin.hostname not in settings.ALLOWED_HOSTS:
    raise SystemExit("Shared demo checks require the configured HTTPS demo origin.")

output = ROOT / "test-results"
output.mkdir(exist_ok=True)
tag = uuid.uuid4().hex[:12]
username = "demo-flow-" + tag
password = secrets.token_urlsafe(30)
title = "Julkaisudemo " + tag
body = "Tämä artikkeli tallennettiin luonnoksena ja julkaistiin sisällönhallinnasta."
sensitive_values = [password]
report = {
    "result": "failed",
    "base_url": BASE_URL,
    "account_role": "Julkaisijat (not superuser)",
    "checks": [],
    "browser_errors": [],
    "screenshots": [],
}
stage = "Create temporary publisher"
user = None
public_page = None


def safe_text(value):
    text = str(value)
    for secret in sensitive_values:
        text = text.replace(secret, "[redacted]")
    return text


def collect_errors(page, label):
    page.on("pageerror", lambda error: report["browser_errors"].append(
        {"page": label, "error": safe_text(error)}
    ))
    page.on("console", lambda message: report["browser_errors"].append(
        {"page": label, "error": safe_text(message.text)}
    ) if message.type == "error" else None)


def screenshot(page, filename):
    page.screenshot(path=str(output / filename), full_page=True)
    report["screenshots"].append(filename)


def click_editor_action(page, name):
    action = page.locator("footer button.action-save" if name == "action-save-draft"
                          else f'button[name="{name}"]')
    if not action.is_visible():
        page.locator('footer [data-w-dropdown-target="toggle"]').click()
    with page.expect_navigation(wait_until="networkidle"):
        action.click()


try:
    group = Group.objects.get(name="Julkaisijat")
    user = get_user_model().objects.create_user(
        username=username, password=password, email=username + "@example.invalid",
    )
    user.groups.add(group)
    assert not user.is_superuser and not user.is_staff
    assert user.has_perm("wagtailadmin.access_admin")

    with sync_playwright() as driver:
        # Separate browsers keep both windows visible while the editor is used;
        # the public browser never receives the publisher's session cookies.
        editor_browser = driver.chromium.launch(headless=True)
        public_browser = driver.chromium.launch(headless=True)
        try:
            editor_context = editor_browser.new_context(
                viewport={"width": 1440, "height": 1050}, reduced_motion="reduce",
            )
            public_context = public_browser.new_context(
                viewport={"width": 1440, "height": 1050}, reduced_motion="reduce",
            )
            editor = editor_context.new_page()
            public_page = public_context.new_page()
            collect_errors(editor, "editor")
            collect_errors(public_page, "public")
            editor.set_default_timeout(30000)
            public_page.set_default_timeout(30000)

            stage = "Real first login and authenticator enrollment"
            editor.goto(BASE_URL + "/admin/", wait_until="networkidle")
            screenshot(editor, "demo-flow-login.png")
            editor.locator('input[name="auth-username"]').fill(username)
            editor.locator('input[name="auth-password"]').fill(password)
            editor.locator('button[type="submit"]').last.click()
            editor.wait_for_url("**/account/two_factor/setup/")
            editor.locator('button[type="submit"]').last.click()
            enrollment_key = editor.locator(".auth-secret code").text_content().strip()
            sensitive_values.append(enrollment_key)
            enrollment_bytes = b32decode(enrollment_key)
            assert len(enrollment_bytes) == 20, "Unexpected authenticator key format"
            qr_deadline = time.monotonic() + 30
            while not editor.locator(".auth-qr img").evaluate(
                "image => image.complete && image.naturalWidth > 0"
            ):
                assert time.monotonic() < qr_deadline, "Authenticator QR image did not load"
                editor.wait_for_timeout(100)
            token = str(totp(enrollment_bytes)).zfill(6)
            sensitive_values.append(token)
            editor.locator('input[name="generator-token"]').fill(token)
            with editor.expect_navigation(wait_until="networkidle"):
                editor.locator('button[type="submit"]').last.click()
            assert TOTPDevice.objects.filter(user=user, confirmed=True).exists()
            editor.goto(BASE_URL + "/admin/", wait_until="networkidle")
            expect(editor.get_by_text("Mitä päivitetään tänään?", exact=True)).to_be_visible()
            screenshot(editor, "demo-flow-dashboard.png")
            report["checks"].append("Limited publisher completed real first login and TOTP enrollment")

            stage = "Open anonymous public news page"
            public_navigations = []
            public_page.on("framenavigated", lambda frame: public_navigations.append(frame.url)
                           if frame.parent_frame is None else None)
            response = public_page.goto(BASE_URL + "/ajankohtaista.html", wait_until="networkidle")
            assert response.status == 200
            assert public_page.evaluate("document.visibilityState") == "visible"
            refresh_script = public_page.locator('script[data-version-url="/__demo/version"]')
            baseline = refresh_script.get_attribute("data-version")
            assert baseline and len(baseline) == 64
            assert public_context.request.get(BASE_URL + "/__demo/version").json()["version"] == baseline
            navigation_count = len(public_navigations)
            screenshot(public_page, "demo-flow-public-before.png")
            report["checks"].append("Anonymous public page opened with automatic-refresh script")

            stage = "Create and save draft through editor"
            editor.get_by_text("Uusi artikkeli", exact=True).click()
            editor.wait_for_load_state("networkidle")
            editor.locator("#id_title").fill(title)
            editor.locator("#id_intro").fill("Toimivan sisällönhallinnan ja julkaisun esittely.")
            rich_text = editor.locator('[contenteditable="true"]').first
            rich_text.click()
            rich_text.press_sequentially(body)
            editor.locator("#id_intro").click()
            click_editor_action(editor, "action-save-draft")
            article = ArticlePage.objects.get(title=title, owner=user)
            assert not article.live, "Saving a draft unexpectedly published it"
            assert public_context.request.get(BASE_URL + article.url).status == 404
            assert public_context.request.get(BASE_URL + "/__demo/version").json()["version"] == baseline
            # Observe a real automatic polling response while the article is a
            # draft. No navigation/reload is invoked on the public page here.
            with public_page.expect_response("**/__demo/version", timeout=20000) as polling:
                pass
            assert polling.value.status == 200
            assert polling.value.json()["version"] == baseline
            assert len(public_navigations) == navigation_count
            expect(public_page.get_by_role("heading", name=title, exact=True)).to_have_count(0)
            report["checks"].append("Saved draft remained private and did not change the public version or reload the page")

            stage = "Publish saved draft through editor"
            editor.goto(BASE_URL + f"/admin/pages/{article.pk}/edit/", wait_until="networkidle")
            screenshot(editor, "demo-flow-draft-editor.png")
            assert public_page.evaluate("document.visibilityState") == "visible"
            published_at = time.monotonic()
            click_editor_action(editor, "action-publish")
            article.refresh_from_db()
            assert article.live, "Browser publish action did not publish the article"
            report["checks"].append("The same draft was published using the editor's Publish action")

            stage = "Observe automatic public refresh without manual navigation"
            expect(public_page.get_by_role("heading", name=title, exact=True)).to_be_visible(timeout=45000)
            elapsed = round(time.monotonic() - published_at, 2)
            assert elapsed <= 45, "Public page took more than 45 seconds to refresh"
            assert len(public_navigations) > navigation_count, "No automatic page navigation was observed"
            assert all(urlsplit(url).path == "/ajankohtaista.html" for url in public_navigations)
            refreshed_version = refresh_script.get_attribute("data-version")
            assert refreshed_version != baseline
            assert public_context.request.get(BASE_URL + "/__demo/version").json()["version"] == refreshed_version
            screenshot(public_page, "demo-flow-public-after.png")
            report["automatic_refresh_seconds"] = elapsed
            report["public_page_automatic_reloads"] = len(public_navigations) - navigation_count
            report["checks"].append("Already-open anonymous page displayed the published article automatically within 45 seconds")

            stage = "Verify published article content"
            article_page = public_context.new_page()
            collect_errors(article_page, "article")
            article_response = article_page.goto(BASE_URL + article.url, wait_until="networkidle")
            assert article_response.status == 200
            expect(article_page.get_by_text(body, exact=True)).to_be_visible()
            screenshot(article_page, "demo-flow-published-article.png")
            report["checks"].append("Published article URL contains the body entered in the browser")
            assert not report["browser_errors"], "Browser reported JavaScript or console errors"
            report["result"] = "passed"
        finally:
            editor_browser.close()
            public_browser.close()
except Exception as error:
    report["failure"] = {"stage": stage, "type": type(error).__name__, "message": safe_text(error)}
finally:
    if user is not None:
        try:
            for article in ArticlePage.objects.filter(owner=user, title=title):
                article.delete()
            user.delete()
            report["temporary_records_removed"] = True
        except Exception as error:
            report["result"] = "failed"
            report["cleanup_error"] = safe_text(error)
    (output / "demo-flow-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )

print(json.dumps(report, ensure_ascii=True))
if report["result"] != "passed":
    raise SystemExit(1)
