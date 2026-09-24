"""Exercise the authenticated uploader and the separately restricted media server."""

from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice
from PIL import Image as PillowImage
from wagtail.images import get_image_model
from wagtail.models import Collection, Page

from content.models import ArticlePage, LegacyPage


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class UploadSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(username="upload-admin", password="Upload-test-password-71!")
        cls.device = TOTPDevice.objects.create(user=cls.user, name="default", confirmed=True)

    def setUp(self):
        self.media_dir = TemporaryDirectory(prefix="kontturi-test-media-")
        self.addCleanup(self.media_dir.cleanup)
        self.media_settings = override_settings(MEDIA_ROOT=Path(self.media_dir.name))
        self.media_settings.enable()
        self.addCleanup(self.media_settings.disable)
        self.verify_client(self.client)

    def verify_client(self, client):
        client.force_login(self.user)
        session = client.session
        session[DEVICE_ID_SESSION_KEY] = self.device.persistent_id
        session.save()

    def upload(self, name, body, content_type="image/png", client=None):
        return (client or self.client).post(
            reverse("wagtailimages:add"),
            {"title": "Security upload test", "collection": Collection.get_first_root_node().pk, "file": SimpleUploadedFile(name, body, content_type=content_type)},
        )

    @staticmethod
    def png_bytes():
        data = BytesIO()
        PillowImage.new("RGB", (4, 4), "white").save(data, format="PNG")
        return data.getvalue()

    def test_valid_raster_image_can_be_uploaded_and_served(self):
        response = self.upload("safe.png", self.png_bytes())
        self.assertEqual(response.status_code, 302)
        uploaded = get_image_model().objects.get(title="Security upload test")
        response = self.client.get(uploaded.file.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "image/png")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        response.close()

    def test_active_svg_and_html_are_rejected_even_with_spoofed_extensions(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4" onload="alert(1)"><script>alert(1)</script></svg>'
        html = b'<html><script>alert(document.cookie)</script></html>'
        attacks = (
            ("active.svg", svg, "image/svg+xml"),
            ("active.png", svg, "image/png"),
            ("active.html", html, "text/html"),
            ("active.png", html, "image/png"),
            ("active.html", self.png_bytes(), "image/png"),
        )
        before = get_image_model().objects.count()
        for name, body, content_type in attacks:
            with self.subTest(name=name, content_type=content_type):
                response = self.upload(name, body, content_type)
                self.assertEqual(response.status_code, 200)
                self.assertIn("file", response.context["form"].errors)
                self.assertEqual(get_image_model().objects.count(), before)

    def test_oversized_image_is_rejected(self):
        response = self.upload("oversized.png", self.png_bytes() + b"\0" * (8 * 1024 * 1024))
        self.assertEqual(response.status_code, 200)
        self.assertIn("file", response.context["form"].errors)
        self.assertEqual(get_image_model().objects.filter(title="Security upload test").count(), 0)

    def test_authenticated_image_upload_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.verify_client(client)
        before = get_image_model().objects.count()
        response = self.upload("csrf.png", self.png_bytes(), client=client)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(get_image_model().objects.count(), before)

    def test_existing_image_bytes_cannot_be_replaced_outside_page_publication(self):
        self.assertEqual(self.upload("published.png", self.png_bytes()).status_code, 302)
        uploaded = get_image_model().objects.get(title="Security upload test")
        original_name = uploaded.file.name
        original_bytes = uploaded.file.read()
        uploaded.file.close()
        replacement = BytesIO()
        PillowImage.new("RGB", (4, 4), "red").save(replacement, format="PNG")
        response = self.client.post(
            reverse("wagtailimages:edit", args=[uploaded.pk]),
            {"title": uploaded.title, "collection": uploaded.collection_id, "file": SimpleUploadedFile("replacement.png", replacement.getvalue(), content_type="image/png")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("file", response.context["form"].errors)
        uploaded.refresh_from_db()
        self.assertEqual(uploaded.file.name, original_name)
        with uploaded.file.open("rb") as stored:
            self.assertEqual(stored.read(), original_bytes)

    def test_document_upload_is_disabled_even_for_admin(self):
        response = self.client.post("/admin/documents/add/", {"title": "Disallowed document", "file": SimpleUploadedFile("active.html", b"<script>alert(1)</script>", content_type="text/html")})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get("/documents/1/active.html").status_code, 404)

    def test_editor_cannot_delete_own_published_image_through_any_delete_endpoint(self):
        home = Page.get_first_root_node().add_child(instance=LegacyPage(title="Image permission home", slug="image-permission-home", source_file="index.html"))
        news = home.add_child(instance=LegacyPage(title="Image permission news", slug="image-permission-news", source_file="ajankohtaista.html"))
        call_command("setup_roles", stdout=StringIO())
        self.user = get_user_model().objects.create_user(username="image-owner-editor", password="Image-owner-test-password-17!")
        self.user.groups.add(Group.objects.get(name="Sisällöntuottajat"))
        self.device = TOTPDevice.objects.create(user=self.user, name="default", confirmed=True)
        self.verify_client(self.client)
        original_bytes = self.png_bytes()
        self.assertEqual(self.upload("published-owned.png", original_bytes).status_code, 302)
        uploaded = get_image_model().objects.get(title="Security upload test")
        self.assertEqual(uploaded.uploaded_by_user_id, self.user.pk)
        article = news.add_child(instance=ArticlePage(title="Uses owned image", slug="uses-owned-image", intro="Public intro", body="<p>Public body</p>", cover_image=uploaded))
        article.save_revision().publish()
        bulk_url = reverse("wagtail_bulk_action", kwargs={"app_label": "wagtailimages", "model_name": "image", "action": "delete"})
        paths = (
            reverse("wagtailimages:delete", args=[uploaded.pk]),
            reverse("wagtailimages:delete_multiple", args=[uploaded.pk]),
            f"{bulk_url}?id={uploaded.pk}",
        )
        for path in paths:
            with self.subTest(path=path):
                response = self.client.post(path, {"confirm": "yes"})
                self.assertEqual(response.status_code, 403)
                self.assertTrue(get_image_model().objects.filter(pk=uploaded.pk).exists())
                article.refresh_from_db()
                self.assertEqual(article.cover_image_id, uploaded.pk)
                with uploaded.file.open("rb") as stored:
                    self.assertEqual(stored.read(), original_bytes)

    def test_media_server_does_not_serve_active_files_even_if_present_on_disk(self):
        originals = Path(self.media_dir.name) / "original_images"
        originals.mkdir()
        for name in ("active.svg", "active.html", "secret.py"):
            (originals / name).write_text("<script>alert(1)</script>", encoding="utf-8")
            with self.subTest(name=name):
                self.assertEqual(self.client.get(f"/media/original_images/{name}").status_code, 404)

    def test_media_traversal_cannot_read_file_outside_permitted_subdirectory(self):
        (Path(self.media_dir.name) / "private.png").write_bytes(self.png_bytes())
        for name in ("original_images/../private.png", "original_images/%2e%2e/private.png", "original_images/..%5cprivate.png"):
            with self.subTest(path=name):
                self.assertEqual(self.client.get("/media/" + name).status_code, 404)
