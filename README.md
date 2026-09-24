# Kontturi & Co — website and content editor

The existing website now has a Wagtail CMS backed by Django. The original HTML,
CSS, photographs, logos, fonts and URLs remain the design source. The editor
runs without a cloud account and stores its local content in SQLite.

## Try the demo

Requires Python 3.13. From this directory in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-backend.ps1
```

- Website: <http://127.0.0.1:8000/>
- Content editor: <http://127.0.0.1:8000/admin/>
- Generated login details: `backend/.local/demo-access.txt`

On first login, enroll an authenticator such as Microsoft Authenticator, Google
Authenticator or a password manager with TOTP. Keep the generated recovery
codes. Every administrator needs a password **and** a second factor; there is no
shared PIN or password-only admin bypass. The demo accepts loopback connections
only. Stop the server with Ctrl+C. Restarting preserves content and accounts.

The launcher imports the existing public content only on the first run; later
runs do not overwrite edits. It does not upload the supplied emails/PDFs or
contact anyone. It does not change the live kontturi.fi site or GitHub Pages.

## Share a working demo

To create a temporary HTTPS link from this Windows PC:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-shareable-demo.ps1
```

The launcher prints the website and editor links. Login details are in
`backend/.local/shared-demo/access.txt`; a Finnish email draft without the password
is in `backend/.local/shared-demo/email-draft.fi.txt`. First login enrolls an
authenticator. The demo account can edit and publish content but cannot manage users.

Open the website and editor in two windows. Save a draft to keep a change private,
then choose **Julkaise** to publish it. An open demo page checks for published
changes every 15 seconds and refreshes automatically. Editing a form or keeping
a dialog open pauses refreshing to protect visitor input. A hidden tab checks
again when reopened. New requests see published content immediately.

This uses a [Cloudflare Quick Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/)
for temporary demonstrations. The PC must stay awake and connected. Restarting
the sharing process creates a new URL; content and login are preserved in a
separate demo database. Stop sharing with `stop-shareable-demo.ps1`. This is not
permanent hosting. No live domain or DNS changes are made.

The sharing process downloads cloudflared from its official GitHub release and
checks the published SHA-256 digest before running it. The application uses only
the exact assigned hostname, HTTPS cookies, no indexing, mandatory MFA and a
loopback-only application server. Demo content, media and credentials remain
separate from the local administrator demo and are excluded from Git.

## What staff can do

- Edit existing page text and photographs while preserving the layout.
- Create rich-text articles with a cover image, author, category and date.
- Save drafts, preview, publish, unpublish and restore page revisions.
- Update shared expert and office contact information.
- Upload validated JPG, PNG and WebP images to the media library.
- Separate content editing and publishing permissions using Wagtail groups.

Shared contact records update immediately; page and article edits use the
draft/publish workflow. The current contact form remains a non-sending preview.
This CMS is for public website material, not confidential legal enquiries or files.

Finnish instructions: [editor guide](docs/EDITOR_GUIDE.fi.md).
Deployment and operational requirements: [deployment guide](docs/DEPLOYMENT.md).
Security boundaries and verification: [security notes](docs/SECURITY.md).

## Development and checks

```powershell
.\.venv\Scripts\python.exe backend/manage.py check
.\.venv\Scripts\python.exe backend/manage.py test tests
.\.venv\Scripts\python.exe -m pip check
```

`backend/requirements.txt` pins the runtime environment. `requirements.in`
documents the intended direct dependencies and LTS version ranges. Upgrade and
audit dependencies regularly; do not treat a pinned environment as maintenance-free.

The database, generated passwords, local secret, uploaded files and test artifacts
are excluded from Git. Do not deploy the repository with a generic file server:
run the application so only its explicitly routed files are served.

For a complete browser publishing check, install `backend/requirements-dev.txt`,
run `python -m playwright install chromium`, start the local server and run
`python scripts/browser_smoke.py`. It verifies password/TOTP login, article
creation and publication, the public listing, and mobile login, then removes its
own temporary test user/article. Screenshots are written to `test-results/`.

`python scripts/browser_demo_flow.py` additionally verifies a limited publisher
account, draft privacy and automatic refresh in a separate anonymous browser.
It records the measured publication-to-refresh time and removes its test content.
It runs against local mode by default; shared-demo checks require
`KONTTURI_ENV=demo` and the currently assigned `KONTTURI_DEMO_HOST`.
