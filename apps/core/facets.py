"""
Faceted-filter helpers for directory views.

The pattern: for each dropdown filter, render its options annotated with
how many results would be returned if the user selected that option,
holding all *other* active filters constant. Zero-count options are
hidden so the UI doesn't dangle dead choices, except for whichever
option is currently selected (so the user can still see and clear it).
"""

from django.db.models import Count


def facet_counts(qs, field):
    """Return ``{value: count}`` for ``field`` over ``qs`` (deduped by id)."""
    rows = qs.values(field).annotate(c=Count("id", distinct=True))
    return {row[field]: row["c"] for row in rows if row[field] is not None}


def decorate_options(items, count_map, current_value, *, value_attr="slug",
                     label_attr="name", extras=()):
    """
    Turn a queryset/iterable of model instances or (value, label) tuples
    into a list of dicts ``{value, label, count, **extras}``.

    Drops zero-count entries unless they're the currently-selected one.
    Each ``extras`` entry maps an output key to a callable that pulls a
    value off the source item (e.g. ``"discipline": lambda s: s.discipline.name``).
    """
    out = []
    for item in items:
        if isinstance(item, tuple) and len(item) == 2:
            value, label = item
        else:
            value = getattr(item, value_attr)
            label = getattr(item, label_attr)
        count = count_map.get(value, 0)
        if count == 0 and value != current_value:
            continue
        entry = {"value": str(value), "label": str(label), "count": count}
        for key, getter in (extras or {}).items():
            try:
                entry[key] = getter(item)
            except (AttributeError, TypeError):
                entry[key] = ""
        out.append(entry)
    return out
