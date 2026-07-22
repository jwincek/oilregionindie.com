---
name: sync-seeded-pages
description: After editing the seeded Wagtail page content (Help/Feedback/Terms/About/etc.) in seed_data.py, also update the already-created page instances in a running dev database. Use whenever you change a ContentPage body in _seed_wagtail_pages — a source edit alone does NOT touch existing DB pages.
---

The public Wagtail pages live in **two places**:

1. `apps/creators/management/commands/seed_data.py` (`_seed_wagtail_pages`) — the
   source, which only affects a **fresh** database (production's deploy-day
   `seed_data --pages`).
2. The `ContentPage` rows already created in the running dev DB — untouched by a
   source edit.

Editing the source without syncing the DB means what you browse locally differs
from what the seed produces. This skill closes that gap without hand-copying
content, by extracting the new body straight from the source via `ast`.

## Run

Save as a scratch script and pipe into the shell (extend `TARGET_SLUGS` to the
pages you changed):

```python
# sync_pages.py
import ast
SEED = "apps/creators/management/commands/seed_data.py"
TARGET_SLUGS = {"help", "feedback", "terms"}   # <-- the slugs you edited

tree = ast.parse(open(SEED).read())
bodies = {}
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "ContentPage":
        kw = {k.arg: k.value for k in node.keywords}
        if "slug" in kw and "body" in kw:
            slug = ast.literal_eval(kw["slug"])
            if slug in TARGET_SLUGS:
                bodies[slug] = ast.literal_eval(kw["body"])
assert set(bodies) == TARGET_SLUGS, f"got {set(bodies)}, want {TARGET_SLUGS}"

from apps.pages.models import ContentPage
for slug, body in sorted(bodies.items()):
    page = ContentPage.objects.get(slug=slug)
    page.body = body
    page.save_revision().publish()
    print(f"synced /{slug}/ ({len(body)} blocks)")
```

```bash
./venv3-13/bin/python manage.py shell < sync_pages.py
```

## Verify

Fetch the rendered pages and grep for the new text — remember `HTTP_HOST`:

```bash
./venv3-13/bin/python manage.py shell -c "
from django.test import Client
html = Client(HTTP_HOST='localhost').get('/help/').content.decode()
print('new text present:', 'the phrase you added' in html)
"
```

## Note

Only `ContentPage` bodies are handled (matched by `ContentPage(` call). HomePage,
BlogIndexPage, and BlogPost use different models — extend the AST match if you
edit those. If page edits become frequent, promote this to a
`sync_seeded_pages` management command.
