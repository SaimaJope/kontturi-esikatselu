"""Check that decorative video allows updates while user activity stays protected."""
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "backend/content/static/content/demo-live.js"
VIDEO = ROOT / "assets/office-meeting.mp4"
ORIGIN = "http://refresh.test"


def verify(browser, *, background, edit_form=False):
    state = {"documents": 0, "changed": False, "checks": 0}
    attributes = 'class="hero-video" aria-hidden="true"' if background else "controls"

    def route(request):
        path = request.request.url.removeprefix(ORIGIN)
        if path == "/video.mp4":
            request.fulfill(path=str(VIDEO), content_type="video/mp4")
        elif path == "/live.js":
            request.fulfill(path=str(SCRIPT), content_type="application/javascript")
        elif path == "/__demo/version":
            state["checks"] += 1
            request.fulfill(json={"version": ("b" if state["changed"] else "a") * 64})
        else:
            state["documents"] += 1
            version = ("b" if state["changed"] else "a") * 64
            request.fulfill(content_type="text/html", body=f"""<!doctype html>
                <video {attributes} muted loop autoplay src="/video.mp4"></video>
                <input aria-label="Message"><p>Public content</p>
                <script src="/live.js" data-version="{version}" data-version-url="/__demo/version"></script>""")

    context = browser.new_context()
    context.route(ORIGIN + "/**", route)
    page = context.new_page()
    page.goto(ORIGIN + "/", wait_until="networkidle")
    page.wait_for_function("!document.querySelector('video').paused && document.querySelector('video').readyState >= 2")
    if edit_form:
        page.get_by_role("textbox", name="Message").fill("Keep this unsent message")
    state["changed"] = True
    previous_checks = state["checks"]
    if background and not edit_form:
        with page.expect_navigation(wait_until="networkidle"):
            page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        assert state["documents"] == 2, "Background video blocked the public update."
    else:
        page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        page.wait_for_timeout(500)
        assert state["checks"] > previous_checks, "The update check did not run."
        assert state["documents"] == 1, "User interaction was interrupted."
        if edit_form:
            assert page.get_by_role("textbox", name="Message").input_value() == "Keep this unsent message"
    context.close()


with sync_playwright() as driver:
    browser = driver.chromium.launch(headless=True)
    verify(browser, background=True)
    verify(browser, background=False)
    verify(browser, background=True, edit_form=True)
    browser.close()
print("Passed: playing background video permits refresh; content video and unsent input prevent refresh.")
