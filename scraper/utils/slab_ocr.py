"""
OCR-based NGC slab label extraction.

Downloads the slab image, crops to the label area (top ~40% of the image),
and runs Tesseract to extract every field printed on the NGC label:

    SICILY, LEONTINI          VF
    c.450-430 BC         Strike: 4/5
    AR Tetradrachm (17.27g)  Surface: 3/5
    obv Apollo, rv lion head
    within four barley grains     light marks
    6826619-006   [barcode]     NGC ANCIENTS

Returns a SlabLabel dataclass with all parsed fields.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from io import BytesIO
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# NGC cert number patterns
_CERT_PAT = re.compile(r'\b(\d{6,10}-\d{3}|\d{7,10})\b')

# Grade patterns (standalone on label — not preceded by other words)
_GRADE_PAT = re.compile(
    r'\b(MS|AU|XF|EF|VF|F|VG|G|AG|P)(?:[- ](\d{1,2}))?\b'
)
_SCORE_PAT = re.compile(r'(?<!\d)([1-5])/5(?!\d)')

# Weight in parentheses e.g. "(17.27g)" or "17.27 g"
_WEIGHT_PAT = re.compile(r'\(?([\d.]+)\s*g\)?')

# Denomination patterns
_DENOM_PAT = re.compile(
    r'\b(AR|AV|AE|EL|BI)\s+(\w+(?:\s+\w+)?)',
    re.IGNORECASE
)

# Details notes that follow a grade on NGC labels
_DETAILS_PAT = re.compile(
    r'\b(light marks?|scratches?|cleaning|tooled|graffiti|holed|'
    r'banker.?s? marks?|test cuts?|edge filing|smoothing|mount removed|'
    r'environmental damage|ex jewelry|gilt|painted|lacquered)\b',
    re.IGNORECASE
)

# Date patterns: "c.450-430 BC", "1st century BC", "circa 100 AD"
_DATE_PAT = re.compile(
    r'(?:c\.?\s*|circa\s+)?'
    r'(?:\d{1,4}(?:\s*[-–]\s*\d{1,4})?\s*(?:BC|AD|BCE|CE)'
    r'|\d(?:st|nd|rd|th)\s+century\s+(?:BC|AD|BCE|CE))',
    re.IGNORECASE
)

try:
    import pytesseract
    from PIL import Image, ImageFilter, ImageEnhance
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False
    logger.debug("pytesseract/Pillow not available — image OCR disabled")


@dataclass
class SlabLabel:
    """All data fields parsed from an NGC slab label."""
    cert_number:   str            = ""
    grade:         str            = ""   # "VF", "MS", "AU", etc.
    grade_numeric: Optional[int]  = None # 65 for MS-65 (US coins)
    strike_score:  Optional[int]  = None # 1-5
    surface_score: Optional[int]  = None # 1-5
    details_note:  str            = ""   # "light marks", "Cleaning", etc.
    region:        str            = ""   # "SICILY, LEONTINI"
    date_struck:   str            = ""   # "c.450-430 BC"
    denomination:  str            = ""   # "AR Tetradrachm"
    weight_g:      Optional[float] = None
    obv_rev_desc:  str            = ""   # full obv/rev text
    raw_ocr_text:  str            = ""   # full OCR output for debugging

    @property
    def found_anything(self) -> bool:
        return bool(self.cert_number or self.grade or self.region or self.denomination)


@lru_cache(maxsize=512)
def extract_label_from_image(image_url: str) -> SlabLabel:
    """
    Download image_url, OCR the NGC slab label area, and return a SlabLabel
    with all parsed fields.  LRU-cached so the same URL is never downloaded twice.
    """
    empty = SlabLabel()
    if not _OCR_AVAILABLE or not image_url:
        return empty

    try:
        resp = httpx.get(
            image_url,
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; coin-grade-bot/1.0)"},
        )
        if resp.status_code != 200:
            return empty

        img = Image.open(BytesIO(resp.content)).convert("L")  # grayscale
        w, h = img.size

        # The NGC label occupies the top ~38% of a slab image.
        # Crop generously: top 45% to catch the cert/barcode row.
        label_img = img.crop((0, 0, w, int(h * 0.45)))

        ocr_text = _ocr_full_text(label_img)
        if not ocr_text.strip():
            # Fallback: try full image
            ocr_text = _ocr_full_text(img)

        label = _parse_label_text(ocr_text)
        label.raw_ocr_text = ocr_text

        if label.found_anything:
            logger.debug(
                f"[OCR] {image_url} → cert={label.cert_number} "
                f"grade={label.grade} region={label.region[:30]}"
            )
        return label

    except Exception as e:
        logger.debug(f"[OCR] Failed for {image_url}: {e}")
        return empty


# Keep the old entry-point name so existing pipeline code still works
@lru_cache(maxsize=512)
def extract_cert_from_image(image_url: str) -> str:
    """Legacy helper — returns just the cert number string."""
    return extract_label_from_image(image_url).cert_number


def _ocr_full_text(img) -> str:
    """Run Tesseract on a PIL image with preprocessing for slab label text."""
    try:
        # Upscale small images — Tesseract works best at ~300 DPI
        w, h = img.size
        if w < 600:
            scale = 600 / w
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        # Enhance contrast and sharpen
        img = ImageEnhance.Contrast(img).enhance(2.0)
        img = img.filter(ImageFilter.SHARPEN)

        # PSM 6 = assume uniform block of text (good for label layouts)
        config = "--psm 6 --oem 3"
        return pytesseract.image_to_string(img, config=config)
    except Exception:
        return ""


def _parse_label_text(text: str) -> SlabLabel:
    """Parse all NGC label fields from OCR text."""
    label = SlabLabel()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # --- Cert number ---
    m = _CERT_PAT.search(text)
    if m:
        label.cert_number = m.group(1)

    # --- Grade (standalone abbreviation, often on its own or top-right) ---
    # Avoid matching inside words; prefer the first clear match
    for m in _GRADE_PAT.finditer(text):
        # Skip if preceded by letters (e.g. "TETRADRACHM")
        start = m.start()
        if start > 0 and text[start - 1].isalpha():
            continue
        label.grade = m.group(1).upper()
        if m.group(2):
            label.grade_numeric = int(m.group(2))
        break

    # --- Strike / Surface scores ---
    scores = [int(s) for s in _SCORE_PAT.findall(text) if 1 <= int(s) <= 5]
    # Prefer scores near "Strike:" and "Surface:" labels
    strike_m = re.search(r'Strike\s*:?\s*([1-5])/5', text, re.IGNORECASE)
    surface_m = re.search(r'Surface\s*:?\s*([1-5])/5', text, re.IGNORECASE)
    if strike_m:
        label.strike_score = int(strike_m.group(1))
    elif len(scores) >= 1:
        label.strike_score = scores[0]
    if surface_m:
        label.surface_score = int(surface_m.group(1))
    elif len(scores) >= 2:
        label.surface_score = scores[1]

    # --- Details note (e.g. "light marks") ---
    dm = _DETAILS_PAT.search(text)
    if dm:
        label.details_note = dm.group(0).strip()

    # --- Weight ---
    wm = _WEIGHT_PAT.search(text)
    if wm:
        try:
            label.weight_g = float(wm.group(1))
        except ValueError:
            pass

    # --- Denomination (AR/AV/AE/EL + type) ---
    dm2 = _DENOM_PAT.search(text)
    if dm2:
        label.denomination = dm2.group(0).strip()

    # --- Date struck ---
    date_m = _DATE_PAT.search(text)
    if date_m:
        label.date_struck = date_m.group(0).strip()

    # --- Region/Mint (typically the first ALL-CAPS line) ---
    for line in lines:
        # Skip lines that are clearly not a region (e.g. pure numbers, grade words)
        if re.match(r'^[A-Z][A-Z ,\.]+$', line) and len(line) > 4:
            # Exclude single grade abbreviations
            if line.strip() not in ("MS", "AU", "XF", "VF", "F", "VG", "G", "AG", "P", "NGC", "ANCIENTS", "PCGS"):
                label.region = line
                break

    # --- Obverse / Reverse description ---
    # Usually lines containing "obv" or "rv" / "rev"
    obv_rev_lines = []
    capture = False
    for line in lines:
        if re.search(r'\bobv\b|\brev\b|\brv\b', line, re.IGNORECASE):
            capture = True
        if capture:
            # Stop at cert number line or NGC logo line
            if _CERT_PAT.search(line) or re.search(r'\bNGC\b', line):
                break
            obv_rev_lines.append(line)
    label.obv_rev_desc = " ".join(obv_rev_lines).strip()

    return label
