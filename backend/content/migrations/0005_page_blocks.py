from copy import deepcopy

import django.db.models.deletion
import modelcluster.fields
from django.db import migrations, models

from content.blocks import blocks_for


def add_blocks(apps, schema_editor):
    alias = schema_editor.connection.alias
    LegacyPage = apps.get_model("content", "LegacyPage")
    LegacyBlock = apps.get_model("content", "LegacyBlock")
    Revision = apps.get_model("wagtailcore", "Revision")
    for page in LegacyPage.objects.using(alias).all():
        rows = []
        for order, (key, _selector, label, default) in enumerate(blocks_for(page.source_file)):
            row, _ = LegacyBlock.objects.using(alias).get_or_create(page_id=page.pk, key=key, defaults={"label": label, "visible": default, "sort_order": order})
            rows.append(row)
        if not rows:
            continue
        # The editor builds its form from the latest revision. Add the sections
        # to the live snapshot and the current draft, otherwise the switches
        # would be missing until someone saved the page once.
        for revision in Revision.objects.using(alias).filter(pk__in={page.live_revision_id, page.latest_revision_id} - {None}):
            if "blocks" in revision.content:
                continue
            content = deepcopy(revision.content)
            content["blocks"] = [{"pk": row.pk, "sort_order": row.sort_order, "key": row.key, "label": row.label, "visible": row.visible, "page": page.pk} for row in rows]
            Revision.objects.using(alias).filter(pk=revision.pk).update(content=content)


class Migration(migrations.Migration):
    dependencies = [("content", "0004_contact_copy")]
    operations = [
        migrations.CreateModel(
            name="LegacyBlock",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sort_order", models.IntegerField(blank=True, editable=False, null=True)),
                ("key", models.CharField(editable=False, max_length=40)),
                ("label", models.CharField(editable=False, max_length=200, verbose_name="Osio")),
                ("visible", models.BooleanField(default=True, help_text="Poista valinta, niin osio piilotetaan sivulta. Valitse uudelleen, niin se palaa. Osion tekstit säilyvät.", verbose_name="Näytetään sivulla")),
                ("page", modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name="blocks", to="content.legacypage")),
            ],
            options={"verbose_name": "osio", "verbose_name_plural": "Osiot", "ordering": ["sort_order"], "abstract": False},
        ),
        migrations.RunPython(add_blocks, migrations.RunPython.noop),
    ]
