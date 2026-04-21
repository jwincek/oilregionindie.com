"""
Tests for creators app forms.

Covers: CreatorProfileForm validation, skill-to-discipline sync on save,
MediaItemForm, and CreatorSocialLinkForm.
"""

from django.test import TestCase

from apps.creators.forms import CreatorProfileForm, MediaItemForm, CreatorSocialLinkForm
from apps.creators.models import CreatorProfile

from .helpers import make_creator, make_discipline, make_skill, make_user


class CreatorProfileFormTest(TestCase):
    def test_valid_minimal_data(self):
        form = CreatorProfileForm(data={
            "display_name": "Test Creator",
            "profile_type": "individual",
            "bio": "",
            "location": "",
            "home_region": "",
            "website": "",
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_requires_display_name(self):
        form = CreatorProfileForm(data={
            "display_name": "",
            "profile_type": "individual",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("display_name", form.errors)

    def test_requires_profile_type(self):
        form = CreatorProfileForm(data={
            "display_name": "Test",
            "profile_type": "",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("profile_type", form.errors)

    def test_accepts_band_profile_type(self):
        form = CreatorProfileForm(data={
            "display_name": "The Test Band",
            "profile_type": "band",
            "bio": "",
            "location": "",
            "home_region": "",
            "website": "",
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_skills_field_is_optional(self):
        form = CreatorProfileForm(data={
            "display_name": "No Skills Creator",
            "profile_type": "individual",
            "bio": "",
            "location": "",
            "home_region": "",
            "website": "",
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_save_syncs_disciplines_from_skills(self):
        """When saving a form with skills, disciplines should be auto-added."""
        musician = make_discipline("Musician")
        guitar = make_skill("Guitar", discipline=musician)
        user = make_user()

        form = CreatorProfileForm(data={
            "display_name": "Sync Test",
            "profile_type": "individual",
            "skills": [guitar.pk],
            "bio": "",
            "location": "",
            "home_region": "",
            "website": "",
        })
        self.assertTrue(form.is_valid(), form.errors)
        profile = form.save(commit=False)
        profile.user = user
        profile.save()
        form.save_m2m()
        # The form's save() calls sync_disciplines_from_skills via save_m2m
        # but since we used commit=False we need to call it manually
        profile.sync_disciplines_from_skills()

        self.assertIn(musician, profile.disciplines.all())

    def test_invalid_website_url(self):
        form = CreatorProfileForm(data={
            "display_name": "Bad URL Creator",
            "profile_type": "individual",
            "bio": "",
            "location": "",
            "home_region": "",
            "website": "not-a-url",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("website", form.errors)


class MediaItemFormTest(TestCase):
    def test_valid_audio_with_embed(self):
        form = MediaItemForm(data={
            "title": "Test Track",
            "media_type": "audio",
            "embed_url": "https://soundcloud.com/test/track",
            "description": "",
            "sort_order": 0,
            "is_featured": False,
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_valid_image_without_embed(self):
        form = MediaItemForm(data={
            "title": "Test Image",
            "media_type": "image",
            "embed_url": "",
            "description": "A painting",
            "sort_order": 1,
            "is_featured": True,
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_requires_title(self):
        form = MediaItemForm(data={
            "title": "",
            "media_type": "audio",
            "sort_order": 0,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("title", form.errors)

    def test_requires_media_type(self):
        form = MediaItemForm(data={
            "title": "Test",
            "media_type": "",
            "sort_order": 0,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("media_type", form.errors)

    def test_valid_with_embed_code(self):
        form = MediaItemForm(data={
            "title": "Bandcamp Track",
            "media_type": "audio",
            "embed_code": '<iframe style="border: 0; width: 100%; height: 120px;" src="https://bandcamp.com/EmbeddedPlayer/track=12345"></iframe>',
            "description": "",
            "sort_order": 0,
            "is_featured": False,
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_embed_code_saved_to_embed_html(self):
        from .helpers import make_user, make_creator
        user = make_user()
        creator = make_creator(user=user)
        embed = '<iframe src="https://bandcamp.com/EmbeddedPlayer/track=12345"></iframe>'
        form = MediaItemForm(data={
            "title": "Bandcamp Track",
            "media_type": "audio",
            "embed_code": embed,
            "description": "",
            "sort_order": 0,
            "is_featured": False,
        })
        self.assertTrue(form.is_valid(), form.errors)
        item = form.save(commit=False)
        item.creator = creator
        item = form.save(commit=True)
        self.assertEqual(item.embed_html, embed)

    def test_embed_code_rejects_plain_text(self):
        form = MediaItemForm(data={
            "title": "Bad Embed",
            "media_type": "audio",
            "embed_code": "This is just text, not an embed code",
            "description": "",
            "sort_order": 0,
            "is_featured": False,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("embed_code", form.errors)

    def test_embed_code_rejects_url(self):
        form = MediaItemForm(data={
            "title": "Not Embed Code",
            "media_type": "audio",
            "embed_code": "https://bandcamp.com/track/something",
            "description": "",
            "sort_order": 0,
            "is_featured": False,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("embed_code", form.errors)

    def test_embed_code_empty_is_valid(self):
        form = MediaItemForm(data={
            "title": "No Embed",
            "media_type": "image",
            "embed_code": "",
            "description": "",
            "sort_order": 0,
            "is_featured": False,
        })
        self.assertTrue(form.is_valid(), form.errors)


class CreatorSocialLinkFormTest(TestCase):
    def test_valid_data(self):
        form = CreatorSocialLinkForm(data={
            "platform": "bandcamp",
            "url": "https://example.bandcamp.com",
            "sort_order": 0,
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_requires_url(self):
        form = CreatorSocialLinkForm(data={
            "platform": "bandcamp",
            "url": "",
            "sort_order": 0,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("url", form.errors)

    def test_validates_url_format(self):
        form = CreatorSocialLinkForm(data={
            "platform": "instagram",
            "url": "not-a-url",
            "sort_order": 0,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("url", form.errors)

    def test_requires_platform(self):
        form = CreatorSocialLinkForm(data={
            "platform": "",
            "url": "https://example.com",
            "sort_order": 0,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("platform", form.errors)
