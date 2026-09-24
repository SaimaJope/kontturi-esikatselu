from django.db import migrations


def expose_imported_image_library(apps, schema_editor):
    """Upgrade the seeded roles without reapplying their other permissions."""
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    GroupCollectionPermission = apps.get_model("wagtailcore", "GroupCollectionPermission")
    change = Permission.objects.filter(
        content_type__app_label="wagtailimages", codename="change_image"
    ).first()
    if change is None:
        # Fresh installations create these permissions after migrations and
        # use the updated setup_roles command to populate the new groups.
        return
    for group in Group.objects.filter(name__in=["Sisällöntuottajat", "Julkaisijat"]):
        collections = GroupCollectionPermission.objects.filter(
            group=group,
            permission__content_type__app_label="wagtailimages",
            permission__codename="choose_image",
        ).values_list("collection_id", flat=True)
        for collection_id in collections:
            GroupCollectionPermission.objects.get_or_create(
                group=group, collection_id=collection_id, permission=change
            )


class Migration(migrations.Migration):
    dependencies = [("content", "0002_alter_articlepage_publication_date")]
    operations = [migrations.RunPython(expose_imported_image_library, migrations.RunPython.noop)]
