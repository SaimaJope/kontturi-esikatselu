from django.urls import reverse
from wagtail import hooks
from wagtail.admin.menu import MenuItem


@hooks.register("construct_main_menu")
def remove_documents(request, menu_items):
    menu_items[:] = [item for item in menu_items if item.name != "documents"]


@hooks.register("register_settings_menu_item")
def security_menu():
    return MenuItem("Kirjautumisen suojaus", reverse("two_factor:profile"), icon_name="lock", order=100)
