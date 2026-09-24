"""Render trusted layouts with escaped, structured editorial content.

Original HTML is application code. Nothing entered in the CMS is treated as a
template, a filesystem path, or unrestricted HTML.
"""
import re
from pathlib import Path
from urllib.parse import quote

import nh3
from bs4 import BeautifulSoup, Comment, NavigableString
from django.conf import settings
from django.core.paginator import Paginator
from django.http import Http404
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from wagtail.rich_text import expand_db_html

from .demo import append_refresh_script, render_version


def source_document(filename):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.html", filename or ""):
        raise Http404("Unknown page layout")
    root = Path(settings.SITE_SOURCE_ROOT).resolve()
    path = (root / filename).resolve()
    if path.parent != root or not path.is_file():
        raise Http404("Unknown page layout")
    return BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")


def editable_nodes(soup):
    main = soup.find("main")
    if main is None:
        return []
    nodes = []
    for node in main.find_all(string=True):
        if isinstance(node, Comment) or not node.strip():
            continue
        if node.find_parent(["script", "style", "svg", "noscript", "form", "select", "textarea"]):
            continue
        if node.find_parent(id="receipt-view") or node.find_parent(id="form-view"):
            continue
        if any(parent.get("aria-hidden") == "true" for parent in node.parents if getattr(parent, "attrs", None)):
            continue
        nodes.append(node)
    return nodes


def editable_images(soup):
    main = soup.find("main")
    if main is None:
        return []
    return [node for node in main.find_all("img") if node.get("src") and node.get("aria-hidden") != "true"]


def replace_text(node, value):
    old = str(node)
    prefix = old[:len(old) - len(old.lstrip())]
    suffix = old[len(old.rstrip()):]
    node.replace_with(NavigableString(prefix + str(value) + suffix))


def _replace_values(root, values, attributes=False):
    values = {str(old): str(new) for old, new in values.items() if old and old != new}
    if not values or root is None:
        return
    for node in list(root.find_all(string=True)):
        if not isinstance(node, Comment) and not node.find_parent(["script", "style", "svg"]):
            replacement = values.get(str(node).strip())
            if replacement is not None:
                replace_text(node, replacement)
    if attributes:
        for tag in root.find_all(True):
            for attr in ("href", "aria-label", "data-person-name", "alt", "title"):
                value = tag.get(attr)
                if not isinstance(value, str):
                    continue
                for old, new in values.items():
                    if value == old:
                        value = new
                    elif attr == "href" and value in ("tel:" + old, "mailto:" + old):
                        value = value.split(":", 1)[0] + ":" + new
                    elif attr in ("aria-label", "alt", "title") and old in value:
                        value = value.replace(old, new)
                tag[attr] = value


def _set_image(node, image):
    node["src"] = image.file.url
    node["width"] = str(image.width)
    node["height"] = str(image.height)
    for attribute in ("srcset", "sizes"):
        node.attrs.pop(attribute, None)


def international_phone(value):
    return "+358 " + value[1:] if value.startswith("0") else value


def apply_shared_content(soup, source_file=""):
    from .models import Office, Person, SiteProfile
    people = list(Person.objects.select_related("image"))
    for person in people:
        original = person.original
        regions = []
        if source_file == person.profile_slug + ".html" and soup.main:
            regions.append(soup.main)
        for region in soup.select(".person-card, .expert-feature"):
            if region.find("a", href=re.compile(re.escape(person.profile_slug) + r"\.html(?:$|[?#])")) or (original.get("name") and original["name"] in region.get_text(" ", strip=True)):
                regions.append(region)
        values = {original.get(key): getattr(person, key) for key in ("name", "role", "phone", "tel", "email")}
        for region in regions:
            _replace_values(region, values, attributes=True)
            if person.role != original.get("role"):
                for role in region.select(".person-role, .profile-role"):
                    role.clear()
                    role.append(NavigableString(person.role))
        _replace_values(soup, {original.get("name"): person.name}, attributes=True)
        if person.image:
            for image in soup.find_all("img"):
                if re.fullmatch(r"/?assets/" + re.escape(original.get("image", "__none__")) + r"(?:-\d+)?\.webp", image.get("src", "")):
                    _set_image(image, person.image)
        for option in soup.select("#person option"):
            if option.get("value") == person.identifier:
                option.string = person.name

    for container in soup.select("#people-cards, .directory-grid"):
        cards = list(container.select(":scope > .person-card"))
        for person in people:
            for card in cards:
                if card.find("a", href=re.compile(re.escape(person.profile_slug) + r"\.html(?:$|[?#])")):
                    container.append(card.extract())

    for office in Office.objects.all():
        original = office.original
        regions = []
        if source_file == office.identifier + ".html" and soup.main:
            regions.append(soup.main)
        for region in soup.select(".office"):
            if region.find(string=lambda value: value and value.strip() == original.get("name")):
                regions.append(region)
        values = {original.get(key): getattr(office, key) for key in ("name", "street", "postal", "phone", "tel", "hours")}
        values[international_phone(original.get("phone", ""))] = international_phone(office.phone)
        values[original.get("postal", "") + ", Finland"] = office.postal + ", Finland"
        for region in regions:
            _replace_values(region, values, attributes=True)
            for link in region.find_all("a", href=re.compile(r"^https://www\.google\.com/maps/")):
                link["href"] = "https://www.google.com/maps/search/?api=1&query=" + quote(office.street + ", " + office.postal)
            if soup.html.get("lang") == "en" and office.hours_en:
                for hours in region.select(".office-hours"):
                    hours.string = office.hours_en
        # The main office number is also present in the shared footer/contact UI.
        for region in soup.select(".site-footer, .english-contact-methods, .contact-direct, .mobile-contact-links"):
            _replace_values(region, {original.get("phone"): office.phone, international_phone(original.get("phone", "")): international_phone(office.phone), original.get("tel"): office.tel}, attributes=True)
        for option in soup.select("#office option"):
            if option.get("value") == office.identifier:
                option.string = office.name

    profile = SiteProfile.objects.first()
    if profile:
        original = profile.original
        _replace_values(soup, {original.get("email"): profile.email, original.get("onCallPhone"): profile.on_call_phone, international_phone(original.get("onCallPhone", "")): international_phone(profile.on_call_phone), original.get("onCallTel"): profile.on_call_tel}, attributes=True)
        brand = original.get("name")
        if brand and brand != profile.name:
            for node in list(soup.find_all(string=True)):
                if not isinstance(node, Comment) and not node.find_parent(["script", "style", "svg"]) and brand in str(node) and profile.name not in str(node):
                    node.replace_with(NavigableString(str(node).replace(brand, profile.name)))


def root_relative_assets(soup):
    for tag in soup.find_all(True):
        for attribute in ("src", "href", "poster"):
            value = tag.get(attribute)
            if isinstance(value, str) and value and not value.startswith(("/", "#")) and not re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", value):
                tag[attribute] = "/" + value
        if tag.get("srcset"):
            parts = []
            for candidate in tag["srcset"].split(","):
                candidate = candidate.strip()
                if candidate.startswith("assets/"):
                    candidate = "/" + candidate
                parts.append(candidate)
            tag["srcset"] = ", ".join(parts)


def set_metadata(soup, page):
    robots = soup.find("meta", attrs={"name": "robots"})
    if robots and getattr(settings, "INDEX_SITE", False) and getattr(page, "source_file", "") not in {"404.html", "index-tumma.html"}:
        robots["content"] = "index, follow"
    if soup.title:
        soup.title.string = (page.seo_title or page.title) + " · Kontturi & Co"
    description_text = page.search_description or getattr(page, "intro", "")[:250]
    if description_text:
        description = soup.find("meta", attrs={"name": "description"})
        if description:
            description["content"] = description_text


def sanitize_rich_text(value):
    expanded = expand_db_html(str(value))
    return nh3.clean(expanded, tags={"p", "h2", "h3", "h4", "strong", "b", "em", "i", "ul", "ol", "li", "a", "blockquote", "br", "hr"}, attributes={"a": {"href", "title"}}, url_schemes={"http", "https", "mailto", "tel"}, strip_comments=True, link_rel="noopener noreferrer")


def render_legacy(page, request=None):
    demo_version = render_version(request)
    soup = source_document(page.source_file)
    nodes = editable_nodes(soup)
    for text in page.texts.all():
        if text.key < len(nodes):
            replace_text(nodes[text.key], text.value)
    images = editable_images(soup)
    for replacement in page.images.select_related("image"):
        if replacement.key < len(images):
            node = images[replacement.key]
            node["alt"] = replacement.alt_text
            if replacement.image:
                _set_image(node, replacement.image)
    if page.source_file == "ajankohtaista.html":
        from .models import ArticlePage
        articles = ArticlePage.objects.live().public().child_of(page).select_related("author", "cover_image").order_by("-publication_date", "-first_published_at")
        pagination = Paginator(articles, 12).get_page(request.GET.get("page", 1) if request else 1)
        markup = render_to_string("content/article_list.html", {"articles": pagination, "pagination": pagination})
        section = soup.select_one(".editorial-story")
        if section:
            section.find_parent("section").replace_with(BeautifulSoup(markup, "html.parser"))
    apply_shared_content(soup, page.source_file)
    set_metadata(soup, page)
    root_relative_assets(soup)
    append_refresh_script(soup, demo_version)
    return str(soup)


def render_article(page, request=None):
    demo_version = render_version(request)
    soup = source_document("ensimmainen-yhteydenotto.html")
    markup = render_to_string("content/article_main.html", {"page": page, "safe_body": mark_safe(sanitize_rich_text(page.body))})
    soup.main.replace_with(BeautifulSoup(markup, "html.parser"))
    apply_shared_content(soup)
    set_metadata(soup, page)
    root_relative_assets(soup)
    append_refresh_script(soup, demo_version)
    return str(soup)
