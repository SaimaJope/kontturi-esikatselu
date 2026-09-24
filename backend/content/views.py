import json
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_safe
from .models import ArticlePage, LegacyPage, Office, Person, SiteProfile


@require_safe
def home(request):
    page = get_object_or_404(LegacyPage.objects.live().public(), source_file="index.html")
    return page.serve(request)


@require_safe
def legacy_page(request, filename):
    source = filename + ".html"
    page = LegacyPage.objects.live().public().filter(source_file=source).first()
    if page is None:
        page = ArticlePage.objects.live().public().filter(legacy_file=source).first()
    if page is None:
        raise Http404
    return page.serve(request)


@require_safe
def site_data(request):
    people = [{"id": p.identifier, "name": p.name, "role": p.role, "phone": p.phone, "tel": p.tel, "email": p.email, "slug": p.profile_slug, "topic": p.topic, "image": p.original.get("image", ""), "imageUrl": p.image.file.url if p.image else None} for p in Person.objects.select_related("image")]
    offices = [{"id": o.identifier, "name": o.name, "street": o.street, "postal": o.postal, "phone": o.phone, "tel": o.tel, "hours": o.hours} for o in Office.objects.all()]
    profile = SiteProfile.objects.first()
    site = {"name": profile.name, "email": profile.email, "onCallPhone": profile.on_call_phone, "onCallTel": profile.on_call_tel} if profile else {}
    def encode(value):
        return json.dumps(value, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    response = HttpResponse(f"export const people = {encode(people)};\nexport const offices = {encode(offices)};\nexport const site = {encode(site)};\n", content_type="text/javascript; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    return response
