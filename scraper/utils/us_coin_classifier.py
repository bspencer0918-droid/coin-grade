"""
US coin classifier — identifies series, date, and mint mark from listing text.

Returns None if the listing does not appear to be a US coin.
Called before ancient coin classification in the main classify() pipeline.
"""
from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Series registry
# Each entry: (pattern, series_slug, display_name)
# Order matters — more specific patterns first.
# ---------------------------------------------------------------------------

_SERIES: list[tuple[re.Pattern, str, str]] = [
    # ── Gold ──────────────────────────────────────────────────────────────
    (re.compile(r'\bsaint.gaudens\b|\b(?:ultra\s+)?high\s+relief\b.*\bdouble\s*eagle\b|\bdouble\s*eagle\b.*\bsaint', re.I),
     'saint-gaudens-double-eagle', 'Saint-Gaudens Double Eagle'),
    (re.compile(r'\bdouble\s*eagle\b|\b\$20\s+gold\b|\bgold\s+\$20\b|\blib.*double eagle\b', re.I),
     'liberty-double-eagle', 'Liberty Double Eagle'),
    (re.compile(r'\bindian\s+(?:head\s+)?eagle\b|\bindian.*\$10\s+gold\b', re.I),
     'indian-eagle', 'Indian Eagle ($10)'),
    (re.compile(r'\bliberty\s+eagle\b|\bgold\s+eagle\b|\b\$10\s+gold\b', re.I),
     'liberty-eagle', 'Liberty Eagle ($10)'),
    (re.compile(r'\bindian\s+(?:head\s+)?half\s+eagle\b', re.I),
     'indian-half-eagle', 'Indian Half Eagle ($5)'),
    (re.compile(r'\bliberty\s+half\s+eagle\b|\bhalf\s+eagle\b|\b\$5\s+gold\b', re.I),
     'liberty-half-eagle', 'Half Eagle ($5)'),
    (re.compile(r'\bquarter\s+eagle\b|\b\$2\.?50\s+gold\b|\b\$2\s*1/2\s+gold\b', re.I),
     'quarter-eagle', 'Quarter Eagle ($2.50)'),
    (re.compile(r'\bgold\s+dollar\b|\b\$1\s+gold\b', re.I),
     'gold-dollar', 'Gold Dollar'),
    (re.compile(r'\bthree\s+dollar\s+gold\b|\b\$3\s+gold\b', re.I),
     'three-dollar-gold', 'Three Dollar Gold'),

    # ── Silver Dollars ────────────────────────────────────────────────────
    (re.compile(r'\bmorgan\b.*\b(?:silver\s+)?dollar\b|\bmorgan\s+(?:silver\s+)?dollar\b', re.I),
     'morgan-dollar', 'Morgan Dollar'),
    (re.compile(r'\bpeace\b.*\b(?:silver\s+)?dollar\b|\bpeace\s+(?:silver\s+)?dollar\b', re.I),
     'peace-dollar', 'Peace Dollar'),
    (re.compile(r'\bseated\s+liberty\b.*\bdollar\b|\bseated.*\$1\b', re.I),
     'seated-liberty-dollar', 'Seated Liberty Dollar'),
    (re.compile(r'\btrade\s+dollar\b', re.I),
     'trade-dollar', 'Trade Dollar'),
    (re.compile(r'\bdraped\s+bust\b.*\bdollar\b|\bflowing\s+hair\b.*\bdollar\b', re.I),
     'early-dollar', 'Early Dollar'),
    (re.compile(r'\beisenhower\b.*\bdollar\b|\bike\s+dollar\b', re.I),
     'eisenhower-dollar', 'Eisenhower Dollar'),

    # ── Half Dollars ──────────────────────────────────────────────────────
    (re.compile(r'\bwalking\s+liberty\b|\bwalk.*lib.*half\b', re.I),
     'walking-liberty-half', 'Walking Liberty Half Dollar'),
    (re.compile(r'\bfranklin\b.*\bhalf\b', re.I),
     'franklin-half', 'Franklin Half Dollar'),
    (re.compile(r'\bkennedy\b.*\bhalf\b', re.I),
     'kennedy-half', 'Kennedy Half Dollar'),
    (re.compile(r'\bbarber\b.*\bhalf\b', re.I),
     'barber-half', 'Barber Half Dollar'),
    (re.compile(r'\bseated\b.*\bhalf\b', re.I),
     'seated-half', 'Seated Liberty Half Dollar'),
    (re.compile(r'\bdraped\s+bust\b.*\bhalf\b|\bflowing\s+hair\b.*\bhalf\b', re.I),
     'early-half', 'Early Half Dollar'),

    # ── Quarters ──────────────────────────────────────────────────────────
    (re.compile(r'\bstanding\s+liberty\b.*\bquarter\b|\bslq\b', re.I),
     'standing-liberty-quarter', 'Standing Liberty Quarter'),
    (re.compile(r'\bbarber\b.*\bquarter\b', re.I),
     'barber-quarter', 'Barber Quarter'),
    (re.compile(r'\bwashington\b.*\bquarter\b', re.I),
     'washington-quarter', 'Washington Quarter'),
    (re.compile(r'\bseated\b.*\bquarter\b', re.I),
     'seated-quarter', 'Seated Liberty Quarter'),

    # ── Dimes ─────────────────────────────────────────────────────────────
    (re.compile(r'\bmercury\s+dime\b|\bwinged\s+liberty.*dime\b', re.I),
     'mercury-dime', 'Mercury Dime'),
    (re.compile(r'\bbarber\b.*\bdime\b', re.I),
     'barber-dime', 'Barber Dime'),
    (re.compile(r'\broosevelt\b.*\bdime\b', re.I),
     'roosevelt-dime', 'Roosevelt Dime'),
    (re.compile(r'\bseated\b.*\bdime\b', re.I),
     'seated-dime', 'Seated Liberty Dime'),

    # ── Nickels ───────────────────────────────────────────────────────────
    (re.compile(r'\bbuffalo\s+nickel\b|\bindian\s+head\s+nickel\b', re.I),
     'buffalo-nickel', 'Buffalo Nickel'),
    (re.compile(r'\bjefferson\s+nickel\b', re.I),
     'jefferson-nickel', 'Jefferson Nickel'),
    (re.compile(r'\bshield\s+nickel\b', re.I),
     'shield-nickel', 'Shield Nickel'),
    (re.compile(r'\bliberty\s+nickel\b|\bv\s+nickel\b', re.I),
     'liberty-nickel', 'Liberty Nickel'),

    # ── Cents ─────────────────────────────────────────────────────────────
    (re.compile(r'\blincoln\b.*\bcent\b|\blincoln\b.*\bpenny\b|\bwheat\s+(?:cent|penny)\b', re.I),
     'lincoln-cent', 'Lincoln Cent'),
    (re.compile(r'\bindian\s+head\b.*\bcent\b|\bindian\s+cent\b', re.I),
     'indian-head-cent', 'Indian Head Cent'),
    (re.compile(r'\bflying\s+eagle\b.*\bcent\b', re.I),
     'flying-eagle-cent', 'Flying Eagle Cent'),
    (re.compile(r'\blarge\s+cent\b|\bmatron\s+head\b|\bclassic\s+head.*cent\b|\bcoronet.*cent\b', re.I),
     'large-cent', 'Large Cent'),
    (re.compile(r'\bhalf\s+cent\b', re.I),
     'half-cent', 'Half Cent'),

    # ── Commemoratives ────────────────────────────────────────────────────
    (re.compile(r'\bcommemorative\b.*\bdollar\b', re.I),
     'commemorative-dollar', 'Commemorative Dollar'),
    (re.compile(r'\bcommemorative\b.*\bhalf\b', re.I),
     'commemorative-half', 'Commemorative Half Dollar'),
    (re.compile(r'\bcommemorative\b.*\bgold\b', re.I),
     'commemorative-gold', 'Commemorative Gold'),
]

# ---------------------------------------------------------------------------
# Date and mint-mark extraction
# ---------------------------------------------------------------------------

# 4-digit year in US coinage range (1792–2030)
_YEAR_RE = re.compile(r'\b(1[78]\d{2}|19\d{2}|20[0-3]\d)\b')

# Mint mark immediately after year: "1921-D", "1921 D", "1921D"
# Mint marks: D=Denver, S=San Francisco, CC=Carson City, O=New Orleans,
#             W=West Point, C=Charlotte, D/O rare branch mints
_MINT_RE = re.compile(
    r'\b(\d{4})'              # year capture group
    r'[-\s]?'                 # optional separator
    r'([DSOW]|CC)\b',         # mint mark
    re.IGNORECASE,
)

# Grading service signals used to confirm this is a TPG-certified US coin
_TPG_RE = re.compile(r'\b(NGC|PCGS)\b', re.IGNORECASE)


def classify_us_coin(text: str) -> Optional[dict]:
    """
    Returns classification dict if text describes a TPG-certified US coin,
    else returns None.

    Returned dict keys: category, series, series_slug, date_struck,
                        mint_mark, denomination, slug.
    """
    # Must mention a grading service — we only track certified US coins
    if not _TPG_RE.search(text):
        return None

    for pattern, series_slug, display_name in _SERIES:
        if not pattern.search(text):
            continue

        # Year extraction
        date_struck: Optional[str] = None
        mint_mark: str = ""

        # Try year+mint together first
        mm = _MINT_RE.search(text)
        if mm:
            date_struck = mm.group(1)
            mint_mark   = mm.group(2).upper()
        else:
            ym = _YEAR_RE.search(text)
            if ym:
                date_struck = ym.group(1)

        # Build slug: us-{series}-{year}-{mint} (mint only if present)
        parts = ["us", series_slug]
        if date_struck:
            parts.append(date_struck)
        if mint_mark:
            parts.append(mint_mark.lower())
        slug = "-".join(parts)

        return {
            "category":     "us",
            "series":       display_name,
            "series_slug":  series_slug,
            "date_struck":  date_struck,
            "mint_mark":    mint_mark or None,
            "denomination": f"{display_name}{' ' + date_struck if date_struck else ''}"
                            f"{'-' + mint_mark if mint_mark else ''}",
            "slug": slug,
            # Ancient-coin fields set to None for US coins
            "ruler":            None,
            "ruler_normalized": None,
            "dynasty":          None,
            "ruler_dates":      None,
            "ruler_rarity":     None,
            "metal":            _infer_metal(series_slug),
        }

    return None


def _infer_metal(series_slug: str) -> str:
    """Infer metal from series slug for US coins."""
    gold_series = {
        'saint-gaudens-double-eagle', 'liberty-double-eagle',
        'indian-eagle', 'liberty-eagle',
        'indian-half-eagle', 'liberty-half-eagle',
        'quarter-eagle', 'gold-dollar', 'three-dollar-gold',
        'commemorative-gold',
    }
    silver_series = {
        'morgan-dollar', 'peace-dollar', 'seated-liberty-dollar',
        'trade-dollar', 'early-dollar', 'eisenhower-dollar',
        'walking-liberty-half', 'franklin-half', 'kennedy-half',
        'barber-half', 'seated-half', 'early-half',
        'standing-liberty-quarter', 'barber-quarter', 'washington-quarter',
        'seated-quarter', 'mercury-dime', 'barber-dime',
        'seated-dime', 'commemorative-dollar', 'commemorative-half',
    }
    if series_slug in gold_series:
        return 'gold'
    if series_slug in silver_series:
        return 'silver'
    return 'bronze'   # cents, nickels, base-metal commemoratives
