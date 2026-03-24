// ============================================================
// Chart.js price history chart — one line per NGC grade
// ============================================================
import { Chart, LineController, LineElement, PointElement, LinearScale,
         Tooltip, Legend, CategoryScale } from 'chart.js'
import type { ListingType, Sale } from '../types/coin.ts'
import { NGC_GRADE_ORDER } from '../types/coin.ts'

Chart.register(LineController, LineElement, PointElement, LinearScale,
               Tooltip, Legend, CategoryScale)

// Grades ordered best → worst, each gets a distinct color
const GRADE_COLORS: Record<string, string> = {
  MS: '#f59e0b',  // gold
  AU: '#fb923c',  // orange
  XF: '#22c55e',  // green
  VF: '#06b6d4',  // cyan
  F:  '#3b82f6',  // blue
  VG: '#6366f1',  // indigo
  G:  '#a855f7',  // purple
  AG: '#f43f5e',  // rose
  P:  '#78716c',  // stone
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let chartInstance: any = null

export function renderPriceChartContainer(): string {
  return `
    <div class="card">
      <div class="card-header">Price History by Grade</div>
      <div class="p-4">
        <div class="flex flex-wrap items-center gap-4 mb-3 text-xs">
          <label class="flex items-center gap-1 text-stone-400 cursor-pointer">
            <input type="checkbox" id="chart-log-scale" class="filter-checkbox" />
            Log scale
          </label>
          <div class="flex items-center gap-3 text-stone-500 ml-auto">
            <span class="flex items-center gap-1">● Auction realized</span>
            <span class="flex items-center gap-1">■ Dealer asking</span>
            <span class="flex items-center gap-1">▲ Estimate</span>
          </div>
        </div>
        <div class="relative h-72">
          <canvas id="price-chart"></canvas>
        </div>
        <p class="text-xs text-stone-600 mt-2">
          Each line represents one NGC grade tier. Grades carry significant premiums: MS ≈ 5×, AU ≈ 3×, XF ≈ 1.75×, VF = baseline.
        </p>
      </div>
    </div>
  `
}

// Point style per listing type: realized=circle, fixed_price=rect, estimate=triangle
const LISTING_POINT_STYLE: Record<ListingType, string> = {
  auction_realized: 'circle',
  fixed_price:      'rect',
  auction_estimate: 'triangle',
}

export function mountPriceChart(sales: Sale[]) {
  const canvas = document.getElementById('price-chart') as HTMLCanvasElement | null
  if (!canvas) return

  if (chartInstance) { chartInstance.destroy(); chartInstance = null }

  // Only plot realized + estimate sales (not fixed-price asking prices)
  const plottable = [...sales]
    .filter(s => s.listing_type !== 'fixed_price')
    .sort((a, b) => a.sale_date.localeCompare(b.sale_date))

  // Unique sorted dates as x-axis labels
  const labels = [...new Set(plottable.map(s => s.sale_date))].sort()

  // One dataset per grade that has data
  const datasets = NGC_GRADE_ORDER
    .map(grade => {
      const gradeSales = plottable.filter(s => s.ngc?.grade === grade)
      if (gradeSales.length === 0) return null

      const color = GRADE_COLORS[grade] ?? '#a8a29e'

      // For each label date, pick the highest-priced sale of this grade on that day
      // (multiple sales same day same grade → show highest)
      const data = labels.map(date => {
        const dayMatches = gradeSales.filter(s => s.sale_date === date)
        if (dayMatches.length === 0) return null
        return Math.max(...dayMatches.map(s => s.hammer_price_usd))
      })

      // Point style from the first matching sale on each date
      const pointStyles = labels.map(date => {
        const match = gradeSales.find(s => s.sale_date === date)
        return match ? LISTING_POINT_STYLE[match.listing_type ?? 'auction_realized'] : 'circle'
      })

      return {
        label:            grade,
        data,
        borderColor:      color,
        backgroundColor:  color + '33',
        pointStyle:       pointStyles as never,
        pointRadius:      5,
        pointHoverRadius: 8,
        tension:          0.25,
        borderWidth:      2,
        spanGaps:         true,
      }
    })
    .filter(Boolean)

  chartInstance = new Chart(canvas, {
    type: 'line',
    data: { labels, datasets } as never,
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      interaction:         { mode: 'index' as const, intersect: false },
      plugins: {
        legend: {
          labels: { color: '#a8a29e', font: { size: 11, weight: 'bold' } },
        },
        tooltip: {
          callbacks: {
            title: (items) => items[0]?.label ?? '',
            label: (ctx) => {
              const v = ctx.parsed.y
              if (v == null) return ''
              const grade = ctx.dataset.label ?? ''
              return ` NGC ${grade}: $${v.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
            },
          },
          backgroundColor: '#1c1917',
          borderColor:     '#44403c',
          borderWidth:     1,
          titleColor:      '#e7e5e4',
          bodyColor:       '#d6d3d1',
        },
      },
      scales: {
        x: {
          ticks: { color: '#78716c', maxRotation: 45, font: { size: 10 } },
          grid:  { color: '#292524' },
        },
        y: {
          ticks: {
            color:    '#78716c',
            callback: (v: number | string) => `$${Number(v).toLocaleString()}`,
            font:     { size: 10 },
          },
          grid: { color: '#292524' },
        },
      },
    },
  })

  // Log scale toggle
  const logToggle = document.getElementById('chart-log-scale') as HTMLInputElement | null
  logToggle?.addEventListener('change', () => {
    if (!chartInstance) return
    chartInstance.options.scales.y.type = logToggle.checked ? 'logarithmic' : 'linear'
    chartInstance.update()
  })
}
