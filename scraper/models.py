"""
Pydantic data models — single source of truth for the JSON schema.
The TypeScript types in src/types/coin.ts must mirror these exactly.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Category(str, Enum):
    ROMAN     = "roman"
    GREEK     = "greek"
    BYZANTINE = "byzantine"
    PERSIAN   = "persian"
    CELTIC    = "celtic"
    EGYPTIAN  = "egyptian"
    OTHER     = "other"


class Metal(str, Enum):
    GOLD     = "gold"
    SILVER   = "silver"
    BRONZE   = "bronze"
    BILLON   = "billon"
    ELECTRUM = "electrum"
    UNKNOWN  = "unknown"


class Source(str, Enum):
    CNG          = "cng"
    HERITAGE     = "heritage"
    VCOINS       = "vcoins"
    MASHOPS      = "mashops"
    NUMISBIDS    = "numisbids"
    SIXBID       = "sixbid"
    HJB          = "hjb"
    COINARCHIVES = "coinarchives"


class ListingType(str, Enum):
    AUCTION_REALIZED = "auction_realized"   # Hammer price from a completed auction
    FIXED_PRICE      = "fixed_price"        # Dealer asking price (not a sale)
    AUCTION_ESTIMATE = "auction_estimate"   # Pre-sale estimate, no transaction yet


class NGCGrade(str, Enum):
    MS = "MS"
    AU = "AU"
    XF = "XF"
    VF = "VF"
    F  = "F"
    VG = "VG"
    G  = "G"
    AG = "AG"
    P  = "P"


NGC_GRADE_ORDER = [NGCGrade.MS, NGCGrade.AU, NGCGrade.XF, NGCGrade.VF,
                   NGCGrade.F, NGCGrade.VG, NGCGrade.G, NGCGrade.AG, NGCGrade.P]


class NGCInfo(BaseModel):
    verified:          bool
    cert_number:       Optional[str]  = None
    grade:             Optional[NGCGrade] = None
    grade_numeric:     Optional[int]  = None   # e.g. 62 in "MS 62"
    strike_score:      Optional[int]  = None   # 1–5
    surface_score:     Optional[int]  = None   # 1–5
    details_grade:     Optional[str]  = None   # e.g. "Cleaning"
    certification_url: Optional[str]  = None


class SaleMetadata(BaseModel):
    mint:         Optional[str]   = None
    weight_g:     Optional[float] = None
    diameter_mm:  Optional[float] = None
    obverse_desc: Optional[str]   = None
    reverse_desc: Optional[str]   = None


class Sale(BaseModel):
    id:                      str
    source:                  Source
    listing_type:            ListingType = ListingType.AUCTION_REALIZED
    lot_url:                 str
    title:                   str
    description:             str = ""
    hammer_price_usd:        float
    currency_original:       str
    price_original:          float
    buyers_premium_included: bool = False
    sale_date:               date
    image_url:               Optional[str] = None
    ngc:                     NGCInfo
    metadata:                SaleMetadata = Field(default_factory=SaleMetadata)


class PriceRange(BaseModel):
    min: float
    max: float


class CoinSummary(BaseModel):
    """Lightweight entry in catalog/index.json — no sale history."""
    slug:                str
    category:            Category
    ruler:               Optional[str]  = None
    ruler_normalized:    Optional[str]  = None
    dynasty:             Optional[str]  = None
    ruler_dates:         Optional[str]  = None
    ruler_rarity:        Optional[str]  = None   # "scarce" | "common" | None
    denomination:        str
    metal:               Metal
    sale_count:          int
    realized_count:      int   = 0     # auction_realized only
    fixed_price_count:   int   = 0     # fixed_price listings
    ngc_verified_count:  int
    price_range_usd:     Optional[PriceRange] = None
    median_price_usd:    float = 0.0   # median of auction_realized only
    last_sale_date:      str   = ""
    grade_distribution:  dict[str, int] = Field(default_factory=dict)
    thumbnail_url:       Optional[str]  = None
    median_weight_g:     Optional[float] = None   # median across all sales with weight data
    top_strike_score:    Optional[int]   = None   # NGC strike score (1–5) of top-grade rep sale
    top_surface_score:   Optional[int]   = None   # NGC surface score (1–5) of top-grade rep sale


class CoinDetail(CoinSummary):
    """Full coin entry with complete sale history."""
    sales: list[Sale] = Field(default_factory=list)


class SourceStatus(BaseModel):
    status:           str   # "ok" | "error" | "blocked" | "pending"
    listings_scraped: int   = 0
    last_error:       Optional[str] = None


class Meta(BaseModel):
    last_updated:        str
    next_update:         str
    total_listings:      int = 0
    ngc_verified_count:  int = 0
    ngc_mentioned_count: int = 0
    schema_version:      str = "1.2"
    sources:             dict[str, SourceStatus] = Field(default_factory=dict)


class RawListing(BaseModel):
    """Intermediate model produced by each scraper before NGC detection/classification."""
    title:          str
    description:    str = ""
    price:          Optional[float] = None
    currency:       str = "USD"
    sale_date:      Optional[date]  = None
    lot_url:        str
    image_url:      Optional[str]   = None
    source:         Source
    raw_cert_text:  str = ""   # Any text that might contain NGC cert info
    listing_type:   ListingType = ListingType.AUCTION_REALIZED
