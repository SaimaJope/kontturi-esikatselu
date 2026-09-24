import json
import re
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from wagtail.images import get_image_model
from wagtail.models import Collection, Page, Site

from content.models import ArticlePage, ImportedAsset, LegacyImage, LegacyPage, LegacyText, Office, Person, SiteProfile
from content.rendering import editable_images, editable_nodes, source_document


class Command(BaseCommand):
    help = "Import the existing Kontturi site once. Existing editorial changes are preserved."

    def add_arguments(self, parser):
        parser.add_argument("--hostname", default="localhost")
        parser.add_argument("--port", type=int, default=8000)

    @transaction.atomic
    def handle(self, *args, **options):
        self.root = Path(settings.SITE_SOURCE_ROOT).resolve()
        source = (self.root / "site-data.js").read_text(encoding="utf-8")
        imported = {}
        for key in ("people", "offices", "site"):
            match = re.search(r"export const " + key + r"\s*=\s*(.*?);", source, flags=re.S)
            if match is None:
                raise CommandError("Cannot read original site-data.js")
            imported[key] = json.loads(match.group(1))
        for order, value in enumerate(imported["people"]):
            Person.objects.get_or_create(identifier=value["id"], defaults={"name": value["name"], "role": value["role"], "phone": value["phone"], "tel": value["tel"], "email": value["email"], "profile_slug": value["slug"], "topic": value.get("topic", ""), "sort_order": order, "original": value})
        for value in imported["offices"]:
            Office.objects.get_or_create(identifier=value["id"], defaults={key: value[key] for key in ("name", "street", "postal", "phone", "tel", "hours")} | {"hours_en": "Weekdays 10 am–4 pm, Finnish time" if value["id"] == "jyvaskyla" else "Weekdays 9 am–4 pm, Finnish time", "original": value})
        value = imported["site"]
        SiteProfile.objects.get_or_create(key="site", defaults={"name": value["name"], "email": value["email"], "on_call_phone": value["onCallPhone"], "on_call_tel": value["onCallTel"], "original": value})
        self.shared_values = {str(v) for group in (imported["people"], imported["offices"], [imported["site"]]) for item in group for k, v in item.items() if k in {"name", "role", "phone", "tel", "email", "street", "postal", "hours", "onCallPhone", "onCallTel"}}
        self.collection = Collection.objects.filter(name="Sivuston alkuperäiset kuvat").first()
        if self.collection is None:
            self.collection = Collection.get_first_root_node().add_child(name="Sivuston alkuperäiset kuvat")

        root_page = LegacyPage.objects.filter(source_file="index.html").first()
        if root_page is None:
            tree_root = Page.get_first_root_node()
            root_page = self.create_page(tree_root, "index.html", slug="kontturi", title="Etusivu")
        created = 0
        for source_path in sorted(self.root.glob("*.html")):
            if source_path.name in {"index.html", "ensimmainen-yhteydenotto.html"}:
                continue
            if not LegacyPage.objects.filter(source_file=source_path.name).exists():
                self.create_page(root_page, source_path.name)
                created += 1

        news = LegacyPage.objects.get(source_file="ajankohtaista.html")
        if not ArticlePage.objects.filter(legacy_file="ensimmainen-yhteydenotto.html").exists():
            original = source_document("ensimmainen-yhteydenotto.html")
            body = original.select_one(".article-body")
            for button in body.select(".button"):
                button.decompose()
            article = ArticlePage(title=original.h1.get_text(" ", strip=True), slug="ensimmainen-yhteydenotto", intro=original.select_one(".page-lead").get_text(" ", strip=True), body="".join(str(node) for node in body.contents), category="Asioinnin tueksi", legacy_file="ensimmainen-yhteydenotto.html", publication_date=None, search_description="Näin aloitat keskustelun asianajotoimiston kanssa.")
            image = self.import_image("assets/tyotilanne-1100.webp")
            if image:
                article.cover_image = image
                article.cover_alt = "Kontturi & Co:n asiantuntijat keskustelevat toimiston neuvottelutilassa."
            news.add_child(instance=article)
            article.save_revision().publish()
        site = Site.objects.filter(is_default_site=True).first()
        if site is None:
            Site.objects.create(hostname=options["hostname"], port=options["port"], site_name="Kontturi & Co", root_page=root_page, is_default_site=True)
        elif site.root_page_id != root_page.pk:
            site.root_page = root_page
            site.hostname = options["hostname"]
            site.port = options["port"]
            site.site_name = "Kontturi & Co"
            site.save()
        self.stdout.write(self.style.SUCCESS(f"Kontturi ready: {LegacyPage.objects.count()} pages, {ArticlePage.objects.count()} articles, {Person.objects.count()} experts, {Office.objects.count()} offices. Existing edits preserved. ({created} new child pages.)"))

    def create_page(self, parent, source_file, slug=None, title=None):
        soup = source_document(source_file)
        meta = soup.find("meta", attrs={"name": "description"})
        page_title = title or soup.title.get_text().split("·")[0].strip()
        page = LegacyPage(title=page_title, slug=slug or Path(source_file).stem, source_file=source_file, search_description=meta.get("content", "") if meta else "")
        parent.add_child(instance=page)
        labels = {"h1": "Pääotsikko", "h2": "Väliotsikko", "h3": "Otsikko", "h4": "Otsikko", "p": "Kappale", "a": "Linkin teksti", "li": "Luettelo"}
        for key, node in enumerate(editable_nodes(soup)):
            text = str(node).strip()
            if text in self.shared_values:
                continue
            closest = node.find_parent(list(labels))
            label = labels.get(closest.name if closest else "", "Teksti") + " · " + text[:150]
            page.texts.add(LegacyText(key=key, label=label, value=text, sort_order=key))
        for key, image in enumerate(editable_images(soup)):
            source = image.get("src", "")
            self.import_image(source)
            # Personal portraits are edited once from the shared expert record.
            if any(source.startswith("assets/" + person.original.get("image", "__none__")) for person in Person.objects.all()):
                continue
            page.images.add(LegacyImage(key=key, label=Path(source).name, alt_text=image.get("alt", ""), sort_order=key))
        page.save_revision().publish()
        return page

    def import_image(self, relative):
        if not relative.startswith("assets/"):
            return None
        path = (self.root / relative).resolve()
        assets = (self.root / "assets").resolve()
        if not path.is_relative_to(assets) or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"} or not path.is_file():
            return None
        imported = ImportedAsset.objects.filter(source=relative).select_related("image").first()
        if imported:
            return imported.image
        Image = get_image_model()
        with path.open("rb") as handle:
            image = Image(title=path.stem.replace("-", " ").capitalize(), collection=self.collection)
            image.file.save(path.name, File(handle), save=False)
            image.save()
        ImportedAsset.objects.create(source=relative, image=image)
        return image
