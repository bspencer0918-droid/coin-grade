// ============================================================
// Lazy JSON data loader — all fetches go through this module
// ============================================================
import type { Meta, CatalogIndex, CoinDetail } from '../types/coin.ts'
import type { HistoryCivilization } from '../types/history.ts'

const BASE = import.meta.env.BASE_URL   // '/coin-grade/' in production, '/' in dev

// Simple in-memory cache so we never fetch the same file twice per session
const cache = new Map<string, unknown>()

async function fetchJSON<T>(path: string): Promise<T> {
  if (cache.has(path)) return cache.get(path) as T
  const res = await fetch(`${BASE}data/${path}`)
  if (!res.ok) throw new Error(`Failed to fetch data/${path}: ${res.status}`)
  const data = await res.json() as T
  cache.set(path, data)
  return data
}

export async function loadMeta(): Promise<Meta> {
  return fetchJSON<Meta>('meta.json')
}

export async function loadCatalog(): Promise<CatalogIndex> {
  return fetchJSON<CatalogIndex>('catalog/index.json')
}

export async function loadCoinDetail(slug: string): Promise<CoinDetail> {
  return fetchJSON<CoinDetail>(`prices/${slug}.json`)
}

export async function loadRulerIndex(category: string): Promise<{ rulers: Array<{ name: string; slug: string; reign: string; sale_count: number; data_url: string }> }> {
  return fetchJSON(`catalog/${category}/by-ruler/index.json`)
}

export async function loadHistory(civ: string): Promise<HistoryCivilization> {
  return fetchJSON<HistoryCivilization>(`history/${civ}.json`)
}

export interface WildwindsEntry {
  ric: number[]
  sear: number[]
  desc: string
  img: string | null
}

export async function loadWildwindsRef(slug: string): Promise<WildwindsEntry[]> {
  try {
    return await fetchJSON<WildwindsEntry[]>(`wildwinds/${slug}.json`)
  } catch {
    return []
  }
}
