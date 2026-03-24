"""
NGC certification detection.

Detects NGC grading from listing text and optionally verifies cert numbers
against the official NGC registry at ngccoin.com.
"""
from __future__ import annotations

import json
import re
import time
import logging
from pathlib import Path
from typing import Optional

import httpx

from ..models import NGCInfo, NGCGrade
from ..config import NGC_CACHE_FILE, RATE_LIMITS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Explicit grade with optional numeric suffix
# Matches: "NGC MS 62", "NGC XF", "NGC Ch VF 35", "NGC AU Strike: 5/5"
_GRADE_PAT = re.compile(
    r'\bNGC\b'
    r'(?:\s+Ch(?:oice)?)?'              # optional "Choice" or "Ch"
    r'\s+'
    r'(MS|AU|XF|EF|VF|F|VG|G|AG|P)'    # grade abbreviation
    r'(?:\s+(\d{1,2}))?',               # optional numeric
    re.IGNORECASE,
)

# Score notation: "5/5" or "4/5"
_SCORE_PAT = re.compile(r'(\d)/5', re.IGNORECASE)

# NGC cert number — 6-10 digit number with optional "-XXX" suffix (NGC Ancients format)
# Examples: "8568382-072", "6066357", "Cert 8568382-072"
_CERT_PAT = re.compile(
    r'(?:cert(?:ificate)?[\s#:]*|ngccoin\.com/cert(?:lookup)?/)'
    r'(\d{6,10}(?:-\d{3})?)',
    re.IGNORECASE,
)

# Standalone long number that could be a cert (used as fallback)
# Also matches hyphenated NGC Ancients format: 8568382-072
_CERT_STANDALONE = re.compile(r'\b(\d{7,10}-\d{3}|\d{7,10})\b')

# Negative patterns — exclude these from NGC matches
_NEGATIVE_PAT = re.compile(
    r'not\s+NGC|cracked\s+out|removed\s+from\s+slab|no\s+longer\s+(?:NGC|encapsulated|slabbed)',
    re.IGNORECASE,
)

# "NGC certified/slabbed/encapsulated" without explicit grade
_GENERIC_PAT = re.compile(
    r'\bNGC\b\s+(?:certified|slabbed|encapsulated|graded)',
    re.IGNORECASE,
)

# Grade normalization map
_GRADE_MAP: dict[str, NGCGrade] = {
    "MS": NGCGrade.MS, "AU": NGCGrade.AU,
    "XF": NGCGrade.XF, "EF": NGCGrade.XF,   # EF = XF (European notation)
    "VF": NGCGrade.VF, "F":  NGCGrade.F,
    "VG": NGCGrade.VG, "G":  NGCGrade.G,
    "AG": NGCGrade.AG, "P":  NGCGrade.P,
}

# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect_ngc(title: str, description: str = "", raw_cert_text: str = "") -> NGCInfo:
    """
    Analyse listing text and return an NGCInfo object.
    Does NOT make any network calls — use verify_cert() for that.
    """
    full_text = f"{title} {description} {raw_cert_text}"

    # Fast-fail: if negative signals are present, not NGC
    if _NEGATIVE_PAT.search(full_text):
        return NGCInfo(verified=False)

    # Must find "NGC" somewhere
    if "NGC" not in full_text.upper():
        return NGCInfo(verified=False)

    grade: Optional[NGCGrade] = None
    grade_numeric: Optional[int] = None
    strike_score: Optional[int] = None
    surface_score: Optional[int] = None
    cert_number: Optional[str] = None

    # Grade extraction
    m = _GRADE_PAT.search(full_text)
    if m:
        grade = _GRADE_MAP.get(m.group(1).upper())
        if m.group(2):
            grade_numeric = int(m.group(2))

    # Score extraction (strike/surface)
    scores = _SCORE_PAT.findall(full_text)
    if len(scores) >= 2:
        strike_score  = int(scores[0])
        surface_score = int(scores[1])

    # Cert number extraction
    m_cert = _CERT_PAT.search(full_text)
    if m_cert:
        cert_number = m_cert.group(1)
    else:
        # Try standalone long numbers as fallback
        m_standalone = _CERT_STANDALONE.search(full_text)
        if m_standalone:
            cert_number = m_standalone.group(1)

    # Details grade (e.g. "NGC VF Details - Cleaning")
    details_grade = None
    details_match = re.search(r'Details?\s*[-–]\s*([A-Za-z\s]+)', full_text)
    if details_match and grade:
        details_grade = details_match.group(1).strip()

    has_ngc = bool(grade or _GENERIC_PAT.search(full_text))

    return NGCInfo(
        verified=False,          # cert lookup required to set True
        cert_number=cert_number,
        grade=grade,
        grade_numeric=grade_numeric,
        strike_score=strike_score,
        surface_score=surface_score,
        details_grade=details_grade,
        certification_url=f"https://www.ngccoin.com/certlookup/{cert_number.replace('-', '')}/" if cert_number else None,
    ) if has_ngc else NGCInfo(verified=False)


# ---------------------------------------------------------------------------
# Cert number verification (network call)
# ---------------------------------------------------------------------------

_cache: dict[str, dict] = {}

def _load_cache() -> None:
    global _cache
    if NGC_CACHE_FILE.exists():
        try:
            _cache = json.loads(NGC_CACHE_FILE.read_text())
        except Exception:
            _cache = {}

def _save_cache() -> None:
    NGC_CACHE_FILE.write_text(json.dumps(_cache, indent=2))


def verify_cert(ngc_info: NGCInfo, client: Optional[httpx.Client] = None) -> NGCInfo:
    """
    Attempt to verify an NGC cert number via the NGC registry API.
    Returns an updated NGCInfo with verified=True and official grade data if found.
    Rate-limited to 1 request per RATE_LIMITS['ngc'] seconds.
    """
    if not ngc_info.cert_number:
        return ngc_info

    _load_cache()
    cert = ngc_info.cert_number

    if cert in _cache:
        cached = _cache[cert]
        if cached.get("verified"):
            return _apply_registry_data(ngc_info, cached)
        return ngc_info   # previously looked up, not verified

    # NGC Ancients certs are like "8568382-072"; the lookup page accepts both
    # the full hyphenated form and the numeric-only form (digits without suffix).
    cert_numeric = cert.replace("-", "")
    urls_to_try = [
        f"https://www.ngccoin.com/certlookup/{cert}/50/",
        f"https://www.ngccoin.com/certlookup/{cert_numeric}/50/",
    ]
    try:
        close_client = client is None
        if client is None:
            client = httpx.Client(timeout=10, follow_redirects=True)

        resp = None
        for url in urls_to_try:
            r = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            time.sleep(RATE_LIMITS["ngc"])
            if r.status_code == 200:
                resp = r
                break
        if resp is None:
            if close_client:
                client.close()
            return ngc_info

        if "No certification record found" not in resp.text:
            # Parse grade from page (NGC uses structured HTML)
            grade_match = re.search(r'<td[^>]*>\s*(MS|AU|XF|VF|F|VG|G|AG|P)\s*(\d{0,2})\s*</td>', resp.text)
            if grade_match:
                data = {
                    "verified": True,
                    "grade":    grade_match.group(1),
                    "grade_numeric": int(grade_match.group(2)) if grade_match.group(2) else None,
                }
                _cache[cert] = data
                _save_cache()
                return _apply_registry_data(ngc_info, data)
        else:
            _cache[cert] = {"verified": False}
            _save_cache()

        if close_client:
            client.close()

    except Exception as e:
        logger.warning(f"NGC cert lookup failed for {cert}: {e}")

    return ngc_info


def _apply_registry_data(ngc_info: NGCInfo, data: dict) -> NGCInfo:
    return ngc_info.model_copy(update={
        "verified":      data.get("verified", False),
        "grade":         NGCGrade(data["grade"]) if data.get("grade") else ngc_info.grade,
        "grade_numeric": data.get("grade_numeric") or ngc_info.grade_numeric,
    })
