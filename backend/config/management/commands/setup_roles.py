from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from wagtail.models import Collection, GroupCollectionPermission, GroupPagePermission

from content.models import LegacyPage


class Command(BaseCommand):
    help = "Create narrowly scoped Finnish editor/publisher groups for the imported website."

    @transaction.atomic
    def handle(self, *args, **options):
        root = LegacyPage.objects.filter(source_file="index.html").first()
        if root is None:
            raise CommandError("Run seed_site before setup_roles.")
        collection = Collection.get_first_root_node()

        def permission(app_label, codename):
            return Permission.objects.get(content_type__app_label=app_label, codename=codename)

        for name, can_publish in [("Sisällöntuottajat", False), ("Julkaisijat", True)]:
            group, created = Group.objects.get_or_create(name=name)
            if not created:
                self.stdout.write(f"{name}: existing administrator-assigned permissions preserved.")
                continue
            group.permissions.add(permission("wagtailadmin", "access_admin"))
            page_actions = ["add", "change"]
            if can_publish:
                page_actions.append("publish")
            for action in page_actions:
                GroupPagePermission.objects.get_or_create(group=group, page=root, permission=permission("wagtailcore", f"{action}_page"))
            for model in ["person", "office", "siteprofile"]:
                group.permissions.add(permission("content", f"view_{model}"))
                if can_publish:
                    group.permissions.add(permission("content", f"change_{model}"))
            # Wagtail's image library lists images with change permission.
            # File replacement and deletion remain separately prohibited.
            for action in ["add", "choose", "change"]:
                GroupCollectionPermission.objects.get_or_create(group=group, collection=collection, permission=permission("wagtailimages", f"{action}_image"))
            self.stdout.write(self.style.SUCCESS(f"{name}: created. Publishing: {can_publish}. No user/group administration rights."))
