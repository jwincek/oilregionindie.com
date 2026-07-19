# Deployment Guide

This guide covers deploying the Oil Region Creative Hub to production using Docker Compose — either behind [Coolify](https://coolify.io) (§3b) or on a plain server.

Production always uses **`docker-compose.prod.yml`**. The bare `docker-compose.yml` is the development file — it bind-mounts source, runs gunicorn with `--reload`, and publishes Postgres/Redis to the host — and must never run on a server.

## Prerequisites

- A server with Docker and Docker Compose installed (or a Coolify instance)
- A domain name pointing to the server (e.g., `oilregionindie.com`)
- SSL certificate (automatic with Coolify; via Certbot/Let's Encrypt or Cloudflare on a plain server)
- A Modoboa mail server (or other SMTP provider) for transactional email
- A Stripe account with Connect enabled for commerce features
- (Optional) Cloudflare account for Turnstile bot protection

## 1. Prepare the Server

Clone the repository:

```bash
git clone https://github.com/jwincek/oilregionindie.com.git
cd oilregionindie.com
```

## 2. Configure Environment

The fastest path is the interactive wizard. The production compose file has no source bind mount, so mount the repo for this one command to land `.env` on the host:

```bash
docker compose -f docker-compose.prod.yml run --rm -v "$(pwd):/app" web python manage.py setup
```

(Deploying with Coolify instead? Run the wizard locally to generate values, then paste them into Coolify's environment UI — see §3b.)

The wizard auto-generates a `DJANGO_SECRET_KEY`, walks through database / Redis / email / Stripe / Turnstile / S3 / feature toggles, then populates the `SiteBranding` Wagtail snippet. It writes `.env` and backs up the previous version to `.env.backup`. Re-runnable: pressing Enter at any prompt keeps the current value, so you can revisit specific sections (`--skip-branding`, `--skip-bootstrap`, etc.).

The rest of this section documents the fields manually for reference when editing `.env` directly.

### Required Settings

```bash
# Generate a real secret key (the wizard does this automatically)
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

DJANGO_SECRET_KEY=<paste-generated-key>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=oilregionindie.com,www.oilregionindie.com
SOFT_LAUNCH=True  # Set to False when ready to remove demo badges/banner

# Feature toggles — disable optional surfaces if you don't need them.
# Apps stay installed (migrations preserved); these only gate URL routing
# and template rendering.
FEATURE_COMMERCE=True
FEATURE_COMMUNITY=True
```

### Database

The compose stack includes PostgreSQL. Set a strong password in `.env` — both variables, with matching passwords (`POSTGRES_PASSWORD` is what the compose file feeds the db container; `DATABASE_URL` is what Django connects with):

```bash
POSTGRES_PASSWORD=<strong-password>
DATABASE_URL=postgres://oilregion:<strong-password>@db:5432/oilregion
```

### Redis

```bash
REDIS_URL=redis://redis:6379/0
```

### Email (Modoboa)

Create these mailboxes in your Modoboa admin:
- `noreply@oilregionindie.com` — transactional emails (verification, notifications, digests)
- `errors@oilregionindie.com` — server error notifications
- `feedback@oilregionindie.com` — user feedback (referenced in help and feedback pages)

```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=mail.oilregionindie.com
EMAIL_PORT=587
EMAIL_HOST_USER=noreply@oilregionindie.com
EMAIL_HOST_PASSWORD=<modoboa-password>
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=noreply@oilregionindie.com
SERVER_EMAIL=errors@oilregionindie.com
```

### Admin Notifications

```bash
DJANGO_ADMINS=Jerome:jerome@oilregionindie.com
```

This receives profile submission notifications, report alerts, and Django error emails.

### Stripe Connect

Create a **separate** Stripe account for the platform (not your personal account):

1. Sign up at [stripe.com](https://stripe.com) using `stripe@oilregionindie.com`
2. Register as a sole proprietorship under your name
3. Enable Connect at [dashboard.stripe.com/connect/overview](https://dashboard.stripe.com/connect/overview)
4. Get your API keys from [dashboard.stripe.com/apikeys](https://dashboard.stripe.com/apikeys)

```bash
STRIPE_PUBLIC_KEY=pk_live_...
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PLATFORM_FEE_PERCENT=0  # Set your platform fee (e.g., 5 for 5%)
```

Set up the webhook at `https://oilregionindie.com/shop/webhooks/stripe/` for events:
- `checkout.session.completed`
- `payment_intent.payment_failed`

### Cloudflare Turnstile

1. Create a Turnstile widget at [dash.cloudflare.com/turnstile](https://dash.cloudflare.com/turnstile)
2. Choose "Managed" mode

```bash
TURNSTILE_SITE_KEY=0x4AAAAAAA...
TURNSTILE_SECRET_KEY=0x4AAAAAAA...
```

Leave blank to disable (signup works without it, just unprotected from bots).

### Wagtail

```bash
WAGTAIL_SITE_NAME=Oil Region Creative Hub
WAGTAILADMIN_BASE_URL=https://oilregionindie.com
```

## 3. TLS / Reverse Proxy

Production uses `docker/nginx.prod.conf`, which serves static/media and passes the upstream proxy's `X-Forwarded-Proto` / `X-Forwarded-For` headers through to Django (falling back to its own values when reached directly). Django trusts that header for HTTPS detection (`SECURE_PROXY_SSL_HEADER` in settings), so whatever terminates TLS must set it.

- **Behind Coolify** (or any TLS-terminating proxy): nothing to configure here — skip to §3b.
- **Plain server with Certbot**: extend `docker/nginx.prod.conf` with a 443 server block like the one below, and uncomment/extend the `ports` mapping on the nginx service in `docker-compose.prod.yml` to publish 80 and 443:

```nginx
upstream web {
    server web:8000;
}

server {
    listen 80;
    server_name oilregionindie.com www.oilregionindie.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name oilregionindie.com www.oilregionindie.com;
    client_max_body_size 20M;

    ssl_certificate /etc/letsencrypt/live/oilregionindie.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/oilregionindie.com/privkey.pem;

    location /static/ {
        alias /app/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /app/media/;
        expires 7d;
    }

    location / {
        proxy_pass http://web;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_redirect off;
    }
}
```

If using Cloudflare for SSL, you can keep the simpler HTTP-only config and let Cloudflare handle TLS termination — Cloudflare sends `X-Forwarded-Proto`, which the prod nginx config passes through.

## 3b. Deploying with Coolify

`docker-compose.prod.yml` works unchanged as a Coolify Docker Compose resource:

1. **New resource → Docker Compose**, pointed at this repository; set **Docker Compose Location** to `/docker-compose.prod.yml`.
2. Set the domain on the **nginx** service (port 80). Coolify's proxy terminates TLS and forwards the `X-Forwarded-*` headers; leave nginx's host ports commented out.
3. Define environment variables in the Coolify UI (it writes them to the `.env` the compose file references). The container filesystem is ephemeral, so a wizard-written `.env` inside a container is lost on redeploy — generate values with the wizard locally and paste them in.
4. `POSTGRES_PASSWORD` must match the password inside `DATABASE_URL` (see §2).
5. Coolify's scheduled-backup UI covers databases it manages as standalone resources — **not** the Postgres inside this compose stack. Keep the pg_dump cron from the Backups section, or split the database out into a Coolify-managed Postgres and point `DATABASE_URL` at it.

Deploys trigger on git push (webhook) or the Deploy button. Every deploy re-runs the startup gate described in §4.

## 4. Build and Start

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

On every start the web container runs `check --deploy` → `migrate --noinput` → `collectstatic --noinput` before gunicorn. A misconfigured `.env` aborts the boot with a named check error (§5b) instead of starting a broken site.

This starts:
- **web** — Gunicorn app server (3 workers)
- **db** — PostgreSQL 16
- **redis** — Redis 7
- **worker** — Django Q2 task queue
- **nginx** — Reverse proxy serving static/media

## 5. Initialize the Database

Migrations and collectstatic run automatically at every container start. If you ran `manage.py setup` in step 2 with the bootstrap section enabled, superuser / starter-page seed / Django Q schedules are already done too. If you skipped that section, run them manually:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
docker compose -f docker-compose.prod.yml exec web python manage.py seed_data --pages    # taxonomy + CMS pages, no sample profiles
docker compose -f docker-compose.prod.yml exec web python manage.py setup_schedules      # weekly digest, daily expiration, daily reminder
```

Always-needed step:

```bash
# Build the search index
docker compose -f docker-compose.prod.yml exec web python manage.py update_index
```

## 5b. Pre-Deploy Checklist

The deploy-time invariant checks run automatically at every container start and abort the boot on errors. To run them by hand:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py check --deploy
```

| ID | Error |
|----|-------|
| `oilregion.E001` | `DJANGO_SECRET_KEY` is unset or the example placeholder |
| `oilregion.E002` | `DJANGO_ALLOWED_HOSTS` is still the dev default |
| `oilregion.E003` | `EMAIL_BACKEND` is the file-based dev backend |
| `oilregion.E004` | `FEATURE_COMMERCE=True` but Stripe keys are blank |
| `oilregion.E009` | Stripe API keys are set but `STRIPE_WEBHOOK_SECRET` is not — checkouts would succeed at Stripe while orders never get marked paid |
| `oilregion.E010` | The database is SQLite — `DATABASE_URL` is unset or misspelled; in Docker that data is wiped on every redeploy |
| `oilregion.W005` / `W006` | Stripe keys are in test mode (`sk_test_*` / `pk_test_*`) — intentional during soft launch |
| `oilregion.W007` | Cloudflare Turnstile not configured — signups unprotected from bots |
| `oilregion.W008` | `SENTRY_DSN` not set — errors only surface in logs |

Errors block startup; warnings are advisory. The wizard normally handles all of these, so failures usually mean someone hand-edited `.env` after the fact.

## 6. Geocode Addresses

After venues start registering with addresses:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py geocode_addresses
```

This uses OpenStreetMap's Nominatim API (free, rate-limited to 1 request/second).

## 7. Verify

- Visit `https://oilregionindie.com` — you should see the home page
- Visit `https://oilregionindie.com/cms/` — Wagtail admin
- Visit `https://oilregionindie.com/dashboard/` — admin dashboard
- Test signup flow — check that verification email arrives via Modoboa
- Test the Stripe webhook — use Stripe CLI: `stripe listen --forward-to localhost:8000/shop/webhooks/stripe/`

## 8. Ongoing Operations

### Security defaults already in place

- **Brute-force lockout** via django-axes. 5 failed logins from a `(username, ip)` pair trigger a 30-minute cooloff. Override with `AXES_FAILURE_LIMIT` / `AXES_COOLOFF_TIME` in `config/settings.py` if 5/30 doesn't suit you. Cleared on successful login.
- **Audit trails** via django-simple-history on UserProfile, Report, CreatorProfile, VenueProfile, BookingRequest. Every save records who-changed-what; admins can browse history and revert via the "History" button on each admin change form.

### Branding and theming

Site name, tagline, footer copy, contact email, source-repo URL, logo, OG image, and the active theme all live on the `SiteBranding` Wagtail snippet. Edit at `/cms/` → Settings → Site branding. Theme switches take effect on the next request — no restart.

To ship a custom theme: add `themes/<your-theme>/theme.json` (metadata) and `themes/<your-theme>/theme.css` (CSS variable overrides). Optional `themes/<your-theme>/templates/` overrides specific Django templates. See [themes/midnight/theme.css](themes/midnight/theme.css) for the minimum CSS variable list.

### Backups

Back up PostgreSQL daily:

```bash
# Manual backup
docker compose -f docker-compose.prod.yml exec db pg_dump -U oilregion oilregion > backup_$(date +%Y%m%d).sql

# Restore from backup
docker compose -f docker-compose.prod.yml exec -T db psql -U oilregion oilregion < backup_20260504.sql
```

Consider automating with cron:

```cron
0 3 * * * cd /path/to/oilregionindie.com && docker compose -f docker-compose.prod.yml exec -T db pg_dump -U oilregion oilregion | gzip > /backups/oilregion_$(date +\%Y\%m\%d).sql.gz
```

Also back up the `media/` volume (user uploads):

```bash
docker compose -f docker-compose.prod.yml exec web tar czf /tmp/media_backup.tar.gz /app/media
docker cp $(docker compose -f docker-compose.prod.yml ps -q web):/tmp/media_backup.tar.gz ./media_backup_$(date +%Y%m%d).tar.gz
```

### Updates

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec web python manage.py update_index
```

`check --deploy`, `migrate`, and `collectstatic` all run automatically during startup — an upgrade that introduces a new invariant your `.env` doesn't satisfy aborts the boot with a named check error rather than starting half-configured.

### Monitoring

- Check logs: `docker compose -f docker-compose.prod.yml logs -f web`
- Check worker: `docker compose -f docker-compose.prod.yml logs -f worker`
- Dashboard: `https://oilregionindie.com/dashboard/` (pending reviews, reports, metrics)

### Scheduled Tasks

The Django Q worker handles:
- **Weekly email digests** — Monday, summarizing activity from followed profiles
- **Daily booking expiration** — expires pending requests older than 30 days
- **Daily verification reminders** — reminds users who haven't verified after 24 hours

Verify tasks are running:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py shell -c "from django_q.models import Schedule; print(Schedule.objects.values_list('name', 'next_run'))"
```

### Turning Off Soft Launch

When you're ready to remove the demo banner and badges:

1. Set `SOFT_LAUNCH=False` in `.env`
2. Restart: `docker compose -f docker-compose.prod.yml up -d` (on Coolify: redeploy, or restart the app after changing the variable in the UI)
3. Optionally delete seed data profiles from Django admin (real profiles will have replaced them)

## Troubleshooting

**Emails not sending:** Check Modoboa logs and verify EMAIL_HOST_PASSWORD is correct. Test with:
```bash
docker compose -f docker-compose.prod.yml exec web python manage.py shell -c "from django.core.mail import send_mail; send_mail('Test', 'Body', None, ['your@email.com'])"
```

**Stripe webhook errors:** Verify STRIPE_WEBHOOK_SECRET matches the webhook endpoint in your Stripe dashboard. Check logs for signature verification failures.

**Search not returning results:** Rebuild the index: `docker compose -f docker-compose.prod.yml exec web python manage.py update_index`. Full-text search with relevance ranking requires PostgreSQL — SQLite uses basic fallback.

**Static files not loading:** Run `docker compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput` and verify nginx is serving from `/app/staticfiles/`.

**Worker not processing tasks:** Check `docker compose -f docker-compose.prod.yml logs worker`. Ensure Redis is running: `docker compose -f docker-compose.prod.yml exec redis redis-cli ping`.
