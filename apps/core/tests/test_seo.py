"""
schema.org structured data + per-object OpenGraph.
"""
import json

from django.template import Context, Template
from django.test import TestCase
from django.urls import reverse

from apps.core.models import SocialPlatform
from apps.core.seo import creator_ld, event_ld, venue_ld
from apps.creators.models import CreatorProfile, CreatorSocialLink
from apps.creators.tests.helpers import make_creator, make_user
from apps.events.tests.helpers import make_event
from apps.venues.models import VenueSocialLink
from apps.venues.tests.helpers import make_venue


class VenueStructuredDataTest(TestCase):
    def test_music_venue_type_and_geo(self):
        venue = make_venue(name="Belize's", venue_type="bar")
        venue.address.latitude, venue.address.longitude = 41.4347, -79.7088
        venue.address.save()
        d = venue_ld(venue)
        self.assertEqual(d["@type"], "MusicVenue")
        self.assertEqual(d["geo"]["latitude"], 41.4347)
        self.assertEqual(d["address"]["@type"], "PostalAddress")

    def test_venue_type_maps_to_schema_type(self):
        self.assertEqual(venue_ld(make_venue(venue_type="gallery"))["@type"], "ArtGallery")
        self.assertEqual(venue_ld(make_venue(venue_type="cafe"))["@type"], "CafeOrCoffeeShop")

    def test_same_as_includes_website_and_social_links(self):
        venue = make_venue(name="Linked Venue", website="https://belizes.example")
        VenueSocialLink.objects.create(
            venue=venue, platform=SocialPlatform.GOOGLE_BUSINESS,
            url="https://maps.google.com/?cid=123",
        )
        VenueSocialLink.objects.create(
            venue=venue, platform=SocialPlatform.INSTAGRAM, url="https://instagram.com/belizes",
        )
        same = venue_ld(venue)["sameAs"]
        self.assertIn("https://belizes.example", same)
        self.assertIn("https://maps.google.com/?cid=123", same)
        self.assertIn("https://instagram.com/belizes", same)


class CreatorStructuredDataTest(TestCase):
    def test_individual_is_person_group_is_musicgroup(self):
        self.assertEqual(
            creator_ld(make_creator(user=make_user(), profile_type="individual"))["@type"],
            "Person",
        )
        self.assertEqual(
            creator_ld(make_creator(user=make_user(), profile_type="band"))["@type"],
            "MusicGroup",
        )

    def test_google_business_link_flows_into_same_as(self):
        creator = make_creator(user=make_user())
        CreatorSocialLink.objects.create(
            creator=creator, platform=SocialPlatform.GOOGLE_BUSINESS,
            url="https://g.page/creator",
        )
        self.assertIn("https://g.page/creator", creator_ld(creator)["sameAs"])


class EventStructuredDataTest(TestCase):
    def test_concert_is_music_event_with_offer_and_location(self):
        venue = make_venue(name="Belize's")
        venue.address.latitude, venue.address.longitude = 41.4347, -79.7088
        venue.address.save()
        event = make_event(
            title="Friday Show", venue=venue, event_type="concert",
            is_free=False, ticket_price_cents=500,
        )
        d = event_ld(event)
        self.assertEqual(d["@type"], "MusicEvent")
        self.assertEqual(d["location"]["@type"], "Place")
        self.assertIn("geo", d["location"])
        self.assertEqual(d["offers"]["price"], "5.00")
        self.assertEqual(d["offers"]["priceCurrency"], "USD")

    def test_cancelled_status_maps_to_schema(self):
        from apps.events.models import Event
        event = make_event(status=Event.Status.CANCELLED)
        self.assertEqual(event_ld(event)["eventStatus"], "https://schema.org/EventCancelled")

    def test_free_event_is_accessible_for_free(self):
        self.assertTrue(event_ld(make_event(is_free=True)).get("isAccessibleForFree"))


class StructuredDataScriptTagTest(TestCase):
    def _render(self, obj):
        t = Template("{% load seo %}{% structured_data_script obj %}")
        return t.render(Context({"obj": obj}))

    def test_renders_ld_json_script(self):
        out = self._render(make_venue(name="Scripted Venue"))
        self.assertIn('<script type="application/ld+json">', out)
        self.assertIn('"@type": "MusicVenue"', out)

    def test_escapes_angle_brackets_to_prevent_script_breakout(self):
        """A venue named with </script> must not break out of the JSON-LD
        block — <, >, & are escaped to unicode."""
        venue = make_venue(name="</script><script>alert(1)</script>")
        out = self._render(venue)
        self.assertNotIn("</script><script>", out)
        self.assertIn("\\u003c", out)  # the < was escaped
        # The JSON payload still parses and carries the raw name.
        payload = out.split(">", 1)[1].rsplit("<", 1)[0]
        decoded = json.loads(payload.replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&"))
        self.assertEqual(decoded["name"], "</script><script>alert(1)</script>")


class OpenGraphTest(TestCase):
    def test_venue_detail_sets_per_object_og_and_ld(self):
        venue = make_venue(name="OG Venue")
        r = self.client.get(reverse("venues:detail", kwargs={"slug": venue.slug}))
        self.assertContains(r, '<meta property="og:title" content="OG Venue">')
        self.assertContains(r, "application/ld+json")

    def test_event_detail_has_meta_description_now(self):
        event = make_event(title="Described Event")
        r = self.client.get(event.get_absolute_url())
        self.assertContains(r, '<meta name="description"')
        self.assertContains(r, "Described Event")
