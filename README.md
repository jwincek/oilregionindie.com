# Oil Region Creative Hub

An open-source platform for independent musicians, visual artists, makers, venues, and fans. Born from twelve years of the [Oil Region Indie Music Festival](https://www.facebook.com/oilregionindie1/) in Oil City, Pennsylvania.

## What It Does

Creators build profiles showcasing their work across disciplines — a guitar-playing silversmith can list both crafts in one place. Venues list their spaces with contacts, amenities, and availability. Fans discover creators and events through directory filtering by discipline, skill, genre, location, and availability status. Booking requests flow bidirectionally between creators and venues. Payments go directly to creators via Stripe Connect — the platform never holds funds.

## Quick Start

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env — set DATABASE_URL=sqlite:///db.sqlite3 for local dev

# Migrate, create admin, seed everything
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_data --full

# Run
python manage.py runserver
```

Visit **http://localhost:8000**. Wagtail admin: **http://localhost:8000/cms/**.

The `seed_data --full` command populates the database with sample creators, venues, events, availability flags, and Wagtail pages so you can see the platform working immediately. Sample accounts use password `testpass123`.

### Docker

```bash
cp .env.example .env
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_data --full
```

Visit **http://localhost**.

## Project Structure

```
oilregion-hub/
├── config/                 # Settings, URLs, WSGI/ASGI
├── apps/
│   ├── core/               # Address, UserProfile, PublishableProfile (abstract),
│   │                         AvailabilityType, ProfileAvailability, SocialPlatform
│   ├── creators/           # CreatorProfile, Discipline, Skill, Genre,
│   │                         MediaItem, Memberships, Social Links, Embeds
│   ├── venues/             # VenueProfile, VenueContact, VenueArea, Amenity
│   ├── events/             # Event, EventSlot, BookingRequest
│   ├── commerce/           # Product, Order, Stripe Connect (Phase 2)
│   ├── community/          # CommunityPost, Tag (Phase 3 stub)
│   └── pages/              # Wagtail CMS: HomePage, ContentPage, Blog
├── templates/
│   ├── account/            # Custom allauth auth pages
│   ├── creators/           # Directory, detail, edit, HTMX partials
│   ├── venues/             # Directory, detail, setup, edit
│   ├── events/             # Listing, detail, create, edit, past
│   ├── pages/              # Wagtail page templates
│   └── includes/           # Nav, footer
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
| Embeds | Wagtail Embeds (oEmbed) + manual embed codes |
| Cache/Queue | Redis + Django Q |
| Auth | django-allauth (email-based) |
| Deployment | Docker Compose |

## Key Concepts

### Multi-Discipline Creators

Creators select specific skills (Guitar, Silversmithing, Wheel Throwing), and their disciplines (Musician, Jeweler, Ceramicist) are auto-populated. The directory filters by both. A creator can belong to a band or collective via memberships while maintaining their own individual profile.

### Availability System

Creators and venues set availability flags — "Available for Booking", "Accepting Commissions", "Gallery Space Available", etc. These are filterable in the directory and displayed on profile pages with optional notes like "Weekends only, July–September". The types are seeded and extensible without migrations.

### Bidirectional Booking

BookingRequests work both ways: a creator can request to play at a venue, or a venue can invite a creator. Only the receiving party can accept or decline. Managers of either profile can participate.

### Embed Pipeline

Media items support three sources: direct file upload, oEmbed URL (YouTube, SoundCloud, Vimeo — auto-fetched on save), or pasted embed code (Bandcamp and other providers without oEmbed). Cached HTML avoids API calls on page load.

### HTMX Management

Social links and media items on the creator edit page use HTMX for inline add/edit/delete without page reloads. Directory filters auto-submit on change.

## Management Commands

```bash
python manage.py seed_data              # Taxonomy only (safe to re-run)
python manage.py seed_data --full       # Full sample content (fresh DB)
python manage.py refresh_embeds         # Backfill oEmbed HTML
python manage.py refresh_embeds --all   # Re-fetch all embeds
```

## Tests

348 tests across core, creators, venues, and events:

```bash
python manage.py test apps.core apps.creators apps.venues apps.events -v 2
```

## Seed Data

`seed_data` seeds 12 disciplines with 139 skills, 20 genres, 23 amenities, and 9 availability types.

`seed_data --full` additionally creates: 9 creator profiles (individuals, a band with memberships, a collective), 3 venues modeled on Oil City locations with contacts and areas, 5 events with slots, a booking request, availability flags, media items, social links, and Wagtail pages (home, about, blog).

## Stripe Connect Setup

1. Create a [Stripe account](https://dashboard.stripe.com/) and enable [Connect](https://dashboard.stripe.com/connect/overview)
2. Add keys to `.env`: `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`
3. Set up webhook at `/shop/webhooks/stripe/` for `checkout.session.completed` and `payment_intent.payment_failed`

## Development Phases

**Phase 1 — Core Platform** (current): Creator profiles, venues, events, bookings, contacts, availability, embeds, HTMX management, auth pages, seed data, 348 tests. Substantially complete.

**Phase 2 — Commerce & Coordination**: Stripe Connect end-to-end, frontend event/lineup management, booking request views with notifications.

**Phase 3 — Community & Growth**: Discussion posts, follow notifications, email digests, advanced search, distance-based filtering.

## License

AGPL-3.0 — see [LICENSE](LICENSE) for details.

Other independent arts communities can deploy their own instance with their own branding and creator base.

Built with care for independent creators everywhere, from Oil City, Pennsylvania.