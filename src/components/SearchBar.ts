// ============================================================
// Fuse.js powered search bar
// ============================================================
import Fuse from 'fuse.js'
import type { CoinSummary } from '../types/coin.ts'

let fuse: Fuse<CoinSummary> | null = null

export function initSearch(coins: CoinSummary[]) {
  fuse = new Fuse(coins, {
    keys: [
      { name: 'denomination', weight: 2   },
      { name: 'ruler',        weight: 1.5 },
      { name: 'dynasty',      weight: 1   },
      { name: 'slug',         weight: 0.8 },
      { name: 'category',     weight: 0.5 },
    ],
    threshold: 0.35,
    includeScore: true,
  })
}

export function searchCoins(query: string, coins: CoinSummary[]): CoinSummary[] {
  if (!query.trim()) return coins
  if (!fuse) initSearch(coins)
  return fuse!.search(query).map(r => r.item)
}

export function renderSearchBar(query: string, onSearch: (q: string) => void): string {
  const id = 'coin-search-input'
  // Attach listener after render via a small timeout trick
  setTimeout(() => {
    const el = document.getElementById(id) as HTMLInputElement | null
    if (!el) return
    let debounce: ReturnType<typeof setTimeout>
    el.addEventListener('input', () => {
      clearTimeout(debounce)
      debounce = setTimeout(() => onSearch(el.value), 250)
    })
    el.value = query
    el.focus()
  }, 0)

  return `
    <div class="relative">
      <span class="absolute left-3 top-1/2 -translate-y-1/2 text-stone-500 pointer-events-none">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
        </svg>
      </span>
      <input
        id="${id}"
        type="search"
        placeholder="Search coins, rulers, denominations…"
        class="w-full bg-stone-800 border border-stone-700 rounded-lg pl-9 pr-4 py-2
               text-sm text-stone-200 placeholder-stone-500 focus:outline-none
               focus:border-gold-600 focus:ring-1 focus:ring-gold-600/30"
        autocomplete="off"
        spellcheck="false"
      />
    </div>
  `
}
