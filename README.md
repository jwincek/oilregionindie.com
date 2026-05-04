# Oil Region Creative Hub

An open-source platform for independent musicians, visual artists, makers, venues, and fans. Born from twelve years of the [Oil Region Indie Music Festival](https://www.facebook.com/oilregionindie1/) in Oil City, Pennsylvania.

## What It Does

Creators build profiles showcasing their work across disciplines — a guitar-playing silversmith can list both crafts in one place. Venues list their spaces with contacts, amenities, and availability. Fans discover creators and events through directory filtering, full-text search, an interactive map, and a monthly calendar. Booking requests flow bidirectionally between creators and venues. Payments go directly to creators via Stripe Connect — the platform never holds funds.

## Quick Start

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_data --full
python manage.py runserver
```

Visit **http://localhost:8000**. Wagtail admin: **http://localhost:8000/cms/**. Admin dashboard: **http://localhost:8000/dashboard/**.

Sample accounts use `@oilregion-demo.example` emails with password `testpass123`. For a detailed walkthrough, see [GETTING-STARTED.md](GETTING-STARTED.md).

### Docker

```bash
cp .env.example .env
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_data --full
```

## Project Structure

```
oilregion-hub/
├── config/                 # Settings, URLs, sitemaps
├── apps/
│   ├── core/               # UserProfile, Notification, Report, BlockedWord,
│   │                         ProfileView, Address, Availability, digest,
│   │                         geocoding, image optimization, feeds, middleware
│   ├── creators/           # CreatorProfile, Discipline, Skill, Genre,
│   │                         MediaItem, Memberships, Social Links, Embeds
│   ├── venues/             # VenueProfile, VenueContact, VenueArea, Amenity
│   ├── events/             # Event, EventSlot, BookingRequest,
│   │                         BookingFeedback, Endorsement
│   ├── commerce/           # Product, ProductGroup, Order, Stripe Connect
│   ├── community/          # CommunityPost, Tag, likes
│   └── pages/              # Wagtail CMS: HomePage, ContentPage, Blog
├── templates/              # Django templates + HTMX partials
├── static/                 # JS, SVG icons, favicon
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.13, Django 6.0.3 |
| CMS | Wagtail 7.3.1 |
| Frontend | HTMX + Alpine.js + Tailwind CSS |
| Database | PostgreSQL (SQLite for dev) |
| Payments | Stripe Connect Express |
| Search | Wagtail full-text search (PostgreSQL) with ORM fallback |
| Maps | Leaflet.js + OpenStreetMap |
| Cache/Queue | Redis + Django Q2 |
| Auth | django-allauth (email + username) |
| Bot Protection | Cloudflare Turnstile |
| Deployment | Docker Compose |

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
- Terms of Service and Code of Conduct (editable in Wagtail CMS)
- Cloudflare Turnstile on signup

### Platform Operations
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

348 tests across core, creators, venues, and events:

```bash
python manage.py test apps.core.tests apps.creators.tests apps.venues.tests apps.events.tests -v 2
```

## Environment Variables

See [.env.example](.env.example) for the full list. Key settings:

| Variable | Purpose | Default |
|----------|---------|---------|
| `SOFT_LAUNCH` | Enable soft-launch banner and demo badges | `False` |
| `TURNSTILE_SITE_KEY` | Cloudflare Turnstile public key | (disabled) |
| `TURNSTILE_SECRET_KEY` | Cloudflare Turnstile secret key | (disabled) |
| `DJANGO_ADMINS` | Admin emails for notifications (`Name:email`) | (none) |
| `DEFAULT_FROM_EMAIL` | Sender address for emails | `noreply@oilregionindie.com` |
| `STRIPE_PUBLIC_KEY` | Stripe publishable key | (required for commerce) |
| `STRIPE_SECRET_KEY` | Stripe secret key | (required for commerce) |
| `DJANGO_DEBUG` | Debug mode | `False` |
| `DATABASE_URL` | PostgreSQL connection string | (required in production) |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, coding conventions, and areas where help is needed.

## License

AGPL-3.0 — see [LICENSE](LICENSE) for details.

Other independent arts communities can deploy their own instance with their own branding and creator base.

Built with care for independent creators everywhere, from Oil City, Pennsylvania.
