import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a local demo administrator with a unique generated password. Never runs in production."

    def handle(self, *args, **options):
        if not settings.LOCAL_DEMO:
            raise CommandError("Demo accounts are available only in local mode.")
        User = get_user_model()
        if User.objects.filter(username="demo-admin").exists():
            self.stdout.write("Demo administrator already exists; password and MFA enrollment unchanged.")
            return
        password = secrets.token_urlsafe(24)
        User.objects.create_superuser(username="demo-admin", email="demo-admin@localhost", password=password, first_name="Kontturi", last_name="Demo")
        access_file = settings.LOCAL_DIR / "demo-access.txt"
        with access_file.open("w", encoding="utf-8") as stream:
            stream.write(
                "KONTTURI & CO - LOCAL CMS DEMO\n\n"
                "Website: http://127.0.0.1:8000/\n"
                "Editor:  http://127.0.0.1:8000/admin/\n\n"
                f"Username: demo-admin\nPassword: {password}\n\n"
                "First login: connect an authenticator app using the QR code.\n"
                "Save recovery codes under Account security after enrollment.\n"
                "This account is only for the local demonstration.\n"
                "This file is excluded from Git and never served by the website.\n"
            )
        self.stdout.write(self.style.SUCCESS(f"Created local demo administrator. Login details: {access_file}"))
