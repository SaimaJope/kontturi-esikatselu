"""Exercise the local editor in Chromium; screenshots go to ignored test-results.

Run after starting the local server, using the project's Python environment.
This creates and removes its own QA account and article, never the demo account.
"""
import json
import os
import secrets
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
import django
django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django_otp.plugins.otp_totp.models import TOTPDevice
from playwright.sync_api import sync_playwright
from content.models import ArticlePage, LegacyPage

if not settings.LOCAL_DEMO:
    raise SystemExit("Browser smoke checks may only run against the local demonstration.")

output = ROOT / "test-results"
output.mkdir(exist_ok=True)
tag = uuid.uuid4().hex[:12]
username = "browser-check-" + tag
password = secrets.token_urlsafe(30)
user = get_user_model().objects.create_superuser(username=username, password=password, email=username + "@localhost")
news = LegacyPage.objects.get(source_file="ajankohtaista.html")
errors = []

try:
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1050}, reduced_motion="reduce")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        response = page.goto("http://127.0.0.1:8000/", wait_until="networkidle")
        assert response.status == 200
        page.screenshot(path=str(output / "website.png"))
        page.goto("http://127.0.0.1:8000/admin/", wait_until="networkidle")
        page.screenshot(path=str(output / "login.png"), full_page=True)
        page.locator('input[name="username"]').fill(username)
        page.locator('input[name="password"]').fill(password)
        with page.expect_navigation(wait_until="networkidle"):
            page.locator('button[type="submit"]').last.click()
        assert not TOTPDevice.objects.filter(user=user).exists()
        assert page.url == "http://127.0.0.1:8000/admin/"
        page.wait_for_load_state("networkidle")
        assert page.get_by_text("Mitä päivitetään tänään?").is_visible()
        page.screenshot(path=str(output / "editor-dashboard.png"), full_page=True)
        page.get_by_text("Uusi artikkeli", exact=True).click()
        page.wait_for_load_state("networkidle")
        page.locator('#id_title').fill("Selainkoe " + tag)
        page.locator('#id_intro').fill("Sisällönhallinnan paikallinen julkaisutesti.")
        page.locator('[contenteditable="true"]').first.click()
        page.locator('[contenteditable="true"]').first.press_sequentially("Tämä teksti kirjoitettiin selaimessa ja julkaistaan testinä.")
        page.locator('#id_intro').click()
        page.screenshot(path=str(output / "article-editor.png"), full_page=True)
        # Wagtail keeps publish as a secondary action in its action menu.
        publish = page.locator('button[name="action-publish"]')
        if not publish.is_visible():
            page.locator('footer [data-w-dropdown-target="toggle"]').click()
        with page.expect_navigation(wait_until="networkidle"):
            publish.click()
        page.screenshot(path=str(output / "after-publish.png"), full_page=True)
        print("Publish response URL:", page.url)
        article = ArticlePage.objects.get(title="Selainkoe " + tag)
        assert article.live, "Publish action did not publish the article"
        page.goto("http://127.0.0.1:8000" + article.url, wait_until="networkidle")
        assert page.get_by_text("Tämä teksti kirjoitettiin selaimessa ja julkaistaan testinä.").is_visible()
        page.screenshot(path=str(output / "published-article.png"), full_page=True)
        page.goto("http://127.0.0.1:8000/ajankohtaista.html", wait_until="networkidle")
        assert page.get_by_role("heading", name="Selainkoe " + tag).is_visible()
        context.clear_cookies()
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto("http://127.0.0.1:8000/account/login/", wait_until="networkidle")
        page.screenshot(path=str(output / "login-mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        browser.close()
    report = {"result": "passed", "checks": ["public homepage", "password login without authenticator enrollment", "admin dashboard", "create and publish article in browser", "article listing", "mobile login"], "browser_errors": errors}
    (output / "browser-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))
    if errors:
        raise SystemExit("Browser errors detected; review test-results/browser-report.json")
finally:
    (output / "browser-errors.json").write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")
    for article in ArticlePage.objects.filter(title="Selainkoe " + tag):
        article.delete()
    user.delete()
