// ============================================================
// Chart.js price history chart
// ============================================================
import { Chart, LineController, LineElement, PointElement, LinearScale,
         Tooltip, Legend, CategoryScale } from 'chart.js'
import type { Sale, Source } from '../types/coin.ts'

Chart.register(LineController, LineElement, PointElement, LinearScale,
               Tooltip, Legend, CategoryScale)

const SOURCE_COLORS: Record<Source, string> = {
  cng:       '#f59e0b',
  heritage:  '#3b82f6',
  ebay:      '#eab308',
  vcoins:    '#22c55e',
  mashops:   '#a855f7',
  numisbids: '#06b6d4',
  sixbid:    '#6366f1',
  hjb:       '#f43f5e',
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let chartInstance: any = null

export function renderPriceChartContainer(): string {
  return `
    <div class="card">
      <div class="card-header">Price History</div>
      <div class="p-4">
        <div class="flex gap-3 mb-3 text-xs">
          <label class="flex items-center gap-1 text-stone-400 cursor-pointer">
            <input type="checkbox" id="chart-log-scale" class="filter-checkbox" />
            Log scale
          </label>
        </div>
        <div class="relative h-64">
          <canvas id="price-chart"></canvas>
        </div>
      </div>
    </div>
  `
}

export function mountPriceChart(sales: Sale[]) {
  const canvas = document.getElementById('price-chart') as HTMLCanvasElement | null
  if (!canvas) return

  if (chartInstance) { chartInstance.destroy(); chartInstance = null }

  const sorted = [...sales].sort((a, b) => a.sale_date.localeCompare(b.sale_date))
  // All unique dates as labels
  const labels = sorted.map(s => s.sale_date)

  const datasets = (['cng','heritage','ebay','vcoins','mashops','numisbids','sixbid','hjb'] as Source[]).map(src => {
    const srcSales = sorted.filter(s => s.source === src)
    if (srcSales.length === 0) return null
    // Map each date label to price for this source (null if no sale on that date)
    const data = labels.map(label => {
      const match = srcSales.find(s => s.sale_date === label)
      return match ? match.hammer_price_usd : null
    })
    return {
      label:            src.toUpperCase(),
      data,
      borderColor:      SOURCE_COLORS[src],
      backgroundColor:  SOURCE_COLORS[src] + '33',
      pointRadius:      5,
      pointHoverRadius: 7,
      tension:          0.3,
      borderWidth:      2,
      spanGaps:         true,
    }
  }).filter(Boolean)

  chartInstance = new Chart(canvas, {
    type: 'line',
    data: { labels, datasets } as never,
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      interaction:         { mode: 'index' as const, intersect: false },
      plugins: {
        legend: {
          labels: { color: '#a8a29e', font: { size: 11 } },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const v = ctx.parsed.y ?? 0
              const label = ctx.dataset.label ?? ''
              return ` ${label}: $${v.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
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
