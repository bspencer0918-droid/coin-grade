// ============================================================
// Simple hash-based client router
// ============================================================

export type Route =
  | { name: 'home' }
  | { name: 'browse' }
  | { name: 'coin';  slug: string }
  | { name: 'about' }

type RouteHandler = (route: Route) => void

let handler: RouteHandler | null = null

export function onRouteChange(fn: RouteHandler) {
  handler = fn
  window.addEventListener('hashchange', () => handler?.(parseRoute()))
  // Fire immediately for current hash
  handler(parseRoute())
}

export function parseRoute(): Route {
  const hash = window.location.hash.replace(/^#\/?/, '') || ''
  if (!hash || hash === 'home') return { name: 'home' }
  if (hash === 'browse') return { name: 'browse' }
  if (hash === 'about')  return { name: 'about' }
  const m = hash.match(/^coin\/(.+)$/)
  if (m) return { name: 'coin', slug: m[1] }
  return { name: 'home' }
}

export function navigate(route: Route) {
  switch (route.name) {
    case 'home':   window.location.hash = '#/home';            break
    case 'browse': window.location.hash = '#/browse';          break
    case 'about':  window.location.hash = '#/about';           break
    case 'coin':   window.location.hash = `#/coin/${route.slug}`; break
  }
}

export function href(route: Route): string {
  switch (route.name) {
    case 'home':   return '#/home'
    case 'browse': return '#/browse'
    case 'about':  return '#/about'
    case 'coin':   return `#/coin/${route.slug}`
  }
}
