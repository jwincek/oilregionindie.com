# Getting Started

A step-by-step guide to running Oil Region Creative Hub locally for development.

## Prerequisites

- Python 3.13+
- pip
- Git
- (Optional) Docker and Docker Compose for containerized setup

No JavaScript build tools are required. The frontend uses Tailwind CSS via CDN, HTMX, Alpine.js, and Leaflet.js — all loaded from script tags.

## Local Setup

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/jwincek/oilregionindie.com.git
cd oilregionindie.com
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements-dev.txt
```

(That file pulls in the runtime dependencies plus the dev/test tools; production images install `requirements.txt` alone.)

### 3. Run the setup wizard

```bash
python manage.py setup
```

The wizard walks through three sections:

- **Infrastructure** — writes `.env` for `DJANGO_SECRET_KEY` (auto-generated), `DEBUG`, `ALLOWED_HOSTS`, database URL, Redis URL, soft-launch banner, feature toggles (commerce, community), optional SMTP / Stripe / Turnstile / S3 sections. Each prompt shows the current value as the default; pressing Enter keeps it. The existing `.env` is preserved on disk as `.env.backup` before writes.
- **Branding** — writes a `SiteBranding` Wagtail snippet with site name, tagline, footer blurb, contact email, source-repo URL, and active theme. Shows the discovered themes in [themes/](themes/) as choices for the active-theme picker.
- **Bootstrap** — runs `migrate`, optionally creates a superuser, optionally seeds Wagtail starter pages, optionally registers Django Q recurring tasks. The defaults flip based on whether each has already been done (no superuser → default Yes; HomePage exists → default No on seed).

Sections can be skipped individually: `--skip-infrastructure`, `--skip-branding`, `--skip-bootstrap`.

### 4. (Optional) Seed sample data

For development with full sample profiles, events, and bookings:

```bash
python manage.py seed_data --full
```

This creates sample creators, venues, events, and 8 Wagtail pages. All sample accounts use `@oilregion-demo.example` emails with password `testpass123`.

For a production-like setup (taxonomy + CMS pages, no sample profiles), the wizard already calls `seed_data --pages` in the bootstrap section.

### 5. Run the development server

```bash
python manage.py runserver
```

- Public site: http://localhost:8000
- Wagtail CMS: http://localhost:8000/cms/
- Django admin: http://localhost:8000/django-admin/
- Admin dashboard: http://localhost:8000/dashboard/ (staff users only)

## Manual Setup (Alternative)

If you'd rather configure by hand:

```bash
cp .env.example .env
# Edit .env: set DJANGO_SECRET_KEY to a long random string
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_data --full     # or --pages for a leaner production-like setup
python manage.py setup_schedules
```

## Docker Setup

```bash
docker compose up -d
docker compose exec web python manage.py setup
```

The wizard inside the container does the same three sections; the `.env` and `SiteBranding` row are written to the mounted volumes.

Visit http://localhost (nginx proxies to the app).

## Exploring the Codebase

### Key directories

- `config/` — Django settings, root URL configuration, sitemaps
- `apps/core/` — Shared models (UserProfile, Notification, Report, BlockedWord, ProfileView, Address), notifications, digest, geocoding, image optimization, feeds, middleware, template tags, **theming engine** ([theming.py](apps/core/theming.py)), **faceted filter helpers** ([facets.py](apps/core/facets.py)), **deploy-time checks** ([checks.py](apps/core/checks.py))
- `apps/creators/` — Creator profiles, the directory, media/social link management, stats
- `apps/venues/` — Venue profiles, directory, social links, contacts
- `apps/events/` — Events, calendar, time slots, booking requests, feedback, endorsements
- `apps/commerce/` — Products, product groups, orders, Stripe Connect, digital downloads
- `apps/community/` — Discussion posts, tags, likes
- `apps/pages/` — Wagtail CMS page models, **SiteBranding settings snippet**, context processors
- `themes/` — Filesystem themes; each subdirectory is `theme.json` + optional `theme.css` + optional `templates/`
- `templates/` — All HTML templates (Django template language + HTMX + Alpine.js)
- `static/` — JavaScript (searchable selects), SVG icons, favicon

### How the profile flow works

1. User signs up (email + username + password via django-allauth)
2. Email verification is required
3. After verification, user lands on `/welcome/` — choose to create a creator profile, register a venue, or browse
4. Profile creation uses a step-by-step wizard
5. User fills out their profile (starts as **draft**)
6. User clicks "Submit for Review" — status moves to **pending**
7. Admin gets an email notification and sees it on the dashboard
8. Admin approves — status becomes **published**, creator gets notified
9. Profile appears in the directory and on the map

Profile owners can preview their unpublished profile at its normal URL. Other users get a 404.

Every status transition is captured by django-simple-history. Admins can see who-changed-what on each profile's admin change form ("History" button).

### How booking requests work

1. Creator visits a venue page and clicks "Request to Book" (or venue visits creator and clicks "Invite to Book")
2. Requester fills out event type (visual card selection), preferred dates, and a message
3. Receiving party sees the request in their booking inbox with a badge count
4. They accept or decline with an optional response message
5. Both parties are notified by email and in-app notification
6. On acceptance, contact info is revealed and a "Create Event" button appears
7. Both parties can leave private feedback and write public endorsements
8. Stale pending requests auto-expire after 30 days

Status transitions are captured in the BookingRequest history table — useful for dispute resolution.

### How commerce works

1. Creator adds products and product groups from "My Products" (no Stripe required)
2. Creator connects Stripe via the pre-onboarding setup page when ready
3. Buyers browse the creator's shop section and click "Buy Now"
4. Stripe Checkout handles payment (including shipping cost for physical items)
5. Digital products get immediate download links on the success page
6. Physical products appear in the creator's order detail view with shipping address
7. Creator marks items as shipped with optional tracking number; buyer gets notified

The whole commerce surface can be turned off with `FEATURE_COMMERCE=False` — shop URLs return 404, nav/footer links disappear, and the profile-edit page hides the Stripe Connect block.

### How theming works

The `themes/` directory holds one folder per theme. Each theme is `theme.json` (metadata: name, version, author, description) plus an optional `theme.css` that overrides the CSS variables in [base.html](templates/base.html) (`--color-brand-50`…`--color-brand-900`, `--color-ink-*`, `--font-sans`, `--font-display`). Tailwind utilities like `bg-brand-500` and `text-ink-800` read those variables, so a theme can repaint the entire site with a few dozen lines of CSS — no template edits required.

Optional `themes/<name>/templates/` lets a theme override individual Django templates (e.g., a different `base.html` or footer). The [ActiveThemeLoader](apps/core/theming.py) sits at the front of the template-loader chain.

The active theme is `SiteBranding.active_theme`, switchable from `/cms/` → Settings → Site branding. A `post_save` signal invalidates the cache so changes take effect on the next request — no restart.

### Running tests

```bash
python manage.py test --parallel auto apps.core.tests apps.creators.tests apps.venues.tests apps.events.tests
```

379 tests covering models, views, forms, theming, deploy-time checks, brute-force lockout, and audit-trail wiring. `--parallel auto` lands in ~50s vs ~150s serial.

### Useful accounts after seeding with --full

| Email | Role | Profile |
|-------|------|---------|
| alice@oilregion-demo.example | Creator | Singer-songwriter (published) |
| bob@oilregion-demo.example | Creator | Painter + silversmith (published) |
| venue_belize@oilregion-demo.example | Venue owner | Belize's Bar (published) |
| eve@oilregion-demo.example | Creator | Draft profile (unpublished) |

All use password `testpass123`.

## Common Tasks

### Approve a pending profile

1. Go to the dashboard: http://localhost:8000/dashboard/
2. Click "Review" next to a pending profile
3. In Django admin, use "Approve selected profiles" action

### Test the signup flow

1. Visit http://localhost:8000/accounts/signup/
2. Register with email + username
3. Check `tmp_emails/` for the verification email
4. Click the confirmation link
5. Choose what to do on the welcome page
6. Complete the profile wizard

### Manage moderation

- **Dashboard**: http://localhost:8000/dashboard/ — pending reviews, open reports, metrics
- **Reports**: Django admin → Reports (filter by status: Pending Review)
- **Word filter**: Django admin → Blocked Words
- **Suspend user**: Django admin → User Profiles → "Suspend selected users" action
- **Audit trail**: Each moderation-adjacent admin page ("UserProfile", "Report", "CreatorProfile", "VenueProfile", "BookingRequest") has a "History" button that shows every save with the responsible staff member.

### Switch the active theme

1. Visit `/cms/` (Wagtail admin)
2. Settings → Site branding
3. Pick from the discovered themes in the dropdown, save
4. Reload any page — the new palette applies immediately

To add a new theme: create `themes/<your-theme>/theme.json` and `themes/<your-theme>/theme.css`. It'll appear in the dropdown on next save.

### Set up scheduled tasks

```bash
python manage.py setup_schedules   # Create weekly digest, daily expiration, daily reminder
python manage.py qcluster          # Start the worker
```

### Geocode new addresses

```bash
python manage.py geocode_addresses         # Geocode addresses without coordinates
python manage.py geocode_addresses --dry-run
```

### Rebuild search index

```bash
python manage.py update_index
```

### Verify production readiness

```bash
python manage.py check --deploy
```

Runs deploy-time invariants — placeholder secret keys, default ALLOWED_HOSTS, dev email backend, Stripe key validity, Turnstile recommendation. Errors (E001-E004) block startup in production; warnings (W005-W007) are advisory.

### Reset the database

```bash
rm db.sqlite3
python manage.py setup    # walks through bootstrap again
```
