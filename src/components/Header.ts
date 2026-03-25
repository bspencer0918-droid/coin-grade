// ============================================================
// Site header — logo + navigation
// ============================================================
import { href } from '../router.ts'

export function renderHeader(activePage: string): string {
  const base = import.meta.env.BASE_URL

  const navLinks: Array<{ label: string; page: string; route: string }> = [
    { label: 'Home',    page: 'home',    route: href({ name: 'home'    }) },
    { label: 'Browse',  page: 'browse',  route: href({ name: 'browse'  }) },
    { label: 'History', page: 'history', route: href({ name: 'history' }) },
    { label: 'About',   page: 'about',   route: href({ name: 'about'   }) },
  ]

  const navHTML = navLinks.map(({ label, page, route }) => `
    <a href="${route}"
       class="nav-link ${activePage === page ? 'nav-link-active' : ''}">
      ${label}
    </a>
  `).join('')

  return `
    <header class="sticky top-0 z-50 bg-stone-950/95 backdrop-blur border-b border-stone-800/80">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 flex items-center justify-between h-20">

        <!-- Logo -->
        <a href="${href({ name: 'home' })}" class="flex items-center">
          <img
            src="${base}Chronicle%20Coins_V1.jpg"
            alt="Chronicle Coins"
            class="h-16 w-auto"
            onerror="this.style.display='none'; this.nextElementSibling.style.display='flex'"
          />
          <!-- Fallback text logo if image fails -->
          <span class="hidden items-center font-display text-2xl text-gold-400 tracking-wider">
            Chronicle Coins
          </span>
        </a>

        <!-- Nav -->
        <nav class="flex items-center gap-1">
          ${navHTML}
        </nav>
      </div>
    </header>
  `
}
