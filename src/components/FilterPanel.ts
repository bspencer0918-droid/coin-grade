// ============================================================
// Filter panel — category, grade, metal, source, price, date
// ============================================================
import type { FilterState, Category, Metal, NGCGrade, Source } from '../types/coin.ts'
import { NGC_GRADE_ORDER } from '../types/coin.ts'

const CATEGORIES: Array<{ value: Category | ''; label: string }> = [
  { value: '',          label: 'All Civilizations' },
  { value: 'roman',     label: 'Roman'      },
  { value: 'greek',     label: 'Greek'      },
  { value: 'byzantine', label: 'Byzantine'  },
  { value: 'persian',   label: 'Persian'    },
  { value: 'celtic',    label: 'Celtic'     },
  { value: 'egyptian',  label: 'Egyptian'   },
  { value: 'other',     label: 'Other'      },
]

const METALS: Array<{ value: Metal | ''; label: string }> = [
  { value: '',          label: 'All Metals' },
  { value: 'gold',      label: 'Gold (AV)'      },
  { value: 'silver',    label: 'Silver (AR)'     },
  { value: 'bronze',    label: 'Bronze (AE)'     },
  { value: 'billon',    label: 'Billon'          },
  { value: 'electrum',  label: 'Electrum (EL)'   },
]

const SOURCES: Array<{ value: Source; label: string }> = [
  { value: 'cng',          label: 'CNG'              },
  { value: 'heritage',     label: 'Heritage Auctions' },
  { value: 'ebay',         label: 'eBay'             },
  { value: 'vcoins',       label: 'VCoins'           },
  { value: 'mashops',      label: 'MA Shops'         },
  { value: 'numisbids',    label: 'NumisBids'        },
  { value: 'sixbid',       label: 'Sixbid'           },
  { value: 'hjb',          label: 'Harlan J. Berk'   },
  { value: 'coinarchives', label: 'Coin Archives'    },
]

export function renderFilterPanel(
  filters: FilterState,
  rulers: Array<{ name: string; slug: string }>,
  onFilter: (f: FilterState) => void
): string {
  const gradeChecks = NGC_GRADE_ORDER.map(g => `
    <label class="flex items-center gap-2 text-sm cursor-pointer group">
      <input type="checkbox" class="filter-checkbox grade-check" value="${g}"
             ${filters.grades.includes(g) ? 'checked' : ''} />
      <span class="text-stone-300 group-hover:text-stone-100 transition-colors">${g}</span>
    </label>
  `).join('')

  const sourceChecks = SOURCES.map(({ value, label }) => `
    <label class="flex items-center gap-2 text-sm cursor-pointer group">
      <input type="checkbox" class="filter-checkbox source-check" value="${value}"
             ${filters.sources.includes(value) ? 'checked' : ''} />
      <span class="text-stone-300 group-hover:text-stone-100 transition-colors">${label}</span>
    </label>
  `).join('')

  const rulerOptions = rulers.length > 0
    ? `<option value="">All Rulers</option>` +
      rulers.map(r => `<option value="${r.slug}" ${filters.ruler === r.slug ? 'selected' : ''}>${r.name}</option>`).join('')
    : `<option value="">All Rulers</option>`

  // Attach event listeners after render
  setTimeout(() => attachFilterListeners(filters, onFilter), 0)

  return `
    <div class="card p-4 space-y-5" id="filter-panel">
      <div class="text-xs uppercase tracking-widest text-gold-600 font-display border-b border-stone-800 pb-2">
        Filters
      </div>

      <!-- Civilization -->
      <div>
        <label class="filter-label">Civilization</label>
        <select id="f-category" class="filter-select">
          ${CATEGORIES.map(c => `<option value="${c.value}" ${filters.category === c.value ? 'selected' : ''}>${c.label}</option>`).join('')}
        </select>
      </div>

      <!-- Ruler (shown when category is roman or byzantine) -->
      <div id="f-ruler-wrap" class="${filters.category === '' || (filters.category !== 'roman' && filters.category !== 'byzantine') ? 'hidden' : ''}">
        <label class="filter-label">Ruler</label>
        <select id="f-ruler" class="filter-select">
          ${rulerOptions}
        </select>
      </div>

      <!-- Metal -->
      <div>
        <label class="filter-label">Metal</label>
        <select id="f-metal" class="filter-select">
          ${METALS.map(m => `<option value="${m.value}" ${filters.metal === m.value ? 'selected' : ''}>${m.label}</option>`).join('')}
        </select>
      </div>

      <!-- NGC Grade -->
      <div>
        <label class="filter-label">NGC Grade</label>
        <div class="grid grid-cols-2 gap-1 mt-1">
          ${gradeChecks}
        </div>
      </div>

      <!-- NGC Verified only -->
      <div>
        <label class="flex items-center gap-2 text-sm cursor-pointer group">
          <input type="checkbox" id="f-ngc-verified" class="filter-checkbox"
                 ${filters.ngcVerified ? 'checked' : ''} />
          <span class="text-stone-300 group-hover:text-stone-100 transition-colors">
            NGC cert verified only
          </span>
        </label>
        <p class="text-xs text-stone-600 mt-1 ml-5">
          Cert number confirmed via NGC registry
        </p>
      </div>

      <!-- Source -->
      <div>
        <label class="filter-label">Auction Source</label>
        <div class="space-y-1 mt-1">
          ${sourceChecks}
        </div>
      </div>

      <!-- Price range -->
      <div>
        <label class="filter-label">Price (USD)</label>
        <div class="flex gap-2 mt-1">
          <input id="f-price-min" type="number" min="0" placeholder="Min"
                 value="${filters.priceMin ?? ''}"
                 class="filter-select w-1/2 text-sm" />
          <input id="f-price-max" type="number" min="0" placeholder="Max"
                 value="${filters.priceMax ?? ''}"
                 class="filter-select w-1/2 text-sm" />
        </div>
      </div>

      <!-- Date range -->
      <div>
        <label class="filter-label">Sale Date</label>
        <div class="flex gap-2 mt-1">
          <input id="f-date-from" type="date" value="${filters.dateFrom}"
                 class="filter-select w-1/2 text-xs" />
          <input id="f-date-to"   type="date" value="${filters.dateTo}"
                 class="filter-select w-1/2 text-xs" />
        </div>
      </div>

      <!-- Reset -->
      <button id="f-reset" class="btn-ghost w-full text-xs">
        Reset Filters
      </button>
    </div>
  `
}

function attachFilterListeners(filters: FilterState, onFilter: (f: FilterState) => void) {
  const panel = document.getElementById('filter-panel')
  if (!panel) return

  const get = <T extends HTMLElement>(id: string) => document.getElementById(id) as T | null

  const emit = () => {
    const gradeChecks = Array.from(panel.querySelectorAll<HTMLInputElement>('.grade-check:checked'))
      .map(el => el.value as NGCGrade)
    const sourceChecks = Array.from(panel.querySelectorAll<HTMLInputElement>('.source-check:checked'))
      .map(el => el.value as Source)

    const priceMin = get<HTMLInputElement>('f-price-min')?.value
    const priceMax = get<HTMLInputElement>('f-price-max')?.value

    const next: FilterState = {
      ...filters,
      category:    (get<HTMLSelectElement>('f-category')?.value ?? '') as Category | '',
      ruler:        get<HTMLSelectElement>('f-ruler')?.value ?? '',
      metal:       (get<HTMLSelectElement>('f-metal')?.value ?? '') as Metal | '',
      grades:      gradeChecks,
      sources:     sourceChecks,
      ngcVerified: get<HTMLInputElement>('f-ngc-verified')?.checked ?? false,
      priceMin:    priceMin ? parseFloat(priceMin) : null,
      priceMax:    priceMax ? parseFloat(priceMax) : null,
      dateFrom:    get<HTMLInputElement>('f-date-from')?.value ?? '',
      dateTo:      get<HTMLInputElement>('f-date-to')?.value ?? '',
      page:        1,
    }
    onFilter(next)
  }

  // Category change → show/hide ruler select
  get<HTMLSelectElement>('f-category')?.addEventListener('change', e => {
    const cat = (e.target as HTMLSelectElement).value
    const rulerWrap = get<HTMLDivElement>('f-ruler-wrap')
    if (rulerWrap) {
      rulerWrap.classList.toggle('hidden', cat !== 'roman' && cat !== 'byzantine')
    }
    emit()
  })

  panel.querySelectorAll('input, select').forEach(el => {
    el.addEventListener('change', emit)
  })

  get<HTMLButtonElement>('f-reset')?.addEventListener('click', () => {
    onFilter({ ...filters, category: '', ruler: '', metal: '', grades: [], sources: [],
                ngcVerified: false, priceMin: null, priceMax: null, dateFrom: '', dateTo: '', page: 1 })
  })
}
