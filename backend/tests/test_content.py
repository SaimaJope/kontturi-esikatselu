"""Publication boundaries and hostile content are checked through public URLs."""

from bs4 import BeautifulSoup
from django.test import TestCase, override_settings
from wagtail.models import Page, PageViewRestriction, Site

from content.models import ArticlePage, LegacyBlock, LegacyPage, LegacyText, Person


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class ContentSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.home = Page.objects.get(depth=1).add_child(
            instance=LegacyPage(title="Security home", slug="security-home", source_file="index.html")
        )
        cls.news = cls.home.add_child(
            instance=LegacyPage(title="Ajankohtaista", slug="ajankohtaista", source_file="ajankohtaista.html")
        )
        Site.objects.all().delete()
        Site.objects.create(hostname="testserver", root_page=cls.home, is_default_site=True)
        cls.article = cls.news.add_child(
            instance=ArticlePage(
                title="Public security test article",
                slug="security-test",
                intro="Public introduction",
                body="<p>Published body marker</p>",
                legacy_file="security-test.html",
            )
        )
        cls.article.save_revision().publish()

    def article_urls(self):
        return ("/security-test.html", "/ajankohtaista/security-test/")

    def test_published_article_is_available_under_both_urls(self):
        for url in self.article_urls():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, "Published body marker")

    def test_new_draft_is_private_under_both_urls(self):
        self.article.unpublish()
        for url in self.article_urls():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 404)
                self.assertNotContains(response, "Published body marker", status_code=404)

    def test_saved_unpublished_revision_does_not_replace_live_article(self):
        self.article.body = "<p>PRIVATE-DRAFT-DO-NOT-DISCLOSE</p>"
        self.article.save_revision()
        for url in self.article_urls():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, "Published body marker")
                self.assertNotContains(response, "PRIVATE-DRAFT-DO-NOT-DISCLOSE")

    def test_legacy_alias_does_not_bypass_page_restrictions(self):
        PageViewRestriction.objects.create(page=self.article, restriction_type="login")
        response = self.client.get("/security-test.html")
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "Published body marker", status_code=404)

    def test_parent_restrictions_apply_to_legacy_article_alias(self):
        PageViewRestriction.objects.create(page=self.news, restriction_type="login")
        response = self.client.get("/security-test.html")
        self.assertEqual(response.status_code, 404)

    def test_private_home_is_not_served_by_root_alias(self):
        PageViewRestriction.objects.create(page=self.home, restriction_type="login")
        self.assertEqual(self.client.get("/").status_code, 404)

    def test_rich_text_sanitizes_stored_active_content(self):
        self.article.body = (
            '<p onclick="window.storedAttack=1">Safe text</p>'
            '<script id="attack-script">window.storedAttack=2</script>'
            '<a id="attack-link" href="javascript:alert(1)">Unsafe link</a>'
            '<a href="https://kontturi.fi/">Safe link</a>'
            '<img id="attack-image" src="missing" onerror="alert(1)">'
            '<svg id="attack-svg" onload="alert(1)"><script>alert(1)</script></svg>'
            '<iframe id="attack-frame" src="https://attacker.invalid/"></iframe>'
            '<form id="attack-form" action="https://attacker.invalid/"><input name="password"></form>'
        )
        self.article.save_revision().publish()
        response = self.client.get("/security-test.html")
        self.assertEqual(response.status_code, 200)
        document = BeautifulSoup(response.content, "html.parser")
        self.assertIn("Safe text", document.get_text())
        for marker in ("attack-script", "attack-image", "attack-svg", "attack-frame", "attack-form"):
            self.assertIsNone(document.find(id=marker))
        for element in document.find_all(True):
            self.assertFalse(any(key.lower().startswith("on") for key in element.attrs), element)
            for attribute in ("href", "src", "action"):
                self.assertFalse(str(element.get(attribute, "")).lower().startswith("javascript:"), element)
        self.assertIsNotNone(document.find("a", href="https://kontturi.fi/"))

    def test_article_metadata_is_escaped_as_text(self):
        self.article.title = '<img id="title-attack" src=x onerror=alert(1)>'
        self.article.intro = '<script id="intro-attack">alert(1)</script>'
        self.article.category = '<svg id="category-attack" onload=alert(1)>'
        self.article.save_revision().publish()
        document = BeautifulSoup(self.client.get("/security-test.html").content, "html.parser")
        for marker in ("title-attack", "intro-attack", "category-attack"):
            self.assertIsNone(document.find(id=marker))
        self.assertIn(self.article.title, document.get_text())

    def test_legacy_editable_text_does_not_become_html(self):
        from content.rendering import editable_nodes, source_document

        # Extract from the actual imported layout, not a synthetic renderer.
        texts = editable_nodes(source_document("index.html"))
        self.assertTrue(texts)
        LegacyText.objects.create(
            page=self.home,
            key=0,
            label="First imported editable text",
            value='<img id="legacy-text-attack" src=x onerror=alert(1)>',
        )
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        document = BeautifulSoup(response.content, "html.parser")
        self.assertIsNone(document.find(id="legacy-text-attack"))

    def test_public_javascript_data_cannot_break_out_of_string(self):
        Person.objects.create(
            identifier="security-person",
            name='</script><script id="data-attack">alert(1)</script>',
            role="Lawyer",
            phone="010 123 4567",
            tel="+358101234567",
            email="security@example.invalid",
            profile_slug="security-person",
        )
        response = self.client.get("/site-data.js")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "</script>")
        self.assertContains(response, r"\u003c/script\u003e")

    def test_public_content_endpoints_reject_writes(self):
        for url in ("/", "/security-test.html", "/site-data.js"):
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, {"title": "unauthorized"}).status_code, 405)


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class HiddenBlockTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.home = Page.objects.get(depth=1).add_child(instance=LegacyPage(title="Etusivu", slug="hidden-home", source_file="index.html"))
        cls.services = cls.home.add_child(instance=LegacyPage(title="Palvelut", slug="palvelut", source_file="palvelut.html"))

    def render(self, page):
        from content.rendering import render_legacy

        return BeautifulSoup(render_legacy(page), "html.parser")

    def test_hero_buttons_and_service_cards_are_hidden_by_default(self):
        self.assertIsNone(self.render(self.home).select_one(".hero-actions"))
        self.assertIsNone(self.render(self.services).select_one(".services-gateways"))
        self.assertIsNotNone(self.render(self.home).select_one(".hero-lead"))
        self.assertIsNotNone(self.render(self.services).select_one(".practice-results"))

    def test_editor_can_switch_a_block_on_and_another_off(self):
        LegacyBlock.objects.create(page=self.home, key="hero-buttons", label="x", visible=True)
        LegacyBlock.objects.create(page=self.home, key="people", label="x", visible=False)
        soup = self.render(self.home)
        self.assertIsNotNone(soup.select_one(".hero-actions"))
        self.assertIsNone(soup.select_one(".people-section"))
        self.assertIsNotNone(soup.select_one(".process-section"))

    def test_hiding_a_block_does_not_move_saved_text_edits(self):
        from content.rendering import editable_nodes, source_document

        nodes = editable_nodes(source_document("index.html"))
        key = next(i for i, node in enumerate(nodes) if "Etkö ole varma" in node)
        LegacyText.objects.create(page=self.home, key=key, label="x", value="Muokattu kappale")
        self.assertIn("Muokattu kappale", self.render(self.home).get_text())


class BlockMigrationTests(TestCase):
    def test_existing_pages_get_switches_in_live_and_draft_revisions(self):
        from importlib import import_module
        from types import SimpleNamespace

        from django.apps import apps
        from django.db import connection

        home = Page.objects.get(depth=1).add_child(instance=LegacyPage(title="Etusivu", slug="migrated-home", source_file="index.html"))
        home.save_revision().publish()
        self.assertEqual(home.get_latest_revision_as_object().blocks.count(), 0)
        import_module("content.migrations.0005_page_blocks").add_blocks(apps, SimpleNamespace(connection=connection))
        home.refresh_from_db()
        draft = home.get_latest_revision_as_object()
        state = {block.key: block.visible for block in draft.blocks.all()}
        self.assertEqual(state["hero-buttons"], False)
        self.assertEqual(state["people"], True)
        self.assertIn("blocks", home.live_revision.content)
