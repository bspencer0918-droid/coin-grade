// ============================================================
// History civilization page — periods and dynasty/group cards
// ============================================================
import type { HistoryCivilization } from '../types/history.ts'
import { href } from '../router.ts'

export function renderHistoryCivPage(civ: HistoryCivilization): string {
  // Build a map from period_id to groups
  const groupsByPeriod = new Map<string, typeof civ.groups>()
  for (const group of civ.groups) {
    const list = groupsByPeriod.get(group.period_id) ?? []
    list.push(group)
    groupsByPeriod.set(group.period_id, list)
  }

  const periodsHTML = civ.periods.map(period => {
    const groups = groupsByPeriod.get(period.id) ?? []
    const groupCards = groups.map(group => {
      const rulerCount = group.rulers.length
      const rulerLabel = rulerCount === 1 ? '1 ruler' : `${rulerCount} rulers`
      const overviewExcerpt = group.overview.length > 140
        ? group.overview.slice(0, 140).trimEnd() + '…'
        : group.overview
      return `
        <a href="${href({ name: 'history-group', civ: civ.id, group: group.id })}"
           class="card p-5 flex flex-col gap-2 hover:border-gold-700/50 transition-colors group cursor-pointer no-underline">
          <div class="flex items-start justify-between gap-2">
            <h3 class="font-display text-lg text-gold-400 group-hover:text-gold-300 transition-colors leading-snug">
              ${group.name}
            </h3>
            <span class="text-xs text-stone-600 shrink-0 mt-0.5">${rulerLabel}</span>
          </div>
          <p class="text-stone-500 text-xs">${group.dates}</p>
          <p class="text-stone-400 text-sm leading-relaxed">${overviewExcerpt}</p>
        </a>
      `
    }).join('')

    return `
      <section class="space-y-4">
        <!-- Period header -->
        <div class="flex items-baseline gap-4 flex-wrap">
          <h2 class="font-display text-2xl text-stone-200">${period.name}</h2>
          <span class="text-stone-500 text-sm">${period.dates}</span>
        </div>
        <p class="text-stone-400 text-sm leading-relaxed max-w-3xl">${period.overview}</p>
        <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-4">
          ${groupCards}
        </div>
      </section>
    `
  }).join(`
    <div class="divider"><span class="divider-text">&#8213;</span></div>
  `)

  return `
    <main class="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-8">

      <!-- Breadcrumb -->
      <nav class="text-sm text-stone-500 flex items-center gap-2">
        <a href="${href({ name: 'history' })}" class="hover:text-gold-400 transition-colors">History</a>
        <span>›</span>
        <span class="text-stone-300">${civ.name}</span>
      </nav>

      <!-- Hero -->
      <section>
        <h1 class="font-display text-4xl text-gold-400 mb-1">${civ.name}</h1>
        <p class="text-stone-500 text-sm mb-4">${civ.dates}</p>
        <p class="text-stone-400 text-lg leading-relaxed max-w-3xl">${civ.overview}</p>
      </section>

      <div class="divider"><span class="divider-text">Periods &amp; Dynasties</span></div>

      <!-- Periods and groups -->
      <div class="space-y-12">
        ${periodsHTML}
      </div>

    </main>
  `
}

export function renderHistoryCivPageLoading(): string {
  return `
    <main class="max-w-7xl mx-auto px-4 sm:px-6 py-8">
      <div class="animate-pulse space-y-6">
        <div class="h-4 bg-stone-800 rounded w-48"></div>
        <div class="h-10 bg-stone-800 rounded w-64"></div>
        <div class="h-4 bg-stone-800 rounded w-96"></div>
        <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          ${Array(6).fill('<div class="h-32 bg-stone-800 rounded-lg"></div>').join('')}
        </div>
      </div>
    </main>
  `
}
