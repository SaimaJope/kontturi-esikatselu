"""The demo refresh signal follows public publication boundaries."""

from bs4 import BeautifulSoup
from django.contrib.staticfiles import finders
from django.test import RequestFactory, TestCase, override_settings
from wagtail.models import Page, PageViewRestriction, Site

from content.demo import published_version
from content.models import ArticlePage, LegacyPage, Office, Person, SiteProfile
from content.rendering import render_article, render_legacy


@override_settings(
    CMS_DEMO_MODE=True,
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class DemoRefreshTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.home = Page.objects.get(depth=1).add_child(instance=LegacyPage(
            title="Demo home", slug="demo-home", source_file="index.html",
        ))
        cls.home.save_revision().publish()
        cls.news = cls.home.add_child(instance=LegacyPage(
            title="Ajankohtaista", slug="ajankohtaista", source_file="ajankohtaista.html",
        ))
        cls.news.save_revision().publish()
        cls.article = cls.news.add_child(instance=ArticlePage(
            title="Published article", slug="published-article", intro="Introduction",
            body="<p>Published article content</p>", legacy_file="published-article.html",
        ))
        cls.article.save_revision().publish()
        Site.objects.all().delete()
        Site.objects.create(hostname="testserver", root_page=cls.home, is_default_site=True)

    def token(self):
        response = self.client.get("/__demo/version")
        self.assertEqual(response.status_code, 200)
        return response.json()["version"]

    def test_endpoint_only_exposes_uncacheable_opaque_version(self):
        response = self.client.get("/__demo/version")
        self.assertEqual(set(response.json()), {"version"})
        self.assertRegex(response.json()["version"], r"^[a-f0-9]{64}$")
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(response.json()["version"], published_version())
        self.assertEqual(self.client.post("/__demo/version").status_code, 405)
        self.assertEqual(self.client.head("/__demo/version").status_code, 405)

    def test_saved_draft_does_not_signal_change_but_publication_does(self):
        original = self.token()
        self.article.body = "<p>Unpublished private draft</p>"
        revision = self.article.save_revision()
        self.assertEqual(self.token(), original)
        revision.publish()
        self.assertNotEqual(self.token(), original)
        self.assertContains(self.client.get("/published-article.html"), "Unpublished private draft")

    def test_new_unpublished_article_is_not_in_version(self):
        original = self.token()
        draft = self.news.add_child(instance=ArticlePage(
            title="Private draft", slug="private-draft", intro="Private introduction",
            body="<p>Private content</p>", live=False,
        ))
        draft.save_revision()
        self.assertEqual(self.token(), original)

    def test_unpublishing_or_restricting_article_changes_version(self):
        original = self.token()
        restriction = PageViewRestriction.objects.create(page=self.article, restriction_type="login")
        self.assertNotEqual(self.token(), original)
        restriction.delete()
        self.assertEqual(self.token(), original)
        self.article.unpublish()
        self.assertNotEqual(self.token(), original)

    def test_immediately_public_shared_content_changes_version(self):
        person = Person.objects.create(
            identifier="demo-person", name="Demo person", role="Lawyer",
            phone="010 123 4567", tel="+358101234567", email="demo@example.invalid",
            profile_slug="demo-person",
        )
        office = Office.objects.create(
            identifier="demo-office", name="Demo office", street="Example 1",
            postal="00100 Helsinki", phone="010 123 4567", tel="+358101234567",
            hours="9–17",
        )
        profile = SiteProfile.objects.create(
            name="Demo office", email="demo@example.invalid", on_call_phone="010 123 4567",
            on_call_tel="+358101234567",
        )
        for obj, field, value in (
            (person, "role", "Updated role"),
            (office, "hours", "10–18"),
            (profile, "email", "changed@example.invalid"),
        ):
            with self.subTest(model=type(obj).__name__):
                original = self.token()
                setattr(obj, field, value)
                obj.save(update_fields=[field])
                self.assertNotEqual(self.token(), original)

    def test_both_public_layouts_include_actual_script_and_baseline(self):
        self.assertIsNotNone(finders.find("content/demo-live.js"))
        for url in ("/", "/published-article.html"):
            with self.subTest(url=url):
                document = BeautifulSoup(self.client.get(url).content, "html.parser")
                script = document.find("script", src="/static/content/demo-live.js")
                self.assertIsNotNone(script)
                self.assertEqual(script["data-version"], self.token())
                self.assertEqual(script["data-version-url"], "/__demo/version")
                self.assertFalse(script.string)

    def test_preview_does_not_refresh_itself_to_published_content(self):
        request = RequestFactory().get("/admin/preview/")
        request.is_preview = True
        self.assertNotIn("content/demo-live.js", render_legacy(self.home, request))
        self.assertNotIn("content/demo-live.js", render_article(self.article, request))

    @override_settings(CMS_DEMO_MODE=False)
    def test_production_has_neither_endpoint_nor_polling_script(self):
        self.assertEqual(self.client.get("/__demo/version").status_code, 404)
        self.assertNotContains(self.client.get("/"), "content/demo-live.js")
        self.assertNotContains(self.client.get("/published-article.html"), "content/demo-live.js")
