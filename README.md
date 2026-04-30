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
# Edit .env — SQLite is the default for local dev

# Migrate, create admin, seed everything
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_data --full

# Run
python manage.py runserver
```

Visit **http://localhost:8000**. Wagtail admin: **http://localhost:8000/cms/**.

The `seed_data --full` command populates the database with sample creators, venues, events, availability flags, and Wagtail pages so you can see the platform working immediately. Sample accounts use `@oilregion-demo.example` emails with password `testpass123`.

For a more detailed walkthrough, see [GETTING-STARTED.md](GETTING-STARTED.md).

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
├── config/                 # Settings, URLs, WSGI/ASGI, sitemaps
├── apps/
│   ├── core/               # UserProfile, PublishableProfile, Notification,
│   │                         Report, BlockedWord, Address, Availability,
│   │                         digest, middleware, sitemaps, template tags
│   ├── creators/           # CreatorProfile, Discipline, Skill, Genre,
│   │                         MediaItem, Memberships, Social Links, Embeds
│   ├── venues/             # VenueProfile, VenueContact, VenueArea, Amenity
│   ├── events/             # Event, EventSlot, BookingRequest,
│   │                         BookingFeedback, Endorsement
│   ├── commerce/           # Product, Order, Stripe Connect
│   ├── community/          # CommunityPost, Tag, likes
│   └── pages/              # Wagtail CMS: HomePage, ContentPage, Blog
├── templates/
│   ├── account/            # Custom allauth auth pages
│   ├── core/               # Welcome, preferences, notifications, search
│   ├── creators/           # Directory, detail, edit, HTMX partials
│   ├── venues/             # Directory, detail, setup, edit
│   ├── events/             # Listing, detail, bookings, lineup, endorsements
│   ├── commerce/           # Products, checkout, Stripe Connect
│   ├── community/          # Posts, detail, likes
│   ├── pages/              # Wagtail page templates
│   └── includes/           # Nav, footer, reusable components
├── static/                 # CSS, JS, favicon, icons
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
| Cache/Queue | Redis + Django Q2 |
| Auth | django-allauth (email-based) |
| Bot Protection | Cloudflare Turnstile |
| Deployment | Docker Compose |

## Key Concepts

### Multi-Discipline Creators

Creators select specific skills (Guitar, Silversmithing, Wheel Throwing), and their disciplines (Musician, Jeweler, Ceramicist) are auto-populated. The directory filters by both. A creator can belong to a band or collective via memberships while maintaining their own individual profile.

### Profile Approval

New profiles start in **draft** status. Creators fill out their profile and submit it for review. An admin reviews and approves (publishes) the profile from the Django admin panel. Published profiles appear in the directory; drafts and pending profiles do not. Owners can preview their unpublished profile at its normal URL.

### Bidirectional Booking

BookingRequests work both ways: a creator can request to play at a venue, or a venue can invite a creator. Only the receiving party can accept or decline. After a booking is accepted, both parties can leave private feedback and write public endorsements.

### Commerce

Creators set up Stripe Connect, add products (digital or physical), and sell directly through their profile. Payments go to the creator's connected Stripe account. The platform can collect a configurable fee.

### Community

Discussion posts with four types (discussion, announcement, opportunity, review), threaded replies, tags, and likes. Users can follow creators and venues to receive notifications and weekly email digests.

### Moderation

Report buttons on profiles and posts, word filter on community content, user suspension via admin. Terms of Service and Code of Conduct are seeded as CMS pages and referenced during signup.

### Soft Launch Mode

Set `SOFT_LAUNCH=True` in `.env` to enable a site-wide banner and "Demo" badges on seed-data profiles. Designed for early deployments where sample data coexists with real user signups.

## Management Commands

```bash
python manage.py seed_data              # Taxonomy only (safe to re-run)
python manage.py seed_data --pages      # Taxonomy + Wagtail pages (production/soft launch)
python manage.py seed_data --full       # Full sample content (dev/demo)
python manage.py send_digests           # Send weekly email digests
python manage.py send_digests --dry-run # Preview without sending
python manage.py setup_schedules        # Configure Django Q recurring tasks
python manage.py refresh_embeds         # Backfill oEmbed HTML
python manage.py refresh_embeds --all   # Re-fetch all embeds
```

## Tests

348 tests across core, creators, venues, and events:

```bash
python manage.py test apps.core.tests apps.creators.tests apps.venues.tests apps.events.tests -v 2
```

## Seed Data

`seed_data` seeds 12 disciplines with 139 skills, 20 genres, 23 amenities, and 9 availability types.

`seed_data --pages` additionally creates 8 Wagtail CMS pages: home, about, feedback (with inline form), terms of service, code of conduct, help, blog index, and a welcome post. Ideal for production deployments.

`seed_data --full` additionally creates: 9 creator profiles (individuals, a band with memberships, a collective), 3 venues with contacts and areas, 5 events with slots, a booking request, availability flags, media items, social links, and all Wagtail pages. All sample accounts use `@oilregion-demo.example` emails with password `testpass123`.

## Environment Variables

See [.env.example](.env.example) for the full list. Key settings:

| Variable | Purpose | Default |
|----------|---------|---------|
| `SOFT_LAUNCH` | Enable soft-launch banner and demo badges | `False` |
| `TURNSTILE_SITE_KEY` | Cloudflare Turnstile public key | (disabled) |
| `TURNSTILE_SECRET_KEY` | Cloudflare Turnstile secret key | (disabled) |
| `DJANGO_ADMINS` | Admin emails for notifications (format: `Name:email`) | (none) |
| `DEFAULT_FROM_EMAIL` | Sender address for transactional emails | `noreply@oilregionindie.com` |
| `DJANGO_DEBUG` | Debug mode | `False` |
| `DATABASE_URL` | PostgreSQL connection string | (required in production) |

## Stripe Connect Setup

1. Create a [Stripe account](https://dashboard.stripe.com/) and enable [Connect](https://dashboard.stripe.com/connect/overview)
2. Add keys to `.env`: `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`
3. Set up webhook at `/shop/webhooks/stripe/` for `checkout.session.completed` and `payment_intent.payment_failed`

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, coding conventions, and areas where help is needed.

## License

AGPL-3.0 — see [LICENSE](LICENSE) for details.

Other independent arts communities can deploy their own instance with their own branding and creator base.

Built with care for independent creators everywhere, from Oil City, Pennsylvania.
