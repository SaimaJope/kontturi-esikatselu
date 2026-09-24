from django.core.exceptions import ValidationError
from modelcluster.forms import BaseChildFormSet
from wagtail.admin.panels import InlinePanel


class FixedContentFormSet(BaseChildFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        existing = list(self.get_queryset())
        self.expected = {item.pk: item.key for item in existing}
        self.extra = 0
        self.min_num = self.max_num = len(existing)
        self.validate_min = self.validate_max = True
        self.can_order = False

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        submitted = [form for form in self.forms if not form.cleaned_data.get("DELETE")]
        identities = {form.instance.pk: form.instance.key for form in submitted}
        if len(submitted) != len(self.expected) or identities != self.expected:
            raise ValidationError("Sivupohjan kenttiä ei voi lisätä tai poistaa. Muokkaa olemassa olevia tekstejä ja kuvia.")


class FixedInlinePanel(InlinePanel):
    def get_form_options(self):
        options = super().get_form_options()
        options["formsets"][self.relation_name].update(formset=FixedContentFormSet, extra=0)
        return options

    class BoundPanel(InlinePanel.BoundPanel):
        template_name = "content/admin/fixed_inline_panel.html"
