"""
PCGS certification detection — mirrors ngc_detector.py for PCGS-graded coins.

Detects PCGS grading from listing text. PCGS uses the same Sheldon scale
as NGC (MS-65, AU-58, VF-35, etc.) so grade values map to the same NGCGrade
enum; we just set grading_service='pcgs' on the NGCInfo object.
"""
from __future__ import annotations

import re
import logging
from typing import Optional

from ..models import NGCInfo, NGCGrade

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Must contain "PCGS" (not just "PCGS-like" descriptions)
_PCGS_PRESENT = re.compile(r'\bPCGS\b', re.IGNORECASE)

# Grade: "PCGS MS-65", "PCGS AU 58", "PCGS Ch MS65", "PCGS VF35"
# Also handles proof: "PCGS PR-65", "PCGS PF-65"
# And Specimen: "PCGS SP-63"
_GRADE_PAT = re.compile(
    r'\bPCGS\b'
    r'(?:\s+(?:Ch(?:oice)?|Gem|Superb))?' # optional prefix
    r'\s+'
    r'(MS|AU|XF|EF|VF|F|VG|G|AG|PO|PR|PF|SP)' # grade letter(s)
    r'[-\s]?(\d{1,2})',                           # numeric suffix
    re.IGNORECASE,
)

# Grade without numeric (e.g. "PCGS VF Details")
_GRADE_NO_NUM_PAT = re.compile(
    r'\bPCGS\b'
    r'(?:\s+(?:Ch(?:oice)?|Gem))?\s+'
    r'(MS|AU|XF|EF|VF|F|VG|G|AG)',
    re.IGNORECASE,
)

# PCGS cert number: 5-9 digits (PCGS uses 8-digit numbers post-2000,
# older certs may be shorter)
_CERT_PAT = re.compile(
    r'(?:PCGS\s+(?:cert(?:ificate)?(?:\s+(?:no\.?|#))?|#)\s*|'
    r'pcgs\.com/cert/)'
    r'(\d{5,9})',
    re.IGNORECASE,
)

# Negative signals
_NEGATIVE_PAT = re.compile(
    r'not\s+PCGS|cracked\s+out|removed\s+from\s+(?:PCGS\s+)?slab',
    re.IGNORECASE,
)

# Details grade: "PCGS VF Details - Scratch"
_DETAILS_PAT = re.compile(r'Details?\s*[-–]\s*([A-Za-z\s]+)', re.IGNORECASE)

_GRADE_MAP: dict[str, NGCGrade] = {
    "MS": NGCGrade.MS, "AU": NGCGrade.AU,
    "XF": NGCGrade.XF, "EF": NGCGrade.XF,
    "VF": NGCGrade.VF, "F":  NGCGrade.F,
    "VG": NGCGrade.VG, "G":  NGCGrade.G,
    "AG": NGCGrade.AG,
    # Proof/Specimen map to MS for display purposes (same price tier logic)
    "PR": NGCGrade.MS, "PF": NGCGrade.MS, "SP": NGCGrade.MS,
    "PO": NGCGrade.P,
}


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect_pcgs(title: str, description: str = "", raw_cert_text: str = "") -> NGCInfo:
    """
    Analyse listing text and return an NGCInfo with grading_service='pcgs'.
    Returns NGCInfo(verified=False) if no PCGS detected.
    Does NOT make network calls.
    """
    full = f"{title} {description} {raw_cert_text}"

    if _NEGATIVE_PAT.search(full):
        return NGCInfo(verified=False)

    if not _PCGS_PRESENT.search(full):
        return NGCInfo(verified=False)

    grade: Optional[NGCGrade] = None
    grade_numeric: Optional[int] = None
    cert_number: Optional[str] = None
    details_grade: Optional[str] = None

    # Grade with numeric
    m = _GRADE_PAT.search(full)
    if m:
        grade        = _GRADE_MAP.get(m.group(1).upper())
        grade_numeric = int(m.group(2))
    else:
        # Grade without numeric
        m2 = _GRADE_NO_NUM_PAT.search(full)
        if m2:
            grade = _GRADE_MAP.get(m2.group(1).upper())

    # Cert number
    mc = _CERT_PAT.search(full)
    if mc:
        cert_number = mc.group(1)

    # Details grade
    if grade:
        md = _DETAILS_PAT.search(full)
        if md:
            details_grade = md.group(1).strip()

    has_pcgs = bool(grade or cert_number)
    if not has_pcgs:
        return NGCInfo(verified=False)

    cert_url = f"https://www.pcgs.com/cert/{cert_number}" if cert_number else None

    return NGCInfo(
        verified=False,
        cert_number=cert_number,
        grade=grade,
        grade_numeric=grade_numeric,
        details_grade=details_grade,
        certification_url=cert_url,
        grading_service="pcgs",
    )
