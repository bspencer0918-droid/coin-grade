// ============================================================
// Browse page — main filter + results view
// ============================================================
import type { CoinSummary, FilterState, SortField } from '../types/coin.ts'
import { DEFAULT_FILTER } from '../types/coin.ts'
import { renderFilterPanel } from '../components/FilterPanel.ts'
import { renderCoinTable, sortCoins } from '../components/CoinTable.ts'
import { renderSearchBar, searchCoins } from '../components/SearchBar.ts'
import { navigate } from '../router.ts'

// Apply all active filters to the catalog
export function applyFilters(coins: CoinSummary[], f: FilterState): CoinSummary[] {
  let result = coins

  if (f.query)       result = searchCoins(f.query, result)
  if (f.category)    result = result.filter(c => c.category    === f.category)
  if (f.ruler)       result = result.filter(c => c.ruler_normalized === f.ruler)
  if (f.metal)       result = result.filter(c => c.metal       === f.metal)
  if (f.grades.length > 0)  result = result.filter(c =>
    f.grades.some(g => (c.grade_distribution[g] ?? 0) > 0))
  if (f.ngcVerified) result = result.filter(c => c.ngc_verified_count > 0)
  if (f.priceMin != null)   result = result.filter(c => c.median_price_usd >= f.priceMin!)
  if (f.priceMax != null)   result = result.filter(c => c.median_price_usd <= f.priceMax!)
  if (f.dateFrom)    result = result.filter(c => c.last_sale_date >= f.dateFrom)
  if (f.dateTo)      result = result.filter(c => c.last_sale_date <= f.dateTo)

  return sortCoins(result, f.sortBy, f.sortDir)
}

// Serialize/deserialize filter state to/from URL hash params
function encodeFilters(f: FilterState): string {
  const params = new URLSearchParams()
  if (f.category)    params.set('cat',     f.category)
  if (f.ruler)       params.set('ruler',   f.ruler)
  if (f.metal)       params.set('metal',   f.metal)
  if (f.grades.length)  params.set('grades',  f.grades.join(','))
  if (f.sources.length) params.set('sources', f.sources.join(','))
  if (f.ngcVerified)    params.set('ngc',     '1')
  if (f.priceMin != null) params.set('pmin', String(f.priceMin))
  if (f.priceMax != null) params.set('pmax', String(f.priceMax))
  if (f.dateFrom)    params.set('from',    f.dateFrom)
  if (f.dateTo)      params.set('to',      f.dateTo)
  if (f.query)       params.set('q',       f.query)
  if (f.sortBy !== DEFAULT_FILTER.sortBy) params.set('sort', f.sortBy)
  if (f.sortDir !== DEFAULT_FILTER.sortDir) params.set('dir', f.sortDir)
  if (f.page > 1)    params.set('page',    String(f.page))
  return params.toString()
}

export function renderBrowse(
  allCoins: CoinSummary[],
  filters: FilterState,
  onFilterChange: (f: FilterState) => void
): string {
  const rulers = allCoins
    .filter(c => c.category === filters.category && c.ruler_normalized)
    .reduce<Map<string, string>>((m, c) => {
      if (c.ruler_normalized && !m.has(c.ruler_normalized)) m.set(c.ruler_normalized, c.ruler ?? c.ruler_normalized)
      return m
    }, new Map())
  const rulerList = Array.from(rulers.entries())
    .map(([slug, name]) => ({ slug, name }))
    .sort((a, b) => a.name.localeCompare(b.name))

  const filtered = applyFilters(allCoins, filters)

  const handleSort = (field: SortField) => {
    const dir = filters.sortBy === field && filters.sortDir === 'desc' ? 'asc' : 'desc'
    onFilterChange({ ...filters, sortBy: field, sortDir: dir, page: 1 })
  }

  const handlePage = (page: number) => {
    onFilterChange({ ...filters, page })
  }

  const handleRowClick = (slug: string) => {
    navigate({ name: 'coin', slug })
  }

  const handleSearch = (q: string) => {
    onFilterChange({ ...filters, query: q, page: 1 })
  }

  return `
    <main class="max-w-7xl mx-auto px-4 sm:px-6 py-8">
      <div class="mb-6">
        <h1 class="font-display text-3xl text-gold-400 mb-1">Browse Coins</h1>
        <p class="text-stone-500 text-sm">NGC-certified ancient coins sorted by most recent auction results</p>
      </div>

      <div class="mb-5">
        ${renderSearchBar(filters.query, handleSearch)}
      </div>

      <div class="flex gap-6">
        <!-- Sidebar filters -->
        <aside class="w-64 shrink-0 hidden lg:block">
          ${renderFilterPanel(filters, rulerList, onFilterChange)}
        </aside>

        <!-- Results -->
        <div class="flex-1 min-w-0">
          ${renderCoinTable(filtered, filters, handleSort, handlePage, handleRowClick)}
        </div>
      </div>
    </main>
  `
}
