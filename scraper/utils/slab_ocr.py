"""
OCR-based NGC cert number extraction from slab images.

When a listing's text doesn't contain the cert number (common for dealer
listings where only the slab photo is provided), this module downloads the
image and runs Tesseract OCR to find the cert number from the label.

NGC Ancients cert numbers appear as:  XXXXXXX-XXX  (e.g. 8568382-072)
Modern NGC cert numbers appear as:    XXXXXXXX      (e.g. 6066357)
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache
from io import BytesIO

import httpx

logger = logging.getLogger(__name__)

# NGC cert number patterns on slab labels
# Ancients:  8568382-072   (7 digits, hyphen, 3 digits)
# Modern:    6066357        (6-10 digits, no hyphen)
_OCR_CERT_PAT = re.compile(r'\b(\d{6,10}-\d{3}|\d{7,10})\b')

# Only import if available — OCR is optional; if Tesseract isn't installed
# the scraper still works, just without image-based cert extraction.
try:
    import pytesseract
    from PIL import Image, ImageFilter
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False
    logger.debug("pytesseract/Pillow not available — image OCR disabled")


@lru_cache(maxsize=512)
def extract_cert_from_image(image_url: str) -> str:
    """
    Download image_url and run OCR to find an NGC cert number.
    Returns the cert number string (e.g. '8568382-072') or '' if not found.
    LRU-cached so the same image URL is never downloaded twice per run.
    """
    if not _OCR_AVAILABLE or not image_url:
        return ""

    try:
        resp = httpx.get(
            image_url,
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; coin-grade-bot/1.0)"},
        )
        if resp.status_code != 200:
            return ""

        img = Image.open(BytesIO(resp.content)).convert("L")  # grayscale

        # Run OCR twice: once on full image, once on bottom third (where label is)
        texts = [_ocr_image(img)]
        h = img.height
        if h > 100:
            texts.append(_ocr_image(img.crop((0, int(h * 0.6), img.width, h))))

        for text in texts:
            m = _OCR_CERT_PAT.search(text)
            if m:
                cert = m.group(1)
                logger.debug(f"[OCR] Found cert {cert} in {image_url}")
                return cert

    except Exception as e:
        logger.debug(f"[OCR] Failed for {image_url}: {e}")

    return ""


def _ocr_image(img) -> str:
    """Run Tesseract on a PIL image with preprocessing for slab label text."""
    try:
        # Sharpen slightly to improve barcode-area text
        img = img.filter(ImageFilter.SHARPEN)
        # Tesseract config: treat as single block of text, digits + punctuation
        config = "--psm 6 -c tessedit_char_whitelist=0123456789-"
        return pytesseract.image_to_string(img, config=config)
    except Exception:
        return ""
