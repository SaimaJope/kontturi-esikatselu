"""Real editorial requests must respect Wagtail's built-in role boundaries."""

from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice
from wagtail.admin.rich_text.converters.contentstate import ContentstateConverter
from wagtail.models import Page

from content.models import ArticlePage, LegacyPage, LegacyText, Person


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class EditorialPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.home = Page.get_first_root_node().add_child(
            instance=LegacyPage(title="Security home", slug="security-home", source_file="index.html")
        )
        cls.home_text = LegacyText.objects.create(page=cls.home, key=0, label="First text", value="Original public text")
        cls.home.save_revision().publish()
        cls.news = cls.home.add_child(
            instance=LegacyPage(title="Security news", slug="security-news", source_file="ajankohtaista.html")
        )
        cls.article = cls.news.add_child(
            instance=ArticlePage(title="Draft article", slug="draft-article", intro="Draft introduction", body="<p>Draft body</p>", live=False)
        )
        cls.article.save_revision()
        call_command("setup_roles", stdout=StringIO())
        cls.editor = get_user_model().objects.create_user(username="security-editor", password="Editor-test-password-27!")
        cls.editor.groups.add(Group.objects.get(name="Sisällöntuottajat"))
        cls.editor_device = TOTPDevice.objects.create(user=cls.editor, name="default", confirmed=True)
        cls.moderator = get_user_model().objects.create_user(username="security-moderator", password="Moderator-test-password-27!")
        cls.moderator.groups.add(Group.objects.get(name="Julkaisijat"))

    def setUp(self):
        self.client.force_login(self.editor)
        session = self.client.session
        session[DEVICE_ID_SESSION_KEY] = self.editor_device.persistent_id
        session.save()

    def test_editor_can_edit_page_but_cannot_manage_accounts_or_groups(self):
        response = self.client.get(reverse("wagtailadmin_pages:edit", args=[self.article.pk]))
        self.assertEqual(response.status_code, 200)
        for path in ("/admin/users/", "/admin/groups/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertIn(response.status_code, (302, 403))

    def test_editor_cannot_escalate_own_account(self):
        response = self.client.post(
            reverse("wagtailusers_users:edit", args=[self.editor.pk]),
            {"username": self.editor.username, "is_superuser": "on", "is_staff": "on"},
        )
        self.assertIn(response.status_code, (302, 403))
        self.editor.refresh_from_db()
        self.assertFalse(self.editor.is_superuser)

    def test_editor_and_moderator_have_distinct_publish_permissions(self):
        self.assertTrue(self.article.permissions_for_user(self.editor).can_edit())
        self.assertFalse(self.article.permissions_for_user(self.editor).can_publish())
        self.assertTrue(self.article.permissions_for_user(self.moderator).can_publish())

    def test_editor_cannot_change_instantly_published_shared_contact_records(self):
        person = Person.objects.create(
            identifier="permission-test", name="Original name", role="Lawyer", phone="010 1234567",
            tel="+358101234567", email="person@example.invalid", profile_slug="permission-test",
            original={"name": "Original name"},
        )
        response = self.client.post(
            reverse("wagtailsnippets_content_person:edit", args=[person.pk]),
            {"name": "Unauthorized change", "role": "Lawyer", "phone": "010 1234567", "tel": "+358101234567", "email": "person@example.invalid", "sort_order": "0"},
        )
        self.assertIn(response.status_code, (302, 403))
        person.refresh_from_db()
        self.assertEqual(person.name, "Original name")
        self.assertTrue(self.moderator.has_perm("content.change_person"))

    def test_role_setup_does_not_override_later_administrator_changes(self):
        group = Group.objects.get(name="Julkaisijat")
        group.permissions.remove(*group.permissions.filter(codename="change_person"))
        call_command("setup_roles", stdout=StringIO())
        self.assertFalse(group.permissions.filter(codename="change_person").exists())

    def legacy_form_data(self):
        return {
            "title": self.home.title,
            "slug": self.home.slug,
            "texts-TOTAL_FORMS": "1", "texts-INITIAL_FORMS": "1",
            "texts-0-id": str(self.home_text.pk), "texts-0-value": "Updated private text",
            "images-TOTAL_FORMS": "0", "images-INITIAL_FORMS": "0",
            "comments-TOTAL_FORMS": "0", "comments-INITIAL_FORMS": "0",
        }

    def test_legacy_text_editor_can_save_revision_without_changing_published_text(self):
        response = self.client.post(reverse("wagtailadmin_pages:edit", args=[self.home.pk]), self.legacy_form_data())
        self.assertEqual(response.status_code, 302)
        self.home.refresh_from_db()
        self.home_text.refresh_from_db()
        self.assertEqual(self.home_text.value, "Original public text")
        self.assertEqual(self.home.get_latest_revision_as_object().texts.first().value, "Updated private text")

    def test_fixed_panels_keep_wagtail_widget_initialization_markup_without_row_controls(self):
        response = self.client.get(reverse("wagtailadmin_pages:edit", args=[self.home.pk]))
        self.assertEqual(response.status_code, 200)
        for relation in ("texts", "images"):
            self.assertContains(response, f'id="id_{relation}-FORMS"')
            self.assertContains(response, f'id="id_{relation}-EMPTY_FORM_TEMPLATE"')
            self.assertNotContains(response, f'id="id_{relation}-ADD"')
        self.assertContains(response, 'id="inline_child_texts-0"')
        self.assertNotContains(response, 'id="id_texts-0-DELETE-button"')

    def test_tampered_inline_management_form_cannot_remove_layout_text_rows(self):
        revision_id = self.home.latest_revision_id
        payload = self.legacy_form_data()
        payload.update({"texts-TOTAL_FORMS": "0", "texts-INITIAL_FORMS": "0"})
        response = self.client.post(reverse("wagtailadmin_pages:edit", args=[self.home.pk]), payload)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].formsets["texts"].non_form_errors())
        self.home.refresh_from_db()
        self.assertEqual(self.home.latest_revision_id, revision_id)
        self.assertEqual(self.home.texts.count(), 1)

    def test_fixed_contact_records_cannot_be_bulk_deleted_even_by_superuser(self):
        person = Person.objects.create(
            identifier="protected-person", name="Protected contact", role="Lawyer", phone="010 1234567",
            tel="+358101234567", email="protected@example.invalid", profile_slug="protected-person",
        )
        administrator = get_user_model().objects.create_superuser(username="bulk-test-admin", password="Bulk-test-password-42!")
        device = TOTPDevice.objects.create(user=administrator, name="default", confirmed=True)
        self.client.force_login(administrator)
        session = self.client.session
        session[DEVICE_ID_SESSION_KEY] = device.persistent_id
        session.save()
        url = reverse("wagtail_bulk_action", kwargs={"app_label": "content", "model_name": "person", "action": "delete"})
        response = self.client.post(f"{url}?id={person.pk}", {"confirm": "yes"})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Person.objects.filter(pk=person.pk).exists())

    def article_form_data(self):
        converter = ContentstateConverter(features=ArticlePage._meta.get_field("body").features)
        return {
            "title": "Edited draft remains private",
            "slug": self.article.slug,
            "intro": "Updated introduction",
            "category": "Ajankohtaista",
            "body": converter.from_database_format("<p>Private edited draft</p>"),
            "publication_date": "2026-09-25",
            "cover_alt": "",
            "comments-TOTAL_FORMS": "0",
            "comments-INITIAL_FORMS": "0",
            "comments-MIN_NUM_FORMS": "0",
            "comments-MAX_NUM_FORMS": "1000",
            "action-publish": "Publish",
        }

    def test_forged_publish_action_saves_only_a_draft_for_editor(self):
        response = self.client.post(
            reverse("wagtailadmin_pages:edit", args=[self.article.pk]),
            self.article_form_data(),
        )
        self.assertEqual(response.status_code, 302, getattr(response.context and response.context.get("form"), "errors", None))
        self.article.refresh_from_db()
        self.assertFalse(self.article.live)
        self.assertEqual(self.article.get_latest_revision_as_object().title, "Edited draft remains private")

    def test_authorized_publisher_can_publish_article_through_editor_endpoint(self):
        device = TOTPDevice.objects.create(user=self.moderator, name="default", confirmed=True)
        self.client.force_login(self.moderator)
        session = self.client.session
        session[DEVICE_ID_SESSION_KEY] = device.persistent_id
        session.save()
        payload = self.article_form_data()
        payload["title"] = "Published through the editor"
        response = self.client.post(reverse("wagtailadmin_pages:edit", args=[self.article.pk]), payload)
        self.assertEqual(response.status_code, 302)
        self.article.refresh_from_db()
        self.assertTrue(self.article.live)
        self.assertEqual(self.article.title, "Published through the editor")
