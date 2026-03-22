// ============================================================
// NGC grade distribution bar
// ============================================================
import type { NGCGrade } from '../types/coin.ts'
import { NGC_GRADE_ORDER } from '../types/coin.ts'

const GRADE_COLORS: Record<NGCGrade, string> = {
  MS:  'bg-emerald-500',
  AU:  'bg-teal-500',
  XF:  'bg-blue-500',
  VF:  'bg-indigo-500',
  F:   'bg-violet-500',
  VG:  'bg-purple-500',
  G:   'bg-stone-500',
  AG:  'bg-stone-600',
  P:   'bg-stone-700',
}

export function renderGradeBreakdown(
  distribution: Partial<Record<NGCGrade, number>>,
  onGradeClick?: (grade: NGCGrade) => void
): string {
  const total = Object.values(distribution).reduce((a, b) => a + (b ?? 0), 0)
  if (total === 0) return '<div class="text-stone-600 text-xs italic">No grade data</div>'

  const segments = NGC_GRADE_ORDER
    .filter(g => distribution[g])
    .map(grade => {
      const count = distribution[grade] ?? 0
      const pct   = ((count / total) * 100).toFixed(1)
      const color = GRADE_COLORS[grade]
      const handler = onGradeClick ? `data-grade="${grade}" style="cursor:pointer"` : ''
      return `
        <div class="group relative flex-1 min-w-0" ${handler}>
          <div class="${color} h-4 rounded-sm transition-opacity group-hover:opacity-80"
               style="min-width:4px"
               title="${grade}: ${count} sale${count !== 1 ? 's' : ''} (${pct}%)">
          </div>
          <div class="absolute -top-6 left-1/2 -translate-x-1/2 text-xs text-stone-300
                      whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity
                      bg-stone-900 border border-stone-700 px-1.5 py-0.5 rounded pointer-events-none">
            ${grade}: ${count}
          </div>
        </div>
      `
    })

  const legend = NGC_GRADE_ORDER
    .filter(g => distribution[g])
    .map(grade => `
      <span class="flex items-center gap-1">
        <span class="inline-block w-2 h-2 rounded-sm ${GRADE_COLORS[grade]}"></span>
        <span class="text-stone-400">${grade}</span>
      </span>
    `).join('')

  return `
    <div>
      <div class="flex gap-0.5 items-stretch h-4 mt-6 mb-2">
        ${segments.join('')}
      </div>
      <div class="flex flex-wrap gap-x-3 gap-y-1 text-xs">
        ${legend}
      </div>
    </div>
  `
}
