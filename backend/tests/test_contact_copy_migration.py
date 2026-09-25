"""Copy upgrades must preserve drafts, custom edits, and layout positions."""

from copy import deepcopy
from importlib import import_module
from types import SimpleNamespace

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase
from wagtail.models import Page, Revision

from content.models import LegacyPage, LegacyText


migration = import_module("content.migrations.0004_contact_copy")


class ContactCopyMigrationTests(TestCase):
    def setUp(self):
        self.page = Page.get_first_root_node().add_child(
            instance=LegacyPage(
                title="Yhteystiedot",
                slug="contact-copy-upgrade",
                source_file="yhteydenotto.html",
                search_description=migration.OLD_DESCRIPTION,
            )
        )
        for key, kind, old, _ in migration.CONTACT_TEXTS:
            self.page.texts.add(
                LegacyText(key=key, sort_order=key, label=f"{kind} · {old[:150]}", value=old)
            )
        self.page.texts.add(LegacyText(key=21, sort_order=21, label="Heading", value="Toimipaikkamme"))
        self.history = self.page.save_revision()
        self.live = self.page.save_revision()
        self.live.publish()
        self.page = LegacyPage.objects.get(pk=self.page.pk)
        self.history.refresh_from_db()

    def migrate_copy(self):
        historical_apps = MigrationExecutor(connection).loader.project_state(
            [("content", "0003_editor_image_library")]
        ).apps
        migration.update_contact_copy(historical_apps, SimpleNamespace(connection=connection))

    def test_updates_live_and_current_draft_without_republishing_or_rewriting_history(self):
        draft = self.page.get_latest_revision_as_object()
        draft.title = "Unpublished contact title"
        draft.search_description = "Custom draft search description"
        draft_texts = list(draft.texts.all())
        for text in draft_texts:
            if text.key == 20:
                text.value = "Our editorial draft remains private."
        draft.texts.set(draft_texts)
        self.latest = draft.save_revision()
        self.latest.refresh_from_db()
        self.page.refresh_from_db()

        page_before = Page.objects.filter(pk=self.page.pk).values().get()
        history_before = deepcopy(self.history.content)
        revision_count = Revision.objects.count()
        created_at = self.latest.created_at
        text_positions = list(LegacyText.objects.filter(page=self.page).order_by("key").values_list("pk", "key", "sort_order"))

        self.migrate_copy()

        self.page = LegacyPage.objects.get(pk=self.page.pk)
        self.live.refresh_from_db()
        self.latest.refresh_from_db()
        self.history.refresh_from_db()
        self.assertEqual(self.history.content, history_before)
        self.assertEqual(Revision.objects.count(), revision_count)
        self.assertEqual(self.latest.created_at, created_at)
        self.assertEqual(
            list(LegacyText.objects.filter(page=self.page).order_by("key").values_list("pk", "key", "sort_order")), text_positions
        )
        page_before["search_description"] = migration.NEW_DESCRIPTION
        self.assertEqual(Page.objects.filter(pk=self.page.pk).values().get(), page_before)
        self.assertEqual(self.live.content["search_description"], migration.NEW_DESCRIPTION)
        self.assertEqual(self.latest.content["search_description"], "Custom draft search description")
        self.assertEqual(self.latest.content["title"], "Unpublished contact title")

        live_texts = {text["key"]: text for text in self.live.content["texts"]}
        draft_texts = {text["key"]: text for text in self.latest.content["texts"]}
        for key, kind, _, new in migration.CONTACT_TEXTS:
            self.assertEqual(self.page.texts.get(key=key).value, new)
            self.assertEqual(live_texts[key]["value"], new)
            self.assertEqual(live_texts[key]["label"], f"{kind} · {new[:150]}")
            if key != 20:
                self.assertEqual(draft_texts[key]["value"], new)
        self.assertEqual(draft_texts[20]["value"], "Our editorial draft remains private.")
        self.assertEqual(self.page.texts.get(key=21).value, "Toimipaikkamme")

        current_draft = deepcopy(self.latest.content)
        self.migrate_copy()
        self.latest.refresh_from_db()
        self.assertEqual(self.latest.content, current_draft)

    def test_custom_published_copy_is_preserved(self):
        page = self.page.get_latest_revision_as_object()
        page.search_description = "Custom published description"
        custom_texts = list(page.texts.all())
        for text in custom_texts:
            text.value = f"Custom text {text.key}"
            text.label = f"Custom label {text.key}"
        page.texts.set(custom_texts)
        revision = page.save_revision()
        revision.publish()
        revision.refresh_from_db()
        before = deepcopy(revision.content)

        self.migrate_copy()

        self.page = LegacyPage.objects.get(pk=self.page.pk)
        revision.refresh_from_db()
        self.assertEqual(self.page.search_description, "Custom published description")
        self.assertEqual(revision.content, before)
        for text in self.page.texts.all():
            self.assertEqual(text.value, f"Custom text {text.key}")
            self.assertEqual(text.label, f"Custom label {text.key}")
