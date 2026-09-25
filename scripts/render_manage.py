"""Run a Django management command with the same Render configuration as WSGI."""
import os
import sys
from start_render import ROOT, configure_render

configure_render(os.environ)
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
from django.core.management import execute_from_command_line
execute_from_command_line(sys.argv)
