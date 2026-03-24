// ============================================================
// Source attribution badge
// ============================================================
import type { Source } from '../types/coin.ts'

const SOURCE_STYLES: Record<Source, string> = {
  cng:          'bg-amber-900/60  text-amber-300  border-amber-700',
  heritage:     'bg-blue-900/60   text-blue-300   border-blue-700',
  vcoins:       'bg-green-900/60  text-green-300  border-green-700',
  mashops:      'bg-purple-900/60 text-purple-300 border-purple-700',
  numisbids:    'bg-cyan-900/60   text-cyan-300   border-cyan-700',
  sixbid:       'bg-indigo-900/60 text-indigo-300 border-indigo-700',
  hjb:          'bg-rose-900/60   text-rose-300   border-rose-700',
  coinarchives: 'bg-teal-900/60   text-teal-300   border-teal-700',
}

const SOURCE_LABELS: Record<Source, string> = {
  cng:          'CNG',
  heritage:     'Heritage',
  vcoins:       'VCoins',
  mashops:      'MA Shops',
  numisbids:    'NumisBids',
  sixbid:       'Sixbid',
  hjb:          'H.J. Berk',
  coinarchives: 'Coin Archives',
}

export function renderSourceBadge(source: Source): string {
  const style = SOURCE_STYLES[source] ?? 'bg-stone-800 text-stone-300 border-stone-600'
  const label = SOURCE_LABELS[source] ?? source
  return `<span class="source-badge ${style}">${label}</span>`
}
