from django.core.validators import RegexValidator
from django.db import models
from django.http import HttpResponse
from django.utils import timezone
from modelcluster.fields import ParentalKey
from wagtail.admin.panels import FieldPanel, HelpPanel, InlinePanel, MultiFieldPanel
from wagtail.fields import RichTextField
from wagtail.models import Orderable, Page
from wagtail.search import index
from wagtail.snippets.models import register_snippet
from .panels import FixedInlinePanel


phone_validator = RegexValidator(r"^\+?[0-9 ()-]{5,30}$", "Kirjoita kelvollinen puhelinnumero.")


def fixed_snippet(model):
    return register_snippet(model, viewset="content.admin.FixedSnippetViewSet")


@fixed_snippet
class Person(index.Indexed, models.Model):
    identifier = models.SlugField(unique=True, editable=False)
    name = models.CharField("Nimi", max_length=160)
    role = models.CharField("Tehtävänimike", max_length=250)
    phone = models.CharField("Puhelin (näytettävä)", max_length=40, validators=[phone_validator])
    tel = models.CharField("Puhelin (kansainvälinen)", max_length=40, validators=[phone_validator])
    email = models.EmailField("Sähköposti")
    profile_slug = models.SlugField(editable=False)
    topic = models.CharField("Yhteydenoton oletusaihe", max_length=30, blank=True, choices=[("yritys", "Yritysjuridiikka"), ("kiinteistot", "Kiinteistöt"), ("perhe", "Perhe ja perintö"), ("muu", "Muu")])
    image = models.ForeignKey("wagtailimages.Image", null=True, blank=True, on_delete=models.SET_NULL, related_name="person_portraits", verbose_name="Uusi henkilökuva")
    sort_order = models.PositiveIntegerField("Järjestys", default=0)
    original = models.JSONField(default=dict, editable=False)

    panels = [HelpPanel(content="Yhteystietojen muutokset näkyvät heti kaikilla sivuilla. Esittelytekstiä muokataan asiantuntijan omalla sivulla. Tyhjä kuvavalinta säilyttää alkuperäisen kuvan."), FieldPanel("name"), FieldPanel("role"), FieldPanel("phone"), FieldPanel("tel"), FieldPanel("email"), FieldPanel("topic"), FieldPanel("image"), FieldPanel("sort_order")]
    search_fields = [index.SearchField("name"), index.SearchField("role")]

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "asiantuntija"
        verbose_name_plural = "Asiantuntijat"

    def __str__(self):
        return self.name


@fixed_snippet
class Office(models.Model):
    identifier = models.SlugField(unique=True, editable=False)
    name = models.CharField("Toimipaikka", max_length=120)
    street = models.CharField("Katuosoite", max_length=200)
    postal = models.CharField("Postinumero ja kaupunki", max_length=120)
    phone = models.CharField("Puhelin (näytettävä)", max_length=40, validators=[phone_validator])
    tel = models.CharField("Puhelin (kansainvälinen)", max_length=40, validators=[phone_validator])
    hours = models.CharField("Aukioloajat", max_length=200)
    hours_en = models.CharField("Aukioloajat englanniksi", max_length=200, blank=True)
    original = models.JSONField(default=dict, editable=False)

    panels = [HelpPanel(content="Toimipaikan yhteystiedot päivittyvät heti koko sivustolle."), FieldPanel("name"), FieldPanel("street"), FieldPanel("postal"), FieldPanel("phone"), FieldPanel("tel"), FieldPanel("hours"), FieldPanel("hours_en")]

    class Meta:
        ordering = ["pk"]
        verbose_name = "toimipaikka"
        verbose_name_plural = "Toimipaikat"

    def __str__(self):
        return self.name


@fixed_snippet
class SiteProfile(models.Model):
    key = models.CharField(default="site", max_length=12, unique=True, editable=False)
    name = models.CharField("Toimiston nimi", max_length=120, default="Kontturi & Co")
    email = models.EmailField("Yleinen sähköposti")
    on_call_phone = models.CharField("Päivystysnumero (näytettävä)", max_length=40, validators=[phone_validator])
    on_call_tel = models.CharField("Päivystysnumero (kansainvälinen)", max_length=40, validators=[phone_validator])
    original = models.JSONField(default=dict, editable=False)

    panels = [HelpPanel(content="Yleiset yhteystiedot päivittyvät heti. Verkkolomake ei lähetä viestejä. Yhteyttä voi ottaa puhelimitse tai sähköpostilla."), FieldPanel("name"), FieldPanel("email"), FieldPanel("on_call_phone"), FieldPanel("on_call_tel")]

    class Meta:
        verbose_name = "sivuston yhteystiedot"
        verbose_name_plural = "Sivuston yhteystiedot"

    def __str__(self):
        return self.name


class LegacyPage(Page):
    source_file = models.CharField(max_length=180, unique=True, editable=False)
    parent_page_types = ["wagtailcore.Page", "content.LegacyPage"]
    subpage_types = ["content.LegacyPage", "content.ArticlePage"]
    content_panels = Page.content_panels + [
        HelpPanel(content="Yläosan otsikko nimeää sivun hallinnassa ja selaimen välilehdellä. Sivulla näkyvä pääotsikko ja muu sisältö löytyvät alta Tekstit-osiosta. Muokkaa tekstejä ja kuvia, tarkista Esikatselu ja valitse Julkaise. Tallennettu luonnos ei näy yleisölle. Asiantuntijoiden ja toimipaikkojen yhteystiedot muokataan yhteisissä sisältötietueissa."),
        FixedInlinePanel("texts", label="Sivun tekstit", heading="Tekstit sivun järjestyksessä"),
        FixedInlinePanel("images", label="Sivun kuvat", heading="Kuvat ja vaihtoehtoiset tekstit"),
    ]

    class Meta:
        verbose_name = "verkkosivu"
        verbose_name_plural = "Verkkosivut"

    @classmethod
    def can_create_at(cls, parent):
        # Existing layouts are imported by seed_site, never created without a template.
        return False

    def get_url(self, request=None, current_site=None):
        return "/" if self.source_file == "index.html" else "/" + self.source_file

    def serve(self, request, *args, **kwargs):
        from .rendering import render_legacy
        return HttpResponse(render_legacy(self, request))


class LegacyText(Orderable):
    page = ParentalKey(LegacyPage, on_delete=models.CASCADE, related_name="texts")
    key = models.PositiveIntegerField(editable=False)
    label = models.CharField("Kohta", max_length=200, editable=False)
    value = models.TextField("Teksti", max_length=20000)
    panels = [FieldPanel("label", read_only=True), FieldPanel("value")]

    class Meta(Orderable.Meta):
        verbose_name = "teksti"
        verbose_name_plural = "Tekstit"


class LegacyImage(Orderable):
    page = ParentalKey(LegacyPage, on_delete=models.CASCADE, related_name="images")
    key = models.PositiveIntegerField(editable=False)
    label = models.CharField("Alkuperäinen kuva", max_length=200, editable=False)
    image = models.ForeignKey("wagtailimages.Image", null=True, blank=True, on_delete=models.SET_NULL, related_name="legacy_replacements", verbose_name="Korvaava kuva", help_text="Tyhjä valinta säilyttää alkuperäisen kuvan.")
    alt_text = models.CharField("Vaihtoehtoinen teksti", max_length=500, blank=True)
    panels = [FieldPanel("label", read_only=True), FieldPanel("image"), FieldPanel("alt_text")]

    class Meta(Orderable.Meta):
        verbose_name = "kuva"
        verbose_name_plural = "Kuvat"


class ArticlePage(Page):
    intro = models.TextField("Johdanto", max_length=1000)
    category = models.CharField("Aihe", max_length=100, default="Ajankohtaista")
    body = RichTextField("Artikkelin sisältö", features=["h2", "h3", "bold", "italic", "ol", "ul", "link", "blockquote", "hr"])
    cover_image = models.ForeignKey("wagtailimages.Image", null=True, blank=True, on_delete=models.SET_NULL, related_name="article_covers", verbose_name="Artikkelikuva")
    cover_alt = models.CharField("Kuvan vaihtoehtoinen teksti", max_length=300, blank=True)
    author = models.ForeignKey(Person, null=True, blank=True, on_delete=models.SET_NULL, related_name="articles", verbose_name="Kirjoittaja")
    publication_date = models.DateField("Julkaisupäivä", default=timezone.localdate, null=True, blank=True)
    legacy_file = models.CharField(max_length=180, blank=True, editable=False)
    parent_page_types = ["content.LegacyPage"]
    subpage_types = []
    content_panels = Page.content_panels + [FieldPanel("category"), FieldPanel("intro"), FieldPanel("body"), MultiFieldPanel([FieldPanel("cover_image"), FieldPanel("cover_alt")], heading="Artikkelikuva"), FieldPanel("author"), FieldPanel("publication_date")]
    search_fields = Page.search_fields + [index.SearchField("intro"), index.SearchField("body")]

    class Meta:
        verbose_name = "artikkeli"
        verbose_name_plural = "Artikkelit"

    @classmethod
    def can_create_at(cls, parent):
        return super().can_create_at(parent) and getattr(parent.specific, "source_file", "") == "ajankohtaista.html"

    def get_url(self, request=None, current_site=None):
        if self.legacy_file:
            return "/" + self.legacy_file
        return super().get_url(request=request, current_site=current_site)

    def serve(self, request, *args, **kwargs):
        from .rendering import render_article
        return HttpResponse(render_article(self, request))


class ImportedAsset(models.Model):
    """Tracks one-time imports even if an editor renames or removes an image."""
    source = models.CharField(max_length=250, unique=True)
    image = models.ForeignKey("wagtailimages.Image", null=True, on_delete=models.SET_NULL)
