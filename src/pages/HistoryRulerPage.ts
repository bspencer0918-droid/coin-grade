// ============================================================
// History ruler profile page — biography, coinage, coin cards
// ============================================================
import type { HistoryCivilization, HistoryGroup, HistoryRuler } from '../types/history.ts'
import type { CoinSummary } from '../types/coin.ts'
import { href } from '../router.ts'

function formatUSD(n: number): string {
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0 })
}

function renderCoinCard(coin: CoinSummary): string {
  const thumb = coin.thumbnail_url
    ? `<img src="${coin.thumbnail_url}" alt="${coin.denomination}"
            class="w-full h-28 object-cover"
            loading="lazy"
            onerror="this.style.display='none'; this.nextElementSibling.style.display='flex'" />
       <div class="w-full h-28 items-center justify-center text-3xl bg-stone-800/60 hidden">🪙</div>`
    : `<div class="w-full h-28 flex items-center justify-center text-3xl bg-stone-800/60">🪙</div>`

  const metalClass = coin.metal === 'gold'   ? 'bg-yellow-900/40 text-yellow-300 border-yellow-700'
                   : coin.metal === 'silver' ? 'bg-slate-800 text-slate-300 border-slate-600'
                   : 'bg-amber-900/40 text-amber-400 border-amber-800'

  return `
    <a href="${href({ name: 'coin', slug: coin.slug })}"
       class="card flex flex-col hover:border-gold-700/50 transition-colors group cursor-pointer no-underline overflow-hidden">
      ${thumb}
      <div class="p-3 flex flex-col gap-1 flex-1">
        <div class="flex items-center gap-1 flex-wrap">
          <span class="px-1.5 py-0.5 rounded text-xs border capitalize ${metalClass}">${coin.metal}</span>
        </div>
        <div class="font-display text-sm text-stone-200 group-hover:text-gold-300 transition-colors leading-snug">
          ${coin.denomination}
        </div>
        <div class="text-xs text-stone-500 mt-auto pt-1">
          <span class="text-gold-400 font-mono">${formatUSD(coin.median_price_usd)}</span>
          <span class="text-stone-600"> median · </span>
          <span>${coin.sale_count} sale${coin.sale_count !== 1 ? 's' : ''}</span>
        </div>
      </div>
    </a>
  `
}

export function renderHistoryRulerPage(
  civ: HistoryCivilization,
  group: HistoryGroup,
  ruler: HistoryRuler,
  catalog: CoinSummary[]
): string {
  // Filter catalog to only coins matching this ruler's slugs
  const slugSet = new Set(ruler.coin_slugs)
  const coins = catalog.filter(c => slugSet.has(c.slug))

  // Biography paragraphs
  const bioParagraphs = ruler.biography
    .split('\n\n')
    .filter(p => p.trim())
    .map(p => `<p class="text-stone-400 leading-relaxed">${p.trim()}</p>`)
    .join('')

  // Coinage paragraphs
  const coinageParagraphs = ruler.coinage
    .split('\n\n')
    .filter(p => p.trim())
    .map(p => `<p class="text-stone-400 leading-relaxed">${p.trim()}</p>`)
    .join('')

  const portraitHTML = ruler.portrait_url
    ? `<img src="${ruler.portrait_url}" alt="${ruler.name}"
            class="w-full max-h-80 object-cover object-top rounded-lg border border-stone-700"
            loading="lazy"
            onerror="this.style.display='none'; this.nextElementSibling.style.display='flex'" />
       <div class="w-full h-64 items-center justify-center text-8xl rounded-lg border border-stone-800 bg-stone-900 hidden">🏛️</div>`
    : `<div class="w-full h-64 flex items-center justify-center text-8xl rounded-lg border border-stone-800 bg-stone-900">🏛️</div>`

  const coinsSection = coins.length > 0 ? `
    <section class="space-y-4">
      <div class="divider"><span class="divider-text">🪙 Coins in Our Collection</span></div>
      <p class="text-stone-500 text-sm">${coins.length} coin type${coins.length !== 1 ? 's' : ''} linked to ${ruler.name}</p>
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
        ${coins.map(renderCoinCard).join('')}
      </div>
    </section>
  ` : ''

  return `
    <main class="max-w-5xl mx-auto px-4 sm:px-6 py-8 space-y-8">

      <!-- Breadcrumb -->
      <nav class="text-sm text-stone-500 flex items-center gap-2 flex-wrap">
        <a href="${href({ name: 'history' })}" class="hover:text-gold-400 transition-colors">History</a>
        <span>›</span>
        <a href="${href({ name: 'history-civ', civ: civ.id })}" class="hover:text-gold-400 transition-colors">${civ.name}</a>
        <span>›</span>
        <a href="${href({ name: 'history-group', civ: civ.id, group: group.id })}" class="hover:text-gold-400 transition-colors">${group.name}</a>
        <span>›</span>
        <span class="text-stone-300">${ruler.name}</span>
      </nav>

      <!-- Hero: portrait + info -->
      <section class="grid md:grid-cols-[280px_1fr] gap-8 items-start">
        <!-- Portrait -->
        <div class="w-full">
          ${portraitHTML}
        </div>

        <!-- Info -->
        <div class="space-y-4">
          <div>
            <p class="text-xs uppercase tracking-widest text-gold-600 font-display mb-1">${civ.name} · ${group.name}</p>
            <h1 class="font-display text-4xl text-gold-400 mb-1">${ruler.name}</h1>
            <p class="text-stone-500 text-sm">${ruler.dates}</p>
          </div>
          <p class="text-stone-300 text-lg leading-relaxed">${ruler.overview}</p>
          ${coins.length > 0 ? `
          <div>
            <a href="#coins-section" class="btn-ghost text-sm">
              🪙 ${coins.length} coin type${coins.length !== 1 ? 's' : ''} in our catalog ↓
            </a>
          </div>` : ''}
        </div>
      </section>

      <!-- Biography -->
      <section class="space-y-4">
        <div class="divider"><span class="divider-text">Biography</span></div>
        <div class="space-y-4">
          ${bioParagraphs}
        </div>
      </section>

      <!-- Coinage -->
      <section class="space-y-4">
        <div class="divider"><span class="divider-text">⚱️ Coinage</span></div>
        <div class="space-y-4">
          ${coinageParagraphs}
        </div>
      </section>

      <!-- Coins in catalog -->
      <div id="coins-section">
        ${coinsSection}
      </div>

      <!-- Back links -->
      <div class="flex gap-3 pt-4 flex-wrap">
        <a href="${href({ name: 'history-group', civ: civ.id, group: group.id })}" class="btn-ghost">
          ← Back to ${group.name}
        </a>
        <a href="${href({ name: 'browse' })}" class="btn-ghost">
          Browse All Coins
        </a>
      </div>

    </main>
  `
}

export function renderHistoryRulerPageLoading(): string {
  return `
    <main class="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      <div class="animate-pulse space-y-6">
        <div class="h-4 bg-stone-800 rounded w-72"></div>
        <div class="grid md:grid-cols-[280px_1fr] gap-8">
          <div class="h-64 bg-stone-800 rounded-lg"></div>
          <div class="space-y-4">
            <div class="h-8 bg-stone-800 rounded w-64"></div>
            <div class="h-4 bg-stone-800 rounded w-40"></div>
            <div class="h-20 bg-stone-800 rounded"></div>
          </div>
        </div>
        <div class="h-40 bg-stone-800 rounded-lg"></div>
        <div class="h-40 bg-stone-800 rounded-lg"></div>
      </div>
    </main>
  `
}
