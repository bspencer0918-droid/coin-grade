// ============================================================
// Coin Grade — Shared TypeScript types (mirrors Pydantic models)
// ============================================================

export type Category    = 'roman' | 'greek' | 'byzantine' | 'persian' | 'celtic' | 'egyptian' | 'us' | 'other'
export type Metal       = 'gold' | 'silver' | 'bronze' | 'billon' | 'electrum' | 'unknown'
export type Source      = 'cng' | 'heritage' | 'numisbids' | 'sixbid' | 'hjb' | 'coinarchives' | 'stacksbowers' | 'greatcollections'
export type ListingType = 'auction_realized' | 'fixed_price' | 'auction_estimate'

export type NGCGrade = 'MS' | 'AU' | 'XF' | 'VF' | 'F' | 'VG' | 'G' | 'AG' | 'P'

export const NGC_GRADE_ORDER: NGCGrade[] = ['MS','AU','XF','VF','F','VG','G','AG','P']

export interface NGCInfo {
  verified:            boolean           // cert number confirmed via ngccoin.com / pcgs.com
  cert_number:         string | null
  grade:               NGCGrade | null
  grade_numeric:       number | null     // e.g. 62 in "MS 62", 65 in "MS-65"
  strike_score:        number | null     // 1–5 (NGC ancients only)
  surface_score:       number | null     // 1–5 (NGC ancients only)
  details_grade:       string | null     // e.g. "Cleaning", "Light Graffito" — coin has issues
  fine_style?:         boolean           // NGC "Fine Style" designation — exceptional artistry, adds significant premium
  certification_url:   string | null
  grading_service:     string            // "ngc" | "pcgs"
}

// Per-grade price statistics (computed from realized auction sales)
export interface GradePriceData {
  median: number
  min:    number
  max:    number
  count:  number
}

export interface Sale {
  id:                      string
  source:                  Source
  listing_type:            ListingType
  lot_url:                 string
  title:                   string
  description:             string
  hammer_price_usd:        number
  currency_original:       string
  price_original:          number
  buyers_premium_included: boolean
  sale_date:               string        // ISO date YYYY-MM-DD
  image_url:               string | null
  ngc:                     NGCInfo
  metadata: {
    mint:          string | null
    weight_g:      number | null
    diameter_mm:   number | null
    obverse_desc:  string | null
    reverse_desc:  string | null
  }
}

// Lightweight summary used in the catalog index (no full sale history)
export type RulerRarity = 'scarce' | 'common'

export interface CoinSummary {
  slug:                string
  category:            Category
  ruler:               string | null
  ruler_normalized:    string | null
  dynasty:             string | null
  ruler_dates:         string | null
  ruler_rarity:        RulerRarity | null
  denomination:        string
  metal:               Metal
  sale_count:          number
  realized_count:      number
  fixed_price_count:   number
  ngc_verified_count:  number
  price_range_usd:     { min: number; max: number }
  median_price_usd:    number
  last_sale_date:      string
  grade_distribution:  Partial<Record<NGCGrade, number>>
  thumbnail_url:       string | null
  median_weight_g:     number | null
  top_strike_score:    number | null   // NGC strike score (1–5) of top-grade rep sale
  top_surface_score:   number | null   // NGC surface score (1–5) of top-grade rep sale
  top_grade_numeric:   number | null   // e.g. 65 for MS-65 (US coins)
  dominant_service:    string          // "ngc" | "pcgs" | "mixed"
  // US coin fields
  series:              string | null   // e.g. "Morgan Dollar"
  date_struck:         string | null   // e.g. "1921"
  mint_mark:           string | null   // e.g. "D", "S", "CC", "" = Philadelphia
}

// Full coin type with complete price history (lazy-loaded per coin)
export interface CoinDetail extends CoinSummary {
  sales: Sale[]
}

// data/meta.json
export interface SourceStatus {
  status:           'ok' | 'error' | 'blocked' | 'pending'
  listings_scraped: number
  last_error:       string | null
}

export interface Meta {
  last_updated:          string
  next_update:           string
  total_listings:        number
  ngc_verified_count:    number
  ngc_mentioned_count:   number
  schema_version:        string
  sources:               Record<Source, SourceStatus>
}

// data/catalog/index.json
export interface CatalogIndex {
  schema_version: string
  generated_at:   string
  coins:          CoinSummary[]
}

// Ruler index entry
export interface RulerEntry {
  name:       string
  slug:       string
  reign:      string
  sale_count: number
  data_url:   string
}

// Active filter state (serialized to/from URL hash)
export interface FilterState {
  category:    Category | ''
  ruler:       string
  metal:       Metal | ''
  grades:      NGCGrade[]
  sources:     Source[]
  ngcVerified: boolean        // only show cert-number-confirmed listings
  priceMin:    number | null
  priceMax:    number | null
  dateFrom:    string
  dateTo:      string
  query:       string
  sortBy:      SortField
  sortDir:     'asc' | 'desc'
  page:        number
}

export type SortField = 'last_sale_date' | 'median_price_usd' | 'sale_count' | 'ruler' | 'denomination'

export const DEFAULT_FILTER: FilterState = {
  category:    '',
  ruler:       '',
  metal:       '',
  grades:      [],
  sources:     [],
  ngcVerified: false,
  priceMin:    null,
  priceMax:    null,
  dateFrom:    '',
  dateTo:      '',
  query:       '',
  sortBy:      'last_sale_date',
  sortDir:     'desc',
  page:        1,
}
