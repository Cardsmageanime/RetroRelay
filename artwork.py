"""Artwork processing for opt-in, rights-cleared room thumbnails.

Never scrape/download artwork or game images automatically. The host supplies a file
and affirms permission to display it. Image data is not game data or ROM data.
"""
from __future__ import annotations

import base64
import io
import warnings

from PIL import Image, UnidentifiedImageError

MAX_SOURCE_BYTES = 800_000
MAX_THUMB_BYTES = 400_000
MAX_IMAGE_PIXELS = 4_000_000
THUMB_SIZE = (280, 200)


def clean_artwork(encoded: str) -> bytes:
    """Validate upload, shrink to preview size, remove metadata, and emit PNG."""
    if len(encoded) > 1_100_000:
        raise ValueError("Artwork exceeds 800 KB upload limit")
    try:
        original = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("Artwork is not valid base64") from exc
    if not original or len(original) > MAX_SOURCE_BYTES:
        raise ValueError("Artwork must be an image smaller than 800 KB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(original), formats=["PNG", "JPEG", "WEBP"]) as img:
                if img.width * img.height > MAX_IMAGE_PIXELS:
                    raise ValueError("Artwork has too many pixels")
                img.load()
                image = img.convert("RGB")
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError) as exc:
        raise ValueError("Only valid PNG, JPEG or WebP artwork is supported") from exc
    image.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    result = out.getvalue()
    if len(result) > MAX_THUMB_BYTES:
        raise ValueError("Image could not be compressed below 400 KB")
    return result
