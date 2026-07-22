---
name: verify
description: Confirm a change works in the real running app, not just the test suite — boot the production compose stack for a smoke test, and/or drive the page in a headless browser. Use for frontend/template/CMS/Wagtail changes, production-config changes, or any bug that needs to be seen rather than asserted.
---

Tests prove logic; this proves the app runs. Reach for it when the change has a
runtime surface the suite can't see — templates, JS, the map, Wagtail admin,
nginx/proxy config, the Dockerfile, or a "clicking it does nothing" bug.

## Path A — production-stack smoke boot

Boots the full prod stack (gunicorn + Postgres + Redis + nginx + worker) with a
prod-like env, without touching the dev `.env`. Use for prod-compose, Dockerfile,
dependency-pin, or CMS-upgrade changes.

Write this override to the scratchpad (it's regenerated each time; promoting it
to a committed `docker-compose.smoke.yml` is a reasonable future step):

```yaml
# docker-compose.smoke.yml
x-smoke-env: &smoke-env
  DJANGO_DEBUG: "False"
  DJANGO_SECRET_KEY: "smoke-only-not-for-production"
  DJANGO_ALLOWED_HOSTS: "oilregion.test,localhost,127.0.0.1"
  DATABASE_URL: "postgres://oilregion:x@db:5432/oilregion"
  REDIS_URL: "redis://redis:6379/0"
  EMAIL_BACKEND: "django.core.mail.backends.console.EmailBackend"
  STRIPE_PUBLIC_KEY: "pk_test_smoke"
  STRIPE_SECRET_KEY: "sk_test_smoke"
  STRIPE_WEBHOOK_SECRET: "whsec_smoke"
  WAGTAILADMIN_BASE_URL: "https://oilregion.test"
  SOFT_LAUNCH: "True"
services:
  web: { environment: *smoke-env }
  worker: { environment: *smoke-env }
  nginx:
    ports: ["127.0.0.1:8080:80"]
```

```bash
POSTGRES_PASSWORD=x docker compose -f docker-compose.prod.yml -f <smoke> build
POSTGRES_PASSWORD=x docker compose -f docker-compose.prod.yml -f <smoke> up -d --wait --wait-timeout 300
# nginx requires the forwarded-proto header or Django SSL-redirects the request:
curl -s -o /dev/null -w "%{http_code}\n" -H "Host: oilregion.test" -H "X-Forwarded-Proto: https" http://127.0.0.1:8080/
# tear down (the -v drops the throwaway volumes):
POSTGRES_PASSWORD=x docker compose -f docker-compose.prod.yml -f <smoke> down -v
```

## Path B — headless browser (for actual UI behavior)

For "does clicking this work" — the map cluster/spiderfy bug and the events-on-map
popups were both diagnosed this way. There is no bundled `chromium-cli` here, so
use Playwright directly.

```bash
# one-time, in a scratch dir:
npm i playwright && npx playwright install --with-deps chromium
# run the dev server on a non-clashing port:
nohup ./venv3-13/bin/python manage.py runserver 127.0.0.1:8020 > /tmp/dev.log 2>&1 & echo $! > /tmp/dev.pid
```

Drive it with a Node script: `chromium.launch()` → `newPage()` → `goto('http://127.0.0.1:8020/...')`
→ act → `page.screenshot(...)`. **Look at the screenshot** — a blank frame is a
failure. Register `page.on('pageerror', ...)` — the double-render map bug announced
itself as "Map container is already initialized" in the console.

## Gotchas that recur

- **`Client(HTTP_HOST='localhost')`** — a bare Django test Client in
  `manage.py shell` 400s on ALLOWED_HOSTS without it.
- **Seed real data first** if the page needs content: `manage.py seed_data --full`
  (geocodes venue addresses via Nominatim — needs network).
- Always tear down / kill the dev server when done.

## Adapting to a similar project

Swap the smoke env vars, the compose file names, the ports, and the venv path.
Path B is project-agnostic apart from the dev-server command and URLs.
