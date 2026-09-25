"""Private object storage with stable image URLs on the website's own origin."""
from urllib.parse import quote
from django.conf import settings
from storages.backends.s3 import S3Storage


class PrivateMediaStorage(S3Storage):
    def url(self, name, parameters=None, expire=None, http_method=None):
        return settings.MEDIA_URL + quote(name, safe="/")
