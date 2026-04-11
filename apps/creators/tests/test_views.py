"""
Tests for creators app views.

Covers: directory with filters, detail page, setup/edit auth gating,
profile creation flow, and HTMX partial responses.
"""

from django.test import TestCase, RequestFactory
from django.urls import reverse

from apps.creators.models import CreatorProfile

from .helpers import (
    make_creator,
    make_band,
    make_discipline,
    make_genre,
    make_skill,
    make_user,
)


# ---------------------------------------------------------------------------
# Directory view
# ---------------------------------------------------------------------------


class DirectoryViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("creators:directory")

        # Disciplines and skills
        cls.musician = make_discipline("Musician")
        cls.jeweler = make_discipline("Jeweler")
        cls.guitar = make_skill("Guitar", discipline=cls.musician)
        cls.silver = make_skill("Silversmithing", discipline=cls.jeweler)

        # Availability types
        from apps.core.models import AvailabilityType, ProfileAvailability
        cls.avail_booking = AvailabilityType.objects.create(
            name="Available for Booking", applies_to="creator", sort_order=1,
        )

        # Creators
        cls.guitarist = make_creator(display_name="Alice Guitar", location="Oil City, PA")
        cls.guitarist.disciplines.add(cls.musician)
        cls.guitarist.skills.add(cls.guitar)
        ProfileAvailability.objects.create(
            creator=cls.guitarist, availability_type=cls.avail_booking,
        )

        cls.silversmith = make_creator(display_name="Bob Silver", location="Franklin, PA")
        cls.silversmith.disciplines.add(cls.jeweler)
        cls.silversmith.skills.add(cls.silver)

        cls.both = make_creator(display_name="Carol Both", location="Titusville, PA")
        cls.both.disciplines.add(cls.musician, cls.jeweler)
        cls.both.skills.add(cls.guitar, cls.silver)

        cls.unpublished = make_creator(
            display_name="Dave Hidden", is_published=False
        )

        cls.band = make_band(display_name="The Test Band")

    def test_directory_loads(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creators/directory.html")

    def test_excludes_unpublished(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, "Dave Hidden")

    def test_shows_published(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Alice Guitar")
        self.assertContains(response, "Bob Silver")

    def test_filter_by_discipline(self):
        response = self.client.get(self.url, {"discipline": "musician"})
        self.assertContains(response, "Alice Guitar")
        self.assertContains(response, "Carol Both")
        self.assertNotContains(response, "Bob Silver")

    def test_filter_by_skill(self):
        response = self.client.get(self.url, {"skill": "silversmithing"})
        self.assertContains(response, "Bob Silver")
        self.assertContains(response, "Carol Both")
        self.assertNotContains(response, "Alice Guitar")

    def test_filter_by_profile_type_band(self):
        response = self.client.get(self.url, {"profile_type": "band"})
        self.assertContains(response, "The Test Band")
        self.assertNotContains(response, "Alice Guitar")

    def test_filter_by_profile_type_individual(self):
        response = self.client.get(self.url, {"profile_type": "individual"})
        self.assertContains(response, "Alice Guitar")
        self.assertNotContains(response, "The Test Band")

    def test_filter_by_location(self):
        response = self.client.get(self.url, {"location": "Oil City"})
        self.assertContains(response, "Alice Guitar")
        self.assertNotContains(response, "Bob Silver")

    def test_search_by_name(self):
        response = self.client.get(self.url, {"q": "Carol"})
        self.assertContains(response, "Carol Both")
        self.assertNotContains(response, "Alice Guitar")

    def test_combined_filters(self):
        response = self.client.get(self.url, {
            "discipline": "musician",
            "location": "Titusville",
        })
        self.assertContains(response, "Carol Both")
        self.assertNotContains(response, "Alice Guitar")

    def test_filter_by_availability(self):
        response = self.client.get(self.url, {"availability": "available-for-booking"})
        self.assertContains(response, "Alice Guitar")
        self.assertNotContains(response, "Bob Silver")
        self.assertNotContains(response, "Carol Both")

    def test_htmx_returns_partial(self):
        response = self.client.get(
            self.url,
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creators/_creator_list.html")

    def test_empty_results(self):
        response = self.client.get(self.url, {"q": "zzzznonexistent"})
        self.assertContains(response, "No creators found")


# ---------------------------------------------------------------------------
# Detail view
# ---------------------------------------------------------------------------


class DetailViewTest(TestCase):
    def test_published_creator_loads(self):
        creator = make_creator(display_name="Visible Creator")
        response = self.client.get(
            reverse("creators:detail", kwargs={"slug": creator.slug})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visible Creator")

    def test_unpublished_creator_returns_404(self):
        creator = make_creator(display_name="Hidden", is_published=False)
        response = self.client.get(
            reverse("creators:detail", kwargs={"slug": creator.slug})
        )
        self.assertEqual(response.status_code, 404)

    def test_nonexistent_slug_returns_404(self):
        response = self.client.get(
            reverse("creators:detail", kwargs={"slug": "no-such-creator"})
        )
        self.assertEqual(response.status_code, 404)

    def test_detail_shows_disciplines(self):
        creator = make_creator(display_name="Skilled Creator")
        d = make_discipline("Musician")
        creator.disciplines.add(d)
        response = self.client.get(
            reverse("creators:detail", kwargs={"slug": creator.slug})
        )
        self.assertContains(response, "Musician")

    def test_detail_shows_skills_by_discipline(self):
        d = make_discipline("Musician")
        s = make_skill("Guitar", discipline=d)
        creator = make_creator(display_name="Guitarist")
        creator.skills.add(s)
        creator.sync_disciplines_from_skills()
        response = self.client.get(
            reverse("creators:detail", kwargs={"slug": creator.slug})
        )
        self.assertContains(response, "Guitar")


# ---------------------------------------------------------------------------
# Setup view (requires login, creates profile)
# ---------------------------------------------------------------------------


class SetupViewTest(TestCase):
    def setUp(self):
        self.url = reverse("creators:setup")
        self.user = make_user()

    def test_requires_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_loads_for_authenticated_user(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creators/setup.html")

    def test_redirects_if_profile_exists(self):
        make_creator(user=self.user)
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("creators:edit"))

    def test_creates_profile_on_post(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {
            "display_name": "New Creator",
            "profile_type": "individual",
            "bio": "",
            "location": "Oil City",
            "home_region": "Venango County",
            "website": "",
            "is_published": True,
        })
        self.assertTrue(CreatorProfile.objects.filter(user=self.user).exists())
        creator = self.user.creator_profile
        self.assertEqual(creator.display_name, "New Creator")
        self.assertEqual(creator.slug, "new-creator")

    def test_skills_sync_disciplines_on_setup(self):
        """Skills selected during setup should auto-populate disciplines."""
        musician = make_discipline("Musician")
        guitar = make_skill("Guitar", discipline=musician)
        self.client.force_login(self.user)
        self.client.post(self.url, {
            "display_name": "Skill Test Creator",
            "profile_type": "individual",
            "skills": [guitar.pk],
            "bio": "",
            "location": "",
            "home_region": "",
            "website": "",
            "is_published": True,
        })
        creator = self.user.creator_profile
        self.assertIn(musician, creator.disciplines.all())


# ---------------------------------------------------------------------------
# Edit view (requires login, requires existing profile)
# ---------------------------------------------------------------------------


class EditViewTest(TestCase):
    def setUp(self):
        self.url = reverse("creators:edit")
        self.user = make_user()
        self.profile = make_creator(user=self.user, display_name="Editable Creator")

    def test_requires_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_loads_for_owner(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creators/edit.html")

    def test_updates_profile_on_post(self):
        self.client.force_login(self.user)
        self.client.post(self.url, {
            "display_name": "Updated Name",
            "profile_type": "individual",
            "bio": "",
            "location": "Franklin, PA",
            "home_region": "",
            "website": "",
            "is_published": True,
        })
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.display_name, "Updated Name")
        self.assertEqual(self.profile.location, "Franklin, PA")

    def test_404_if_no_profile(self):
        other_user = make_user()
        self.client.force_login(other_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# Add media view
# ---------------------------------------------------------------------------


class AddMediaViewTest(TestCase):
    def setUp(self):
        self.url = reverse("creators:add_media")
        self.user = make_user()
        self.profile = make_creator(user=self.user)

    def test_requires_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_loads_for_creator(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_creates_media_item(self):
        self.client.force_login(self.user)
        self.client.post(self.url, {
            "title": "My Song",
            "media_type": "audio",
            "embed_url": "https://soundcloud.com/example/track",
            "embed_code": "",
            "description": "A test track",
            "sort_order": 0,
            "is_featured": False,
        })
        self.assertEqual(self.profile.media_items.count(), 1)
        self.assertEqual(self.profile.media_items.first().title, "My Song")

    def test_creates_media_with_embed_code(self):
        self.client.force_login(self.user)
        embed = '<iframe src="https://bandcamp.com/EmbeddedPlayer/track=12345"></iframe>'
        self.client.post(self.url, {
            "title": "Bandcamp Track",
            "media_type": "audio",
            "embed_code": embed,
            "embed_url": "",
            "description": "",
            "sort_order": 0,
            "is_featured": False,
        })
        self.assertEqual(self.profile.media_items.count(), 1)
        item = self.profile.media_items.first()
        self.assertEqual(item.embed_html, embed)


# ---------------------------------------------------------------------------
# Social link views (HTMX)
# ---------------------------------------------------------------------------


class SocialLinksViewTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.profile = make_creator(user=self.user, display_name="Link Tester")

    def test_list_requires_login(self):
        response = self.client.get(reverse("creators:social_links"))
        self.assertEqual(response.status_code, 302)

    def test_list_loads(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("creators:social_links"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creators/_social_links.html")

    def test_add_form_loads(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("creators:add_social_link"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creators/_social_link_form.html")

    def test_add_link(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("creators:add_social_link"), {
            "platform": "bandcamp",
            "url": "https://example.bandcamp.com",
            "sort_order": 0,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.profile.social_links.count(), 1)
        link = self.profile.social_links.first()
        self.assertEqual(link.platform, "bandcamp")
        self.assertEqual(link.url, "https://example.bandcamp.com")

    def test_add_link_validation(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("creators:add_social_link"), {
            "platform": "bandcamp",
            "url": "not-a-url",
            "sort_order": 0,
        })
        self.assertEqual(response.status_code, 200)
        # Should return form with errors, not create the link
        self.assertEqual(self.profile.social_links.count(), 0)
        self.assertTemplateUsed(response, "creators/_social_link_form.html")

    def test_edit_form_loads(self):
        from apps.creators.models import CreatorSocialLink
        link = CreatorSocialLink.objects.create(
            creator=self.profile, platform="bandcamp",
            url="https://example.bandcamp.com",
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("creators:edit_social_link", kwargs={"pk": link.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creators/_social_link_form.html")

    def test_edit_link(self):
        from apps.creators.models import CreatorSocialLink
        link = CreatorSocialLink.objects.create(
            creator=self.profile, platform="bandcamp",
            url="https://example.bandcamp.com",
        )
        self.client.force_login(self.user)
        self.client.post(reverse("creators:edit_social_link", kwargs={"pk": link.pk}), {
            "platform": "soundcloud",
            "url": "https://soundcloud.com/example",
            "sort_order": 1,
        })
        link.refresh_from_db()
        self.assertEqual(link.platform, "soundcloud")
        self.assertEqual(link.url, "https://soundcloud.com/example")

    def test_delete_link(self):
        from apps.creators.models import CreatorSocialLink
        link = CreatorSocialLink.objects.create(
            creator=self.profile, platform="bandcamp",
            url="https://example.bandcamp.com",
        )
        self.client.force_login(self.user)
        response = self.client.post(reverse("creators:delete_social_link", kwargs={"pk": link.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.profile.social_links.count(), 0)

    def test_cannot_edit_others_link(self):
        from apps.creators.models import CreatorSocialLink
        other_user = make_user()
        other_profile = make_creator(user=other_user, display_name="Other")
        link = CreatorSocialLink.objects.create(
            creator=other_profile, platform="bandcamp",
            url="https://other.bandcamp.com",
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("creators:edit_social_link", kwargs={"pk": link.pk}))
        self.assertEqual(response.status_code, 404)

    def test_cannot_delete_others_link(self):
        from apps.creators.models import CreatorSocialLink
        other_user = make_user()
        other_profile = make_creator(user=other_user, display_name="Other")
        link = CreatorSocialLink.objects.create(
            creator=other_profile, platform="bandcamp",
            url="https://other.bandcamp.com",
        )
        self.client.force_login(self.user)
        response = self.client.post(reverse("creators:delete_social_link", kwargs={"pk": link.pk}))
        self.assertEqual(response.status_code, 404)
        # Link should still exist
        self.assertTrue(CreatorSocialLink.objects.filter(pk=link.pk).exists())


# ---------------------------------------------------------------------------
# Media management views (HTMX)
# ---------------------------------------------------------------------------


class MediaManagementViewTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.profile = make_creator(user=self.user, display_name="Media Tester")

    def _make_item(self, title="Test Track", **kwargs):
        from apps.creators.models import MediaItem
        defaults = {
            "creator": self.profile,
            "title": title,
            "media_type": "audio",
            "sort_order": 0,
        }
        defaults.update(kwargs)
        return MediaItem.objects.create(**defaults)

    def test_list_requires_login(self):
        response = self.client.get(reverse("creators:media_items"))
        self.assertEqual(response.status_code, 302)

    def test_list_loads(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("creators:media_items"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creators/_media_items.html")

    def test_list_shows_items(self):
        self._make_item(title="Visible Track")
        self.client.force_login(self.user)
        response = self.client.get(reverse("creators:media_items"))
        self.assertContains(response, "Visible Track")

    def test_add_form_loads_via_htmx(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("creators:add_media"),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creators/_media_form.html")

    def test_add_form_loads_standalone(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("creators:add_media"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creators/add_media.html")

    def test_add_item_via_htmx(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("creators:add_media"),
            {
                "title": "New Track",
                "media_type": "audio",
                "embed_url": "",
                "embed_code": "",
                "description": "",
                "sort_order": 0,
                "is_featured": False,
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.profile.media_items.count(), 1)
        self.assertTemplateUsed(response, "creators/_media_items.html")

    def test_add_item_with_embed_code(self):
        self.client.force_login(self.user)
        embed = '<iframe src="https://bandcamp.com/EmbeddedPlayer/track=123"></iframe>'
        self.client.post(
            reverse("creators:add_media"),
            {
                "title": "Bandcamp Track",
                "media_type": "audio",
                "embed_url": "",
                "embed_code": embed,
                "description": "",
                "sort_order": 0,
                "is_featured": False,
            },
            HTTP_HX_REQUEST="true",
        )
        item = self.profile.media_items.first()
        self.assertEqual(item.embed_html, embed)

    def test_edit_form_loads(self):
        item = self._make_item()
        self.client.force_login(self.user)
        response = self.client.get(reverse("creators:edit_media", kwargs={"pk": item.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creators/_media_form.html")

    def test_edit_item(self):
        item = self._make_item(title="Original Title")
        self.client.force_login(self.user)
        self.client.post(reverse("creators:edit_media", kwargs={"pk": item.pk}), {
            "title": "Updated Title",
            "media_type": "audio",
            "embed_url": "",
            "embed_code": "",
            "description": "New description",
            "sort_order": 1,
            "is_featured": True,
        })
        item.refresh_from_db()
        self.assertEqual(item.title, "Updated Title")
        self.assertEqual(item.description, "New description")
        self.assertTrue(item.is_featured)

    def test_delete_item(self):
        item = self._make_item()
        self.client.force_login(self.user)
        response = self.client.post(reverse("creators:delete_media", kwargs={"pk": item.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.profile.media_items.count(), 0)

    def test_cannot_edit_others_media(self):
        other_user = make_user()
        other_profile = make_creator(user=other_user, display_name="Other")
        item = self._make_item.__func__(self, title="Other's Track")  # won't work, make directly
        from apps.creators.models import MediaItem
        other_item = MediaItem.objects.create(
            creator=other_profile, title="Other's Track",
            media_type="audio", sort_order=0,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("creators:edit_media", kwargs={"pk": other_item.pk}))
        self.assertEqual(response.status_code, 404)

    def test_cannot_delete_others_media(self):
        from apps.creators.models import MediaItem
        other_user = make_user()
        other_profile = make_creator(user=other_user, display_name="Other Media")
        other_item = MediaItem.objects.create(
            creator=other_profile, title="Their Track",
            media_type="audio", sort_order=0,
        )
        self.client.force_login(self.user)
        response = self.client.post(reverse("creators:delete_media", kwargs={"pk": other_item.pk}))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(MediaItem.objects.filter(pk=other_item.pk).exists())
