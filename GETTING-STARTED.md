# Getting Started

A step-by-step guide to running Oil Region Creative Hub locally for development.

## Prerequisites

- Python 3.13+
- pip
- Git
- (Optional) Docker and Docker Compose for containerized setup

No JavaScript build tools are required. The frontend uses Tailwind CSS via CDN, HTMX, and Alpine.js — all loaded from script tags.

## Local Setup

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/jeromewincek/oilregionindie.com.git
cd oilregion-hub
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

This creates sample creators, venues, events, and Wagtail pages. All sample accounts use password `testpass123`.

For a production-like setup (taxonomy + CMS pages, no sample profiles):

```bash
python manage.py seed_data --pages
```

### 7. Run the development server

```bash
python manage.py runserver
```

- Public site: http://localhost:8000
- Wagtail CMS admin: http://localhost:8000/cms/
- Django admin: http://localhost:8000/django-admin/

## Docker Setup

If you prefer containers:

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

- `config/` — Django settings, root URL configuration
- `apps/core/` — Shared models (Address, UserProfile, PublishableProfile), notifications, template tags
- `apps/creators/` — Creator profiles, the directory, media/social link management
- `apps/venues/` — Venue profiles and directory
- `apps/events/` — Events, time slots, booking requests
- `apps/pages/` — Wagtail CMS page models and context processors
- `templates/` — All HTML templates (Django template language + HTMX attributes)

### How the profile flow works

1. User signs up (email + password via django-allauth)
2. Email verification is required (`ACCOUNT_EMAIL_VERIFICATION = "mandatory"`)
3. After verification, user is redirected to `/creators/setup/`
4. User fills out their profile (starts as **draft**)
5. User clicks "Submit for Review" — status moves to **pending**
6. Admin gets an email notification
7. Admin approves in Django admin (bulk action) — status becomes **published**
8. Profile appears in the public directory

### Running tests

```bash
python manage.py test apps.core.tests apps.creators.tests apps.venues.tests apps.events.tests -v 2
```

348 tests covering models, views, forms, and the seed data command.

### Useful accounts after seeding with --full

| Email | Role | Profile |
|-------|------|---------|
| alice@example.com | Creator | Singer-songwriter (published) |
| bob@example.com | Creator | Painter + silversmith (published) |
| venue_billy@example.com | Venue owner | Billy's Bar (published) |
| eve@example.com | Creator | Draft profile (unpublished) |

All use password `testpass123`.

## Environment Variables

The `.env.example` file documents all available settings. Key ones for development:

| Variable | What it does | Dev default |
|----------|-------------|-------------|
| `DJANGO_DEBUG` | Enables debug mode, detailed errors | `True` |
| `SOFT_LAUNCH` | Shows site banner + demo badges | `True` |
| `TURNSTILE_SITE_KEY` | Cloudflare Turnstile (leave blank to skip) | (empty) |
| `DATABASE_URL` | Database connection | SQLite (no config needed) |
| `EMAIL_BACKEND` | Where emails go | File-based (writes to `tmp_emails/`) |

## Common Tasks

### Add a new discipline or skill

Edit `DISCIPLINES_WITH_SKILLS` in `apps/creators/management/commands/seed_data.py`, then re-run `python manage.py seed_data` (idempotent — won't duplicate existing entries).

### Approve a pending profile

1. Go to Django admin: http://localhost:8000/django-admin/
2. Navigate to Creator Profiles or Venue Profiles
3. Filter by "Publish status = Pending Review"
4. Select profiles, choose "Approve selected profiles (publish)" action

### Test the signup flow locally

1. Visit http://localhost:8000/accounts/signup/
2. Register with any email
3. Check `tmp_emails/` for the verification email (file-based backend in dev)
4. Click the confirmation link
5. Fill out your profile at `/creators/setup/`

### Reset the database

```bash
rm db.sqlite3
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_data --full
```
