// ============================================================
// Sortable coin results table
// ============================================================
import type { CoinSummary, SortField, FilterState, NGCGrade } from '../types/coin.ts'
import { NGC_GRADE_ORDER } from '../types/coin.ts'
import { renderSourceBadge } from './SourceBadge.ts'
import { href } from '../router.ts'

const PAGE_SIZE = 50

const GRADE_BADGE_CLASS: Record<NGCGrade, string> = {
  MS: 'badge-ms', AU: 'badge-au', XF: 'badge-xf', VF: 'badge-vf',
  F:  'badge-f',  VG: 'badge-vg', G:  'badge-g',  AG: 'badge-ag', P: 'badge-g',
}

function gradeBar(dist: Partial<Record<NGCGrade, number>>): string {
  const total = Object.values(dist).reduce((a, b) => a + (b ?? 0), 0)
  if (total === 0) return '<span class="text-stone-700 text-xs">—</span>'
  const top = NGC_GRADE_ORDER.find(g => dist[g])
  if (!top) return ''
  return `<span class="${GRADE_BADGE_CLASS[top]} mr-1">${top}</span>
          <span class="text-stone-500 text-xs">+${Object.keys(dist).length - 1} more</span>`
}

export function sortCoins(coins: CoinSummary[], sortBy: SortField, dir: 'asc' | 'desc'): CoinSummary[] {
  return [...coins].sort((a, b) => {
    let cmp = 0
    switch (sortBy) {
      case 'last_sale_date':   cmp = a.last_sale_date.localeCompare(b.last_sale_date); break
      case 'median_price_usd': cmp = a.median_price_usd - b.median_price_usd;          break
      case 'sale_count':       cmp = a.sale_count - b.sale_count;                      break
      case 'ruler':            cmp = (a.ruler ?? '').localeCompare(b.ruler ?? '');     break
      case 'denomination':     cmp = a.denomination.localeCompare(b.denomination);     break
    }
    return dir === 'asc' ? cmp : -cmp
  })
}

function col(label: string, field: SortField, currentSort: SortField, dir: 'asc' | 'desc'): string {
  const active = field === currentSort
  const arrow  = active ? (dir === 'asc' ? ' ↑' : ' ↓') : ''
  return `<th class="table-header" data-sort="${field}">${label}${arrow}</th>`
}

export function renderCoinTable(
  coins: CoinSummary[],
  filters: FilterState,
  onSort: (field: SortField) => void,
  onPageChange: (page: number) => void,
  onRowClick: (slug: string) => void
): string {
  const start  = (filters.page - 1) * PAGE_SIZE
  const paged  = coins.slice(start, start + PAGE_SIZE)
  const total  = coins.length
  const pages  = Math.ceil(total / PAGE_SIZE)

  if (total === 0) {
    return `
      <div class="card p-12 text-center text-stone-500">
        <div class="text-4xl mb-3">🏛️</div>
        <div class="text-lg mb-1">No coins found</div>
        <div class="text-sm">Try adjusting your filters or search query</div>
      </div>
    `
  }

  const rows = paged.map(coin => {
    const price  = coin.median_price_usd
      ? `$${coin.median_price_usd.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
      : '—'
    const range  = coin.price_range_usd
      ? `$${coin.price_range_usd.min.toLocaleString()} – $${coin.price_range_usd.max.toLocaleString()}`
      : '—'
    const forSaleNote = (coin.fixed_price_count ?? 0) > 0
      ? `<div class="text-xs text-sky-500 mt-0.5">${coin.fixed_price_count} for sale</div>`
      : ''
    const isCustomThumb = coin.denomination === 'AR Tetradrachm'
    const thumbSrc = isCustomThumb ? '/coin-grade/ar-tetradrachm.jpg' : coin.thumbnail_url
    const thumbClass = isCustomThumb
      ? 'w-10 h-10 object-contain rounded-full border border-stone-700 bg-stone-900 p-0.5'
      : 'w-10 h-10 object-cover rounded border border-stone-700'
    const thumb  = isCustomThumb
      ? `<div style="background-image:url('${thumbSrc}');background-size:95%;background-position:center;background-repeat:no-repeat;" class="w-10 h-10 rounded-full border border-stone-700 bg-stone-900"></div>`
      : thumbSrc
        ? `<img src="${thumbSrc}" alt="" class="${thumbClass}" loading="lazy" />`
        : `<div class="w-10 h-10 rounded border border-stone-800 bg-stone-900 flex items-center justify-center text-stone-700 text-lg">🪙</div>`
    const verified = coin.ngc_verified_count > 0
      ? `<span title="NGC cert verified" class="text-emerald-400 text-xs">✓</span>`
      : ''

    const topGrade = NGC_GRADE_ORDER.find(g => coin.grade_distribution[g])

    // White line: "AV Aureus | Commodus (AD 177–192)"
    const rulerPart = coin.ruler
      ? ` | ${coin.ruler}${coin.ruler_dates ? ` (${coin.ruler_dates})` : ''}`
      : ''
    const rarityBadge = coin.ruler_rarity === 'scarce'
      ? `<span class="ml-1.5 px-1 py-0.5 rounded text-[10px] border bg-amber-900/40 text-amber-300 border-amber-700 align-middle">Scarce</span>`
      : coin.ruler_rarity === 'common'
        ? `<span class="ml-1.5 px-1 py-0.5 rounded text-[10px] border bg-stone-800 text-stone-500 border-stone-600 align-middle">High Mintage</span>`
        : ''

    // Grey line: "NGC AU 5/5-2/5 (7.13g)" or simpler fallbacks
    const scoreStr = (coin.top_strike_score != null && coin.top_surface_score != null)
      ? ` ${coin.top_strike_score}/5-${coin.top_surface_score}/5`
      : ''
    const weightStr = coin.median_weight_g != null
      ? ` (${coin.median_weight_g.toFixed(2)}g)`
      : ''
    const gradeSubtitle = topGrade
      ? `NGC ${topGrade}${scoreStr}${weightStr}`
      : coin.category

    return `
      <tr class="table-row cursor-pointer" data-slug="${coin.slug}">
        <td class="table-cell w-12">${thumb}</td>
        <td class="table-cell">
          <div class="font-medium text-stone-100">${coin.denomination}${rulerPart}${rarityBadge}</div>
          <div class="text-xs text-stone-500">${gradeSubtitle}</div>
        </td>
        <td class="table-cell text-stone-300">${coin.ruler ?? '—'}</td>
        <td class="table-cell capitalize text-stone-400">${coin.metal}</td>
        <td class="table-cell">${gradeBar(coin.grade_distribution)}</td>
        <td class="table-cell">
          <div class="text-gold-300 font-mono">${price}</div>
          <div class="text-xs text-stone-600">${range}</div>
          ${forSaleNote}
        </td>
        <td class="table-cell text-stone-400 text-xs">${coin.last_sale_date}</td>
        <td class="table-cell text-stone-400 text-center">${coin.sale_count}</td>
        <td class="table-cell">${verified}</td>
      </tr>
    `
  }).join('')

  // Pagination
  const prevBtn = filters.page > 1
    ? `<button class="btn-ghost text-xs px-3 py-1" data-page="${filters.page - 1}">← Prev</button>`
    : `<button class="btn-ghost text-xs px-3 py-1 opacity-30 cursor-not-allowed" disabled>← Prev</button>`
  const nextBtn = filters.page < pages
    ? `<button class="btn-ghost text-xs px-3 py-1" data-page="${filters.page + 1}">Next →</button>`
    : `<button class="btn-ghost text-xs px-3 py-1 opacity-30 cursor-not-allowed" disabled>Next →</button>`

  // Attach listeners after render
  setTimeout(() => {
    const table = document.getElementById('coin-table')
    if (!table) return

    table.querySelectorAll<HTMLElement>('[data-sort]').forEach(el => {
      el.addEventListener('click', () => onSort(el.dataset['sort'] as SortField))
    })
    table.querySelectorAll<HTMLElement>('[data-slug]').forEach(el => {
      el.addEventListener('click', () => onRowClick(el.dataset['slug']!))
    })
    table.querySelectorAll<HTMLElement>('[data-page]').forEach(el => {
      el.addEventListener('click', () => onPageChange(parseInt(el.dataset['page']!)))
    })
  }, 0)

  return `
    <div id="coin-table" class="card overflow-hidden">
      <div class="px-4 py-3 border-b border-stone-800 flex items-center justify-between">
        <span class="text-sm text-stone-400">
          <span class="text-gold-400 font-mono">${total.toLocaleString()}</span> coin types found
        </span>
        <span class="text-xs text-stone-600">
          Page ${filters.page} of ${pages}
        </span>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="bg-stone-900/50">
              <th class="table-header w-12"></th>
              ${col('Coin', 'denomination', filters.sortBy, filters.sortDir)}
              ${col('Ruler', 'ruler', filters.sortBy, filters.sortDir)}
              <th class="table-header">Metal</th>
              <th class="table-header">Top Grades</th>
              ${col('Median Hammer', 'median_price_usd', filters.sortBy, filters.sortDir)}
              ${col('Last Sale', 'last_sale_date', filters.sortBy, filters.sortDir)}
              ${col('Sales', 'sale_count', filters.sortBy, filters.sortDir)}
              <th class="table-header" title="NGC cert verified">✓</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>

      <div class="px-4 py-3 border-t border-stone-800 flex items-center justify-between">
        <div class="flex gap-2">${prevBtn}${nextBtn}</div>
        <span class="text-xs text-stone-600">
          Showing ${start + 1}–${Math.min(start + PAGE_SIZE, total)} of ${total.toLocaleString()}
        </span>
      </div>
    </div>
  `
}
