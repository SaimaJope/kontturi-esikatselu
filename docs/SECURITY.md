# Security boundaries

This is a working CMS demonstration with security controls, not a claim of an
independent penetration test or a guarantee against compromise.

## Implemented controls

- Supported Django/Wagtail LTS stack and pinned runtime dependencies.
- Framework-managed password hashing, session rotation, CSRF validation and ORM
  queries. Password validation requires at least 14 characters.
- Mandatory TOTP or recovery-token verification before every Wagtail admin route.
  Alternate Wagtail login routes cannot bypass the MFA middleware.
- Five failed password attempts for an account/IP combination cause a 15-minute
  database-backed lockout. OTP verification uses django-otp's throttling and replay
  protection. An edge rate limit is still needed for distributed abuse.
- One-hour HttpOnly, SameSite sessions; Secure cookies and HTTPS redirects in
  production. Authenticated editor/account responses are private and not cached.
- Published/public page filtering on every public page route. Drafts and previews
  require authorized editor access. Wagtail handles revision history and permissions.
- Template source paths are fixed application code. Page text is escaped, article
  rich text is sanitized server-side with an explicit allowlist and dangerous URL
  schemes are rejected. Editors cannot save executable templates or JavaScript.
- Existing image bytes cannot be overwritten. Editors upload a new image and
  select it in a page draft; deletion and bulk image operations are reserved for
  maintainers so ownership alone cannot bypass publication permissions.
- Images are limited to validated JPG, JPEG, PNG and WebP, at most 8 MiB and 24
  megapixels. SVG/HTML/document uploads are not part of this CMS. Existing trusted
  SVG logos are application assets, separate from uploaded media.
- File serving is allowlisted and constrained to designated directories. Database,
  source code, environment files and generated credentials are not public routes.
- CSP, MIME-sniffing protection, framing restrictions, referrer and permissions
  policies. The public site disallows inline scripts. Wagtail admin allows inline
  initialization code required by its UI, so its CSP is less restrictive than the
  public site's. Wagtail previews allow same-origin framing.
- Local mode is loopback-only with a unique generated secret and password. Public
  production mode fails to start without explicit hosts, a strong secret and
  PostgreSQL. DEBUG remains off.
- Shared demonstration mode uses a separate database, media directory and secret,
  one exact temporary HTTPS hostname, Secure cookies and a limited publisher.
  The application accepts loopback connections only, behind the temporary tunnel.
  Client-supplied forwarding headers cannot change its request identity or scheme.
  Search indexing stays disabled even if production indexing is requested in the
  environment. Demo credentials never provision a production administrator.
- Demo auto-refresh exposes only an opaque digest of already-public content.
  Saving a draft does not change it. The polling endpoint and script are disabled
  in production and the script is excluded from editorial previews.

## Content and operational scope

The CMS contains public marketing/editorial content only. Uploaded images are
public assets, including images selected for draft pages if their URL is known;
do not upload confidential material. There are no client accounts, confidential
enquiry APIs, attachment intake, public registration or embedded third-party
tracking. The original contact form remains explicitly non-sending.

Account recovery, TLS, database/media backups, monitoring, edge traffic controls
and patching need an identified owner before production. The supplied
correspondence remains outside the repository and was not imported into the CMS.

## Verification

Run `python backend/manage.py test tests` for access-control, CSRF, MFA, draft
visibility, content sanitization, file-serving and image validation regressions.
Run `python backend/manage.py check --deploy` with production environment settings.
Audit the locked dependencies with `pip-audit -r backend/requirements.txt` after
installing the audit tool in a development environment. A passing dependency audit
only covers vulnerabilities known to that advisory source at the time of the scan.
