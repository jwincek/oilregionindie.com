# Contributing to Oil Region Creative Hub

Thanks for your interest in contributing. This project is built to serve independent arts communities, and contributions of all kinds are welcome — code, design, documentation, testing, and feedback.

## Getting Set Up

Follow the [Getting Started guide](GETTING-STARTED.md) to get the project running locally. The full setup takes under five minutes with Python and pip.

## How to Contribute

1. **Find something to work on** — check the [Issues](https://github.com/jeromewincek/oilregionindie.com/issues) page. Issues labeled `good first issue` are scoped for newcomers. If you want to work on something not listed, open an issue first to discuss.
2. **Fork the repo** and create a branch from `main`.
3. **Make your changes** — keep commits focused and write descriptive messages.
4. **Run the tests** before submitting:
   ```bash
   python manage.py test apps.core.tests apps.creators.tests apps.venues.tests apps.events.tests -v 2
   ```
5. **Open a pull request** against `main` with a clear description of what changed and why.

## Where Help Is Needed

### Phase 2 — Commerce & Coordination

These are the highest-impact areas right now:

- **Stripe Connect integration** — wiring up Express onboarding and checkout flows in `apps/commerce/`. The models exist; the views and templates need to be built.
- **Booking request UI** — building notification and response views for the bidirectional booking system in `apps/events/`. The `BookingRequest` model is complete; it needs frontend views where creators and venues can see, accept, and decline requests.
- **Event management views** — creator- and venue-facing tools for managing lineups and time slots. The `EventSlot` model supports multi-stage scheduling; the frontend needs build-out.

### Phase 3 — Community & Growth

- **Community posts** — `apps/community/` is a stub. Discussion posts, tags, and feeds need implementation.
- **Distance-based search** — the `Address` model has lat/lng fields ready for geocoding. Needs a geocoding integration and distance filtering in directory views.
- **Notification system** — email digests, follow notifications, booking status updates.

### Design & Frontend

- **Template refinement** — the Tailwind-based templates are functional but could use design polish. All templates are in `templates/`.
- **Responsive testing** — mobile layouts, touch interactions, and accessibility improvements.
- **Tailwind build pipeline** — currently using the CDN; a production build with purging would reduce page weight.

### Testing

- **Commerce and community apps** — these are stubs awaiting tests alongside their implementation.
- **Integration tests** — the signup-to-published-profile flow, booking request lifecycle, and Stripe webhooks.

### Documentation

- **Deployment guides** — production setup on various platforms (Railway, Fly.io, DigitalOcean, etc.)
- **API documentation** — if/when a REST or GraphQL API is added.

## Code Style

- **Python** — follow the existing patterns in the codebase. Standard Django conventions: class-based or function-based views (this project uses function views), model/form/view organization per app.
- **Templates** — Django template language with Tailwind utility classes. HTMX for dynamic interactions, Alpine.js for client-side state (dropdowns, dismissals).
- **No JavaScript build step** — the frontend intentionally avoids a JS build pipeline. HTMX and Alpine.js are loaded via CDN.

## Project Conventions

- **Apps live in `apps/`** — each Django app is a subdirectory of `apps/`.
- **Shared models in `apps/core/`** — `PublishableProfile` is the abstract base for creator and venue profiles. New profile-like models should extend it.
- **Seed data is idempotent** — `python manage.py seed_data` uses `get_or_create` for taxonomy. Running it multiple times is safe.
- **Tests alongside apps** — each app has a `tests/` directory with `helpers.py` for factory functions. Use the existing `make_*` helpers rather than creating objects inline.
- **HTMX partials** — templates prefixed with `_` (e.g., `_creator_list.html`) are HTMX partials returned for fragment swaps. Views check `request.htmx` to decide which template to render.

## Reporting Issues

If you find a bug or have a suggestion, [open an issue](https://github.com/jeromewincek/oilregionindie.com/issues). Include:

- What you expected to happen
- What actually happened
- Steps to reproduce (if a bug)
- Your Python/Django version and OS

## License

By contributing, you agree that your contributions will be licensed under the [AGPL-3.0 License](LICENSE).
