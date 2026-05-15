"""
Tests for apps.core.image_utils.optimize_image.

The function takes a Django ImageField-like object (something with a
`name` attribute, file-like read/seek, and a `save(name, ContentFile,
save=False)` method) and resizes/recompresses it in place. We use a
small wrapper around BytesIO so the tests don't need a real Django
model + migrations.
"""

import io
from unittest import mock

from django.test import SimpleTestCase
from PIL import Image

from apps.core.image_utils import (
    MAX_PROFILE_SIZE,
    optimize_image,
)


class FakeImageField:
    """Mimics enough of a Django ImageFieldFile that optimize_image can
    treat it like the real thing."""

    def __init__(self, image_bytes: bytes, name: str = "test.jpg"):
        self._buf = io.BytesIO(image_bytes)
        self.name = name
        # Captures what optimize_image wrote back via save(...).
        self.saved_content: bytes | None = None

    def __bool__(self):
        return True

    def __getattr__(self, attr):
        """Delegate file-like methods (read, seek, tell, …) to the
        underlying BytesIO so Pillow's Image.open can consume us."""
        return getattr(self._buf, attr)

    def save(self, name, content_file, save=False):
        self.saved_content = content_file.read()
        self.name = name


def _make_image_bytes(size, mode="RGB", color=None, format="PNG", **save_kwargs):
    if color is None:
        color = (255, 0, 0) if mode == "RGB" else (
            (255, 0, 0, 128) if mode in ("RGBA",) else 128
        )
    buf = io.BytesIO()
    Image.new(mode, size, color=color).save(buf, format=format, **save_kwargs)
    return buf.getvalue()


def _decode_saved(field):
    """Open the bytes that optimize_image wrote back as a Pillow Image
    for inspection."""
    assert field.saved_content is not None
    return Image.open(io.BytesIO(field.saved_content))


# ---------------------------------------------------------------------------
# Short-circuits
# ---------------------------------------------------------------------------


class OptimizeImageShortCircuitsTest(SimpleTestCase):
    def test_returns_false_for_none(self):
        self.assertFalse(optimize_image(None, MAX_PROFILE_SIZE))

    def test_returns_false_for_falsy_field(self):
        """Django ImageField that hasn't been set is falsy."""
        empty = mock.Mock()
        empty.__bool__ = lambda self: False
        self.assertFalse(optimize_image(empty, MAX_PROFILE_SIZE))

    def test_returns_false_for_unreadable_image(self):
        """Pillow's Image.open raises on garbage bytes — we log and
        return False rather than crashing the upload."""
        field = FakeImageField(b"not actually an image", name="bad.jpg")
        self.assertFalse(optimize_image(field, MAX_PROFILE_SIZE))
        self.assertIsNone(field.saved_content)

    def test_image_already_within_max_size_is_not_modified(self):
        """A 100×100 image under a 800×800 cap doesn't get resaved."""
        small = _make_image_bytes((100, 100), mode="RGB")
        field = FakeImageField(small, name="small.png")
        self.assertFalse(optimize_image(field, MAX_PROFILE_SIZE))
        self.assertIsNone(field.saved_content)
        self.assertEqual(field.name, "small.png")


# ---------------------------------------------------------------------------
# Resize + format conversion
# ---------------------------------------------------------------------------


class OptimizeImageResizeTest(SimpleTestCase):
    def test_oversized_rgb_image_is_resized_and_saved_as_jpeg(self):
        big = _make_image_bytes((2000, 1500), mode="RGB")
        field = FakeImageField(big, name="upload.jpg")
        self.assertTrue(optimize_image(field, MAX_PROFILE_SIZE))
        # The saved bytes are JPEG and fit within the cap.
        img = _decode_saved(field)
        self.assertEqual(img.format, "JPEG")
        self.assertLessEqual(img.size[0], MAX_PROFILE_SIZE[0])
        self.assertLessEqual(img.size[1], MAX_PROFILE_SIZE[1])

    def test_resize_preserves_aspect_ratio(self):
        """Pillow's thumbnail() keeps the aspect ratio when fitting into
        the max-size box. A 2000×1000 image hitting an 800×800 cap
        should become 800×400, not stretched."""
        big = _make_image_bytes((2000, 1000), mode="RGB")
        field = FakeImageField(big, name="wide.jpg")
        optimize_image(field, (800, 800))
        img = _decode_saved(field)
        self.assertEqual(img.size, (800, 400))

    def test_non_jpeg_extension_gets_renamed_to_jpg(self):
        big = _make_image_bytes((2000, 2000), mode="RGB")
        field = FakeImageField(big, name="photo.bmp")
        optimize_image(field, MAX_PROFILE_SIZE)
        self.assertTrue(field.name.endswith(".jpg"))
        self.assertEqual(field.name, "photo.jpg")

    def test_existing_jpg_extension_is_preserved(self):
        big = _make_image_bytes((2000, 2000), mode="RGB")
        field = FakeImageField(big, name="photo.jpg")
        optimize_image(field, MAX_PROFILE_SIZE)
        self.assertEqual(field.name, "photo.jpg")

    def test_existing_jpeg_extension_is_preserved(self):
        """The case-insensitive .jpeg variant is also accepted as-is."""
        big = _make_image_bytes((2000, 2000), mode="RGB")
        field = FakeImageField(big, name="photo.JPEG")
        optimize_image(field, MAX_PROFILE_SIZE)
        self.assertEqual(field.name, "photo.JPEG")

    def test_grayscale_image_is_converted_to_rgb_before_jpeg(self):
        """Pillow can't save 'L' (single-channel grayscale) as JPEG
        with quality flag in some modes — the function converts to RGB
        when the mode isn't already a JPEG-compatible color mode."""
        big = _make_image_bytes((2000, 2000), mode="L")
        field = FakeImageField(big, name="gray.tiff")
        self.assertTrue(optimize_image(field, MAX_PROFILE_SIZE))
        img = _decode_saved(field)
        self.assertEqual(img.format, "JPEG")
        self.assertEqual(img.mode, "RGB")


class OptimizeImageTransparencyTest(SimpleTestCase):
    def test_rgba_image_is_saved_as_png_to_preserve_alpha(self):
        big = _make_image_bytes((2000, 2000), mode="RGBA")
        field = FakeImageField(big, name="overlay.jpg")
        self.assertTrue(optimize_image(field, MAX_PROFILE_SIZE))
        img = _decode_saved(field)
        self.assertEqual(img.format, "PNG")
        # Extension was renamed to .png since the original was .jpg.
        self.assertTrue(field.name.endswith(".png"))

    def test_rgba_image_with_png_extension_keeps_extension(self):
        big = _make_image_bytes((2000, 2000), mode="RGBA")
        field = FakeImageField(big, name="overlay.png")
        optimize_image(field, MAX_PROFILE_SIZE)
        self.assertEqual(field.name, "overlay.png")

    def test_la_image_is_treated_as_transparent_and_saved_as_png(self):
        """LA = grayscale + alpha. Also has transparency — should round-
        trip as PNG."""
        big = _make_image_bytes((2000, 2000), mode="LA",
                                color=(128, 200))
        field = FakeImageField(big, name="masked.bmp")
        self.assertTrue(optimize_image(field, MAX_PROFILE_SIZE))
        img = _decode_saved(field)
        self.assertEqual(img.format, "PNG")

    def test_palette_image_with_transparency_is_saved_as_png(self):
        """Palette ("P") mode with an explicit transparency entry in
        info{} also takes the PNG path."""
        # Build a palette image with a transparency index in info{}.
        buf = io.BytesIO()
        img = Image.new("P", (2000, 2000), color=0)
        img.info["transparency"] = 0
        img.save(buf, format="PNG", transparency=0)
        field = FakeImageField(buf.getvalue(), name="palette.png")
        self.assertTrue(optimize_image(field, MAX_PROFILE_SIZE))
        self.assertEqual(_decode_saved(field).format, "PNG")

    def test_palette_image_without_transparency_is_converted_to_jpeg(self):
        """Bare 'P' mode with no transparency info → falls through to
        the JPEG path (converted to RGB)."""
        buf = io.BytesIO()
        Image.new("P", (2000, 2000), color=0).save(buf, format="PNG")
        field = FakeImageField(buf.getvalue(), name="palette.png")
        self.assertTrue(optimize_image(field, MAX_PROFILE_SIZE))
        img = _decode_saved(field)
        self.assertEqual(img.format, "JPEG")
        # The new name has the .jpg extension since the path doesn't go
        # through the PNG branch.
        self.assertTrue(field.name.endswith(".jpg"))


# ---------------------------------------------------------------------------
# Quality parameter (overridable)
# ---------------------------------------------------------------------------


class OptimizeImageQualityTest(SimpleTestCase):
    def test_custom_quality_is_passed_to_save(self):
        """We can't easily assert on the exact compression, but we can
        verify a lower-quality save produces fewer bytes than a higher
        one for the same source."""
        big = _make_image_bytes((1500, 1500), mode="RGB",
                                color=(100, 150, 200))
        a = FakeImageField(big, name="a.jpg")
        b = FakeImageField(big, name="b.jpg")
        optimize_image(a, (800, 800), quality=20)
        optimize_image(b, (800, 800), quality=95)
        # Lower quality → smaller bytes.
        self.assertLess(len(a.saved_content), len(b.saved_content))
