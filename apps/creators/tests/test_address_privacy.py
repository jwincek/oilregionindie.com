"""
Creator address privacy invariant (issue #92): a creator's address —
often a home address — must never be plotted or rendered publicly.
"""
from django.test import TestCase

from apps.core.models import Address
from apps.creators.tests.helpers import make_creator


class CreatorAddressNeverPlottedTest(TestCase):
    def test_creator_detail_never_exposes_address_or_coordinates(self):
        addr = Address.objects.create(
            street="123 Private Home St", city="Oil City", state="PA",
            latitude="41.430000", longitude="-79.700000",
        )
        creator = make_creator()
        creator.address = addr
        creator.save(update_fields=["address"])

        r = self.client.get(creator.get_absolute_url())
        self.assertEqual(r.status_code, 200)
        # Street text, a directions link, and the raw coordinates must all be
        # absent — any of them would leak a home location.
        self.assertNotContains(r, "123 Private Home St")
        self.assertNotContains(r, "Get directions")
        self.assertNotContains(r, "41.430000")
