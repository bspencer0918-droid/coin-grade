// ============================================================
// Home / landing page
// ============================================================
import type { Meta, CatalogIndex } from '../types/coin.ts'
import { href } from '../router.ts'

const CATEGORY_ICONS: Record<string, string> = {
  us:        '🦅',
  roman:     '🏛️',
  greek:     '⚡',
  byzantine: '✝️',
  persian:   '👑',
  celtic:    '🌿',
  egyptian:  '𓂀',
  other:     '🪙',
}

export function renderHome(meta: Meta | null, catalog: CatalogIndex | null): string {
  const totalSales  = meta?.total_listings        ?? 0
  const ngcVerified = meta?.ngc_verified_count    ?? 0
  const lastUpdated = meta?.last_updated ? new Date(meta.last_updated).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short',
  }) : 'Loading…'

  // Category summary from catalog
  const catCounts = catalog?.coins.reduce<Record<string, number>>((acc, c) => {
    acc[c.category] = (acc[c.category] ?? 0) + 1
    return acc
  }, {}) ?? {}

  const categoryCards = Object.entries(catCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([cat, count]) => `
      <a href="${href({ name: 'browse' })}#cat-${cat}"
         class="card p-5 hover:border-gold-700/50 transition-colors group cursor-pointer block">
        <div class="text-3xl mb-2">${CATEGORY_ICONS[cat] ?? '🪙'}</div>
        <div class="font-display text-lg text-stone-100 group-hover:text-gold-300 transition-colors capitalize">
          ${cat}
        </div>
        <div class="text-sm text-stone-500 mt-1">${count.toLocaleString()} coin types</div>
      </a>
    `).join('')

  // Recent / highest-value coins
  const recentCoins = (catalog?.coins ?? [])
    .sort((a, b) => b.last_sale_date.localeCompare(a.last_sale_date))
    .slice(0, 6)
    .map(coin => {
      const price = coin.median_price_usd
        ? `$${coin.median_price_usd.toLocaleString('en-US', { minimumFractionDigits: 0 })}`
        : '—'
      const thumb = coin.thumbnail_url
        ? `<img src="${coin.thumbnail_url}" alt="" class="w-16 h-16 object-cover rounded-lg border border-stone-700" loading="lazy" />`
        : `<div class="w-16 h-16 rounded-lg border border-stone-800 bg-stone-900 flex items-center justify-center text-2xl">🪙</div>`
      return `
        <a href="${href({ name: 'coin', slug: coin.slug })}"
           class="card p-4 flex gap-4 hover:border-gold-700/50 transition-colors group cursor-pointer">
          ${thumb}
          <div class="min-w-0 flex-1">
            <div class="font-medium text-stone-100 group-hover:text-gold-300 transition-colors truncate">
              ${coin.denomination}
            </div>
            <div class="text-sm text-stone-500">${coin.ruler ?? coin.category}</div>
            <div class="text-gold-400 font-mono text-sm mt-1">${price}</div>
            <div class="text-xs text-stone-600 mt-0.5">Last: ${coin.last_sale_date}</div>
          </div>
        </a>
      `
    }).join('')

  // Source status indicators
  const sourceStatus = meta ? Object.entries(meta.sources).map(([src, info]) => {
    const dot = info.status === 'ok'
      ? 'bg-emerald-500' : info.status === 'blocked'
      ? 'bg-amber-500'   : 'bg-red-500'
    return `
      <div class="flex items-center gap-2 text-xs text-stone-400">
        <span class="w-1.5 h-1.5 rounded-full ${dot} inline-block"></span>
        <span class="capitalize">${src}</span>
        <span class="text-stone-600">${info.listings_scraped.toLocaleString()}</span>
      </div>
    `
  }).join('') : ''

  return `
    <main class="max-w-7xl mx-auto px-4 sm:px-6 py-10 space-y-12">

      <!-- Hero -->
      <section class="text-center py-8">
        <h1 class="font-display text-4xl sm:text-5xl text-gold-400 mb-3">
          Ancient Coin Price Intelligence
        </h1>
        <p class="text-stone-400 text-lg max-w-2xl mx-auto leading-relaxed">
          Realized auction prices for NGC-certified ancient coins, aggregated daily from
          CNG, Heritage Auctions, VCoins, MA Shops, NumisBids, Sixbid, Coin Archives, and more.
        </p>
        <div class="flex flex-wrap justify-center gap-3 mt-6">
          <a href="${href({ name: 'browse' })}" class="btn-primary text-base px-6 py-2.5">
            Browse Prices
          </a>
          <a href="${href({ name: 'about' })}" class="btn-ghost text-base px-6 py-2.5">
            How It Works
          </a>
        </div>
      </section>

      <!-- Stats bar -->
      <section class="grid grid-cols-3 gap-4">
        ${[
          { label: 'Total Sales', value: totalSales.toLocaleString() },
          { label: 'NGC Cert Verified', value: ngcVerified.toLocaleString() },
          { label: 'Coin Types', value: (catalog?.coins.length ?? 0).toLocaleString() },
        ].map(s => `
          <div class="card p-4 text-center">
            <div class="text-2xl font-mono text-gold-400">${s.value}</div>
            <div class="text-xs text-stone-500 uppercase tracking-wider mt-1 font-display">${s.label}</div>
          </div>
        `).join('')}
      </section>

      <!-- Categories -->
      <section>
        <div class="divider"><span class="divider-text">Browse by Civilization</span></div>
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 mt-6">
          ${categoryCards || '<div class="col-span-full text-center text-stone-600 py-8">Loading catalog…</div>'}
        </div>
      </section>

      <!-- Recent sales -->
      <section>
        <div class="divider"><span class="divider-text">Recently Sold</span></div>
        <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-6">
          ${recentCoins || '<div class="col-span-full text-center text-stone-600 py-8">Loading…</div>'}
        </div>
        <div class="text-center mt-6">
          <a href="${href({ name: 'browse' })}" class="btn-ghost">View all coins →</a>
        </div>
      </section>

      <!-- Data sources -->
      <section class="card p-5">
        <div class="card-header mb-4">Data Source Status</div>
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          ${sourceStatus || '<div class="col-span-full text-stone-600 text-sm">Loading…</div>'}
        </div>
        <div class="text-xs text-stone-600 mt-3">
          Updated: ${lastUpdated}
        </div>
      </section>

    </main>
  `
}
