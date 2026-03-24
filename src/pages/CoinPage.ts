// ============================================================
// Individual coin detail page
// ============================================================
import type { CoinDetail, Sale, NGCGrade } from '../types/coin.ts'
import { NGC_GRADE_ORDER } from '../types/coin.ts'
import { renderSourceBadge } from '../components/SourceBadge.ts'
import { renderGradeBreakdown } from '../components/GradeBreakdown.ts'
import { renderPriceChartContainer, mountPriceChart } from '../components/PriceChart.ts'
import { href } from '../router.ts'

const GRADE_BADGE: Record<NGCGrade, string> = {
  MS:'badge-ms', AU:'badge-au', XF:'badge-xf', VF:'badge-vf',
  F:'badge-f', VG:'badge-vg', G:'badge-g', AG:'badge-ag', P:'badge-g',
}

function formatUSD(n: number): string {
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0 })
}

function saleRow(sale: Sale): string {
  const ngc = sale.ngc
  const grade = ngc.grade
    ? `<span class="${GRADE_BADGE[ngc.grade] ?? 'badge-grade bg-stone-800 text-stone-300'}">${ngc.grade}${ngc.grade_numeric ? ` ${ngc.grade_numeric}` : ''}</span>`
    : '—'
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

  return `
    <tr class="table-row">
      <td class="table-cell w-14">${img}</td>
      <td class="table-cell">
        <a href="${sale.lot_url}" target="_blank" rel="noopener noreferrer"
           class="text-stone-200 hover:text-gold-300 transition-colors text-sm line-clamp-2">
          ${sale.title}
        </a>
      </td>
      <td class="table-cell">${grade}</td>
      <td class="table-cell text-gold-300 font-mono">${formatUSD(sale.hammer_price_usd)}</td>
      <td class="table-cell text-stone-400 text-sm">${sale.sale_date}</td>
      <td class="table-cell">${renderSourceBadge(sale.source)}</td>
      <td class="table-cell">${certLink}${verified}</td>
    </tr>
  `
}

export function renderCoinPage(coin: CoinDetail): string {
  const medianPrice = coin.median_price_usd ? formatUSD(coin.median_price_usd) : '—'
  const minPrice    = coin.price_range_usd ? formatUSD(coin.price_range_usd.min) : '—'
  const maxPrice    = coin.price_range_usd ? formatUSD(coin.price_range_usd.max) : '—'

  const metalBadge = `<span class="px-2 py-0.5 rounded text-xs border capitalize
    ${coin.metal === 'gold'   ? 'bg-yellow-900/40 text-yellow-300 border-yellow-700' :
      coin.metal === 'silver' ? 'bg-slate-800     text-slate-300  border-slate-600'  :
                                'bg-amber-900/40  text-amber-400  border-amber-800'}">
    ${coin.metal}
  </span>`

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
          ? `<img src="/coin-grade/ar-tetradrachm.jpg" alt="${coin.denomination}"
                  class="w-32 h-32 object-contain rounded-full border border-stone-700 shadow-lg bg-stone-900" />`
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
          ${coin.ruler ? `<div class="text-xl text-stone-400">${coin.ruler}</div>` : ''}

          <div class="flex flex-wrap gap-6 mt-4">
            <div>
              <div class="text-xs text-stone-600 uppercase tracking-wider font-display">Median Price</div>
              <div class="text-2xl text-gold-400 font-mono">${medianPrice}</div>
            </div>
            <div>
              <div class="text-xs text-stone-600 uppercase tracking-wider font-display">Range</div>
              <div class="text-lg text-stone-300 font-mono">${minPrice} – ${maxPrice}</div>
            </div>
            <div>
              <div class="text-xs text-stone-600 uppercase tracking-wider font-display">Total Sales</div>
              <div class="text-2xl text-stone-200 font-mono">${coin.sale_count}</div>
            </div>
            <div>
              <div class="text-xs text-stone-600 uppercase tracking-wider font-display">Last Sale</div>
              <div class="text-stone-300">${coin.last_sale_date}</div>
            </div>
          </div>
        </div>
      </section>

      <!-- Grade breakdown -->
      <section class="card p-5">
        <div class="card-header mb-4">NGC Grade Distribution</div>
        ${renderGradeBreakdown(coin.grade_distribution)}
      </section>

      <!-- Price chart -->
      ${renderPriceChartContainer()}

      <!-- Sales table -->
      <section class="card overflow-hidden">
        <div class="card-header">All Sales (${coin.sale_count})</div>
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="bg-stone-900/50">
                <th class="table-header w-14"></th>
                <th class="table-header">Listing</th>
                <th class="table-header">Grade</th>
                <th class="table-header">Price</th>
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
