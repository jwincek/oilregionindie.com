# Deployment Guide

This guide covers deploying the Oil Region Creative Hub to a production server using Docker Compose.

## Prerequisites

- A server with Docker and Docker Compose installed
- A domain name pointing to the server (e.g., `oilregionindie.com`)
- SSL certificate (via Certbot/Let's Encrypt or Cloudflare)
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

The fastest path is the interactive wizard:

```bash
docker compose run --rm web python manage.py setup
```

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

The Docker Compose file includes PostgreSQL. For production, set a strong password:

```bash
DATABASE_URL=postgres://oilregion:<strong-password>@db:5432/oilregion
```

Update the `docker-compose.yml` PostgreSQL environment to match:

```yaml
environment:
  POSTGRES_DB: oilregion
  POSTGRES_USER: oilregion
  POSTGRES_PASSWORD: <same-strong-password>
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

## 3. Configure Nginx for SSL

Replace `docker/nginx.conf` with your production configuration. If using Certbot:

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

If using Cloudflare for SSL, you can keep the simpler HTTP-only config and let Cloudflare handle TLS termination.

## 4. Build and Start

```bash
docker compose up -d --build
```

This starts:
- **web** — Gunicorn app server (3 workers)
- **db** — PostgreSQL 16
- **redis** — Redis 7
- **worker** — Django Q2 task queue
- **nginx** — Reverse proxy serving static/media

## 5. Initialize the Database

If you ran `manage.py setup` in step 2 with the bootstrap section enabled, migrations / superuser / starter-page seed / Django Q schedules are already done. If you skipped that section, run them manually:

```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_data --pages    # taxonomy + CMS pages, no sample profiles
docker compose exec web python manage.py setup_schedules      # weekly digest, daily expiration, daily reminder
```

Always-needed steps:

```bash
# Build the search index
docker compose exec web python manage.py update_index

# Collect static files (usually done during build, but verify)
docker compose exec web python manage.py collectstatic --noinput
```

## 5b. Pre-Deploy Checklist

Before exposing the site to the public, run the deploy-time invariant checks:

```bash
docker compose exec web python manage.py check --deploy
```

This refuses to start if any of these are wrong:

| ID | Error |
|----|-------|
| `oilregion.E001` | `DJANGO_SECRET_KEY` is unset or the example placeholder |
| `oilregion.E002` | `DJANGO_ALLOWED_HOSTS` is still the dev default |
| `oilregion.E003` | `EMAIL_BACKEND` is the file-based dev backend |
| `oilregion.E004` | `FEATURE_COMMERCE=True` but Stripe keys are blank |
| `oilregion.W005` / `W006` | Stripe keys are in test mode (`sk_test_*` / `pk_test_*`) — intentional during soft launch |
| `oilregion.W007` | Cloudflare Turnstile not configured — signups unprotected from bots |

Errors block startup; warnings are advisory. The wizard normally handles all of these, so failures usually mean someone hand-edited `.env` after the fact.

## 6. Geocode Addresses

After venues start registering with addresses:

```bash
docker compose exec web python manage.py geocode_addresses
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
docker compose exec db pg_dump -U oilregion oilregion > backup_$(date +%Y%m%d).sql

# Restore from backup
docker compose exec -T db psql -U oilregion oilregion < backup_20260504.sql
```

Consider automating with cron:

```cron
0 3 * * * cd /path/to/oilregionindie.com && docker compose exec -T db pg_dump -U oilregion oilregion | gzip > /backups/oilregion_$(date +\%Y\%m\%d).sql.gz
```

Also back up the `media/` volume (user uploads):

```bash
docker compose exec web tar czf /tmp/media_backup.tar.gz /app/media
docker cp $(docker compose ps -q web):/tmp/media_backup.tar.gz ./media_backup_$(date +%Y%m%d).tar.gz
```

### Updates

```bash
git pull
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py collectstatic --noinput
docker compose exec web python manage.py update_index
docker compose exec web python manage.py check --deploy
```

The final `check --deploy` catches the case where an upgrade introduced a new invariant that your `.env` doesn't satisfy (e.g., a feature toggle that now requires extra config).

### Monitoring

- Check logs: `docker compose logs -f web`
- Check worker: `docker compose logs -f worker`
- Dashboard: `https://oilregionindie.com/dashboard/` (pending reviews, reports, metrics)

### Scheduled Tasks

The Django Q worker handles:
- **Weekly email digests** — Monday, summarizing activity from followed profiles
- **Daily booking expiration** — expires pending requests older than 30 days
- **Daily verification reminders** — reminds users who haven't verified after 24 hours

Verify tasks are running:

```bash
docker compose exec web python manage.py shell -c "from django_q.models import Schedule; print(Schedule.objects.values_list('name', 'next_run'))"
```

### Turning Off Soft Launch

When you're ready to remove the demo banner and badges:

1. Set `SOFT_LAUNCH=False` in `.env`
2. Restart: `docker compose up -d`
3. Optionally delete seed data profiles from Django admin (real profiles will have replaced them)

## Troubleshooting

**Emails not sending:** Check Modoboa logs and verify EMAIL_HOST_PASSWORD is correct. Test with:
```bash
docker compose exec web python manage.py shell -c "from django.core.mail import send_mail; send_mail('Test', 'Body', None, ['your@email.com'])"
```

**Stripe webhook errors:** Verify STRIPE_WEBHOOK_SECRET matches the webhook endpoint in your Stripe dashboard. Check logs for signature verification failures.

**Search not returning results:** Rebuild the index: `docker compose exec web python manage.py update_index`. Full-text search with relevance ranking requires PostgreSQL — SQLite uses basic fallback.

**Static files not loading:** Run `docker compose exec web python manage.py collectstatic --noinput` and verify nginx is serving from `/app/staticfiles/`.

**Worker not processing tasks:** Check `docker compose logs worker`. Ensure Redis is running: `docker compose exec redis redis-cli ping`.
