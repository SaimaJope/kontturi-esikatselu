"""Export the current demo privately for a controlled database/media migration."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "backend/.local/shared-demo"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "backend/.local").resolve()):
        parser.error("Snapshots contain private account data: save only under backend/.local/.")
    if output.exists():
        parser.error("Refusing to overwrite an existing snapshot.")
    status = json.loads((STATE / "status.json").read_text(encoding="utf-8"))
    environment = os.environ.copy()
    environment.update(KONTTURI_ENV="demo", KONTTURI_DEMO_HOST=status["host"],
                       DJANGO_SETTINGS_MODULE="config.settings", PYTHONUTF8="1")
    environment.pop("TRUST_HTTPS_PROXY", None)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        temporary = Path(temporary)
        database = temporary / "snapshot.sqlite3"
        with closing(sqlite3.connect((STATE / "db.sqlite3").as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(database)) as destination:
                source.backup(destination)
        environment["KONTTURI_SNAPSHOT_DATABASE"] = str(database)
        environment["KONTTURI_SNAPSHOT_FIXTURE"] = str(temporary / "database.json")
        script = """
import os
from django.conf import settings
settings.DATABASES['default']['NAME'] = os.environ['KONTTURI_SNAPSHOT_DATABASE']
import django
django.setup()
from django.core.management import call_command
from django.core.serializers import register_serializer
register_serializer('snapshot_json', 'config.snapshot_serializer')
call_command('dumpdata', format='snapshot_json', natural_foreign=True,
             exclude=['contenttypes', 'auth.permission', 'sessions', 'axes', 'wagtailsearch'],
             output=os.environ['KONTTURI_SNAPSHOT_FIXTURE'], verbosity=0)
"""
        exported = subprocess.run([sys.executable, "-c", script], cwd=ROOT / "backend", env=environment,
                                  capture_output=True, text=True)
        if exported.returncode:
            sys.stderr.write(exported.stderr)
            raise RuntimeError("Snapshot export failed; source database was not modified.")
        manifest = {"format": 1, "exported_at": datetime.now(timezone.utc).isoformat(), "files": {}}
        files = [(temporary / "database.json", "database.json")]
        media = STATE / "media"
        for path in sorted(media.rglob("*")):
            if path.is_symlink() or not path.resolve().is_relative_to(media.resolve()):
                raise RuntimeError("Media contains an unexpected filesystem link.")
            if path.is_file():
                files.append((path, "media/" + path.relative_to(media).as_posix()))
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, name in files:
                data = path.read_bytes()
                manifest["files"][name] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
                archive.writestr(name, data)
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    print(json.dumps({"snapshot": str(output), "files": len(files), "size_bytes": output.stat().st_size,
                      "contains_private_account_data": True, "source_changed": False}))


if __name__ == "__main__":
    main()
