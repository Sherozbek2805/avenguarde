// Home, part 4: the notes. The counts, the sources and the engine's AI line are read from the backend's files; nothing is typed by hand.
import { CONFIG } from './config.js';

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const json = async (path) => { const r = await fetch(CONFIG.DATA_BASE + path); if (!r.ok) throw new Error(`cannot read ${path}`); return r.json(); };
const NAMES = { moon: 'the Moon', mars: 'Mars' };

async function notes() {
  // one row per target: the main result (CONFIG.MAIN_SYSTEM), in the construction shown first on the map page
  const bodies = [];
  for (const body of CONFIG.ENABLED_BODIES) {
    const main = (await json(`runs/${body}_summary.json`)).filter((r) => r.system === CONFIG.MAIN_SYSTEM), first = new Map();
    for (const r of main) if (!first.has(r.target) || r.construction === 'without_composition') first.set(r.target, r);
    bodies.push({ body, runs: [...first.values()] });
  }
  const all = bodies.flatMap((b) => b.runs), passed = all.filter((r) => r.significant).length, control = all.filter((r) => r.control_passed).length;
  const list = (f) => bodies.map((b) => `<b>${f(b)}</b> on ${NAMES[b.body]}`).join(', ');
  $('notesResults').innerHTML = `
    <li>Targets searched: ${list((b) => b.runs.length)}.</li>
    <li>Passed the chance test (p &lt; 0.05): ${list((b) => b.runs.filter((r) => r.significant).length)}.${passed ? '' : ' No target is a significant match today.'}</li>
    <li>Check of the test: the Atacama patch was found in <b>${control}</b> of <b>${all.length}</b> searches.</li>`;

  // the sources, the engine's AI line and Earth's limits are the same in every result file: read them from one
  const doc = await json(`${all[0].out_dir}/output.json`);
  // The result files still name the Mars elevation source by its old label. The repository's SOURCES.md is the authority:
  // the terrain layers come from the MOLA – HRSC blend at 200 m (Fergason et al. 2018). The label is corrected here until the files are rebuilt.
  const FIX = { 'MOLA 463 m Mars DEM': { name: 'MOLA – HRSC blended elevation model, 200 m (Fergason et al. 2018, USGS Astrogeology)', url: 'https://github.com/Sherozbek2805/avenguarde/blob/main/SOURCES.md' } };
  $('notesSources').innerHTML = doc.sources.map((s) => ({ ...s, ...(FIX[s.name] || {}) })).map((s) => `<li><a href="${esc(s.url)}" rel="noopener">${esc(s.name)}</a><span>${esc(s.used_for)}</span></li>`).join('');
  $('notesAi').textContent = doc.ai_disclosure;
  const li = document.createElement('li');
  li.textContent = `Every place on Earth is a partial analog. These differ everywhere: ${doc.earths_limits.map((l) => l.what.toLowerCase()).join(', ')}.`;
  $('notesLimits').append(li);
}

notes().catch((e) => { console.error(e); $('notesResults').innerHTML = '<li>The results could not be read.</li>'; $('notesSources').innerHTML = ''; });
