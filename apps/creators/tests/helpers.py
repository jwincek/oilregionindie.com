"""
Shared test helpers for the creators app.

These factory functions create test objects with sensible defaults.
Override any field by passing keyword arguments.
"""

import uuid

from django.contrib.auth import get_user_model

from apps.core.models import SocialPlatform
from apps.creators.models import (
    CreatorMembership,
    CreatorProfile,
    CreatorSocialLink,
    Discipline,
    Genre,
    MediaItem,
    Skill,
)

User = get_user_model()


def make_user(**kwargs):
    """Create a unique test user."""
    uid = uuid.uuid4().hex[:8]
    defaults = {
        "username": f"testuser_{uid}",
        "email": f"testuser_{uid}@example.com",
        "password": "testpass123",
    }
    defaults.update(kwargs)
    password = defaults.pop("password")
    user = User(**defaults)
    user.set_password(password)
    user.save()
    return user


def make_discipline(name="Musician", icon="music", **kwargs):
    """Create or retrieve a Discipline."""
    obj, _ = Discipline.objects.get_or_create(name=name, defaults={"icon": icon, **kwargs})
    return obj


def make_genre(name="Indie Rock", **kwargs):
    """Create or retrieve a Genre."""
    obj, _ = Genre.objects.get_or_create(name=name, defaults=kwargs)
    return obj


def make_skill(name="Guitar", discipline=None, **kwargs):
    """Create or retrieve a Skill under a discipline."""
    if discipline is None:
        discipline = make_discipline()
    obj, _ = Skill.objects.get_or_create(
        name=name, discipline=discipline, defaults=kwargs
    )
    return obj


def make_creator(user=None, display_name="Test Creator", publish_status="published", **kwargs):
    """Create a CreatorProfile with sensible defaults."""
    if user is None:
        user = make_user()
    defaults = {
        "display_name": display_name,
        "publish_status": publish_status,
        "profile_type": CreatorProfile.ProfileType.INDIVIDUAL,
        "location": "Oil City, PA",
        "home_region": "Venango County",
    }
    defaults.update(kwargs)
    return CreatorProfile.objects.create(user=user, **defaults)


def make_band(user=None, display_name="Test Band", **kwargs):
    """Create a band CreatorProfile."""
    return make_creator(
        user=user,
        display_name=display_name,
        profile_type=CreatorProfile.ProfileType.BAND,
        **kwargs,
    )


def make_collective(user=None, display_name="Test Collective", **kwargs):
    """Create a collective CreatorProfile."""
    return make_creator(
        user=user,
        display_name=display_name,
        profile_type=CreatorProfile.ProfileType.COLLECTIVE,
        **kwargs,
    )


def make_membership(group, member, role="", is_active=True, **kwargs):
    """Create a CreatorMembership linking a member to a group."""
    return CreatorMembership.objects.create(
        group=group, member=member, role=role, is_active=is_active, **kwargs
    )


def make_social_link(creator, platform=SocialPlatform.BANDCAMP, url="https://example.bandcamp.com", **kwargs):
    """Create a CreatorSocialLink."""
    return CreatorSocialLink.objects.create(
        creator=creator, platform=platform, url=url, **kwargs
    )


def make_media_item(creator, title="Test Track", media_type=MediaItem.MediaType.AUDIO, **kwargs):
    """Create a MediaItem on a creator's profile."""
    return MediaItem.objects.create(
        creator=creator, title=title, media_type=media_type, **kwargs
    )
