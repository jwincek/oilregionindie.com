"""
Seed the database with initial data.

Usage:
    python manage.py seed_data           # Taxonomy only (safe to re-run)
    python manage.py seed_data --pages   # Taxonomy + Wagtail pages (soft launch)
    python manage.py seed_data --full    # Taxonomy + sample content + pages (dev/demo)
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.models import Address, AvailabilityType, ProfileAvailability, SocialPlatform
from apps.creators.models import (
    CreatorMembership,
    CreatorProfile,
    CreatorSocialLink,
    Discipline,
    Genre,
    MediaItem,
    Skill,
)
from apps.events.models import BookingRequest, Event, EventSlot
from apps.venues.models import Amenity, VenueArea, VenueContact, VenueProfile

User = get_user_model()


# =========================================================================
# TAXONOMY DATA (safe to re-run)
# =========================================================================

# (discipline_name, icon, [skills])
DISCIPLINES_WITH_SKILLS = [
    ("Musician", "music", [
        "Acoustic Guitar", "Electric Guitar", "Classical Guitar",
        "Bass Guitar", "Upright Bass", "Vocals", "Drums", "Percussion",
        "Piano", "Keys/Synthesizer", "Violin/Fiddle", "Mandolin",
        "Banjo", "Ukulele", "Lap Steel", "Dobro", "Harmonica",
        "Saxophone", "Trumpet", "Trombone", "Flute", "Cello",
        "DJ/Turntables", "Electronic Production", "Sound Engineering", "Songwriting",
    ]),
    ("Visual Artist", "palette", [
        "Oil Painting", "Acrylic Painting", "Watercolor", "Drawing",
        "Charcoal", "Pastel", "Digital Illustration", "Screen Printing",
        "Printmaking", "Collage", "Murals", "Graphic Design",
        "Calligraphy", "Portraiture", "Landscape", "Abstract",
    ]),
    ("Jeweler", "gem", [
        "Silversmithing", "Goldsmithing", "Beadwork", "Wire Wrapping",
        "Lapidary", "Metal Casting", "Metalwork", "Enameling",
        "Stone Setting", "Engraving", "Resin",
    ]),
    ("Ceramicist", "coffee", [
        "Wheel Throwing", "Hand Building", "Slab Building", "Coiling",
        "Glazing", "Raku", "Pit Firing", "Sculpture", "Tile Making",
    ]),
    ("Photographer", "camera", [
        "Portrait", "Landscape", "Street Photography", "Concert/Live Music",
        "Documentary", "Fine Art", "Film/Analog", "Digital",
        "Darkroom Printing", "Photo Editing",
    ]),
    ("Sculptor", "box", [
        "Stone Carving", "Wood Carving", "Metal Sculpture", "Welding",
        "Bronze Casting", "Clay/Ceramic Sculpture", "Found Object/Assemblage",
        "Installation", "Kinetic Sculpture",
    ]),
    ("Printmaker", "printer", [
        "Letterpress", "Linocut", "Woodcut", "Etching",
        "Lithography", "Screen Printing", "Monotype", "Risograph",
    ]),
    ("Textile Artist", "scissors", [
        "Weaving", "Knitting", "Crochet", "Embroidery", "Quilting",
        "Dyeing", "Felting", "Sewing/Garment Making", "Macrame", "Tapestry",
    ]),
    ("Woodworker", "hammer", [
        "Furniture Making", "Cabinetry", "Turning/Lathe", "Carving",
        "Joinery", "Scroll Saw", "Pyrography", "Instrument Building",
    ]),
    ("Glassblower", "droplet", [
        "Blown Glass", "Lampwork", "Fused Glass", "Stained Glass",
        "Glass Casting", "Glass Etching",
    ]),
    ("Leather Worker", "briefcase", [
        "Tooling", "Saddle Making", "Bag Making", "Wallet/Small Goods",
        "Belts", "Dyeing/Finishing", "Carving",
    ]),
    ("Mixed Media", "layers", [
        "Assemblage", "Collage", "Installation", "Book Arts",
        "Zine Making", "Art Journaling", "Encaustic",
    ]),
]

GENRES = [
    "Indie Rock", "Folk", "Americana", "Blues", "Jazz", "Electronic",
    "Hip Hop", "Punk", "Singer-Songwriter", "Bluegrass", "Country",
    "Metal", "Alternative", "Experimental", "R&B/Soul", "Acoustic",
    "Psychedelic", "Post-Rock", "Noise", "Ambient",
]

AMENITIES = [
    "PA System", "Stage", "Lighting Rig", "Green Room", "Backline Available",
    "Parking", "Street Parking", "Accessible", "All Ages", "21+",
    "Kitchen", "Full Bar", "Beer/Wine Only", "Outdoor Space", "Patio",
    "Wi-Fi", "Projector/Screen", "Gallery Walls", "Display Cases",
    "Loading Dock", "Air Conditioning", "Seating", "Standing Room",
]

# (name, applies_to, description, sort_order)
AVAILABILITY_TYPES = [
    ("Available for Booking", "creator", "Open to live performance opportunities", 1),
    ("Open to Collaboration", "creator", "Interested in working with other creators", 2),
    ("Accepting Commissions", "creator", "Taking custom orders for artwork, jewelry, etc.", 3),
    ("Available for Hire", "creator", "Session work, photography, design, etc.", 4),
    ("Seeking Members", "creator", "Band or collective looking for new members", 5),
    ("Accepting Booking Requests", "venue", "Open to booking inquiries from creators", 1),
    ("Gallery Space Available", "venue", "Wall space or display area for visual artists", 2),
    ("Seeking Acts", "venue", "Actively looking for performers to fill dates", 3),
    ("Open for Private Events", "venue", "Available for private bookings and rentals", 4),
]


class Command(BaseCommand):
    help = "Seed the database with taxonomy data and optionally sample content"

    def add_arguments(self, parser):
        parser.add_argument(
            "--pages",
            action="store_true",
            help="Also create Wagtail pages (home, about, blog) for soft launch",
        )
        parser.add_argument(
            "--full",
            action="store_true",
            help="Also create sample creators, venues, events, and Wagtail pages (fresh DB only)",
        )

    def handle(self, *args, **options):
        self._seed_taxonomy()

        if options["full"]:
            self._seed_sample_content()
            self._seed_wagtail_pages()
        elif options["pages"]:
            self._seed_wagtail_pages()

    # =====================================================================
    # TAXONOMY (idempotent, safe to re-run)
    # =====================================================================

    def _seed_taxonomy(self):
        total_skills = 0

        self.stdout.write(self.style.MIGRATE_HEADING("\nSeeding disciplines and skills..."))
        for disc_name, icon, skill_names in DISCIPLINES_WITH_SKILLS:
            disc, created = Discipline.objects.get_or_create(
                name=disc_name, defaults={"icon": icon},
            )
            status = "+" if created else "="
            self.stdout.write(f"  [{status}] {disc_name}")

            for skill_name in skill_names:
                skill, sk_created = Skill.objects.get_or_create(
                    name=skill_name, discipline=disc,
                )
                if sk_created:
                    total_skills += 1

        self.stdout.write(self.style.MIGRATE_HEADING("\nSeeding genres..."))
        for name in GENRES:
            Genre.objects.get_or_create(name=name)

        self.stdout.write(self.style.MIGRATE_HEADING("\nSeeding amenities..."))
        for name in AMENITIES:
            Amenity.objects.get_or_create(name=name)

        self.stdout.write(self.style.MIGRATE_HEADING("\nSeeding availability types..."))
        for name, applies_to, description, sort_order in AVAILABILITY_TYPES:
            AvailabilityType.objects.get_or_create(
                name=name,
                defaults={
                    "applies_to": applies_to,
                    "description": description,
                    "sort_order": sort_order,
                },
            )

        self.stdout.write(self.style.SUCCESS(
            f"\nTaxonomy: {len(DISCIPLINES_WITH_SKILLS)} disciplines, "
            f"{total_skills} new skills, {len(GENRES)} genres, "
            f"{len(AMENITIES)} amenities, {len(AVAILABILITY_TYPES)} availability types."
        ))

    # =====================================================================
    # SAMPLE CONTENT (run once on fresh DB)
    # =====================================================================

    def _seed_sample_content(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\nSeeding sample content..."))

        if CreatorProfile.objects.exists():
            self.stdout.write(self.style.WARNING(
                "  Creators already exist — skipping sample content. "
                "Use --full only on a fresh database."
            ))
            return

        # --- Helper to get skill by name ---
        def skill(name):
            return Skill.objects.get(name=name)

        def disc(name):
            return Discipline.objects.get(name=name)

        def genre(name):
            return Genre.objects.get(name=name)

        def amenity(name):
            return Amenity.objects.get(name=name)

        # --- Sample users (password: "testpass123" for all) ---
        self.stdout.write("  Creating sample users...")
        users = {}
        for username in [
            "alice", "bob", "carol", "dave", "eve",
            "frank", "grace", "venue_belize", "venue_midtown", "venue_petrol",
        ]:
            u = User.objects.create_user(
                username=username,
                email=f"{username}@oilregion-demo.example",
                password="testpass123",
            )
            users[username] = u

        # =================================================================
        # CREATORS
        # =================================================================
        self.stdout.write("  Creating sample creators...")

        # Alice — solo musician, guitar + vocals
        alice = CreatorProfile.objects.create(
            user=users["alice"],
            display_name="Alice Brewster",
            profile_type=CreatorProfile.ProfileType.INDIVIDUAL,
            bio="<p>Singer-songwriter from Oil City. Acoustic folk with Appalachian roots.</p>",
            location="Pittsburgh, PA",
            home_region="Oil City, PA",
            publish_status="published",
        )
        alice.skills.add(skill("Acoustic Guitar"), skill("Vocals"), skill("Songwriting"))
        alice.genres.add(genre("Folk"), genre("Singer-Songwriter"), genre("Americana"))
        alice.sync_disciplines_from_skills()
        CreatorSocialLink.objects.create(
            creator=alice, platform=SocialPlatform.BANDCAMP,
            url="https://alicebrewster.bandcamp.com",
        )

        # Bob — visual artist + jeweler (the cross-discipline case)
        bob = CreatorProfile.objects.create(
            user=users["bob"],
            display_name="Bob Hartman",
            profile_type=CreatorProfile.ProfileType.INDIVIDUAL,
            bio="<p>Oil painter and silversmith based in Franklin. Inspired by the Allegheny landscape.</p>",
            location="Franklin, PA",
            home_region="Venango County, PA",
            publish_status="published",
        )
        bob.skills.add(
            skill("Oil Painting"), skill("Watercolor"),
            skill("Silversmithing"), skill("Stone Setting"),
        )
        bob.genres.add()
        bob.sync_disciplines_from_skills()
        CreatorSocialLink.objects.create(
            creator=bob, platform=SocialPlatform.INSTAGRAM,
            url="https://instagram.com/bobhartman_art",
        )
        CreatorSocialLink.objects.create(
            creator=bob, platform=SocialPlatform.ETSY,
            url="https://etsy.com/shop/bobhartmansilver",
        )

        # Carol — photographer
        carol = CreatorProfile.objects.create(
            user=users["carol"],
            display_name="Carol Sears",
            profile_type=CreatorProfile.ProfileType.INDIVIDUAL,
            bio="<p>Documentary photographer. Capturing the stories of small-town Pennsylvania.</p>",
            location="Titusville, PA",
            home_region="Titusville, PA",
            publish_status="published",
        )
        carol.skills.add(
            skill("Documentary"), skill("Concert/Live Music"), skill("Film/Analog"),
        )
        carol.sync_disciplines_from_skills()

        # Dave — ceramicist
        dave = CreatorProfile.objects.create(
            user=users["dave"],
            display_name="Dave Oakman",
            profile_type=CreatorProfile.ProfileType.INDIVIDUAL,
            bio="<p>Functional pottery and raku firing. Studio in Cranberry.</p>",
            location="Cranberry, PA",
            home_region="Venango County, PA",
            publish_status="published",
        )
        dave.skills.add(skill("Wheel Throwing"), skill("Raku"), skill("Glazing"))
        dave.sync_disciplines_from_skills()

        # Eve — multi-instrumentalist, unpublished (for testing)
        eve = CreatorProfile.objects.create(
            user=users["eve"],
            display_name="Eve Lanich",
            profile_type=CreatorProfile.ProfileType.INDIVIDUAL,
            bio="<p>Work in progress.</p>",
            location="Oil City, PA",
            home_region="Oil City, PA",
            publish_status="draft",
        )
        eve.skills.add(skill("Piano"), skill("Vocals"))
        eve.sync_disciplines_from_skills()

        # Frank — musician (bass, guitar)
        frank = CreatorProfile.objects.create(
            user=users["frank"],
            display_name="Frank Custer",
            profile_type=CreatorProfile.ProfileType.INDIVIDUAL,
            bio="<p>Bass player. Plays in everything from punk to bluegrass.</p>",
            location="Oil City, PA",
            home_region="Oil City, PA",
            publish_status="published",
        )
        frank.skills.add(
            skill("Bass Guitar"), skill("Upright Bass"),
            skill("Electric Guitar"), skill("Vocals"),
        )
        frank.genres.add(genre("Punk"), genre("Bluegrass"), genre("Indie Rock"))
        frank.sync_disciplines_from_skills()

        # Grace — textile artist + mixed media
        grace = CreatorProfile.objects.create(
            user=users["grace"],
            display_name="Grace Huegel",
            profile_type=CreatorProfile.ProfileType.INDIVIDUAL,
            bio="<p>Fiber art and mixed media. Quilts, weavings, and zines.</p>",
            location="Meadville, PA",
            home_region="Oil City, PA",
            publish_status="published",
        )
        grace.skills.add(
            skill("Weaving"), skill("Quilting"), skill("Zine Making"),
        )
        grace.sync_disciplines_from_skills()

        # --- Band: The Concrete Summer ---
        band_user = User.objects.create_user(
            username="concrete_summer",
            email="theconcretesummer@oilregion-demo.example",
            password="testpass123",
        )
        band = CreatorProfile.objects.create(
            user=band_user,
            display_name="The Concrete Summer",
            profile_type=CreatorProfile.ProfileType.BAND,
            bio="<p>Indie rock from Oil City. Loud guitars, louder harmonies.</p>",
            location="Oil City, PA",
            home_region="Venango County, PA",
            publish_status="published",
        )
        band.managers.add(users["alice"], users["frank"])
        band.skills.add(
            skill("Electric Guitar"), skill("Bass Guitar"),
            skill("Drums"), skill("Vocals"),
        )
        band.genres.add(genre("Indie Rock"), genre("Alternative"), genre("Punk"))
        band.sync_disciplines_from_skills()
        CreatorSocialLink.objects.create(
            creator=band, platform=SocialPlatform.BANDCAMP,
            url="https://theconcretesummer.bandcamp.com",
        )

        # Memberships
        CreatorMembership.objects.create(
            group=band, member=alice, role="Guitar, Vocals", sort_order=1,
        )
        CreatorMembership.objects.create(
            group=band, member=frank, role="Bass", sort_order=2,
        )

        # --- Collective: Oil City Arts Collective ---
        collective_user = User.objects.create_user(
            username="oc_arts",
            email="collective@oilregion-demo.example",
            password="testpass123",
        )
        collective = CreatorProfile.objects.create(
            user=collective_user,
            display_name="Oil City Arts Collective",
            profile_type=CreatorProfile.ProfileType.COLLECTIVE,
            bio="<p>A loose collective of visual artists, makers, and musicians from the Oil Region.</p>",
            location="Oil City, PA",
            home_region="Venango County, PA",
            publish_status="published",
        )
        collective.managers.add(users["bob"], users["grace"])
        CreatorMembership.objects.create(group=collective, member=bob, role="Visual Art", sort_order=1)
        CreatorMembership.objects.create(group=collective, member=grace, role="Fiber Art", sort_order=2)
        CreatorMembership.objects.create(group=collective, member=carol, role="Photography", sort_order=3)
        CreatorMembership.objects.create(group=collective, member=dave, role="Ceramics", sort_order=4)

        # --- Media items ---
        MediaItem.objects.create(
            creator=alice, title="Reckoning (Live at Mid-Town)",
            media_type=MediaItem.MediaType.AUDIO,
            embed_url="https://soundcloud.com/example/reckoning-live",
            is_featured=True, sort_order=1,
        )
        MediaItem.objects.create(
            creator=alice, title="Upstream",
            media_type=MediaItem.MediaType.AUDIO,
            embed_url="https://soundcloud.com/example/upstream",
            sort_order=2,
        )
        MediaItem.objects.create(
            creator=bob, title="Allegheny Morning (Oil on Canvas)",
            media_type=MediaItem.MediaType.IMAGE,
            description="36x48, oil on stretched canvas. Inspired by the view from Petroleum Centre.",
            is_featured=True, sort_order=1,
        )
        MediaItem.objects.create(
            creator=band, title="Static Characters (Full Set, Petrol Alley 2019)",
            media_type=MediaItem.MediaType.EMBED,
            embed_url="https://youtube.com/watch?v=example",
            is_featured=True, sort_order=1,
        )

        self.stdout.write(f"  Created {CreatorProfile.objects.count()} creator profiles")
        self.stdout.write(f"  Created {CreatorMembership.objects.count()} memberships")

        # =================================================================
        # VENUES
        # =================================================================
        self.stdout.write("  Creating sample venues...")

        belize_addr = Address.objects.create(
            street="210 Seneca St", city="Oil City", state="PA", zip_code="16301",
            latitude=41.4340, longitude=-79.7025,
        )
        belize = VenueProfile.objects.create(
            user=users["venue_belize"],
            name="Belize's",
            venue_type=VenueProfile.VenueType.BAR,
            description="<p>Dive bar with live music. The heart of Oil City's North Side music scene since the 90s.</p>",
            address=belize_addr, city="Oil City", state="PA",
            capacity=75, publish_status="published",
        )
        belize.amenities.add(amenity("PA System"), amenity("Stage"), amenity("Full Bar"), amenity("21+"))
        VenueArea.objects.create(venue=belize, name="Main Room", capacity=75, sort_order=1)
        VenueArea.objects.create(venue=belize, name="Back Patio", capacity=30, sort_order=2)
        VenueContact.objects.create(
            venue=belize, contact_type=VenueContact.ContactType.BOOKING,
            method=VenueContact.Method.EMAIL, value="booking@belizes-oilcity.example",
            name="Mike", notes="Email preferred. Best response on weekdays.",
        )
        VenueContact.objects.create(
            venue=belize, contact_type=VenueContact.ContactType.BOOKING,
            method=VenueContact.Method.PHONE, value="814-555-0101",
            name="Mike", notes="Call after 2pm.",
        )

        midtown_addr = Address.objects.create(
            street="218 Seneca St", city="Oil City", state="PA", zip_code="16301",
            latitude=41.4342, longitude=-79.7022,
        )
        midtown = VenueProfile.objects.create(
            user=users["venue_midtown"],
            name="Mid-Town Cafe",
            venue_type=VenueProfile.VenueType.CAFE,
            description="<p>Coffee shop and community gathering space. Acoustic shows, open mics, and art on the walls.</p>",
            address=midtown_addr, city="Oil City", state="PA",
            capacity=40, publish_status="published",
        )
        midtown.amenities.add(
            amenity("PA System"), amenity("All Ages"), amenity("Wi-Fi"),
            amenity("Gallery Walls"), amenity("Seating"),
        )
        VenueArea.objects.create(venue=midtown, name="Performance Corner", capacity=40, sort_order=1)
        VenueContact.objects.create(
            venue=midtown, contact_type=VenueContact.ContactType.BOOKING,
            method=VenueContact.Method.EMAIL, value="music@midtowncafe.example",
        )
        VenueContact.objects.create(
            venue=midtown, contact_type=VenueContact.ContactType.GENERAL,
            method=VenueContact.Method.EMAIL, value="hello@midtowncafe.example",
        )

        petrol_addr = Address.objects.create(
            street="Seneca St (outdoor)", city="Oil City", state="PA", zip_code="16301",
            latitude=41.4338, longitude=-79.7028,
        )
        petrol = VenueProfile.objects.create(
            user=users["venue_petrol"],
            name="Petrol Alley",
            venue_type=VenueProfile.VenueType.OUTDOOR,
            description="<p>Outdoor performance space next to the National Transit Building. Home of the summer concert series.</p>",
            address=petrol_addr, city="Oil City", state="PA",
            capacity=150, publish_status="published",
        )
        petrol.amenities.add(
            amenity("PA System"), amenity("Stage"), amenity("All Ages"),
            amenity("Outdoor Space"), amenity("Accessible"),
        )
        VenueArea.objects.create(venue=petrol, name="Main Stage", capacity=150, sort_order=1)
        VenueContact.objects.create(
            venue=petrol, contact_type=VenueContact.ContactType.BOOKING,
            method=VenueContact.Method.EMAIL, value="events@petrol-alley.example",
        )

        self.stdout.write(f"  Created {VenueProfile.objects.count()} venues")

        # =================================================================
        # EVENTS
        # =================================================================
        self.stdout.write("  Creating sample events...")

        now = timezone.now()

        # Upcoming: Friday Night at Belize's
        friday_show = Event.objects.create(
            created_by=users["venue_belize"],
            title="Friday Night at Belize's",
            event_type=Event.EventType.CONCERT,
            venue=belize,
            organizing_venue=belize,
            start_datetime=now + timedelta(days=10, hours=2),
            doors_time=time(20, 0),
            is_free=False,
            ticket_price_cents=500,
            is_published=True,
        )
        belize_main = belize.areas.get(name="Main Room")
        EventSlot.objects.create(
            event=friday_show, creator=alice,
            start_time=time(20, 30), end_time=time(21, 15),
            venue_area=belize_main, set_description="Acoustic Set",
            sort_order=1, status=EventSlot.Status.CONFIRMED,
        )
        EventSlot.objects.create(
            event=friday_show, creator=band,
            start_time=time(21, 30), end_time=time(23, 0),
            venue_area=belize_main, set_description="Full Band",
            sort_order=2, status=EventSlot.Status.CONFIRMED,
        )

        # Upcoming: Open Mic at Mid-Town
        open_mic = Event.objects.create(
            created_by=users["venue_midtown"],
            title="Thursday Open Mic",
            event_type=Event.EventType.OPEN_MIC,
            venue=midtown,
            organizing_venue=midtown,
            start_datetime=now + timedelta(days=5, hours=1),
            doors_time=time(18, 30),
            is_free=True,
            is_published=True,
        )

        # Upcoming: Art Walk (multi-venue, organized by collective)
        art_walk = Event.objects.create(
            created_by=collective_user,
            title="First Friday Art Walk",
            event_type=Event.EventType.ART_SHOW,
            venue=None,  # multi-venue, no single host
            organizing_creator=collective,
            start_datetime=now + timedelta(days=17, hours=3),
            is_free=True,
            is_published=True,
            description="<p>Gallery openings, live demos, and music across downtown Oil City.</p>",
        )
        EventSlot.objects.create(
            event=art_walk, creator=bob,
            set_description="Live painting demo",
            sort_order=1, status=EventSlot.Status.CONFIRMED,
        )
        EventSlot.objects.create(
            event=art_walk, creator=grace,
            set_description="Weaving demonstration",
            sort_order=2, status=EventSlot.Status.CONFIRMED,
        )
        EventSlot.objects.create(
            event=art_walk, creator=carol,
            set_description="Photo exhibition",
            sort_order=3, status=EventSlot.Status.CONFIRMED,
        )

        # Past: Last Month's Show
        past_show = Event.objects.create(
            created_by=users["venue_petrol"],
            title="Summer Kickoff at Petrol Alley",
            event_type=Event.EventType.CONCERT,
            venue=petrol,
            organizing_venue=petrol,
            start_datetime=now - timedelta(days=30),
            is_free=True,
            is_published=True,
        )
        petrol_stage = petrol.areas.get(name="Main Stage")
        EventSlot.objects.create(
            event=past_show, creator=alice,
            start_time=time(18, 0), end_time=time(19, 0),
            venue_area=petrol_stage,
            sort_order=1, status=EventSlot.Status.CONFIRMED,
        )
        EventSlot.objects.create(
            event=past_show, creator=band,
            start_time=time(19, 30), end_time=time(21, 0),
            venue_area=petrol_stage,
            sort_order=2, status=EventSlot.Status.CONFIRMED,
        )

        # Past: Maker Market
        past_market = Event.objects.create(
            created_by=collective_user,
            title="Holiday Maker Market",
            event_type=Event.EventType.MARKET,
            venue=midtown,
            organizing_creator=collective,
            organizing_venue=midtown,
            start_datetime=now - timedelta(days=90),
            is_free=True,
            is_published=True,
        )
        EventSlot.objects.create(
            event=past_market, creator=bob,
            set_description="Jewelry booth", sort_order=1,
            status=EventSlot.Status.CONFIRMED,
        )
        EventSlot.objects.create(
            event=past_market, creator=dave,
            set_description="Pottery booth", sort_order=2,
            status=EventSlot.Status.CONFIRMED,
        )
        EventSlot.objects.create(
            event=past_market, creator=grace,
            set_description="Fiber art & zines", sort_order=3,
            status=EventSlot.Status.CONFIRMED,
        )

        # --- Sample booking request ---
        BookingRequest.objects.create(
            creator=alice,
            venue=midtown,
            initiated_by=users["alice"],
            direction=BookingRequest.Direction.CREATOR_TO_VENUE,
            event_type=Event.EventType.CONCERT,
            preferred_dates="Any Saturday in August",
            message="Hi! I'd love to do a solo acoustic set at Mid-Town. I've played there during the festival before and it's a great room for my sound.",
            status=BookingRequest.Status.PENDING,
        )

        self.stdout.write(f"  Created {Event.objects.count()} events with {EventSlot.objects.count()} slots")
        self.stdout.write(f"  Created {BookingRequest.objects.count()} booking request")

        # =================================================================
        # AVAILABILITY FLAGS
        # =================================================================
        self.stdout.write("  Setting availability flags...")

        avail_booking = AvailabilityType.objects.get(slug="available-for-booking")
        avail_commissions = AvailabilityType.objects.get(slug="accepting-commissions")
        avail_collab = AvailabilityType.objects.get(slug="open-to-collaboration")
        avail_venue_booking = AvailabilityType.objects.get(slug="accepting-booking-requests")
        avail_gallery = AvailabilityType.objects.get(slug="gallery-space-available")
        avail_seeking = AvailabilityType.objects.get(slug="seeking-acts")

        # Creator availability
        ProfileAvailability.objects.create(
            creator=alice, availability_type=avail_booking,
            note="Weekends, July\u2013September",
        )
        ProfileAvailability.objects.create(
            creator=alice, availability_type=avail_collab,
        )
        ProfileAvailability.objects.create(
            creator=bob, availability_type=avail_commissions,
            note="2\u20133 week turnaround on custom pieces",
        )
        ProfileAvailability.objects.create(
            creator=frank, availability_type=avail_booking,
            note="Available as a sideman or with the band",
        )
        ProfileAvailability.objects.create(
            creator=band, availability_type=avail_booking,
            note="Regional shows only, within 2 hours of Oil City",
        )
        ProfileAvailability.objects.create(
            creator=grace, availability_type=avail_commissions,
            note="Custom quilts and weavings, 4\u20136 week lead time",
        )

        # Venue availability
        ProfileAvailability.objects.create(
            venue=belize, availability_type=avail_venue_booking,
        )
        ProfileAvailability.objects.create(
            venue=belize, availability_type=avail_seeking,
            note="Looking for acoustic acts for Wednesday residency",
        )
        ProfileAvailability.objects.create(
            venue=midtown, availability_type=avail_venue_booking,
        )
        ProfileAvailability.objects.create(
            venue=midtown, availability_type=avail_gallery,
            note="Rotating monthly exhibits \u2014 submit portfolio to music@midtowncafe.example",
        )
        ProfileAvailability.objects.create(
            venue=petrol, availability_type=avail_venue_booking,
            note="Summer season only (June\u2013September)",
        )

        self.stdout.write(f"  Created {ProfileAvailability.objects.count()} availability flags")

    # =====================================================================
    # WAGTAIL PAGES
    # =====================================================================

    def _seed_wagtail_pages(self):
        from wagtail.models import Page, Site
        from apps.pages.models import (
            BlogIndexPage, BlogPost, ContentPage, HomePage,
            HomePageFeaturedCreator, HomePageFeaturedVenue,
        )

        self.stdout.write(self.style.MIGRATE_HEADING("\nSeeding Wagtail pages..."))

        if HomePage.objects.exists():
            self.stdout.write(self.style.WARNING("  HomePage already exists — skipping."))
            return

        root = Page.objects.first()

        # Remove Wagtail's default "Welcome to your new Wagtail site!" page
        # which occupies the 'home' slug
        for default_page in Page.objects.filter(depth=2, slug="home"):
            if not isinstance(default_page.specific, HomePage):
                self.stdout.write(f"  Removing default Wagtail page: {default_page.title}")
                default_page.delete()

        # Rebuild treebeard path data after deletion
        Page.fix_tree()
        root.refresh_from_db()

        # --- Home Page ---
        home = HomePage(
            title="Oil Region Creative Hub",
            slug="home",
            subtitle="A home for independent musicians, visual artists, makers, venues, and fans.",
            hero_text=(
                "<p>Born from twelve years of the Oil Region Indie Music Festival in Oil City, Pennsylvania. "
                "Now a year-round platform connecting creators, venues, and community.</p>"
            ),
        )
        root.add_child(instance=home)
        home.save_revision().publish()

        # Featured creators (link to seeded profiles)
        for i, creator in enumerate(CreatorProfile.objects.filter(
            publish_status="published",
            profile_type=CreatorProfile.ProfileType.INDIVIDUAL,
        )[:3]):
            HomePageFeaturedCreator.objects.create(
                page=home, creator=creator,
                blurb=f"{creator.discipline_list} — {creator.location}",
                sort_order=i,
            )

        # Featured venues
        for i, venue in enumerate(VenueProfile.objects.filter(
            publish_status="published",
        )[:3]):
            HomePageFeaturedVenue.objects.create(
                page=home, venue=venue,
                blurb=f"{venue.get_venue_type_display()} — {venue.city}, {venue.state}",
                sort_order=i,
            )

        # --- About page ---
        about = ContentPage(
            title="About",
            slug="about",
            subtitle="The story behind the Oil Region Creative Hub.",
            body=[
                ("heading", "From Festival to Platform"),
                ("paragraph", (
                    "<p>The Oil Region Indie Music Festival ran for twelve years in Oil City, Pennsylvania, "
                    "bringing together independent musicians, visual artists, jewelers, makers, and fans "
                    "across nine venues in the North Side business district. Free to attend, community-organized, "
                    "and powered by the Oil City Arts Council and the Pennsylvania Council on the Arts.</p>"
                )),
                ("paragraph", (
                    "<p>After pausing in 2020, the festival is evolving into something new: a year-round "
                    "online community where creators share their work, venues list their shows, and fans "
                    "discover the independent arts scene of western Pennsylvania and beyond.</p>"
                )),
                ("heading", "Open Source"),
                ("paragraph", (
                    "<p>The Oil Region Creative Hub is open-source software, released under the AGPL-3.0 license. "
                    "Other independent arts communities can deploy their own instance with their own branding "
                    "and creator base. The code is available on GitHub.</p>"
                )),
            ],
        )
        home.add_child(instance=about)
        about.save_revision().publish()

        # --- Feedback page ---
        feedback = ContentPage(
            title="Feedback",
            slug="feedback",
            subtitle="Help us improve the Oil Region Creative Hub.",
            body=[
                ("paragraph", (
                    "<p>This platform is in active development. Your feedback helps us "
                    "prioritize what to build next and catch issues we've missed. Whether you've "
                    "found a bug, have an idea for a feature, or just want to share your "
                    "experience — we'd love to hear from you.</p>"
                )),
                ("heading", "Report a Bug"),
                ("paragraph", (
                    "<p>Something not working right? Let us know:</p>"
                    "<ul>"
                    "<li><b>What happened</b> — describe what you saw</li>"
                    "<li><b>What you expected</b> — what should have happened instead</li>"
                    "<li><b>Steps to reproduce</b> — how can we see the same issue?</li>"
                    "<li><b>Browser &amp; device</b> — e.g., Chrome on iPhone, Firefox on Windows</li>"
                    "</ul>"
                )),
                ("heading", "Suggest a Feature"),
                ("paragraph", (
                    "<p>Have an idea that would make the platform more useful? Tell us:</p>"
                    "<ul>"
                    "<li><b>What you'd like</b> — describe the feature</li>"
                    "<li><b>Why it matters</b> — how would it help you or the community?</li>"
                    "</ul>"
                )),
                ("heading", "How to Submit"),
                ("paragraph", (
                    "<p>You can reach us in two ways:</p>"
                    "<ul>"
                    "<li><b>GitHub Issues</b> — "
                    '<a href="https://github.com/jwincek/oilregionindie.com/issues">open an issue</a> '
                    "on our repository. Best for bug reports and detailed feature requests.</li>"
                    "<li><b>Email</b> — send feedback to "
                    '<a href="mailto:feedback@oilregionindie.com">feedback@oilregionindie.com</a></li>'
                    "</ul>"
                )),
                ("heading", "Support the Project"),
                ("paragraph", (
                    "<p>The Oil Region Creative Hub is a volunteer-run, open-source project. "
                    "Financial contributions help cover hosting, domain registration, and development time. "
                    "Every contribution — no matter the size — makes a difference.</p>"
                    "<ul>"
                    "<li><b>Open Collective</b> — "
                    '<a href="https://opencollective.com/oilregionindie">support us on Open Collective</a>. '
                    "All contributions and spending are transparent.</li>"
                    "<li><b>GitHub Sponsors</b> — "
                    '<a href="https://github.com/sponsors/jwincek">sponsor on GitHub</a> '
                    "if you prefer to support through the platform where the code lives.</li>"
                    "</ul>"
                )),
                ("paragraph", (
                    "<p>This project is open source under the AGPL-3.0 license. "
                    "If you're a developer, designer, or just curious, "
                    '<a href="https://github.com/jwincek/oilregionindie.com">visit the repository</a> '
                    "to see the code, open issues, or contribute.</p>"
                )),
            ],
        )
        home.add_child(instance=feedback)
        feedback.save_revision().publish()

        # --- Terms of Service ---
        tos = ContentPage(
            title="Terms of Service",
            slug="terms",
            subtitle="",
            body=[
                ("paragraph", (
                    "<p>By creating an account on the Oil Region Creative Hub, you agree to the following terms. "
                    "These terms are written in plain language to be understandable, not to obscure your rights.</p>"
                )),
                ("heading", "Your Account"),
                ("paragraph", (
                    "<p>You must provide a valid email address and accurate information when creating your account. "
                    "You are responsible for maintaining the security of your account and for all activity that occurs under it. "
                    "You must be at least 13 years old to create an account.</p>"
                )),
                ("heading", "Your Content"),
                ("paragraph", (
                    "<p>You retain ownership of any content you post — profile information, media, community posts, "
                    "endorsements, and messages. By posting content on the platform, you grant the Oil Region Creative Hub "
                    "a non-exclusive license to display it as part of the platform's normal operation (e.g., showing your "
                    "profile in the directory, displaying your posts in the community feed).</p>"
                    "<p>You may delete your content at any time. If you delete your account, we will remove your content "
                    "within a reasonable timeframe.</p>"
                )),
                ("heading", "Acceptable Use"),
                ("paragraph", (
                    "<p>You agree not to:</p>"
                    "<ul>"
                    "<li>Post content that is illegal, harassing, threatening, or discriminatory</li>"
                    "<li>Impersonate another person or misrepresent your identity</li>"
                    "<li>Use the platform to spam, scam, or mislead other users</li>"
                    "<li>Attempt to access other users' accounts or private data</li>"
                    "<li>Use automated tools to scrape content or create accounts</li>"
                    "</ul>"
                    "<p>Violations may result in content removal or account suspension at our discretion.</p>"
                )),
                ("heading", "Payments"),
                ("paragraph", (
                    "<p>Product purchases are processed through Stripe. The platform facilitates the transaction but "
                    "does not hold funds — payments go directly to the creator's connected Stripe account. "
                    "Refund and dispute policies are handled between the buyer and creator, with Stripe's standard "
                    "dispute resolution process available.</p>"
                )),
                ("heading", "Platform Availability"),
                ("paragraph", (
                    "<p>We aim to keep the platform available and reliable, but we cannot guarantee uninterrupted access. "
                    "The platform is provided as-is, without warranties of any kind. We are not liable for any damages "
                    "arising from your use of the platform.</p>"
                )),
                ("heading", "Changes to These Terms"),
                ("paragraph", (
                    "<p>We may update these terms as the platform evolves. Significant changes will be announced "
                    "via the blog or email. Continued use of the platform after changes constitutes acceptance.</p>"
                )),
                ("heading", "Open Source"),
                ("paragraph", (
                    "<p>The Oil Region Creative Hub software is open source under the AGPL-3.0 license. "
                    "These terms of service apply to this hosted instance of the platform, not to the software itself.</p>"
                )),
                ("paragraph", (
                    "<p>Questions? Contact us at "
                    '<a href="mailto:feedback@oilregionindie.com">feedback@oilregionindie.com</a>.</p>'
                )),
            ],
        )
        home.add_child(instance=tos)
        tos.save_revision().publish()

        # --- Code of Conduct ---
        coc = ContentPage(
            title="Code of Conduct",
            slug="code-of-conduct",
            subtitle="How we treat each other in this community.",
            body=[
                ("paragraph", (
                    "<p>The Oil Region Creative Hub exists to connect independent creators, venues, and fans. "
                    "This code of conduct applies to all interactions on the platform — profiles, community posts, "
                    "booking requests, endorsements, and messages.</p>"
                )),
                ("heading", "Be Respectful"),
                ("paragraph", (
                    "<p>Treat everyone with the same respect you'd show a fellow artist at a show or a neighbor "
                    "on Seneca Street. Disagreement is fine; personal attacks, insults, and harassment are not.</p>"
                )),
                ("heading", "Be Honest"),
                ("paragraph", (
                    "<p>Represent yourself and your work accurately. Don't impersonate other creators, "
                    "misrepresent your skills or experience, or post misleading information about venues or events.</p>"
                )),
                ("heading", "Be Constructive"),
                ("paragraph", (
                    "<p>Community posts and endorsements should contribute positively. Share opportunities, "
                    "ask questions, offer help, celebrate each other's work. If you have a concern about "
                    "a creator or venue, use private feedback through the booking system rather than public posts.</p>"
                )),
                ("heading", "No Discrimination"),
                ("paragraph", (
                    "<p>This platform welcomes people of all backgrounds, identities, and experience levels. "
                    "Discrimination based on race, gender, sexuality, religion, disability, age, or any other "
                    "characteristic will not be tolerated.</p>"
                )),
                ("heading", "No Spam or Self-Promotion Abuse"),
                ("paragraph", (
                    "<p>Your profile is the place to showcase your work. Community posts should be conversations, "
                    "not advertisements. Occasional sharing of your own events or releases is welcome; "
                    "flooding the feed with promotional content is not.</p>"
                )),
                ("heading", "Reporting and Enforcement"),
                ("paragraph", (
                    "<p>If you see behavior that violates this code of conduct, please report it. "
                    "We take reports seriously and will review them promptly.</p>"
                    "<p>Depending on the severity, responses may include:</p>"
                    "<ul>"
                    "<li>A private warning</li>"
                    "<li>Removal of the offending content</li>"
                    "<li>Temporary or permanent account suspension</li>"
                    "</ul>"
                    "<p>We aim to be fair and proportionate. Our goal is to maintain a community where "
                    "everyone feels welcome to participate.</p>"
                )),
                ("paragraph", (
                    "<p>This code of conduct may be updated as the community grows. "
                    "Questions or concerns? Reach out at "
                    '<a href="mailto:feedback@oilregionindie.com">feedback@oilregionindie.com</a>.</p>'
                )),
            ],
        )
        home.add_child(instance=coc)
        coc.save_revision().publish()

        # --- Help page ---
        help_page = ContentPage(
            title="Help",
            slug="help",
            subtitle="How to use the Oil Region Creative Hub.",
            body=[
                ("heading", "Getting Started"),
                ("paragraph", (
                    "<p><b>How do I create a creator profile?</b><br>"
                    "Sign up with your email and username, verify your email, then choose "
                    "\"Create a creator profile\" from the welcome page. A step-by-step wizard "
                    "will walk you through adding your name, skills, bio, and images. "
                    "Your profile starts as a draft — submit it for review and we'll publish it within 48 hours.</p>"
                    "<p><b>How do I register a venue?</b><br>"
                    "Choose \"Register a venue\" from the welcome page. The wizard guides you through "
                    "your venue details, address, amenities, and description. Submit for review when ready.</p>"
                    "<p><b>Do I need a profile to browse?</b><br>"
                    "No. The creator directory, venue directory, events, map, calendar, and community "
                    "are all publicly visible. You only need an account to create a profile, post, or interact.</p>"
                )),
                ("heading", "Profiles"),
                ("paragraph", (
                    "<p><b>How does the review process work?</b><br>"
                    "New profiles start as drafts. When you're ready, click \"Submit for Review\" — "
                    "you'll find this on the Basics tab of your edit page, or in the notification banner "
                    "on other pages. We review and publish profiles within 48 hours. "
                    "You'll receive a notification when your profile goes live.</p>"
                    "<p><b>Can I preview my profile before it's published?</b><br>"
                    "Yes. Visit your profile URL while logged in — you'll see a preview banner. "
                    "Other users will see a 404 until it's published.</p>"
                    "<p><b>How do I edit my profile?</b><br>"
                    "Your edit page is organized into tabs: Basics, Skills & Genres, About, Images, "
                    "Availability, Social Links, and Media. Each section saves independently.</p>"
                    "<p><b>Can I add skills or genres not in the list?</b><br>"
                    "Yes. Use the searchable skill and genre selectors to find existing options, "
                    "and use the \"Other Skills\" and \"Other Genres\" text fields for anything not listed.</p>"
                    "<p><b>How do I see my profile stats?</b><br>"
                    "Click \"Profile Stats\" in the menu to see view counts, follower count, "
                    "and a daily views chart for the last 30 days.</p>"
                )),
                ("heading", "Finding Creators & Venues"),
                ("paragraph", (
                    "<p><b>How do I search?</b><br>"
                    "Use the search icon in the navigation bar for a global search across "
                    "creators, venues, events, and community posts. Each directory also has "
                    "its own filters — you can filter by discipline, skill, genre, location, "
                    "availability, and more. Active filters appear as removable pills above the results.</p>"
                    "<p><b>Is there a map?</b><br>"
                    "Yes. Click \"Map\" in the navigation to see an interactive map of all creators "
                    "and venues with addresses. Venues appear as gold dots, creators as blue dots.</p>"
                )),
                ("heading", "Events"),
                ("paragraph", (
                    "<p><b>How do I create an event?</b><br>"
                    "Click \"Create Event\" in the menu. A wizard walks you through the basics, "
                    "date and time, and details (free/paid, virtual, poster image). "
                    "After creating, you can manage the lineup from the event edit page.</p>"
                    "<p><b>Is there a calendar view?</b><br>"
                    "Yes. From the events listing, click \"Calendar View\" to see a monthly grid "
                    "with events on their dates. Navigate between months with the arrows.</p>"
                )),
                ("heading", "Booking Requests"),
                ("paragraph", (
                    "<p><b>How do booking requests work?</b><br>"
                    "Creators can request to book at a venue (\"Request to Book\" on any venue page), "
                    "and venues can invite creators (\"Invite to Book\" on any creator page). "
                    "The form lets you choose the event type, preferred dates, and write a message. "
                    "The receiving party can accept or decline from their booking inbox.</p>"
                    "<p><b>Where do I see my booking requests?</b><br>"
                    "Click \"Booking Requests\" in the menu. You'll see requests needing your response, "
                    "requests you've sent, and past requests. You can search and filter by status. "
                    "A badge in the menu shows how many need your attention.</p>"
                    "<p><b>What happens when a booking is accepted?</b><br>"
                    "Both parties see each other's contact information. A \"Create Event\" button "
                    "appears to quickly set up the event from the booking details. Both parties "
                    "can leave private feedback and write public endorsements.</p>"
                )),
                ("heading", "Community"),
                ("paragraph", (
                    "<p><b>What are community posts for?</b><br>"
                    "Share announcements, opportunities, discussions, and reviews with the community. "
                    "Not for spam or self-promotion — your profile is the place to showcase your work. "
                    "Please follow our <a href=\"/code-of-conduct/\">Code of Conduct</a>.</p>"
                    "<p><b>How do I follow creators or venues?</b><br>"
                    "Visit a creator or venue profile and click the \"Follow\" button. "
                    "You'll receive notifications about their activity and see updates in your weekly digest.</p>"
                    "<p><b>Can I control email notifications?</b><br>"
                    "Yes. Go to Preferences in the menu to toggle the weekly digest on or off.</p>"
                )),
                ("heading", "Selling Products"),
                ("paragraph", (
                    "<p><b>How do I sell through the platform?</b><br>"
                    "You can add products and set up your shop from \"My Products\" in the menu — "
                    "no payment setup required to get started. When you're ready to accept payments, "
                    "connect with Stripe from the setup page (click \"Set Up Payments\" on your edit page). "
                    "Payments go directly to your Stripe account — the platform never holds your funds.</p>"
                    "<p><b>Can I sell digital products?</b><br>"
                    "Yes. Mark a product as digital and upload the file. Buyers get an immediate download "
                    "link after purchase.</p>"
                    "<p><b>Can I group products together?</b><br>"
                    "Yes. Create a product group from \"My Products.\" Groups can be either a "
                    "\"Collection\" (items sold individually with a bundle discount, like an album) "
                    "or a \"Set\" (items only sold together, like a tea set).</p>"
                    "<p><b>How do I handle shipping?</b><br>"
                    "Set a flat-rate shipping cost on each physical product. After a buyer purchases, "
                    "you'll see their shipping address in your order detail view. Mark items as shipped "
                    "with an optional tracking number — the buyer gets notified by email.</p>"
                    "<p><b>What if I sell something outside the platform?</b><br>"
                    "Use the \"Sold\" button on your products page to mark a physical item as sold out. "
                    "You can restock later with a specific quantity or set it back to unlimited.</p>"
                )),
                ("heading", "Account & Privacy"),
                ("paragraph", (
                    "<p><b>How do I change my password?</b><br>"
                    "Go to Preferences in the menu and click \"Change password.\"</p>"
                    "<p><b>How do I report a problem?</b><br>"
                    "Use the \"Report\" link on any profile or community post, or visit our "
                    "<a href=\"/feedback/\">feedback page</a> to submit a bug report or feature request.</p>"
                    "<p><b>How do I delete my account?</b><br>"
                    "Go to Preferences, scroll to the bottom, and click \"Delete my account.\" "
                    "Type DELETE to confirm. This permanently removes your account and all associated data.</p>"
                )),
            ],
        )
        home.add_child(instance=help_page)
        help_page.save_revision().publish()

        # --- Blog index ---
        blog_index = BlogIndexPage(
            title="Blog",
            slug="blog",
            intro="<p>News, creator spotlights, and updates from the Oil Region Creative Hub.</p>",
        )
        home.add_child(instance=blog_index)
        blog_index.save_revision().publish()

        # --- Sample blog post ---
        post = BlogPost(
            title="Welcome to the Hub",
            slug="welcome",
            subtitle="A new home for the Oil Region creative community.",
            body=[
                ("paragraph", (
                    "<p>After twelve years of bringing independent creators together for one night each summer, "
                    "we're building something that lasts year-round. The Oil Region Creative Hub is a platform "
                    "where musicians, visual artists, jewelers, ceramicists, photographers, and makers of all kinds "
                    "can share their work, connect with venues, and find each other.</p>"
                )),
                ("paragraph", (
                    "<p>If you performed at the festival, sold your work at the street fair, or came out to "
                    "support the scene — this is your home. Create a profile, share your work, and help us "
                    "grow this community.</p>"
                )),
            ],
            author_name="Jerome Wincek",
            tags="announcement, launch",
        )
        blog_index.add_child(instance=post)
        post.save_revision().publish()

        # --- Update default site ---
        Site.objects.update_or_create(
            is_default_site=True,
            defaults={
                "root_page": home,
                "hostname": "localhost",
                "site_name": "Oil Region Creative Hub",
            },
        )

        self.stdout.write(self.style.SUCCESS(
            f"  Created {Page.objects.count() - 1} pages (home, about, feedback, terms, code of conduct, help, blog, 1 post)"
        ))
        self.stdout.write(self.style.SUCCESS("\nSample content seeding complete!"))
