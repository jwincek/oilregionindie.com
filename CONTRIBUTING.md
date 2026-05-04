# Contributing to Oil Region Creative Hub

Thanks for your interest in contributing. This project is built to serve independent arts communities, and contributions of all kinds are welcome — code, design, documentation, testing, and feedback.

## Getting Set Up

Follow the [Getting Started guide](GETTING-STARTED.md) to get the project running locally. The full setup takes under five minutes with Python and pip.

## How to Contribute

1. **Find something to work on** — check the [Issues](https://github.com/jwincek/oilregionindie.com/issues) page. Issues labeled `good first issue` are scoped for newcomers. If you want to work on something not listed, open an issue first to discuss.
2. **Fork the repo** and create a branch from `main`.
3. **Make your changes** — keep commits focused and write descriptive messages.
4. **Run the tests** before submitting:
   ```bash
   python manage.py test apps.core.tests apps.creators.tests apps.venues.tests apps.events.tests -v 2
   ```
5. **Open a pull request** against `main` with a clear description of what changed and why.

## Where Help Is Needed

### Features

- **Distance-based filtering** — the Address model has lat/lng fields and geocoding works. Adding a "within X miles" filter to directories would connect with the existing map.
- **Saved/bookmarked profiles and events** — let fans bookmark things they're interested in.
- **Event RSVP/interest** — "Interested" or "Going" buttons on events for headcount signals.
- **Social share links** — simple URL-based share buttons on profiles, events, and products.
- **Image lightbox** — click-to-enlarge for media items and product images.
- **REST API** — Django REST Framework or Django Ninja endpoints for potential mobile/desktop clients.

### Design & Frontend

- **Template refinement** — the Tailwind-based templates are functional but could use design polish.
- **Responsive testing** — mobile layouts, touch interactions.
- **Accessibility** — skip navigation links, ARIA labels on interactive elements, keyboard navigation improvements.
- **Tailwind build pipeline** — currently using the CDN; a production build with purging would reduce page weight.
- **SVG initials centering** — the initials avatars may need CSS adjustments in some browsers due to Tailwind's box-sizing reset.

### Testing

- **Commerce app tests** — the Stripe Connect flow, checkout, product groups, and order management need test coverage.
- **Community app tests** — posts, replies, likes, and moderation.
- **Integration tests** — the signup-to-published-profile flow, booking request lifecycle, and notification delivery.

### Infrastructure

- **Lightweight analytics** — Plausible or Umami integration for privacy-friendly traffic insights.
- **Automated backups** — PostgreSQL backup strategy documentation or management command.
- **Deployment guides** — production setup on various platforms (Railway, Fly.io, DigitalOcean, etc.).

## Code Style

- **Python** — follow the existing patterns. Function-based views, model/form/view organization per app.
- **Templates** — Django template language with Tailwind utility classes. HTMX for dynamic interactions, Alpine.js for client-side state.
- **No JavaScript build step** — HTMX, Alpine.js, and Leaflet.js are loaded via CDN. The only custom JS is `static/js/searchable-select.js`.

## Project Conventions

- **Apps live in `apps/`** — each Django app is a subdirectory.
- **Shared models in `apps/core/`** — PublishableProfile (abstract base for profiles), Notification, Report, BlockedWord, ProfileView, Address.
- **Seed data is idempotent** — `python manage.py seed_data` uses `get_or_create` for taxonomy.
- **Tests alongside apps** — each app has a `tests/` directory with `helpers.py` for factory functions. Use the existing `make_*` helpers.
- **HTMX partials** — templates prefixed with `_` (e.g., `_creator_list.html`) are HTMX partials. Views check `request.htmx` to decide which template to render.
- **Notifications** — use `apps.core.models.Notification` for in-app and `apps.core.notifications` for email.
- **Reusable template includes** — `templates/includes/` has shared components: `_follow_button.html`, `_report_button.html`, `_searchable_select.html`, `_multi_select.html`, `_availability_list.html`, `_unpublished_reminder.html`.
- **Image optimization** — `apps.core.image_utils.optimize_image()` auto-resizes uploads in model `save()` methods.
- **Prices in cents** — stored as integers in the database, displayed as dollars via form proxy fields (`price_dollars`, `shipping_dollars`, `bundle_price_dollars`).

## Reporting Issues

If you find a bug or have a suggestion, [open an issue](https://github.com/jwincek/oilregionindie.com/issues) or use the [feedback form](https://oilregionindie.com/feedback/) on the live site. Include:

- What you expected to happen
- What actually happened
- Steps to reproduce (if a bug)
- Your Python/Django version and OS

## License

By contributing, you agree that your contributions will be licensed under the [AGPL-3.0 License](LICENSE).
