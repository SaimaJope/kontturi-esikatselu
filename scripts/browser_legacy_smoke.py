"""Check fixed page widgets and publication as a limited local publisher.

Runs its own temporary server, removes its QA user/revisions and restores the
original live page. Never changes the separate shared-demo database/account.
"""
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

import django
django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice
from playwright.sync_api import expect, sync_playwright

from content.models import LegacyPage

if not settings.LOCAL_DEMO:
    raise SystemExit("This regression check is restricted to the local demo database.")

output = ROOT / "test-results"
output.mkdir(exist_ok=True)
base = "http://127.0.0.1:8002"
home = LegacyPage.objects.get(source_file="index.html")
text_index, edited_text = next(
    (index, row) for index, row in enumerate(home.texts.order_by("sort_order"))
    if row.label.startswith("Pääotsikko")
)
original_live = home.live_revision
if original_live is None:
    raise SystemExit("The seeded homepage must have a published revision.")
original_state = {
    key: getattr(home, key) for key in (
        "latest_revision_id", "live_revision_id", "has_unpublished_changes",
        "latest_revision_created_at", "last_published_at",
    )
}
tag = secrets.token_hex(6)
marker = "Sivun julkaisutesti " + tag
user = get_user_model().objects.create_user("legacy-check-" + tag, password=secrets.token_urlsafe(30))
user.groups.add(Group.objects.get(name="Julkaisijat"))
device = TOTPDevice.objects.create(user=user, name="default", confirmed=True)
client = Client()
client.force_login(user)
session = client.session
session[DEVICE_ID_SESSION_KEY] = device.persistent_id
session.save()
errors = []

try:
    with (output / "legacy-server.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen(
            [sys.executable, "backend/manage.py", "runserver", "127.0.0.1:8002", "--noreload", "--nostatic"],
            cwd=ROOT, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            for attempt in range(50):
                try:
                    urllib.request.urlopen(base + "/healthz", timeout=1).close()
                    break
                except Exception:
                    if server.poll() is not None:
                        raise RuntimeError("The temporary test server did not start.")
                    time.sleep(0.2)
            else:
                raise RuntimeError("The temporary test server did not become ready.")
            with sync_playwright() as driver:
                browser = driver.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1440, "height": 1050})
                context.add_cookies([{"name": "sessionid", "value": session.session_key, "url": base}])
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(error.stack))
                page.goto(base + "/admin/images/", wait_until="networkidle")
                assert page.locator('a[href*="/admin/images/"][href$="/"] img').count() > 0
                page.screenshot(path=str(output / "publisher-image-library.png"), full_page=True)

                page.goto(base + f"/admin/pages/{home.pk}/edit/", wait_until="networkidle")
                page.locator(f'[name="texts-{text_index}-value"]').fill(marker)
                page.locator('.image-chooser .chooser__choose-button').first.click()
                chooser_image = page.locator('.modal-content a[href*="/chooser/chosen/"]').first
                expect(chooser_image).to_be_visible()
                chooser_image.click()
                expect(page.locator('.modal-content')).not_to_be_visible()
                image_id = page.locator('[name="images-0-image"]').input_value()
                assert image_id.isdigit()
                page.screenshot(path=str(output / "legacy-page-editor.png"), full_page=True)

                with page.expect_navigation(wait_until="networkidle"):
                    page.locator('footer button.action-save').first.click()
                home.refresh_from_db()
                assert home.texts.get(pk=edited_text.pk).value != marker
                assert home.get_latest_revision_as_object().texts.get(id=edited_text.pk).value == marker
                page.goto(base + f"/admin/pages/{home.pk}/edit/", wait_until="networkidle")
                publish = page.locator('button[name="action-publish"]')
                if not publish.is_visible():
                    page.locator('footer [data-w-dropdown-target="toggle"]').click()
                with page.expect_navigation(wait_until="networkidle"):
                    publish.click()
                home.refresh_from_db()
                assert home.texts.get(pk=edited_text.pk).value == marker
                assert str(home.images.order_by("sort_order").first().image_id) == image_id
                page.goto(base + "/", wait_until="networkidle")
                assert marker in page.content()
                assert not errors, errors
                browser.close()
        finally:
            server.terminate()
            server.wait(timeout=20)
finally:
    home.refresh_from_db()
    if home.live_revision_id != original_live.pk:
        original_live.publish()
    LegacyPage.objects.filter(pk=home.pk).update(**original_state)
    home.revisions.filter(user=user).delete()
    client.logout()
    user.delete()
    (output / "legacy-browser-errors.json").write_text(json.dumps(errors, indent=2), encoding="utf-8")

print("Passed: limited publisher image library, fixed page widgets, image chooser, private draft, text and image publication; original page restored; no browser errors.")
