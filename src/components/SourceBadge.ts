// ============================================================
// Source attribution badge
// ============================================================
import type { Source } from '../types/coin.ts'

const SOURCE_STYLES: Record<Source, string> = {
  cng:      'bg-amber-900/60  text-amber-300  border-amber-700',
  heritage: 'bg-blue-900/60  text-blue-300   border-blue-700',
  ebay:     'bg-yellow-900/60 text-yellow-300 border-yellow-700',
  vcoins:   'bg-green-900/60  text-green-300  border-green-700',
  mashops:  'bg-purple-900/60 text-purple-300 border-purple-700',
}

const SOURCE_LABELS: Record<Source, string> = {
  cng:      'CNG',
  heritage: 'Heritage',
  ebay:     'eBay',
  vcoins:   'VCoins',
  mashops:  'MA Shops',
}

export function renderSourceBadge(source: Source): string {
  const style = SOURCE_STYLES[source] ?? 'bg-stone-800 text-stone-300 border-stone-600'
  const label = SOURCE_LABELS[source] ?? source
  return `<span class="source-badge ${style}">${label}</span>`
}
