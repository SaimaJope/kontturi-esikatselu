import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import zipfile
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings


@override_settings(ENVIRONMENT="staging")
class SnapshotImportBoundaryTests(TestCase):
    @override_settings(ENVIRONMENT="production")
    def test_existing_production_is_never_an_import_target(self):
        with self.assertRaisesMessage(CommandError, "restricted to hosted staging"):
            call_command("import_site_snapshot", Path("unused.zip"))

    def test_any_existing_user_blocks_overwrite(self):
        user = get_user_model().objects.create_user(username="already-here", password="retained-test-password")
        with self.assertRaisesMessage(CommandError, "Refusing to overwrite"):
            call_command("import_site_snapshot", Path("unused.zip"))
        user.refresh_from_db()
        self.assertTrue(user.check_password("retained-test-password"))

    def write_archive(self, path, files, corrupt=False):
        manifest = {"format": 1, "files": {key: {"size": len(value), "sha256": hashlib.sha256(value).hexdigest()}
                                            for key, value in files.items()}}
        if corrupt:
            manifest["files"]["database.json"]["sha256"] = "0" * 64
        with zipfile.ZipFile(path, "w") as archive:
            for key, value in files.items():
                archive.writestr(key, value)
            archive.writestr("manifest.json", json.dumps(manifest))

    def test_traversal_and_corruption_are_rejected_before_storage_writes(self):
        cases = [({"database.json": b"[]", "media/../../outside.png": b"unsafe"}, False, "Unsafe snapshot path"),
                 ({"database.json": b"[]"}, True, "checksum mismatch")]
        for files, corrupt, message in cases:
            with self.subTest(message=message), TemporaryDirectory() as directory:
                directory = Path(directory)
                snapshot = directory / "snapshot.zip"
                self.write_archive(snapshot, files, corrupt)
                with override_settings(MEDIA_ROOT=directory / "media"), \
                     patch("config.management.commands.import_site_snapshot.default_storage") as storage:
                    storage.exists.return_value = False
                    with self.assertRaisesMessage(CommandError, message):
                        call_command("import_site_snapshot", snapshot)
                    storage.save.assert_not_called()
                self.assertFalse(get_user_model().objects.exists())
