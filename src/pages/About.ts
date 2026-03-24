// ============================================================
// About page
// ============================================================
import { href } from '../router.ts'

export function renderAbout(): string {
  return `
    <main class="max-w-4xl mx-auto px-4 sm:px-6 py-10 space-y-10">
      <section>
        <h1 class="font-display text-4xl text-gold-400 mb-3">About Coin Grade</h1>
        <p class="text-stone-400 text-lg leading-relaxed">
          Coin Grade aggregates realized auction prices for NGC-certified ancient coins
          from the world's leading numismatic platforms, updated daily.
        </p>
      </section>

      <section class="card p-6 space-y-4">
        <h2 class="font-display text-xl text-gold-500">How It Works</h2>
        <ol class="space-y-3 text-stone-300">
          <li class="flex gap-3">
            <span class="text-gold-600 font-mono font-bold shrink-0">01</span>
            <span>Every day at 6:00 AM UTC, an automated scraper collects completed
            auction results and fixed-price sales from CNG, Heritage Auctions, VCoins,
            MA Shops, NumisBids, Sixbid, Harlan J. Berk, Coin Archives, and more.</span>
          </li>
          <li class="flex gap-3">
            <span class="text-gold-600 font-mono font-bold shrink-0">02</span>
            <span>Each listing is checked for NGC certification. Listings with an NGC
            certificate number are verified against the official NGC registry.
            Listings that mention NGC grading without a cert number are flagged as
            "NGC mentioned" but not confirmed.</span>
          </li>
          <li class="flex gap-3">
            <span class="text-gold-600 font-mono font-bold shrink-0">03</span>
            <span>Coins are classified by civilization (Roman, Greek, Byzantine, etc.),
            ruler, metal (AV/AR/AE), and denomination. All prices are normalized to USD
            using the exchange rate at the time of the scrape.</span>
          </li>
          <li class="flex gap-3">
            <span class="text-gold-600 font-mono font-bold shrink-0">04</span>
            <span>Results are published as static JSON files and the site is rebuilt
            automatically via GitHub Actions, so prices are always current with no
            server infrastructure required.</span>
          </li>
        </ol>
      </section>

      <section class="card p-6 space-y-3">
        <h2 class="font-display text-xl text-gold-500">Data Sources</h2>
        <div class="grid sm:grid-cols-2 gap-3 text-sm">
          ${[
            { name: 'CNG (Classical Numismatic Group)', note: 'Leading US ancient coin auction house'          },
            { name: 'Heritage Auctions',                note: 'World\'s largest numismatic auctioneer'        },
            { name: 'VCoins',                           note: 'Fixed-price dealer marketplace'                },
            { name: 'MA Shops',                         note: 'European dealer marketplace'                   },
            { name: 'NumisBids',                        note: 'International auction aggregator'              },
            { name: 'Sixbid',                           note: 'European numismatic auction platform'          },
            { name: 'Harlan J. Berk',                   note: 'Chicago-based ancient coin dealer'             },
            { name: 'Coin Archives',                    note: 'Historical auction result archive'             },
          ].map(s => `
            <div class="flex gap-3 p-3 bg-stone-800/50 rounded-lg">
              <span class="text-gold-500">▸</span>
              <div>
                <div class="text-stone-100 font-medium">${s.name}</div>
                <div class="text-stone-500 text-xs">${s.note}</div>
              </div>
            </div>
          `).join('')}
        </div>
      </section>

      <section class="card p-6 space-y-3">
        <h2 class="font-display text-xl text-gold-500">NGC Grading Scale</h2>
        <p class="text-stone-400 text-sm">
          All coins tracked here are graded by the Numismatic Guaranty Company (NGC),
          the world's largest third-party coin certification service.
        </p>
        <div class="grid sm:grid-cols-2 gap-2 text-sm mt-2">
          ${[
            { grade: 'MS',  desc: 'Mint State — no wear, fully uncirculated'        },
            { grade: 'AU',  desc: 'About Uncirculated — trace wear on high points'  },
            { grade: 'XF',  desc: 'Extremely Fine — light even wear'                },
            { grade: 'VF',  desc: 'Very Fine — moderate wear, all major details'    },
            { grade: 'F',   desc: 'Fine — even wear, all lettering visible'         },
            { grade: 'VG',  desc: 'Very Good — heavy wear, main features clear'     },
            { grade: 'G',   desc: 'Good — heavily worn, design visible in outline'  },
            { grade: 'AG',  desc: 'About Good — very heavily worn'                  },
          ].map(g => `
            <div class="flex gap-3 items-start p-2 rounded bg-stone-800/30">
              <span class="badge-${g.grade.toLowerCase().replace(' ','')} shrink-0 mt-0.5">${g.grade}</span>
              <span class="text-stone-400">${g.desc}</span>
            </div>
          `).join('')}
        </div>
      </section>

      <section class="card p-6">
        <h2 class="font-display text-xl text-gold-500 mb-3">Disclaimer</h2>
        <p class="text-stone-400 text-sm leading-relaxed">
          Coin Grade aggregates publicly available auction data for informational purposes only.
          Past realized prices do not guarantee future values. Always consult a professional
          numismatist before making purchasing or selling decisions. Coin Grade is not affiliated
          with NGC, CNG, Heritage Auctions, VCoins, MA Shops, NumisBids, Sixbid,
          Harlan J. Berk, or Coin Archives.
        </p>
      </section>

      <div class="text-center">
        <a href="${href({ name: 'browse' })}" class="btn-primary">Browse Coin Prices →</a>
      </div>

    </main>
  `
}
