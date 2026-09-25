import mimetypes
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, HttpResponse
from django.views.decorators.http import require_safe

ROOT_ASSETS = frozenset(path.name for pattern in ("*.css", "*.js") for path in settings.PROJECT_ROOT.glob(pattern))
SOURCE_EXTENSIONS = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".woff2", ".woff", ".mp4", ".ico"}
UPLOAD_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def _file_response(root: Path, name: str, extensions):
    if "\\" in name or "\x00" in name or any(part.startswith(".") for part in name.split("/")):
        raise Http404
    root = root.resolve()
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root) or candidate.suffix.lower() not in extensions or not candidate.is_file():
        raise Http404
    response = FileResponse(candidate.open("rb"), content_type=mimetypes.guess_type(candidate.name)[0] or "application/octet-stream")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "public, max-age=3600"
    return response


@require_safe
def source_asset(request, path):
    return _file_response(settings.PROJECT_ROOT / "assets", path, SOURCE_EXTENSIONS)


@require_safe
def root_asset(request, filename):
    if filename not in ROOT_ASSETS:
        raise Http404
    return _file_response(settings.PROJECT_ROOT, filename, {".css", ".js"})


@require_safe
def public_image(request, path):
    if path.split("/", 1)[0] not in {"images", "original_images", "avatar_images"}:
        raise Http404
    if settings.MEDIA_STORAGE == "s3":
        if ("\\" in path or "\x00" in path or any(part.startswith(".") for part in path.split("/"))
                or Path(path).suffix.lower() not in UPLOAD_EXTENSIONS):
            raise Http404
        try:
            stream = default_storage.open(path, "rb")
        except FileNotFoundError:
            raise Http404
        response = FileResponse(stream, content_type=mimetypes.guess_type(path)[0] or "application/octet-stream")
        response["Cache-Control"] = "public, max-age=3600"
        response["X-Content-Type-Options"] = "nosniff"
        return response
    return _file_response(settings.MEDIA_ROOT, path, UPLOAD_EXTENSIONS)


@require_safe
def health(request):
    return HttpResponse("ok", content_type="text/plain")


@require_safe
def robots(request):
    body = "User-agent: *\nDisallow: /admin/\nDisallow: /account/\n" if settings.INDEX_SITE else "User-agent: *\nDisallow: /\n"
    return HttpResponse(body, content_type="text/plain")
