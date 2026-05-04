"""
Image optimization utilities.
Resizes uploaded images to reasonable maximum dimensions
and converts to JPEG for smaller file sizes.
"""

import io
import logging

from PIL import Image

logger = logging.getLogger(__name__)

# Maximum dimensions for different image types
MAX_PROFILE_SIZE = (800, 800)
MAX_HEADER_SIZE = (1600, 600)
MAX_PRODUCT_SIZE = (1200, 1200)
MAX_MEDIA_SIZE = (1920, 1080)

JPEG_QUALITY = 85


def optimize_image(image_field, max_size, quality=JPEG_QUALITY):
    """
    Resize an image field if it exceeds max_size dimensions.
    Converts to JPEG for compression (except PNGs with transparency).
    Returns True if the image was modified, False otherwise.
    """
    if not image_field:
        return False

    try:
        img = Image.open(image_field)
    except Exception:
        logger.warning("Could not open image for optimization: %s", image_field.name)
        return False

    original_size = img.size
    needs_resize = (
        original_size[0] > max_size[0] or
        original_size[1] > max_size[1]
    )

    if not needs_resize:
        return False

    # Resize maintaining aspect ratio
    img.thumbnail(max_size, Image.LANCZOS)

    # Save back to the field
    buffer = io.BytesIO()

    # Keep PNG if it has transparency, otherwise convert to JPEG
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img.save(buffer, format="PNG", optimize=True)
        if not image_field.name.lower().endswith(".png"):
            image_field.name = image_field.name.rsplit(".", 1)[0] + ".png"
    else:
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        if not image_field.name.lower().endswith((".jpg", ".jpeg")):
            image_field.name = image_field.name.rsplit(".", 1)[0] + ".jpg"

    buffer.seek(0)
    from django.core.files.base import ContentFile
    image_field.save(image_field.name, ContentFile(buffer.read()), save=False)

    logger.info(
        "Optimized image %s: %dx%d → %dx%d",
        image_field.name, original_size[0], original_size[1], img.size[0], img.size[1],
    )
    return True
