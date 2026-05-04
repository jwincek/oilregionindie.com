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
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set a `DJANGO_SECRET_KEY` (any random string works for local dev). The defaults work out of the box with SQLite.

### 4. Create the database

```bash
python manage.py migrate
```

### 5. Create an admin account

```bash
python manage.py createsuperuser
```

### 6. Seed the database

For development with full sample data:

```bash
python manage.py seed_data --full
```

This creates sample creators, venues, events, and 8 Wagtail pages (home, about, feedback, terms, code of conduct, help, blog, welcome post). All sample accounts use `@oilregion-demo.example` emails with password `testpass123`.

For a production-like setup (taxonomy + CMS pages, no sample profiles):

```bash
python manage.py seed_data --pages
```

### 7. Run the development server

```bash
python manage.py runserver
```

- Public site: http://localhost:8000
- Wagtail CMS: http://localhost:8000/cms/
- Django admin: http://localhost:8000/django-admin/
- Admin dashboard: http://localhost:8000/dashboard/ (staff users only)

## Docker Setup

```bash
cp .env.example .env
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_data --full
```

Visit http://localhost (nginx proxies to the app).

## Exploring the Codebase

### Key directories

- `config/` — Django settings, root URL configuration, sitemaps
- `apps/core/` — Shared models (UserProfile, Notification, Report, BlockedWord, ProfileView, Address), notifications, digest, geocoding, image optimization, feeds, middleware, template tags
- `apps/creators/` — Creator profiles, the directory, media/social link management, stats
- `apps/venues/` — Venue profiles, directory, social links, contacts
- `apps/events/` — Events, calendar, time slots, booking requests, feedback, endorsements
- `apps/commerce/` — Products, product groups, orders, Stripe Connect, digital downloads
- `apps/community/` — Discussion posts, tags, likes
- `apps/pages/` — Wagtail CMS page models and context processors
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

### How booking requests work

1. Creator visits a venue page and clicks "Request to Book" (or venue visits creator and clicks "Invite to Book")
2. Requester fills out event type (visual card selection), preferred dates, and a message
3. Receiving party sees the request in their booking inbox with a badge count
4. They accept or decline with an optional response message
5. Both parties are notified by email and in-app notification
6. On acceptance, contact info is revealed and a "Create Event" button appears
7. Both parties can leave private feedback and write public endorsements
8. Stale pending requests auto-expire after 30 days

### How commerce works

1. Creator adds products and product groups from "My Products" (no Stripe required)
2. Creator connects Stripe via the pre-onboarding setup page when ready
3. Buyers browse the creator's shop section and click "Buy Now"
4. Stripe Checkout handles payment (including shipping cost for physical items)
5. Digital products get immediate download links on the success page
6. Physical products appear in the creator's order detail view with shipping address
7. Creator marks items as shipped with optional tracking number; buyer gets notified

### Running tests

```bash
python manage.py test apps.core.tests apps.creators.tests apps.venues.tests apps.events.tests -v 2
```

348 tests covering models, views, and forms.

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

### Reset the database

```bash
rm db.sqlite3
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_data --full
```
