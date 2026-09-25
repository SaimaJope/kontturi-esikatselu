from io import BytesIO
from unittest.mock import patch
from django.test import TestCase, override_settings
from config.storage import PrivateMediaStorage


@override_settings(MEDIA_STORAGE="s3", ALLOWED_HOSTS=["testserver"])
class ObjectStorageImageTests(TestCase):
    def test_image_urls_stay_same_origin_without_exposing_bucket_or_credentials(self):
        storage = PrivateMediaStorage(bucket_name="private-bucket", access_key="test-only",
                                      secret_key="test-only", endpoint_url="https://storage.example.invalid")
        self.assertEqual(storage.url("images/photo name.webp"), "/media/images/photo%20name.webp")

    def test_public_image_streams_from_storage_instead_of_ephemeral_disk(self):
        with patch("config.views.default_storage") as storage:
            storage.open.return_value = BytesIO(b"test-image-content")
            response = self.client.get("/media/images/photo.webp")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"test-image-content")
            self.assertEqual(response["Content-Type"], "image/webp")
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")
            storage.open.assert_called_once_with("images/photo.webp", "rb")
            response.close()

    def test_private_keys_and_unsafe_types_are_never_read(self):
        with patch("config.views.default_storage") as storage:
            for path in ("migration/snapshot.zip", "images/../secret.png", "images/.secret.png",
                         "images/code.svg", "images/code.html", "images/x%5Cy.png"):
                with self.subTest(path=path):
                    self.assertEqual(self.client.get("/media/" + path).status_code, 404)
            storage.open.assert_not_called()

    def test_missing_object_returns_not_found(self):
        with patch("config.views.default_storage") as storage:
            storage.open.side_effect = FileNotFoundError
            self.assertEqual(self.client.get("/media/images/missing.webp").status_code, 404)
