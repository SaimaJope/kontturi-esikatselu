"""Small presentation hooks; authorization stays with Wagtail's permission policies."""

from django.conf import settings
from django.templatetags.static import static
from django.urls import NoReverseMatch, reverse
from django.utils.html import format_html
from wagtail import hooks
from wagtail.admin.site_summary import PagesSummaryItem
from wagtail.admin.ui.components import Component
from wagtail.models import Page


def _snippet_link(user, model_name):
    if not user.has_perm(f"content.change_{model_name}"):
        return None
    try:
        return reverse(f"wagtailsnippets_content_{model_name}:list")
    except NoReverseMatch:
        return None


class KontturiStartPanel(Component):
    name = "kontturi_start"
    order = -100
    template_name = "wagtailadmin/home/kontturi_start.html"

    def __init__(self, request):
        self.request = request

    def get_context_data(self, parent_context):
        context = super().get_context_data(parent_context)
        user = self.request.user
        news = Page.objects.filter(slug="ajankohtaista").first()
        context["article_add_url"] = None
        if news and news.permissions_for_user(user).can_add_subpage():
            context["article_add_url"] = reverse(
                "wagtailadmin_pages:add", args=["content", "articlepage", news.pk]
            )
        context["people_url"] = _snippet_link(user, "person")
        context["offices_url"] = _snippet_link(user, "office")
        context["is_demo"] = settings.CMS_DEMO_MODE
        return context


@hooks.register("construct_homepage_panels")
def add_kontturi_start_panel(request, panels):
    panels.append(KontturiStartPanel(request))


class KontturiPagesSummaryItem(PagesSummaryItem):
    def get_context_data(self, parent_context):
        context = super().get_context_data(parent_context)
        root_page = context["root_page"]
        if root_page:
            # Wagtail may initially count the global tree before choosing this
            # site's root. Count the same subtree that this dashboard links to.
            context["total_pages"] = (
                Page.objects.descendant_of(root_page, inclusive=True)
                .exclude(depth=1)
                .count()
            )
        return context


@hooks.register("construct_homepage_summary_items", order=1000)
def tailor_kontturi_summary(request, items):
    items[:] = [
        KontturiPagesSummaryItem(request) if isinstance(item, PagesSummaryItem) else item
        for item in items
        if getattr(item, "template_name", "")
        != "wagtaildocs/homepage/site_summary_documents.html"
    ]


@hooks.register("insert_global_admin_css")
def kontturi_admin_styles():
    return format_html('<link rel="stylesheet" href="{}">', static("cms/admin.css"))
