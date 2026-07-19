# Oil Region Creative Hub

[![CI](https://github.com/jwincek/oilregionindie.com/actions/workflows/ci.yml/badge.svg)](https://github.com/jwincek/oilregionindie.com/actions/workflows/ci.yml)

An open-source platform for independent musicians, visual artists, makers, venues, and fans. Born from twelve years of the [Oil Region Indie Music Festival](https://www.facebook.com/oilregionindie1/) in Oil City, Pennsylvania.

## What It Does

Creators build profiles showcasing their work across disciplines — a guitar-playing silversmith can list both crafts in one place. Venues list their spaces with contacts, amenities, and availability. Fans discover creators and events through directory filtering, full-text search, an interactive map, and a monthly calendar. Booking requests flow bidirectionally between creators and venues. Payments go directly to creators via Stripe Connect — the platform never holds funds.

## Quick Start

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py setup
python manage.py runserver
```

`manage.py setup` is an interactive wizard that walks through three sections — infrastructure (`.env`: secret key, database, email, Stripe, Turnstile, S3, feature toggles), branding (site name, tagline, footer copy, contact email, active theme), and bootstrap (migrate, create superuser, seed Wagtail starter pages, register Django Q schedules). Re-runnable: pressing Enter at any prompt keeps the current value.

Visit **http://localhost:8000**. Wagtail admin: **http://localhost:8000/cms/**. Admin dashboard: **http://localhost:8000/dashboard/**. For a detailed walkthrough, see [GETTING-STARTED.md](GETTING-STARTED.md).

### Docker

```bash
docker compose up -d
docker compose exec web python manage.py setup
```

## Project Structure

```
oilregion-hub/
├── config/                 # Settings, URLs, sitemaps
├── apps/
│   ├── core/               # UserProfile, Notification, Report, BlockedWord,
│   │                         ProfileView, Address, Availability, theming,
│   │                         facets, checks, digest, geocoding, image
│   │                         optimization, feeds, middleware
│   ├── creators/           # CreatorProfile, Discipline, Skill, Genre,
│   │                         MediaItem, Memberships, Social Links, Embeds
│   ├── venues/             # VenueProfile, VenueContact, VenueArea, Amenity
│   ├── events/             # Event, EventSlot, BookingRequest,
│   │                         BookingFeedback, Endorsement
│   ├── commerce/           # Product, ProductGroup, Order, Stripe Connect
│   ├── community/          # CommunityPost, Tag, likes
│   └── pages/              # Wagtail CMS: HomePage, ContentPage, Blog,
│                             SiteBranding settings snippet
├── themes/                 # Filesystem-based themes (default, midnight, …)
├── templates/              # Django templates + HTMX partials
├── static/                 # JS, SVG icons, favicon
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.13, Django 5.2 LTS |
| CMS | Wagtail 7.3.x |
| Frontend | HTMX + Alpine.js + Tailwind CSS (CDN) |
| Database | PostgreSQL (SQLite for dev) |
| Payments | Stripe Connect Express |
| Search | Wagtail full-text search (PostgreSQL) with ORM fallback |
| Maps | Leaflet.js + OpenStreetMap |
| Cache/Queue | Redis + Django Q2 |
| Auth | django-allauth (email + username) + django-axes (brute-force lockout) |
| Audit trails | django-simple-history on moderation-adjacent models |
| Bot Protection | Cloudflare Turnstile |
| Deployment | Docker Compose |

Django 5.2 LTS is supported through April 2028 — deployers can pin a version and forget.

## Built for Forks

This isn't just a site running at oilregionindie.com — it's a platform designed for other independent arts communities to deploy their own instance. Three concerns are first-class:

- **Branding lives in a Wagtail snippet** ([SiteBranding](apps/pages/models.py)), not source code. Site name, tagline, origin-story blurb, contact email, source-repo URL, logo, and OG image are all editable from `/cms/` → Settings → Site branding.
- **Themes are filesystem directories** under [themes/](themes/). A theme is `theme.json` (metadata) + optional `theme.css` (CSS variable overrides) + optional `templates/` (Django template overrides). Switching themes is one save in the Wagtail admin — no restart, no PHP, no hooks. Two themes ship: `default` and `midnight` (a dark variant).
- **Feature toggles** (`FEATURE_COMMERCE`, `FEATURE_COMMUNITY`) gate optional surfaces in URLs and templates. Apps stay in `INSTALLED_APPS` (migrations preserved); the flags only affect routing and rendering. A community that doesn't want commerce or a forum can turn either off.

`python manage.py check --deploy` runs production-readiness invariants (placeholder secret key, default `ALLOWED_HOSTS`, dev email backend, Stripe key validity, Turnstile recommended) and refuses to start when any error-level rule fails.

## Features

### Creator & Venue Profiles
- Multi-discipline creators with skills, genres, and availability flags
- Step-by-step profile creation wizards
- Tabbed edit pages with HTMX inline management for social links, media, availability, and contacts
- Profile approval workflow (draft → pending review → published)
- Initials avatars and SVG banner patterns as defaults
- Image optimization on upload (auto-resize with Pillow)
- Profile analytics with daily view tracking

### Discovery
- Searchable directories with filter pills, result counts, and mobile-responsive filters
- Full-text search powered by Wagtail (relevance ranking on PostgreSQL)
- Global search across creators, venues, events, and community posts
- Interactive map with Leaflet.js and OpenStreetMap
- Similar creators sidebar based on shared disciplines and skills
- Genre, skill, amenity, availability, and location filtering
- Searchable multi-select dropdowns for high-option filters

### Events
- Event creation wizard with conditional fields (free/paid, virtual/in-person)
- Monthly calendar view alongside list view
- Event lineup management with HTMX add/edit/delete
- Venue and cost filtering
- Past events archive with toggle on profile pages

### Booking System
- Bidirectional booking requests (creator → venue and venue → creator)
- Booking inbox with search, status filters, and badge counts
- Accept/decline with response messages and email notifications
- Private feedback after accepted bookings
- Public endorsements displayed on both profiles
- Create event directly from an accepted booking
- Automatic expiration of stale pending requests
- Context-aware booking buttons based on availability status
- Multi-venue selection for users managing multiple venues

### Commerce
- Stripe Connect Express onboarding with pre-onboarding info page
- Product management with 2-step creation wizard
- Product groups (collections with individual purchase + bundles, and sets sold only together)
- Product image management with HTMX upload
- Flat-rate shipping costs for physical products
- Digital product downloads with delivery and download tracking
- Order management with shipping address display and mark-as-shipped
- Tracking numbers with buyer email notification
- Inventory management (mark as sold, restock)
- Bulk media upload for portfolios

### Community
- Discussion posts with four types (discussion, announcement, opportunity, review)
- Threaded replies, tags, and likes
- Follow creators and venues with notification delivery
- Weekly email digests of activity from followed profiles
- In-app notification system with unread badge count

### Moderation & Safety
- Report button on profiles and community posts
- Word filter on all user-submitted content
- Bleach HTML sanitization on all rich text fields
- User suspension with middleware enforcement
- Audit trails on UserProfile, Report, CreatorProfile, VenueProfile, BookingRequest — every save records who-changed-what (django-simple-history); browsable from each model's admin change form
- Brute-force login lockout via django-axes (5 failures from a (username, IP) pair triggers 30-minute cooloff)
- Terms of Service and Code of Conduct (editable in Wagtail CMS)
- Cloudflare Turnstile on signup

### Platform Operations
- Interactive setup wizard (`manage.py setup`) for first-deploy and reconfiguration
- Deploy-time invariant checks (`manage.py check --deploy`) — placeholder secrets, default ALLOWED_HOSTS, dev email backend, Stripe key validity, Turnstile recommended
- Admin dashboard with pending reviews, open reports, recent signups, and key metrics
- Profile approval with creator notification on publish
- Email verification reminders for unverified accounts
- Booking expiration for stale requests
- Django Q2 scheduled tasks (digests, expiration, reminders)
- Sitemap.xml, robots.txt, RSS feeds, OG meta tags
- Custom 404/500 error pages
- Soft launch mode with demo badges and dismissible banner

## Management Commands

```bash
python manage.py setup                  # Interactive first-deploy / reconfiguration wizard
python manage.py check --deploy         # Production-readiness invariant checks
python manage.py seed_data              # Taxonomy only (safe to re-run)
python manage.py seed_data --pages      # Taxonomy + Wagtail pages (production)
python manage.py seed_data --full       # Full sample content (dev/demo)
python manage.py send_digests           # Send weekly email digests
python manage.py send_digests --dry-run # Preview without sending
python manage.py expire_bookings        # Expire stale booking requests
python manage.py remind_unverified      # Remind unverified users
python manage.py geocode_addresses      # Geocode addresses without coordinates
python manage.py setup_schedules        # Configure Django Q recurring tasks
python manage.py update_index           # Rebuild Wagtail search index
python manage.py refresh_embeds         # Backfill oEmbed HTML
```

## Tests

Run the full suite (all apps) with:

```bash
python manage.py test --parallel auto
```

CI runs the same suite against PostgreSQL on every push and pull request — the badge at the top of this README is the live answer to "do the tests pass." Locally the suite uses your configured database (SQLite by default).

## Environment Variables

The wizard writes these for you. See [.env.example](.env.example) for the full list and ranges; key settings:

| Variable | Purpose | Default |
|----------|---------|---------|
| `DJANGO_SECRET_KEY` | Cryptographic signing key | (auto-generated by wizard) |
| `DJANGO_DEBUG` | Debug mode | `False` |
| `DJANGO_ALLOWED_HOSTS` | Allowed hostnames (comma-separated) | `localhost,127.0.0.1` |
| `DATABASE_URL` | PostgreSQL connection string | `sqlite:///db.sqlite3` |
| `REDIS_URL` | Redis URL (blank disables cache + async tasks) | (blank) |
| `FEATURE_COMMERCE` | Enable shop, Stripe Connect surfaces | `True` |
| `FEATURE_COMMUNITY` | Enable discussion posts, follows | `True` |
| `SOFT_LAUNCH` | Enable soft-launch banner and demo badges | `False` |
| `STRIPE_PUBLIC_KEY` / `STRIPE_SECRET_KEY` | Stripe keys | (required when `FEATURE_COMMERCE=True`) |
| `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY` | Cloudflare Turnstile | (disabled if blank) |
| `DJANGO_ADMINS` | Admin emails for notifications (`Name:email`) | (none) |
| `DEFAULT_FROM_EMAIL` | Sender address for emails | `noreply@example.com` |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for coding conventions and areas where help is needed. For setup, see [GETTING-STARTED.md](GETTING-STARTED.md); for deployment, see [DEPLOYMENT.md](DEPLOYMENT.md).

## License

AGPL-3.0 — see [LICENSE](LICENSE) for details.

Built with care for independent creators everywhere, from Oil City, Pennsylvania.
