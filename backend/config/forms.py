from django.core.exceptions import ValidationError
from wagtail.images.forms import BaseImageForm


class ImageForm(BaseImageForm):
    """Replacing a file would also change every already-published reference."""
    def clean_file(self):
        upload = self.cleaned_data.get("file")
        if self.instance.pk and "file" in self.changed_data:
            raise ValidationError(
                "Lisää uusi kuva kuvakirjastoon ja valitse se sivun luonnokseen. "
                "Näin julkaistut kuvat ja aiemmat sivuversiot säilyvät."
            )
        return upload
