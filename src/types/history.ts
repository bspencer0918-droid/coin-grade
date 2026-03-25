// ============================================================
// History feature — type definitions
// ============================================================

export interface HistoryRuler {
  id: string
  name: string
  dates: string
  portrait_url?: string
  overview: string        // 2-3 sentence summary shown on group page
  biography: string       // Full history, paragraphs separated by \n\n
  coinage: string         // Coinage-specific notes, \n\n separated
  coin_slugs: string[]    // Catalog slugs for coins linked to this ruler
}

export interface HistoryGroup {
  id: string
  name: string
  period_id: string       // Which period this group belongs to
  dates: string
  overview: string
  rulers: HistoryRuler[]
}

export interface HistoryPeriod {
  id: string
  name: string
  dates: string
  overview: string
}

export interface HistoryCivilization {
  id: string
  name: string
  emoji: string
  dates: string
  overview: string
  periods: HistoryPeriod[]
  groups: HistoryGroup[]
}
