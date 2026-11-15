// Home, part 2: the two tiles. The facts on each tile are read from the backend's files; nothing is typed by hand.
import { CONFIG } from './config.js';

const assets = CONFIG.DATA_BASE + 'export/site_assets/';
const BODIES = {
  moon: { catalogue: 'catalogue/targets_moon_artemis3.geojson', kind: 'Artemis III candidate regions' },
  mars: { catalogue: 'catalogue/targets_mars.geojson', kind: 'NASA Exploration Zones' },
};

async function tile(body) {
  const el = document.querySelector(`.world[data-body="${body}"]`), fact = el.querySelector('[data-fact]');
  if (!CONFIG.ENABLED_BODIES.includes(body)) {   // the body is switched off in js/config.js
    el.classList.add('is-off'); el.removeAttribute('href'); el.setAttribute('aria-disabled', 'true');
    fact.textContent = 'Not in this demo';
    return;
  }
  const [cat, targets] = await Promise.all([
    (await fetch(assets + BODIES[body].catalogue)).json(),
    (await fetch(`${CONFIG.DATA_BASE}contract/targets_${body}.json`)).json(),
  ]);
  fact.textContent = `${cat.features.length} ${BODIES[body].kind} · ${targets.pairing_dimensions.length} variables compared with Earth`;
}

// the "Earth analogs" link in the header: the Earth map for the default target of the first world that is switched on
const first = CONFIG.ENABLED_BODIES[0], link = document.getElementById('navEarth');
if (link && first) link.href = `results.html?body=${first}&target=${encodeURIComponent(CONFIG.DEFAULT_TARGET[first])}`;

tile('moon').catch((e) => console.error(e));
tile('mars').catch((e) => console.error(e));
