from wagtail.permission_policies import ModelPermissionPolicy
from wagtail.snippets.views.snippets import SnippetViewSet


class FixedRecordPermissionPolicy(ModelPermissionPolicy):
    """Imported records have matching public layouts, so allow edits only."""
    def user_has_permission(self, user, action):
        if action in {"add", "delete"}:
            return False
        return super().user_has_permission(user, action)

    def user_has_any_permission(self, user, actions):
        allowed = set(actions) - {"add", "delete"}
        return bool(allowed) and super().user_has_any_permission(user, allowed)

    def user_has_permission_for_instance(self, user, action, instance):
        return self.user_has_permission(user, action)

    def user_has_any_permission_for_instance(self, user, actions, instance):
        return self.user_has_any_permission(user, actions)


class FixedSnippetViewSet(SnippetViewSet):
    @property
    def permission_policy(self):
        return FixedRecordPermissionPolicy(self.model)
