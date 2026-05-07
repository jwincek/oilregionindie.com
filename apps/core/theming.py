"""
Theme support — filesystem-driven, no PHP-style runtime.

A theme is a directory under ``./themes/`` containing:

  theme.json   metadata (required: name, version)
  theme.css    CSS variable overrides loaded after the defaults in
               base.html. Optional but expected.
  templates/   optional Django template overrides; checked before the
               project's own templates/ via ActiveThemeLoader.
  static/      optional additional static assets; reachable at
               /static/themes/<name>/static/... via STATICFILES_DIRS.

The active theme is stored on ``apps.pages.SiteBranding.active_theme``.
We avoid every WordPress-style trap: no theme-local Python is executed,
no upload-via-admin, no hooks/filters, no enqueue API. Themes are
content, not apps.
"""

import json
from pathlib import Path

from django.apps import apps as django_apps
from django.conf import settings
from django.template.loaders.filesystem import Loader as FilesystemLoader


def themes_dir() -> Path:
    return Path(settings.BASE_DIR) / "themes"


def discover_themes() -> dict[str, dict]:
    """Return ``{slug: metadata}`` for every valid theme on disk."""
    out: dict[str, dict] = {}
    root = themes_dir()
    if not root.exists():
        return out
    for theme_path in sorted(root.iterdir()):
        if not theme_path.is_dir():
            continue
        meta_path = theme_path / "theme.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except json.JSONDecodeError:
            continue
        meta["_path"] = theme_path
        out[theme_path.name] = meta
    return out


def theme_choices() -> list[tuple[str, str]]:
    """Choices list for ``SiteBranding.active_theme``."""
    discovered = discover_themes()
    if not discovered:
        return [("default", "Default")]
    return [(slug, meta.get("name", slug)) for slug, meta in discovered.items()]


# Cache the active theme per process so the template loader doesn't hit
# the DB on every template lookup. Invalidated by a post_save signal on
# SiteBranding (see apps/pages/apps.py).
_active_theme_cache: dict[str, str] = {}


def get_active_theme() -> str:
    cached = _active_theme_cache.get("name")
    if cached is not None:
        return cached
    name = "default"
    try:
        SiteBranding = django_apps.get_model("pages", "SiteBranding")
        b = SiteBranding.load()
        if b.active_theme:
            name = b.active_theme
    except Exception:
        # DB not ready (initial migrate, tests bootstrapping, etc.)
        pass
    _active_theme_cache["name"] = name
    return name


def invalidate_active_theme_cache(*args, **kwargs) -> None:
    _active_theme_cache.pop("name", None)


class ActiveThemeLoader(FilesystemLoader):
    """
    Resolves templates from the active theme's ``templates/`` directory
    first. Sits at the front of the loader chain so a theme can override
    ``base.html``, ``includes/footer.html``, etc., without touching core.
    """

    def get_dirs(self):
        return [str(themes_dir() / get_active_theme() / "templates")]
