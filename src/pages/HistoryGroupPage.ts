// ============================================================
// History group/dynasty page — ruler cards with portraits
// ============================================================
import type { HistoryCivilization, HistoryGroup } from '../types/history.ts'
import { href } from '../router.ts'

export function renderHistoryGroupPage(civ: HistoryCivilization, group: HistoryGroup): string {
  const rulerCards = group.rulers.map(ruler => {
    const portraitHTML = ruler.portrait_url
      ? `<img src="${ruler.portrait_url}" alt="${ruler.name}"
              class="w-full h-48 object-cover object-top rounded-t-lg"
              loading="lazy"
              onerror="this.style.display='none'; this.nextElementSibling.style.display='flex'" />
         <div class="w-full h-48 items-center justify-center text-5xl rounded-t-lg bg-stone-800/60 hidden">🏛️</div>`
      : `<div class="w-full h-48 flex items-center justify-center text-5xl rounded-t-lg bg-stone-800/60">🏛️</div>`

    const coinCount = ruler.coin_slugs.length
    const coinLabel = coinCount === 1 ? '1 coin type' : `${coinCount} coin types`

    return `
      <a href="${href({ name: 'history-ruler', civ: civ.id, group: group.id, ruler: ruler.id })}"
         class="card flex flex-col hover:border-gold-700/50 transition-colors group cursor-pointer no-underline overflow-hidden">
        ${portraitHTML}
        <div class="p-4 flex flex-col gap-2 flex-1">
          <div class="flex items-start justify-between gap-2">
            <h3 class="font-display text-lg text-gold-400 group-hover:text-gold-300 transition-colors leading-snug">
              ${ruler.name}
            </h3>
            <span class="text-xs text-stone-600 shrink-0 mt-0.5">${coinLabel}</span>
          </div>
          <p class="text-stone-500 text-xs">${ruler.dates}</p>
          <p class="text-stone-400 text-sm leading-relaxed line-clamp-3">${ruler.overview}</p>
        </div>
      </a>
    `
  }).join('')

  return `
    <main class="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-8">

      <!-- Breadcrumb -->
      <nav class="text-sm text-stone-500 flex items-center gap-2 flex-wrap">
        <a href="${href({ name: 'history' })}" class="hover:text-gold-400 transition-colors">History</a>
        <span>›</span>
        <a href="${href({ name: 'history-civ', civ: civ.id })}" class="hover:text-gold-400 transition-colors">${civ.name}</a>
        <span>›</span>
        <span class="text-stone-300">${group.name}</span>
      </nav>

      <!-- Dynasty overview -->
      <section>
        <h1 class="font-display text-4xl text-gold-400 mb-1">${group.name}</h1>
        <p class="text-stone-500 text-sm mb-4">${group.dates}</p>
        <p class="text-stone-400 text-lg leading-relaxed max-w-3xl">${group.overview}</p>
      </section>

      <div class="divider"><span class="divider-text">Rulers &amp; Leaders</span></div>

      <!-- Ruler grid -->
      <div class="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
        ${rulerCards}
      </div>

    </main>
  `
}

export function renderHistoryGroupPageLoading(): string {
  return `
    <main class="max-w-7xl mx-auto px-4 sm:px-6 py-8">
      <div class="animate-pulse space-y-6">
        <div class="h-4 bg-stone-800 rounded w-64"></div>
        <div class="h-10 bg-stone-800 rounded w-72"></div>
        <div class="h-4 bg-stone-800 rounded w-96"></div>
        <div class="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
          ${Array(8).fill('<div class="h-64 bg-stone-800 rounded-lg"></div>').join('')}
        </div>
      </div>
    </main>
  `
}
