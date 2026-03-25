// ============================================================
// Simple hash-based client router
// ============================================================

export type Route =
  | { name: 'home' }
  | { name: 'browse'; category?: string }
  | { name: 'coin';  slug: string }
  | { name: 'about' }
  | { name: 'history' }
  | { name: 'history-civ'; civ: string }
  | { name: 'history-group'; civ: string; group: string }
  | { name: 'history-ruler'; civ: string; group: string; ruler: string }

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
  if (hash === 'about')  return { name: 'about' }
  const m = hash.match(/^coin\/(.+)$/)
  if (m) return { name: 'coin', slug: m[1] }
  if (hash.startsWith('browse')) {
    const qIdx = hash.indexOf('?')
    const params = qIdx >= 0 ? new URLSearchParams(hash.slice(qIdx + 1)) : null
    const category = params?.get('cat') ?? undefined
    return { name: 'browse', category }
  }
  const hm = hash.match(/^history(?:\/([^/?]+)(?:\/([^/?]+)(?:\/([^/?]+))?)?)?$/)
  if (hm) {
    if (hm[3]) return { name: 'history-ruler', civ: hm[1], group: hm[2], ruler: hm[3] }
    if (hm[2]) return { name: 'history-group', civ: hm[1], group: hm[2] }
    if (hm[1]) return { name: 'history-civ', civ: hm[1] }
    return { name: 'history' }
  }
  return { name: 'home' }
}

export function navigate(route: Route) {
  switch (route.name) {
    case 'home':           window.location.hash = '#/home';            break
    case 'browse':         window.location.hash = '#/browse';          break
    case 'about':          window.location.hash = '#/about';           break
    case 'coin':           window.location.hash = `#/coin/${route.slug}`; break
    case 'history':        window.location.hash = '#/history';         break
    case 'history-civ':    window.location.hash = `#/history/${route.civ}`; break
    case 'history-group':  window.location.hash = `#/history/${route.civ}/${route.group}`; break
    case 'history-ruler':  window.location.hash = `#/history/${route.civ}/${route.group}/${route.ruler}`; break
  }
}

export function href(route: Route): string {
  switch (route.name) {
    case 'home':           return '#/home'
    case 'browse':         return route.category ? `#/browse?cat=${route.category}` : '#/browse'
    case 'about':          return '#/about'
    case 'coin':           return `#/coin/${route.slug}`
    case 'history':        return '#/history'
    case 'history-civ':    return `#/history/${route.civ}`
    case 'history-group':  return `#/history/${route.civ}/${route.group}`
    case 'history-ruler':  return `#/history/${route.civ}/${route.group}/${route.ruler}`
  }
}
