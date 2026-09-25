"""Preserve Wagtail audit references to deleted objects during portable export."""
from django.core.serializers.json import Serializer as JSONSerializer


class Serializer(JSONSerializer):
    def handle_fk_field(self, obj, field):
        if not field.db_constraint:
            # Wagtail deliberately keeps audit rows after their page or actor
            # is deleted. Resolving those references as natural keys fails.
            self._current[field.name] = getattr(obj, field.attname)
        else:
            super().handle_fk_field(obj, field)
