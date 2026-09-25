"""Import a private demo snapshot only into a fresh hosted staging database."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from wagtail.models import GroupCollectionPermission, GroupPagePermission, Page, Site

from content.models import LegacyPage, Office, Person, SiteProfile


class Command(BaseCommand):
    help = "Restore an exported demo into an empty hosted staging CMS, preserving accounts and content."

    def add_arguments(self, parser):
        parser.add_argument("snapshot", type=Path)

    def handle(self, *args, **options):
        if settings.ENVIRONMENT != "staging":
            raise CommandError("Snapshot import is restricted to hosted staging.")
        if (LegacyPage.objects.exists() or get_user_model().objects.exists()
                or Page.objects.count() > 2 or Person.objects.exists()
                or Office.objects.exists() or SiteProfile.objects.exists()):
            raise CommandError("Target contains content or accounts. Refusing to overwrite it.")
        media = Path(settings.MEDIA_ROOT).resolve()
        media.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(options["snapshot"]) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise CommandError("Snapshot contains duplicate entries.")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format") != 1 or set(names) != set(manifest["files"]) | {"manifest.json"}:
                raise CommandError("Unsupported or incomplete snapshot.")
            if "database.json" not in manifest["files"]:
                raise CommandError("Snapshot has no database.")
            # Validate every path and digest before writing or touching the DB.
            for name, expected in manifest["files"].items():
                path = PurePosixPath(name)
                if ("\\" in name or path.is_absolute() or ".." in path.parts
                        or (name != "database.json" and not name.startswith("media/"))):
                    raise CommandError("Unsafe snapshot path.")
                data = archive.read(name)
                if len(data) != expected["size"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
                    raise CommandError("Snapshot checksum mismatch.")
                if name.startswith("media/"):
                    target = (media / name.removeprefix("media/")).resolve()
                    if not target.is_relative_to(media) or target == media:
                        raise CommandError("Unsafe media destination.")
                    key = name.removeprefix("media/")
                    if default_storage.exists(key):
                        with default_storage.open(key, "rb") as existing:
                            if existing.read() != data:
                                raise CommandError("Target media conflicts with snapshot; refusing to overwrite.")
            for name in manifest["files"]:
                if name.startswith("media/"):
                    key = name.removeprefix("media/")
                    if not default_storage.exists(key):
                        saved = default_storage.save(key, ContentFile(archive.read(name)))
                        if saved != key:
                            raise CommandError("Media filename conflict; stop concurrent uploads before importing.")
            with tempfile.TemporaryDirectory() as temporary:
                fixture = Path(temporary) / "database.json"
                fixture.write_bytes(archive.read("database.json"))
                with transaction.atomic():
                    # Fresh Wagtail migrations seed group permissions whose
                    # PKs can differ across database engines. Restore the
                    # snapshot's complete permission rows without collisions.
                    GroupCollectionPermission.objects.all().delete()
                    GroupPagePermission.objects.all().delete()
                    call_command("loaddata", str(fixture), verbosity=0)
                    for username in ("tatu-demo", "niina-demo"):
                        if not get_user_model().objects.filter(username=username, is_active=True, is_staff=True, is_superuser=True).exists():
                            raise CommandError("Expected personal administrator is missing from snapshot.")
                    from urllib.parse import urlsplit
                    origin = urlsplit(settings.WAGTAILADMIN_BASE_URL)
                    Site.objects.filter(is_default_site=True).update(hostname=origin.hostname, port=443)
        call_command("update_index", verbosity=0)
        self.stdout.write(self.style.SUCCESS("Snapshot imported. Accounts and password hashes retained; search index rebuilt; old sessions excluded."))
