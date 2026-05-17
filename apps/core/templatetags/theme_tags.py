"""
Template tags for resolving theme static assets through the staticfiles
storage backend.

Under ManifestStaticFilesStorage (production), `{% static "..." %}`
rewrites filenames with a content hash so the browser cache busts on
each deploy. The base template's theme stylesheet is loaded with a
*dynamic* path (`themes/<active_theme>/theme.css`) that can't be
expressed in a literal `{% static ... %}` call. This tag closes the
gap: it asks the configured staticfiles storage for the URL of
`themes/<theme>/theme.css`, which yields the hashed filename in
production and the plain path in DEBUG mode.
"""

from django import template
from django.contrib.staticfiles.storage import staticfiles_storage

register = template.Library()


@register.simple_tag
def theme_static(active_theme):
    """Return the (possibly manifest-hashed) URL for the given theme's
    `theme.css`. Falls back to the default theme path if the file isn't
    in the manifest yet (e.g., a freshly added theme that hasn't been
    collectstatic'd)."""
    path = f"themes/{active_theme or 'default'}/theme.css"
    try:
        return staticfiles_storage.url(path)
    except ValueError:
        # ManifestStaticFilesStorage raises ValueError when the file
        # isn't in the manifest. Fall back to the un-hashed path so
        # a missing manifest entry doesn't break the page render.
        return f"/static/{path}"
