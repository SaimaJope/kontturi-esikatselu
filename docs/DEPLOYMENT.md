# Deploying the CMS

The local demonstration is ready to run without paid accounts. Production is a
separate deployment: GitHub Pages cannot run a Python CMS or a database.

Use a managed application host with an EU region, managed PostgreSQL and a
persistent private media volume. The included Dockerfile runs as a non-root user
and serves WSGI with Waitress. A hosting provider must terminate HTTPS and forward
requests to port 8000. Select a service whose backup, patching and availability
terms meet the firm's needs. No service has been purchased or provisioned.

## Configuration

1. Create managed PostgreSQL with TLS and automated encrypted backups.
2. Mount a persistent writable media volume at `/var/lib/kontturi/media`. Do not
   rely on an ephemeral application filesystem for uploads.
3. Set production environment variables from `.env.example` using the host's
   secret manager. Generate `DJANGO_SECRET_KEY` with a cryptographically secure
   random generator. Do not reuse the local demo secret or account.
4. Set exact allowed hosts and HTTPS CSRF origins. Enable `TRUST_HTTPS_PROXY=1`
   only if the proxy strips client-supplied forwarded headers and supplies its
   own `X-Forwarded-Proto`. Configure Waitress/proxy trusted-header handling as
   appropriate for the host, and verify an HTTPS request is recognized as secure.
   Never trust all internet clients as proxies.
5. Run `python manage.py migrate --noinput`, `python manage.py seed_site`, and
   `python manage.py setup_roles`, and `python manage.py createsuperuser` from `backend/`. Import uses the checked-in
   public site content, not the local database. For moving edited demo content,
   plan a controlled database/media migration rather than rerunning the seed.
6. Run `python manage.py check --deploy`. Start the application and verify HTTPS,
   secure cookies, login, MFA, image upload, draft preview, publishing and rollback.
7. Create individual staff users. Assign the editor group for drafts and the
   publisher group for publication; reserve superuser access for the designated
   site owner and maintainers. Every
   admin session must complete MFA, including superusers.
8. Configure SMTP if editorial workflow notifications are needed. Password reset
   by email is disabled; maintainers can use Django's `changepassword` command.
9. Keep `INDEX_SITE=0` on staging. Approve the final content, production domain,
   redirects and privacy links before enabling indexing and switching DNS.

## Operations

- Put rate limits at the hosting edge on `/account/` and `/admin/` as well as the
  application's database-backed failed-password protection. Only trust client IP
  metadata from the hosting ingress. The application ignores user-supplied
  `X-Forwarded-For` values.
- Back up PostgreSQL and the media volume together, encrypted and with restricted
  access. Set retention with the owner and test a restore into an isolated staging
  environment. Revision history is not a database backup.
- Apply supported Django, Wagtail and dependency security updates. Re-run tests
  and review security advisories before deploying updates.
- Monitor failed logins, application errors, uptime, disk capacity and backup
  failures. Avoid logging request bodies, passwords or OTP secrets.
- HSTS applies to the application hostname after HTTPS is enabled; it does not
  preload or force unrelated subdomains.
- Remove departing staff promptly. Keep two separately secured maintenance
  accounts and documented offline recovery procedures.

The original `.html` URLs remain available. Do not invent old-site redirects:
obtain the actual old URL list and configure approved mappings in Wagtail's
redirects UI or at the hosting edge before domain migration. An `INDEX_SITE=1`
deployment still needs a content/SEO review; this demo does not claim to complete
the whole live-site migration.
