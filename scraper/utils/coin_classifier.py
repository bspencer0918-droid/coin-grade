"""
Coin classifier — derives category, ruler, metal, and denomination
from listing title and description text.
"""
from __future__ import annotations

import re
import yaml
from functools import lru_cache
from pathlib import Path
from typing import Optional

from ..models import Category, Metal
from .us_coin_classifier import classify_us_coin

_DATA_DIR = Path(__file__).parent.parent / "data"


@lru_cache(maxsize=1)
def _load_rulers() -> dict:
    """Load rulers.yaml once and cache it."""
    path = _DATA_DIR / "rulers.yaml"
    if path.exists():
        return yaml.safe_load(path.read_text()) or {}
    return {}


@lru_cache(maxsize=1)
def _load_taxonomy() -> list[dict]:
    """
    Load coin_type_taxonomy.yaml and flatten all type entries into a list.
    Each entry includes its parent_slug and compiled match patterns.
    """
    path = _DATA_DIR / "coin_type_taxonomy.yaml"
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text()) or {}
    flat: list[dict] = []
    for _group_key, entries in raw.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            title_pats = [
                re.compile(p, re.I) for p in entry.get("match_title", [])
            ]
            rev_pats = [
                re.compile(p, re.I) for p in entry.get("match_reverse", [])
            ]
            flat.append({
                "id":           entry["id"],
                "label":        entry.get("label", ""),
                "parent_slug":  entry["parent_slug"],
                "title_pats":   title_pats,
                "rev_pats":     rev_pats,
                "date_range":   entry.get("date_range", ""),
                "relative_value": entry.get("relative_value", 1.0),
                "rarity":       entry.get("rarity", ""),
            })
    return flat


def detect_coin_type(base_slug: str, title: str, description: str = "") -> Optional[str]:
    """
    Returns a type suffix (e.g. 'classical-owl', 'dacia-capta') if the coin
    matches one of the types in coin_type_taxonomy.yaml, else None.

    The full slug would be:  base_slug + '-' + type_id
    e.g.  greek-athens-ar-tetradrachm-classical-owl
    """
    for entry in _load_taxonomy():
        if entry["parent_slug"] != base_slug:
            continue
        # Check title patterns
        for pat in entry["title_pats"]:
            if pat.search(title):
                return entry["id"]
        # Check reverse description patterns (only in description, not title)
        for pat in entry["rev_pats"]:
            if pat.search(description):
                return entry["id"]
    return None


def get_coin_type_info(slug: str) -> Optional[dict]:
    """
    For a full type slug (e.g. 'greek-athens-ar-tetradrachm-classical-owl'),
    return the taxonomy entry dict (label, date_range, relative_value, etc.)
    or None if not found.
    """
    for entry in _load_taxonomy():
        expected = f"{entry['parent_slug']}-{entry['id']}"
        if slug == expected:
            return entry
    return None


# ---------------------------------------------------------------------------
# Metal detection
# ---------------------------------------------------------------------------

# Map of prefix/keyword → Metal
_METAL_PATTERNS: list[tuple[re.Pattern, Metal]] = [
    (re.compile(r'\bAV\b|\bgold\b|\baureus\b|\bsolidus\b|\bsemissis\b|\btremissis\b', re.I), Metal.GOLD),
    (re.compile(r'\bEL\b|\belectrum\b|\bstater\b', re.I),                                    Metal.ELECTRUM),
    (re.compile(r'\bAR\b|\bsilver\b|\bdenarius\b|\bdrachm\b|\btetradrachm\b|\bsiliqua\b|\bmiliarense\b', re.I), Metal.SILVER),
    (re.compile(r'\bBIL\b|\bbillon\b|\bantoninan\b|\bpost.reform\b', re.I),                   Metal.BILLON),
    (re.compile(r'\bAE\b|\bbronze\b|\bcopper\b|\bfollis\b|\bsestertius\b|\bduo?pondius\b|\bas\b|\bnummus\b', re.I), Metal.BRONZE),
]


def detect_metal(text: str) -> Metal:
    for pattern, metal in _METAL_PATTERNS:
        if pattern.search(text):
            return metal
    return Metal.UNKNOWN


# ---------------------------------------------------------------------------
# Category detection
# ---------------------------------------------------------------------------

_CATEGORY_PATTERNS: list[tuple[re.Pattern, Category]] = [
    # Byzantine must come before Roman (solidus/follis overlap)
    (re.compile(r'\bbyzantin\b|\bconstantinople\b|\bnomisma\b|\btrachy\b|\baspron\b', re.I),   Category.BYZANTINE),
    (re.compile(r'\broman\b|\brome\b|\bimperial\b|\brepublic\b|\bdenarius\b|\baureus\b|\bsestertius\b|\baugustus\b|\bnero\b|\btrajan\b|\bhadrian\b', re.I), Category.ROMAN),
    (re.compile(r'\bcelt\b|\bgaul\b|\bbritish\b|\bpotin\b|\bbiga\b|\biberia\b|\bceltib\b', re.I), Category.CELTIC),
    (re.compile(r'\begypt\b|\bptolem\b|\bcleopatra\b|\bnile\b', re.I),                          Category.EGYPTIAN),
    (re.compile(r'\bpersian\b|\bachemenid\b|\bdarius\b|\bxerxes\b|\bsigloi\b|\bdaric\b|\bsassan\b', re.I), Category.PERSIAN),
    # Greek: broad — covers city-states, Macedon, South Italy, Sicily, Punic, etc.
    (re.compile(r'\bgreek\b|\bathens\b|\bcorinth\b|\bsparta\b|\btetradrachm\b|\bdrachm\b|\battica\b'
                r'|\blucania\b|\bcalabrh?\b|\bsicily\b|\bsyracuse\b|\bmacedon\b|\bpunic\b'
                r'|\bcarthag\b|\bshekel\b|\bnomos\b|\btarentin\b|\bmetapon\b|\bstater\b', re.I), Category.GREEK),
    # Other / Islamic / Medieval go to OTHER
    (re.compile(r'\bisla[mn]\b|\bumayyad\b|\babbasid\b|\bdinar\b|\bdirham\b|\bfatimid\b', re.I),  Category.OTHER),
]


def detect_category(text: str) -> Category:
    for pattern, category in _CATEGORY_PATTERNS:
        if pattern.search(text):
            return category
    return Category.OTHER


# ---------------------------------------------------------------------------
# Ruler detection
# ---------------------------------------------------------------------------

def detect_ruler(text: str, category: Category) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Returns (ruler_display_name, ruler_slug, ruler_dates, ruler_rarity) or (None, None, None, None).
    Uses rulers.yaml for the keyword lookup table.
    rarity is one of: 'scarce', 'common', or None (average).
    """
    rulers_data = _load_rulers()
    cat_rulers: list[dict] = rulers_data.get(category.value, [])

    text_lower = text.lower()
    for ruler in cat_rulers:
        name: str = ruler["name"]
        keywords: list[str] = ruler.get("keywords", [name.lower()])
        if any(kw in text_lower for kw in keywords):
            return name, ruler.get("slug", name.lower().replace(" ", "-")), ruler.get("dates"), ruler.get("rarity")

    return None, None, None, None


# ---------------------------------------------------------------------------
# Denomination normalization
# ---------------------------------------------------------------------------

_DENOMINATION_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Roman gold
    (re.compile(r'\baureus\b', re.I),                           "AV Aureus"),
    (re.compile(r'\bsolidus\b', re.I),                          "AV Solidus"),
    (re.compile(r'\bsemissis\b', re.I),                         "AV Semissis"),
    (re.compile(r'\btremissis\b', re.I),                        "AV Tremissis"),
    # Roman silver
    (re.compile(r'\bdenarius\b', re.I),                         "AR Denarius"),
    (re.compile(r'\bantoninan\b|\bdouble\s+denarius\b', re.I),  "AR Antoninianus"),
    (re.compile(r'\bquinarius\b', re.I),                        "AR Quinarius"),
    (re.compile(r'\bsiliqua\b', re.I),                          "AR Siliqua"),
    # Roman bronze
    (re.compile(r'\bsestertius\b', re.I),                       "AE Sestertius"),
    (re.compile(r'\bduo?pondius\b', re.I),                      "AE Dupondius"),
    (re.compile(r'\bfollis\b', re.I),                           "AE Follis"),
    (re.compile(r'\bnummus\b', re.I),                           "AE Nummus"),
    (re.compile(r'\bAE\s*(\d+)', re.I),                         "AE {0}"),
    # Greek / South Italian / Sicilian
    (re.compile(r'\btetradrachm\b', re.I),                      "AR Tetradrachm"),
    (re.compile(r'\bdidrachm\b', re.I),                         "AR Didrachm"),
    (re.compile(r'\bnomos\b', re.I),                            "AR Nomos"),
    (re.compile(r'\bdrachm\b', re.I),                           "AR Drachm"),
    (re.compile(r'\bhemidrachm\b', re.I),                       "AR Hemidrachm"),
    (re.compile(r'\bobol\b', re.I),                             "AR Obol"),
    (re.compile(r'\bAV\s+stater\b|\bgold\s+stater\b', re.I),   "AV Stater"),
    (re.compile(r'\bstater\b', re.I),                           "AR Stater"),
    (re.compile(r'\blitra\b', re.I),                            "AR Litra"),
    # Punic / Carthaginian
    (re.compile(r'\bshekel\b|\bsickle\b', re.I),                "AR Shekel"),
    (re.compile(r'\bdishekel\b', re.I),                         "AR Dishekel"),
    (re.compile(r'\btrihemiobol\b', re.I),                      "AR Trihemiobol"),
    # Celtic
    (re.compile(r'\bAR\s+unit\b|\bsilver\s+unit\b', re.I),      "AR Unit"),
    (re.compile(r'\bAV\s+(?:stater|quarter\s+stater|half\s+stater)\b', re.I), "AV Stater"),
    (re.compile(r'\bpotin\b', re.I),                            "Potin"),
    # Islamic / Medieval
    (re.compile(r'\bdinar\b', re.I),                            "AV Dinar"),
    (re.compile(r'\bdirham\b', re.I),                           "AR Dirham"),
    (re.compile(r'\bfals\b|\bfulus\b', re.I),                   "AE Fals"),
    # Persian
    (re.compile(r'\bdaric\b', re.I),                            "AV Daric"),
    (re.compile(r'\bsigloi\b|\bsiglos\b', re.I),                "AR Siglos"),
    # Byzantine
    (re.compile(r'\bnomisma\b|\bhystamenon\b', re.I),           "AV Nomisma"),
    (re.compile(r'\bhistamenon\b', re.I),                       "AV Histamenon"),
    (re.compile(r'\belectrum\s+(?:nomisma|histamenon)\b', re.I),"EL Nomisma"),
    (re.compile(r'\baspron\s+trachy\b|\btrachea?\b', re.I),     "EL/BI Trachy"),
    (re.compile(r'\bhalf\s+siliqua\b', re.I),                   "AR Half Siliqua"),
]


def detect_denomination(text: str) -> str:
    for pattern, denom in _DENOMINATION_PATTERNS:
        m = pattern.search(text)
        if m:
            if '{0}' in denom and m.lastindex:
                return denom.format(m.group(1))
            return denom
    return "Unknown"


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------

def make_slug(category: Category, ruler_slug: Optional[str], denomination: str, metal: Metal) -> str:
    parts = [category.value]
    if ruler_slug:
        parts.append(ruler_slug)
    parts.append(denomination.lower().replace(" ", "-").replace("/", "-"))
    return "-".join(parts)


# ---------------------------------------------------------------------------
# Main classify function
# ---------------------------------------------------------------------------

def classify(title: str, description: str = "") -> dict:
    """
    Returns a dict with: category, ruler, ruler_normalized, dynasty,
    ruler_dates, ruler_rarity, denomination, metal, slug.

    Strategy: scan all ruler lists first so that listings like
    "Heraclius... AV solidus" (which never say "Byzantine") are
    correctly assigned to the Byzantine category via ruler match.
    Only fall back to text-based category detection when no ruler
    is found in any list.
    """
    full = f"{title} {description}"
    text_lower = full.lower()

    # --- US coin detection (runs before ancient classification) ---
    # US coins are identified by series keywords + a TPG service (NGC/PCGS).
    # They never match ancient ruler keywords so would otherwise fall to OTHER.
    us_result = classify_us_coin(full)
    if us_result:
        metal        = Metal(us_result["metal"]) if us_result["metal"] in Metal._value2member_map_ else Metal.UNKNOWN
        us_result["metal"] = metal
        us_result["category"] = Category.US
        return us_result

    metal        = detect_metal(full)
    denomination = detect_denomination(full)

    # --- Ruler-first detection (scans all categories in yaml order) ---
    rulers_data   = _load_rulers()
    ruler         = None
    ruler_slug    = None
    ruler_dates   = None
    ruler_rarity  = None
    dynasty       = None
    category: Optional[Category] = None

    for cat_name, cat_rulers in rulers_data.items():
        try:
            cat_enum = Category(cat_name)
        except ValueError:
            continue  # unknown category key — skip
        for r in cat_rulers:
            keywords: list[str] = r.get("keywords", [r["name"].lower()])
            if any(kw in text_lower for kw in keywords):
                ruler        = r["name"]
                ruler_slug   = r.get("slug", r["name"].lower().replace(" ", "-"))
                ruler_dates  = r.get("dates")
                ruler_rarity = r.get("rarity")
                dynasty      = r.get("dynasty")
                category     = cat_enum
                break
        if category is not None:
            break

    # Fall back to keyword-based category when no ruler matched
    if category is None:
        category = detect_category(full)

    slug = make_slug(category, ruler_slug, denomination, metal)

    # Refine slug with specific coin type (e.g. dacia-capta, classical-owl)
    coin_type = detect_coin_type(slug, title, description)
    if coin_type:
        slug = f"{slug}-{coin_type}"

    return {
        "category":         category,
        "ruler":            ruler,
        "ruler_normalized": ruler_slug,
        "dynasty":          dynasty,
        "ruler_dates":      ruler_dates,
        "ruler_rarity":     ruler_rarity,
        "denomination":     denomination,
        "metal":            metal,
        "slug":             slug,
        "coin_type":        coin_type,
    }
