from copy import deepcopy

from django.db import migrations


# These positions stay unchanged in the trusted contact-page layout. Match the
# complete original values so the upgrade never overwrites editorial changes.
CONTACT_TEXTS = (
    (3, "Kappale", "Soita, lähetä sähköpostia tai jätä yhteydenottopyyntö.", "Soita meille tai ota yhteyttä sähköpostitse."),
    (19, "Teksti", "Esikatselu", "Ei lähetystä"),
    (20, "Kappale", "Kokeile esimerkkitiedoilla. Tämä lomake ei lähetä eikä tallenna tietoja.", "Lomake ei lähetä eikä tallenna tietoja. Ota yhteyttä puhelimitse tai sähköpostilla."),
)
OLD_DESCRIPTION = "Kontturi & Co:n yhteystiedot ja toimipaikat. Yhteydenottolomake on esikatselu eikä lähetä tietoja."
NEW_DESCRIPTION = "Kontturi & Co:n yhteystiedot ja toimipaikat. Ota yhteyttä puhelimitse tai sähköpostilla."


def update_contact_copy(apps, schema_editor):
    alias = schema_editor.connection.alias
    LegacyPage = apps.get_model("content", "LegacyPage")
    LegacyText = apps.get_model("content", "LegacyText")
    Page = apps.get_model("wagtailcore", "Page")
    Revision = apps.get_model("wagtailcore", "Revision")

    for page in LegacyPage.objects.using(alias).filter(source_file="yhteydenotto.html"):
        for key, kind, old, new in CONTACT_TEXTS:
            texts = LegacyText.objects.using(alias).filter(page_id=page.pk, key=key)
            texts.filter(value=old).update(value=new)
            texts.filter(label=f"{kind} · {old[:150]}").update(label=f"{kind} · {new[:150]}")

        Page.objects.using(alias).filter(pk=page.pk, search_description=OLD_DESCRIPTION).update(
            search_description=NEW_DESCRIPTION
        )

        # Repair only the live snapshot and current draft; leave historical
        # revisions and their audit information exactly as they were.
        revision_ids = {page.live_revision_id, page.latest_revision_id} - {None}
        for revision in Revision.objects.using(alias).filter(pk__in=revision_ids):
            content = deepcopy(revision.content)
            if content.get("search_description") == OLD_DESCRIPTION:
                content["search_description"] = NEW_DESCRIPTION
            for text in content.get("texts", []):
                for key, kind, old, new in CONTACT_TEXTS:
                    if text.get("key") != key:
                        continue
                    if text.get("value") == old:
                        text["value"] = new
                    if text.get("label") == f"{kind} · {old[:150]}":
                        text["label"] = f"{kind} · {new[:150]}"
            if content != revision.content:
                Revision.objects.using(alias).filter(pk=revision.pk).update(content=content)


class Migration(migrations.Migration):
    dependencies = [("content", "0003_editor_image_library")]
    operations = [migrations.RunPython(update_contact_copy, migrations.RunPython.noop)]
