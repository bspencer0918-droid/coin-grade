// ============================================================
// Coin Grade — Application entry point
// ============================================================
import './styles/main.css'
import { onRouteChange, type Route } from './router.ts'
import { renderHeader } from './components/Header.ts'
import { renderHome } from './pages/Home.ts'
import { renderBrowse } from './pages/Browse.ts'
import { renderCoinPage, renderCoinPageLoading } from './pages/CoinPage.ts'
import { renderAbout } from './pages/About.ts'
import { renderHistoryPage } from './pages/HistoryPage.ts'
import { renderHistoryCivPage, renderHistoryCivPageLoading } from './pages/HistoryCivPage.ts'
import { renderHistoryGroupPage, renderHistoryGroupPageLoading } from './pages/HistoryGroupPage.ts'
import { renderHistoryRulerPage, renderHistoryRulerPageLoading } from './pages/HistoryRulerPage.ts'
import { loadMeta, loadCatalog, loadCoinDetail, loadHistory } from './data/loader.ts'
import type { Meta, CatalogIndex, FilterState } from './types/coin.ts'
import { DEFAULT_FILTER } from './types/coin.ts'

// ---- App state ----
let meta:    Meta         | null = null
let catalog: CatalogIndex | null = null
let filters: FilterState         = { ...DEFAULT_FILTER }

const app = document.getElementById('app')!

// ---- Render utilities ----
function setContent(header: string, body: string) {
  app.innerHTML = header + body
}

function renderFooter(): string {
  const updated = meta?.last_updated
    ? new Date(meta.last_updated).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    : '…'
  return `
    <footer class="border-t border-stone-800/60 mt-16 py-8">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 flex flex-col sm:flex-row items-center
                  justify-between gap-3 text-xs text-stone-600">
        <span>© ${new Date().getFullYear()} Chronicle Coins · Data updated ${updated}</span>
        <span>Prices in USD · NGC-certified ancient coins only</span>
      </div>
    </footer>
  `
}

// ---- Route handlers ----
async function renderRoute(route: Route) {
  switch (route.name) {
    case 'home': {
      setContent(
        renderHeader('home'),
        renderHome(meta, catalog) + renderFooter()
      )
      break
    }

    case 'browse': {
      if (route.category) {
        filters = { ...DEFAULT_FILTER, category: route.category as FilterState['category'] }
      }
      setContent(
        renderHeader('browse'),
        renderBrowse(catalog?.coins ?? [], filters, (f) => {
          filters = f
          renderRoute({ name: 'browse' })
        }) + renderFooter()
      )
      break
    }

    case 'coin': {
      setContent(
        renderHeader('browse'),
        renderCoinPageLoading() + renderFooter()
      )
      try {
        const coin = await loadCoinDetail(route.slug)
        setContent(
          renderHeader('browse'),
          renderCoinPage(coin, catalog?.coins ?? []) + renderFooter()
        )
      } catch {
        setContent(
          renderHeader('browse'),
          `<main class="max-w-4xl mx-auto px-4 py-16 text-center">
            <div class="text-5xl mb-4">🏛️</div>
            <h1 class="font-display text-2xl text-gold-400 mb-2">Coin not found</h1>
            <p class="text-stone-500 mb-6">The coin data for "<code class="text-stone-300">${route.slug}</code>" could not be loaded.</p>
            <a href="#/browse" class="btn-ghost">← Back to Browse</a>
          </main>` + renderFooter()
        )
      }
      break
    }

    case 'about': {
      setContent(renderHeader('about'), renderAbout() + renderFooter())
      break
    }

    case 'history': {
      setContent(renderHeader('history'), renderHistoryPage() + renderFooter())
      break
    }

    case 'history-civ': {
      setContent(renderHeader('history'), renderHistoryCivPageLoading() + renderFooter())
      try {
        const civ = await loadHistory(route.civ)
        setContent(renderHeader('history'), renderHistoryCivPage(civ) + renderFooter())
      } catch {
        setContent(
          renderHeader('history'),
          `<main class="max-w-4xl mx-auto px-4 py-16 text-center">
            <div class="text-5xl mb-4">🏛️</div>
            <h1 class="font-display text-2xl text-gold-400 mb-2">Civilization not found</h1>
            <p class="text-stone-500 mb-6">History data for "<code class="text-stone-300">${route.civ}</code>" could not be loaded.</p>
            <a href="#/history" class="btn-ghost">← Back to History</a>
          </main>` + renderFooter()
        )
      }
      break
    }

    case 'history-group': {
      setContent(renderHeader('history'), renderHistoryGroupPageLoading() + renderFooter())
      try {
        const civ = await loadHistory(route.civ)
        const group = civ.groups.find(g => g.id === route.group)
        if (!group) throw new Error('Group not found')
        setContent(renderHeader('history'), renderHistoryGroupPage(civ, group) + renderFooter())
      } catch {
        setContent(
          renderHeader('history'),
          `<main class="max-w-4xl mx-auto px-4 py-16 text-center">
            <div class="text-5xl mb-4">🏛️</div>
            <h1 class="font-display text-2xl text-gold-400 mb-2">Dynasty not found</h1>
            <p class="text-stone-500 mb-6">Could not load data for this dynasty.</p>
            <a href="#/history/${route.civ}" class="btn-ghost">← Back to ${route.civ}</a>
          </main>` + renderFooter()
        )
      }
      break
    }

    case 'history-ruler': {
      setContent(renderHeader('history'), renderHistoryRulerPageLoading() + renderFooter())
      try {
        const civ = await loadHistory(route.civ)
        const group = civ.groups.find(g => g.id === route.group)
        if (!group) throw new Error('Group not found')
        const ruler = group.rulers.find(r => r.id === route.ruler)
        if (!ruler) throw new Error('Ruler not found')
        const coins = catalog?.coins ?? []
        setContent(renderHeader('history'), renderHistoryRulerPage(civ, group, ruler, coins) + renderFooter())
      } catch {
        setContent(
          renderHeader('history'),
          `<main class="max-w-4xl mx-auto px-4 py-16 text-center">
            <div class="text-5xl mb-4">🏛️</div>
            <h1 class="font-display text-2xl text-gold-400 mb-2">Ruler not found</h1>
            <p class="text-stone-500 mb-6">Could not load data for this ruler.</p>
            <a href="#/history/${route.civ}/${route.group}" class="btn-ghost">← Back</a>
          </main>` + renderFooter()
        )
      }
      break
    }
  }

  // Scroll to top on route change
  window.scrollTo({ top: 0, behavior: 'instant' })
}

// ---- Bootstrap ----
async function init() {
  // Show loading state immediately
  app.innerHTML = `
    <div class="flex items-center justify-center min-h-screen flex-col gap-3">
      <img src="${import.meta.env.BASE_URL}Chronicle%20Coins_V1.jpg" alt="Chronicle Coins" class="h-16 w-auto opacity-80"
           onerror="this.style.display='none'" />
      <div class="text-gold-500 font-display text-xl tracking-wider">Chronicle Coins</div>
      <div class="text-stone-600 text-sm">Loading auction data…</div>
    </div>
  `

  // Load meta and catalog in parallel, non-blocking (site works without them)
  try {
    ;[meta, catalog] = await Promise.all([loadMeta(), loadCatalog()])
  } catch (err) {
    console.warn('Could not load data files. Running in demo mode.', err)
  }

  // Start routing
  onRouteChange(renderRoute)
}

init()
