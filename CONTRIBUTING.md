# Contributing

Thanks for your interest. Code, design, documentation, tests, and feedback are all welcome.

For setup, see [GETTING-STARTED.md](GETTING-STARTED.md). The short version: `python manage.py setup` walks you through the whole bootstrap in a few minutes.

## Where Help Is Needed

### Features

- **Distance-based filtering** — the Address model has lat/lng fields and geocoding works. A "within X miles" filter on the directories would compose with the existing map and the new faceted-counts pattern.
- **Saved/bookmarked profiles and events** — let fans bookmark things they're interested in.
- **Event RSVP/interest** — "Interested" or "Going" buttons on events for headcount signals.
- **Social share links** — simple URL-based share buttons on profiles, events, and products.
- **Image lightbox** — click-to-enlarge for media items and product images.
- **REST API** — Django REST Framework or Django Ninja endpoints for potential mobile/desktop clients.
- **Pagination prefetch on hover** — the pet-listing-grid reference pattern; HTMX has `hx-ext="preload"` or `hx-trigger="mouseenter once"`. Only worth it if pagination feels slow.

### Design & Frontend

- **Template refinement** — Tailwind templates are functional but could use design polish.
- **Responsive testing** — mobile layouts, touch interactions.
- **Accessibility** — skip navigation links, keyboard navigation, more `aria-live` regions beyond the directory result counts already wired up.
- **Tailwind build pipeline** — currently using the CDN; a production build with purging would reduce page weight. Compatible with the CSS-variables theming pattern, just needs build configuration.
- **More themes in `themes/`** — `default` and `midnight` ship; a high-contrast theme, a print stylesheet, or community-contributed palettes are all welcome additions.

### Testing

- **Commerce app tests** — Stripe Connect flow, checkout, product groups, and order management need coverage.
- **Community app tests** — posts, replies, likes, and moderation.
- **Integration tests** — signup-to-published-profile flow, booking request lifecycle, notification delivery.

### Infrastructure

- **Lightweight analytics** — Plausible or Umami integration for privacy-friendly traffic insights.
- **Automated backups** — PostgreSQL backup strategy management command.
- **Deployment guides for other platforms** — current [DEPLOYMENT.md](DEPLOYMENT.md) covers Docker Compose; Railway, Fly.io, and DigitalOcean App Platform recipes would help.

## Project Conventions

These aren't obvious from reading the code and save you from style-nit feedback in code review.

- **Apps live in `apps/`.** Each Django app is a subdirectory.
- **Shared models in `apps/core/`** — `PublishableProfile` (abstract base for creator/venue profiles), Notification, Report, BlockedWord, ProfileView, Address.
- **Function-based views**, not class-based. Match what's there.
- **HTMX partials are prefixed with `_`** (e.g., `_creator_list.html`). Views check `request.htmx` to decide which template to render.
- **Reusable template includes live in `templates/includes/`** — `_follow_button.html`, `_report_button.html`, `_searchable_select.html`, `_multi_select.html`, `_availability_list.html`, `_unpublished_reminder.html`.
- **Notifications** — use `apps.core.models.Notification` for in-app, `apps.core.notifications` for email.
- **Image optimization** — `apps.core.image_utils.optimize_image()` auto-resizes uploads in model `save()` methods.
- **Prices in cents** — stored as integers, exposed as dollars via form proxy fields (`price_dollars`, `shipping_dollars`, `bundle_price_dollars`).
- **Seed data is idempotent** — `seed_data` uses `get_or_create` for taxonomy.
- **Tests alongside apps** — each app has a `tests/` directory with `helpers.py` for factory functions. Use the existing `make_*` helpers.
- **No JavaScript build step.** HTMX, Alpine.js, Leaflet.js, and Tailwind load from CDNs. The only custom JS is `static/js/searchable-select.js`.
- **Default to `--parallel auto`** when running tests. The suite is parallel-safe (374+ tests in ~50s).
- **Faceted filter helpers** — when adding a new directory-style view, use `apps.core.facets.facet_counts()` and `decorate_options()` to render per-option result counts. See [creators/views.py](apps/creators/views.py) for the canonical pattern.
- **Hardcoded branding is a bug.** Anything user-facing that says "Oil Region" should be a `SiteBranding` field. Wire it through `apps.pages.context_processors`.
- **Audit-trail-friendly model design.** If you add a model where state transitions could be disputed, attach `HistoricalRecords()` and register it with `SimpleHistoryAdmin`.

## License

By contributing, you agree that your contributions will be licensed under the [AGPL-3.0 License](LICENSE).
