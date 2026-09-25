"""Prepare a separate, narrowly scoped account for a temporary public demo."""
import json
import re
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from wagtail.models import Site


class Command(BaseCommand):
    help = "Create the limited shared-demo publisher and refresh the temporary demo links."

    def handle(self, *args, **options):
        if not settings.SHARED_DEMO:
            raise CommandError("Shared-demo accounts require KONTTURI_ENV=demo.")
        User = get_user_model()
        group = Group.objects.filter(name="Julkaisijat").first()
        site = Site.objects.filter(is_default_site=True).first()
        if group is None or site is None:
            raise CommandError("Run seed_site and setup_roles first.")
        credentials_path = settings.DEMO_DIR / "credentials.json"
        username = "kontturi-demo"
        password = None
        with transaction.atomic():
            user = User.objects.filter(username=username).first()
            if user is None:
                if credentials_path.exists():
                    raise CommandError("Demo credentials exist without their account. Review the demo state before proceeding.")
                password = secrets.token_urlsafe(24)
                user = User.objects.create_user(username=username, password=password, first_name="Kontturi", last_name="Demo")
                user.groups.add(group)
                with credentials_path.open("x", encoding="utf-8") as stream:
                    json.dump({"username": username, "password": password}, stream)
            elif user.is_superuser or user.is_staff or user.user_permissions.exists() or set(user.groups.values_list("pk", flat=True)) != {group.pk}:
                raise CommandError("The shared demo account must have only the publisher role, without administration rights.")
            elif not user.is_active:
                raise CommandError("The shared demo account has been disabled; leaving it disabled.")
            elif credentials_path.exists():
                initial = json.loads(credentials_path.read_text(encoding="utf-8"))
                candidate = initial.get("password", "")
                if user.check_password(candidate):
                    password = candidate
            site.hostname = settings.ALLOWED_HOSTS[0]
            site.port = 443
            site.save(update_fields=["hostname", "port"])

        base_url = settings.WAGTAILADMIN_BASE_URL
        access_path = settings.DEMO_DIR / "access.txt"
        access_path.write_text(
            "KONTTURI & CO - SHARED CMS DEMO\n\n"
            f"Website: {base_url}/\nEditor: {base_url}/admin/\n\n"
            f"Username: {username}\n"
            + (f"Password: {password}\n" if password else "Password: use the password you set in the editor.\n")
            + "\nSign in with your username and password. No authenticator is required for this demo.\n"
            "Use this account for your demonstration; each further editor needs their own account.\n"
            "Publish page/article changes. An open public page refreshes in about 15 seconds.\n"
            "Drafts do not change the public website.\n\n"
            "Temporary demo: this PC and the sharing process must remain running.\n"
            "The URL changes when the sharing process restarts. Content and login are preserved.\n"
            "This file contains a password. Send access details separately from the public demo link.\n"
            "This demo uses a separate database and does not modify kontturi.fi.\n",
            encoding="utf-8",
        )
        (settings.DEMO_DIR / "email-draft.fi.txt").write_text(
            "Aihe: Kontturin uuden verkkosivuston sisällönhallinnan demo\n\n"
            "Hei,\n\n"
            "Uuden verkkosivuston sisällönhallinnasta on nyt toimiva demo. "
            "Sen kautta voi muokata sivujen tekstejä ja kuvia sekä kirjoittaa ja julkaista artikkeleita.\n\n"
            f"Demosivusto: {base_url}/\nSisällönhallinta: {base_url}/admin/\n\n"
            "Sisällönhallintaan kirjaudutaan käyttäjätunnuksella ja salasanalla. "
            "Demossa ei tarvita tunnistautumissovellusta. Tunnukset toimitetaan erikseen.\n\n"
            "Muutokset voi tallentaa ensin luonnoksena ja tarkistaa esikatselussa. "
            "Julkaise-painikkeen jälkeen ne tulevat demosivulle. "
            "Valmiiksi auki oleva demosivu päivittyy automaattisesti noin 15 sekunnissa.\n\n"
            "Demo on erillinen nykyisestä kontturi.fi-sivustosta. Tämä on tilapäinen esittelylinkki, "
            "joka toimii esittelykoneen ollessa päällä; sovitaan kokeilulle sopiva ajankohta.\n",
            encoding="utf-8",
        )
        # Refresh already prepared recipient instructions when the temporary
        # hostname changes. Keep their wording, passwords and account untouched.
        for filename in ("tatu-access.txt", "email-tatu.fi.txt"):
            path = settings.DEMO_DIR / filename
            if path.is_file():
                existing = path.read_text(encoding="utf-8")
                refreshed = re.sub(
                    r"https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com(?=[/\s]|$)",
                    lambda match: base_url,
                    existing,
                )
                if refreshed != existing:
                    path.write_text(refreshed, encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Shared demo publisher ready. Login details: {access_path}"))
