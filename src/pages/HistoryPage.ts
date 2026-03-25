// ============================================================
// History landing page — civilization selection
// ============================================================
import { href } from '../router.ts'

interface CivCard {
  id: string
  name: string
  emoji: string
  dates: string
  overview: string
}

const CIVILIZATIONS: CivCard[] = [
  {
    id: 'roman',
    name: 'Roman',
    emoji: '🦅',
    dates: '509 BC – 476 AD',
    overview: 'From Republic to Empire, Rome shaped the ancient world for nearly a millennium. Roman coinage evolved from rough bronze lumps to finely struck portraits that recorded every emperor, every triumph, and every dynasty across a thousand years of history.',
  },
  {
    id: 'greek',
    name: 'Greek',
    emoji: '🏛️',
    dates: '700 – 31 BC',
    overview: 'Greek city-states invented coinage and elevated it into an art form. From the archaic owls of Athens to the magnificent portrait coins of the Hellenistic kingdoms, Greek coinage reflects the intellectual and artistic brilliance of the ancient Mediterranean world.',
  },
  {
    id: 'byzantine',
    name: 'Byzantine',
    emoji: '✝️',
    dates: '330 – 1453 AD',
    overview: 'The Byzantine Empire preserved Roman traditions while forging a distinctly Christian culture that lasted over a thousand years. Byzantine gold solidi were the dollar of the medieval world, maintaining a standard of purity that made them trusted from London to China.',
  },
]

export function renderHistoryPage(): string {
  const cards = CIVILIZATIONS.map(civ => `
    <a href="${href({ name: 'history-civ', civ: civ.id })}"
       class="card p-6 flex flex-col gap-4 hover:border-gold-700/50 transition-colors group cursor-pointer no-underline">
      <div class="text-5xl">${civ.emoji}</div>
      <div>
        <h2 class="font-display text-2xl text-gold-400 group-hover:text-gold-300 transition-colors mb-1">
          ${civ.name}
        </h2>
        <p class="text-stone-500 text-sm mb-3">${civ.dates}</p>
        <p class="text-stone-400 text-sm leading-relaxed">${civ.overview}</p>
      </div>
      <div class="mt-auto">
        <span class="btn-primary inline-block text-sm">Explore ${civ.name} History →</span>
      </div>
    </a>
  `).join('')

  return `
    <main class="max-w-7xl mx-auto px-4 sm:px-6 py-10 space-y-10">

      <!-- Page header -->
      <section>
        <h1 class="font-display text-4xl text-gold-400 mb-3">Ancient Coin History</h1>
        <p class="text-stone-400 text-lg leading-relaxed max-w-3xl">
          Explore the rulers, dynasties, and city-states behind the coins in our catalog.
          Each civilization's history is linked directly to the NGC-certified coins we track —
          so you can read about an emperor and immediately see what his coins sell for today.
        </p>
      </section>

      <!-- Divider -->
      <div class="divider"><span class="divider-text">Choose a Civilization</span></div>

      <!-- Civilization cards -->
      <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
        ${cards}
      </div>

    </main>
  `
}
