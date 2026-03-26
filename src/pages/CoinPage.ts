// ============================================================
// Individual coin detail page
// ============================================================
import type { CoinDetail, CoinSummary, GradePriceData, ListingType, Sale, NGCGrade } from '../types/coin.ts'
import { NGC_GRADE_ORDER } from '../types/coin.ts'
import { renderSourceBadge } from '../components/SourceBadge.ts'
import { renderGradeBreakdown } from '../components/GradeBreakdown.ts'
import { renderPriceChartContainer, mountPriceChart } from '../components/PriceChart.ts'
import { href } from '../router.ts'
import type { WildwindsEntry } from '../data/loader.ts'

const GRADE_BADGE: Record<NGCGrade, string> = {
  MS:'badge-ms', AU:'badge-au', XF:'badge-xf', VF:'badge-vf',
  F:'badge-f', VG:'badge-vg', G:'badge-g', AG:'badge-ag', P:'badge-g',
}

// ---------------------------------------------------------------------------
// Grade-by-price helpers
// ---------------------------------------------------------------------------

function computeGradePrices(sales: Sale[]): Partial<Record<NGCGrade, GradePriceData>> {
  const groups: Partial<Record<NGCGrade, number[]>> = {}
  for (const sale of sales) {
    if (sale.listing_type !== 'auction_realized') continue
    if (!sale.ngc.grade) continue
    if (!groups[sale.ngc.grade]) groups[sale.ngc.grade] = []
    groups[sale.ngc.grade]!.push(sale.hammer_price_usd)
  }
  const result: Partial<Record<NGCGrade, GradePriceData>> = {}
  for (const [grade, prices] of Object.entries(groups) as [NGCGrade, number[]][]) {
    if (prices.length < 3) continue   // too few sales for meaningful stats
    const sorted = [...prices].sort((a, b) => a - b)
    const mid    = Math.floor(sorted.length / 2)
    const median = sorted.length % 2 === 0
      ? (sorted[mid - 1] + sorted[mid]) / 2
      : sorted[mid]
    result[grade] = { median, min: sorted[0], max: sorted[sorted.length - 1], count: prices.length }
  }
  return result
}

function renderGradeByPrice(gradePrices: Partial<Record<NGCGrade, GradePriceData>>): string {
  const grades = NGC_GRADE_ORDER.filter(g => gradePrices[g])
  if (grades.length === 0) return ''

  const maxMedian = Math.max(...grades.map(g => gradePrices[g]!.median))

  const rows = grades.map(grade => {
    const d      = gradePrices[grade]!
    const pct    = maxMedian > 0 ? Math.round((d.median / maxMedian) * 100) : 0
    const badge  = GRADE_BADGE[grade] ?? 'badge-grade bg-stone-800 text-stone-300'
    return `
      <tr class="border-b border-stone-900 last:border-0 hover:bg-stone-900/30 transition-colors">
        <td class="py-2.5 pr-4 w-14">
          <span class="${badge} text-xs px-2 py-0.5 rounded font-mono">${grade}</span>
        </td>
        <td class="py-2.5 pr-6 text-stone-500 font-mono text-xs text-right whitespace-nowrap">
          ${d.count.toLocaleString()} sale${d.count !== 1 ? 's' : ''}
        </td>
        <td class="py-2.5 pr-4 min-w-[8rem]">
          <div class="flex items-center gap-2">
            <div class="flex-1 bg-stone-900 rounded-full h-1.5 min-w-[60px]">
              <div class="h-1.5 rounded-full bg-gold-500 opacity-70" style="width:${pct}%"></div>
            </div>
          </div>
        </td>
        <td class="py-2.5 pr-6 text-gold-400 font-mono font-semibold text-sm text-right whitespace-nowrap">
          ${formatUSD(d.median)}
        </td>
        <td class="py-2.5 text-stone-500 font-mono text-xs text-right whitespace-nowrap hidden sm:table-cell">
          ${formatUSD(d.min)} – ${formatUSD(d.max)}
        </td>
      </tr>
    `
  }).join('')

  return `
    <section class="card p-5">
      <div class="flex items-baseline gap-3 mb-1">
        <div class="card-header">Price by Grade</div>
        <div class="text-xs text-stone-600">auction realized · median of ${grades.reduce((n, g) => n + gradePrices[g]!.count, 0).toLocaleString()} sales</div>
      </div>
      <div class="overflow-x-auto mt-4">
        <table class="w-full">
          <thead>
            <tr class="border-b border-stone-800">
              <th class="text-left pb-2 text-stone-600 font-display text-xs uppercase tracking-wider">Grade</th>
              <th class="text-right pb-2 text-stone-600 font-display text-xs uppercase tracking-wider pr-6">Count</th>
              <th class="pb-2"></th>
              <th class="text-right pb-2 text-stone-600 font-display text-xs uppercase tracking-wider pr-6">Median</th>
              <th class="text-right pb-2 text-stone-600 font-display text-xs uppercase tracking-wider hidden sm:table-cell">Range</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </section>
  `
}

function formatUSD(n: number): string {
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0 })
}

const LISTING_TYPE_CONFIG: Record<ListingType, { label: string; priceLabel: string; cls: string }> = {
  auction_realized: { label: 'Sold',    priceLabel: 'Hammer',  cls: 'bg-emerald-900/40 text-emerald-300 border-emerald-700' },
  fixed_price:      { label: 'For Sale', priceLabel: 'Asking',  cls: 'bg-sky-900/40     text-sky-300     border-sky-700'     },
  auction_estimate: { label: 'Estimate', priceLabel: 'Est.',    cls: 'bg-stone-800      text-stone-400   border-stone-600'   },
}

function saleRow(sale: Sale): string {
  const ngc = sale.ngc
  const lt  = LISTING_TYPE_CONFIG[sale.listing_type ?? 'auction_realized']

  // Grade badge
  const gradeBadge = ngc.grade
    ? `<span class="${GRADE_BADGE[ngc.grade] ?? 'badge-grade bg-stone-800 text-stone-300'}">${ngc.grade}${ngc.grade_numeric ? ` ${ngc.grade_numeric}` : ''}</span>`
    : '—'

  // Strike / surface scores
  const scores = (ngc.strike_score != null && ngc.surface_score != null)
    ? `<div class="text-xs text-stone-500 mt-0.5 font-mono">
         Strike ${ngc.strike_score}/5 &middot; Surface ${ngc.surface_score}/5
       </div>`
    : ''

  // Issue badge (details grade — blemish warning)
  const issueBadge = ngc.details_grade
    ? `<div class="mt-1">
         <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border
                      bg-amber-900/40 text-amber-300 border-amber-700 text-xs">
           ⚠ ${ngc.details_grade}
         </span>
       </div>`
    : ''

  // Fine Style badge (positive designation — exceptional artistry)
  const fineStyleBadge = ngc.fine_style
    ? `<div class="mt-1">
         <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border
                      bg-teal-900/40 text-teal-300 border-teal-700 text-xs">
           ★ Fine Style
         </span>
       </div>`
    : ''

  const gradeCell = `<div>${gradeBadge}${scores}${issueBadge}${fineStyleBadge}</div>`

  const certLink = ngc.certification_url
    ? `<a href="${ngc.certification_url}" target="_blank" rel="noopener noreferrer"
          class="text-gold-500 hover:text-gold-300 font-mono text-xs">${ngc.cert_number}</a>`
    : ngc.cert_number
      ? `<span class="font-mono text-xs text-stone-400">${ngc.cert_number}</span>`
      : '—'
  const verified = ngc.verified
    ? `<span title="NGC cert verified" class="text-emerald-400 text-xs ml-1">✓</span>`
    : ''
  const img = sale.image_url
    ? `<img src="${sale.image_url}" alt="" class="w-12 h-12 object-cover rounded border border-stone-700" loading="lazy" />`
    : `<div class="w-12 h-12 rounded border border-stone-800 bg-stone-900"></div>`

  const priceColor = sale.listing_type === 'fixed_price'      ? 'text-sky-300'
                   : sale.listing_type === 'auction_estimate'  ? 'text-stone-400'
                   : 'text-gold-300'

  const rowGlow = ngc.grade === 'MS' ? 'grade-row-ms'
                : ngc.grade === 'AU' ? 'grade-row-au'
                : ngc.grade === 'VF' ? 'grade-row-vf'
                : ''

  return `
    <tr class="table-row ${rowGlow}">
      <td class="table-cell w-14">${img}</td>
      <td class="table-cell">
        <a href="${sale.lot_url}" target="_blank" rel="noopener noreferrer"
           class="text-stone-200 hover:text-gold-300 transition-colors text-sm line-clamp-2">
          ${sale.title}
        </a>
      </td>
      <td class="table-cell">${gradeCell}</td>
      <td class="table-cell">
        <div class="${priceColor} font-mono">${formatUSD(sale.hammer_price_usd)}</div>
        <div class="text-xs mt-0.5">
          <span class="px-1.5 py-0.5 rounded border text-xs ${lt.cls}">${lt.label}</span>
        </div>
      </td>
      <td class="table-cell text-stone-400 text-sm">${sale.sale_date}</td>
      <td class="table-cell">${renderSourceBadge(sale.source)}</td>
      <td class="table-cell">${certLink}${verified}</td>
    </tr>
  `
}

function renderRelatedTypes(coin: CoinDetail, allCoins: CoinSummary[]): string {
  // Find sibling types: coins whose slug is a variant of the same parent
  // e.g. for "greek-athens-ar-tetradrachm-classical-owl", parent is "greek-athens-ar-tetradrachm"
  const slug = coin.slug
  // Check if this slug has a type suffix (contains a known type separator pattern)
  // We find siblings by looking for coins with the same prefix but different suffix
  const parts = slug.split('-')

  // Find the base parent slug (the longest prefix that matches other siblings)
  // Strategy: look for other coins that share a long common prefix
  const siblings = allCoins.filter(c => {
    if (c.slug === slug) return false
    // Same ruler + denomination root = same parent group
    // We check if one slug is a prefix of the other, or they share a common base
    const minLen = Math.min(slug.length, c.slug.length)
    // Find longest common prefix
    let prefixLen = 0
    for (let i = 0; i < minLen; i++) {
      if (slug[i] === c.slug[i]) prefixLen++
      else break
    }
    // Require sharing at least 25 chars and that the common prefix ends at a word boundary
    if (prefixLen < 25) return false
    const commonPrefix = slug.slice(0, prefixLen)
    // Make sure it ends at a dash (word boundary), not mid-word
    if (!commonPrefix.endsWith('-') && slug[prefixLen] !== '-' && c.slug[prefixLen] !== '-') return false
    return true
  })

  if (siblings.length === 0) return ''

  const items = siblings.map(c => {
    const price = c.median_price_usd
      ? `$${c.median_price_usd.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
      : '—'
    const isCurrent = c.slug === slug
    return `
      <a href="${href({ name: 'coin', slug: c.slug })}"
         class="flex items-center justify-between gap-3 p-2.5 rounded-lg
                ${isCurrent ? 'bg-stone-800 ring-1 ring-gold-700' : 'hover:bg-stone-800/60'} transition-colors">
        <div class="text-sm ${isCurrent ? 'text-gold-300' : 'text-stone-300'} leading-tight">
          ${c.denomination}
        </div>
        <div class="text-xs font-mono text-stone-500 shrink-0">
          ${price} · ${c.sale_count} sale${c.sale_count !== 1 ? 's' : ''}
        </div>
      </a>
    `
  })

  return `
    <section class="card p-5">
      <div class="card-header mb-3">Related Types</div>
      <div class="space-y-1">
        ${items.join('')}
      </div>
    </section>
  `
}

function renderWildwindsRef(entries: WildwindsEntry[], slug: string): string {
  if (entries.length === 0) return ''
  const shown = entries.slice(0, 15)
  const ruler = slug.split('-').slice(1, -2).join('-')  // e.g. 'hadrian'
  const wwUrl = `https://www.wildwinds.com/coins/ric/${ruler.replace('-', '_')}/t.html`

  const rows = shown.map(e => {
    const refs = [
      ...e.ric.map(n  => `<span class="font-mono text-xs text-stone-500 border border-stone-800 px-1.5 py-0.5 rounded bg-stone-900/60">RIC ${n}</span>`),
      ...e.sear.map(n => `<span class="font-mono text-xs text-stone-500 border border-stone-800 px-1.5 py-0.5 rounded bg-stone-900/60">Sear ${n}</span>`),
    ].join('')
    return `
      <div class="py-2.5 border-b border-stone-900/70 last:border-0">
        <div class="text-xs text-stone-400 leading-relaxed mb-1">${e.desc}</div>
        <div class="flex flex-wrap gap-1">${refs}</div>
      </div>
    `
  }).join('')

  const more = entries.length > 15
    ? `<div class="mt-3 text-xs text-stone-600">
         Showing 15 of ${entries.length} known varieties.
         <a href="${wwUrl}" target="_blank" rel="noopener noreferrer"
            class="text-gold-600 hover:text-gold-400 ml-1">Browse all on Wildwinds →</a>
       </div>`
    : `<div class="mt-3 text-xs text-stone-600">
         <a href="${wwUrl}" target="_blank" rel="noopener noreferrer"
            class="text-gold-600 hover:text-gold-400">View on Wildwinds →</a>
       </div>`

  return `
    <section class="card p-5">
      <div class="flex items-baseline gap-3 mb-1">
        <div class="card-header">RIC Type Reference</div>
        <div class="text-xs text-stone-600">${entries.length} known varieties · via Wildwinds.com</div>
      </div>
      <div class="mt-3">${rows}</div>
      ${more}
    </section>
  `
}

export function renderCoinPage(coin: CoinDetail, allCoins: CoinSummary[] = [], wildwinds: WildwindsEntry[] = []): string {
  const medianPrice = coin.median_price_usd ? formatUSD(coin.median_price_usd) : '—'
  const minPrice    = coin.price_range_usd ? formatUSD(coin.price_range_usd.min) : '—'
  const maxPrice    = coin.price_range_usd ? formatUSD(coin.price_range_usd.max) : '—'

  const metalBadge = `<span class="px-2 py-0.5 rounded text-xs border capitalize
    ${coin.metal === 'gold'   ? 'bg-yellow-900/40 text-yellow-300 border-yellow-700' :
      coin.metal === 'silver' ? 'bg-slate-800     text-slate-300  border-slate-600'  :
                                'bg-amber-900/40  text-amber-400  border-amber-800'}">
    ${coin.metal}
  </span>`

  // Grade-by-price stats (computed from auction realized sales)
  const gradePrices      = computeGradePrices(coin.sales)
  const gradePriceHTML   = renderGradeByPrice(gradePrices)
  const relatedTypesHTML = renderRelatedTypes(coin, allCoins)
  const wildwindsHTML    = renderWildwindsRef(wildwinds, coin.slug)

  // Sort sales by date desc
  const sortedSales = [...coin.sales].sort((a, b) => b.sale_date.localeCompare(a.sale_date))
  const saleRows    = sortedSales.map(saleRow).join('')

  // Attach chart after render
  setTimeout(() => mountPriceChart(coin.sales), 0)

  return `
    <main class="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-6">

      <!-- Breadcrumb -->
      <nav class="text-sm text-stone-500 flex items-center gap-2">
        <a href="${href({ name: 'home' })}"   class="hover:text-gold-400 transition-colors">Home</a>
        <span>›</span>
        <a href="${href({ name: 'browse' })}" class="hover:text-gold-400 transition-colors">Browse</a>
        <span>›</span>
        <span class="text-stone-300">${coin.denomination}</span>
      </nav>

      <!-- Header -->
      <section class="flex gap-6 flex-wrap">
        ${coin.denomination === 'AR Tetradrachm'
          ? `<div style="background-image:url('/coin-grade/ar-tetradrachm.jpg');background-size:95%;background-position:center;background-repeat:no-repeat;"
                  class="w-32 h-32 rounded-full border border-stone-700 shadow-lg bg-stone-900 flex-shrink-0"></div>`
          : coin.thumbnail_url
            ? `<img src="${coin.thumbnail_url}" alt="${coin.denomination}"
                    class="w-32 h-32 object-cover rounded-xl border border-stone-700 shadow-lg" />`
            : `<div class="w-32 h-32 rounded-xl border border-stone-800 bg-stone-900 flex items-center justify-center text-5xl">🪙</div>`
        }
        <div class="flex-1 min-w-0">
          <div class="flex flex-wrap items-center gap-2 mb-1">
            <span class="text-xs uppercase tracking-widest text-gold-600 font-display capitalize">
              ${coin.category}${coin.dynasty ? ` · ${coin.dynasty}` : ''}
            </span>
            ${metalBadge}
          </div>
          <h1 class="font-display text-3xl text-stone-100 mb-1">${coin.denomination}</h1>
          ${coin.ruler
            ? `<div class="text-xl text-stone-400 flex items-center gap-2 flex-wrap">
                 ${coin.ruler}${coin.ruler_dates ? ` <span class="text-sm text-stone-600">(${coin.ruler_dates})</span>` : ''}
                 ${coin.ruler_rarity === 'scarce'
                   ? `<span class="px-2 py-0.5 rounded text-xs border bg-amber-900/40 text-amber-300 border-amber-700">Scarce Reign</span>`
                   : coin.ruler_rarity === 'common'
                     ? `<span class="px-2 py-0.5 rounded text-xs border bg-stone-800 text-stone-500 border-stone-600">High Mintage</span>`
                     : ''}
               </div>`
            : ''}

          <div class="flex flex-wrap gap-6 mt-4">
            <div>
              <div class="text-xs text-stone-600 uppercase tracking-wider font-display">Median Hammer</div>
              <div class="text-2xl text-gold-400 font-mono">${medianPrice}</div>
              <div class="text-xs text-stone-600 mt-0.5">${coin.realized_count} auction sale${coin.realized_count !== 1 ? 's' : ''}</div>
            </div>
            <div>
              <div class="text-xs text-stone-600 uppercase tracking-wider font-display">Hammer Range</div>
              <div class="text-lg text-stone-300 font-mono">${minPrice} – ${maxPrice}</div>
            </div>
            ${coin.fixed_price_count > 0 ? `
            <div>
              <div class="text-xs text-stone-600 uppercase tracking-wider font-display">For Sale</div>
              <div class="text-2xl text-sky-400 font-mono">${coin.fixed_price_count}</div>
              <div class="text-xs text-stone-600 mt-0.5">dealer listing${coin.fixed_price_count !== 1 ? 's' : ''}</div>
            </div>` : ''}
            <div>
              <div class="text-xs text-stone-600 uppercase tracking-wider font-display">Last Sale</div>
              <div class="text-stone-300">${coin.last_sale_date}</div>
            </div>
          </div>
        </div>
      </section>

      <!-- Collector notes (taxonomy knowledge for this specific type) -->
      ${coin.type_info?.notes ? `
        <section class="card p-5">
          <div class="flex items-start gap-4">
            <div class="text-2xl mt-0.5 shrink-0">📚</div>
            <div class="flex-1">
              <div class="flex flex-wrap items-center gap-2 mb-2">
                <div class="card-header">Collector Notes</div>
                ${coin.type_info.date_range ? `<span class="text-xs text-stone-500">${coin.type_info.date_range}</span>` : ''}
                ${coin.type_info.relative_value && coin.type_info.relative_value !== 1.0
                  ? `<span class="px-2 py-0.5 rounded text-xs border ${
                      coin.type_info.relative_value >= 3 ? 'bg-amber-900/40 text-amber-300 border-amber-700' :
                      coin.type_info.relative_value >= 1.5 ? 'bg-teal-900/40 text-teal-300 border-teal-700' :
                      'bg-stone-800 text-stone-400 border-stone-600'
                    }">${coin.type_info.relative_value}× relative value</span>`
                  : ''}
                ${coin.type_info.rarity && coin.type_info.rarity !== 'common' && coin.type_info.rarity !== 'very_common'
                  ? `<span class="px-2 py-0.5 rounded text-xs border bg-stone-800 text-stone-400 border-stone-600 capitalize">${coin.type_info.rarity.replace('_', ' ')}</span>`
                  : ''}
              </div>
              <p class="text-sm text-stone-400 leading-relaxed">${coin.type_info.notes}</p>
              ${(coin.type_info.sear?.length || coin.type_info.ric?.length) ? `
                <div class="mt-3 flex flex-wrap gap-2">
                  ${coin.type_info.sear?.length ? coin.type_info.sear.map(n =>
                    `<span class="px-2 py-0.5 rounded text-xs border bg-stone-900 text-stone-400 border-stone-700 font-mono">Sear ${n}</span>`
                  ).join('') : ''}
                  ${coin.type_info.ric?.length ? coin.type_info.ric.map(n =>
                    `<span class="px-2 py-0.5 rounded text-xs border bg-stone-900 text-stone-400 border-stone-700 font-mono">RIC ${n}</span>`
                  ).join('') : ''}
                </div>` : ''}
            </div>
          </div>
        </section>
      ` : ''}

      <!-- Wildwinds RIC type reference -->
      ${wildwindsHTML}

      <!-- Related types (other varieties/periods of same coin family) -->
      ${relatedTypesHTML}

      <!-- Price by grade (KBB-style value guide) -->
      ${gradePriceHTML}

      <!-- Grade breakdown -->
      <section class="card p-5">
        <div class="card-header mb-4">NGC Grade Distribution</div>
        ${renderGradeBreakdown(coin.grade_distribution)}
      </section>

      <!-- Price chart -->
      ${renderPriceChartContainer()}

      <!-- Sales table -->
      <section class="card overflow-hidden">
        <div class="card-header">All Records (${coin.sale_count})</div>
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="bg-stone-900/50">
                <th class="table-header w-14"></th>
                <th class="table-header">Listing</th>
                <th class="table-header">Grade</th>
                <th class="table-header">Price / Type</th>
                <th class="table-header">Date</th>
                <th class="table-header">Source</th>
                <th class="table-header">NGC Cert</th>
              </tr>
            </thead>
            <tbody>${saleRows}</tbody>
          </table>
        </div>
      </section>

    </main>
  `
}

export function renderCoinPageLoading(): string {
  return `
    <main class="max-w-7xl mx-auto px-4 sm:px-6 py-8">
      <div class="animate-pulse space-y-6">
        <div class="h-4 bg-stone-800 rounded w-48"></div>
        <div class="flex gap-6">
          <div class="w-32 h-32 bg-stone-800 rounded-xl"></div>
          <div class="flex-1 space-y-3">
            <div class="h-8 bg-stone-800 rounded w-64"></div>
            <div class="h-5 bg-stone-800 rounded w-40"></div>
            <div class="h-10 bg-stone-800 rounded w-48 mt-4"></div>
          </div>
        </div>
        <div class="h-40 bg-stone-800 rounded-lg"></div>
        <div class="h-64 bg-stone-800 rounded-lg"></div>
      </div>
    </main>
  `
}
