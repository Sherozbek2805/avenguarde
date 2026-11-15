// Results: the best places on Earth for one target. Everything shown is read from the run's output.json and its rank picture
// (contract 2.4). The site computes nothing new: the slider only thresholds the engine's rank picture.
import { CONFIG } from './config.js';
import { EarthMap } from './earthmap.js';
import { fmtCoord, fmtSig3, fmtInt, fmtGap, fmtP, unit } from './format.js';

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const json = async (path) => { const r = await fetch(CONFIG.DATA_BASE + path); if (!r.ok) throw new Error(`cannot read ${path}`); return r.json(); };
const NAMES = { moon: 'Moon', mars: 'Mars' }, THE = { moon: 'the Moon', mars: 'Mars' };
const SHARES = [0.1, 0.2, 0.5, 1, 2, 3, 5, 10, 15, 20];   // percent; the slider's stops
const VAR = { slope: 'Slope', 'roughness_5.25km': 'Roughness, 5.25 km', 'roughness_10.5km': 'Roughness, 10.5 km', 'roughness_21km': 'Roughness, 21 km', 'roughness_42km': 'Roughness, 42 km',
  tpi_7km: 'Landform position, 7 km', tpi_21km: 'Landform position, 21 km', svf_30km: 'Open sky', temp_level: 'Temperature level', temp_range_diurnal: 'Day–night swing',
  temp_range_seasonal: 'Seasonal swing', SiO2: 'Silica (SiO₂)', FeO: 'Iron oxide (FeO)' };
const GROUP = { terrain: 'Terrain', thermal: 'Temperature', composition: 'Rock' };
const VERDICT = { agrees: '<i class="vd vd--agrees"></i>agrees', partial: '<i class="vd vd--partial"></i>partial', differs: '<i class="vd vd--differs"></i>differs', withheld: 'no data' };   // a shape and a word

const q = new URLSearchParams(location.search);
const body = q.get('body');
let target = q.get('target');
// "Your place": a circle the visitor picked on the globe. It has no stored result: the engine searches it live, then the run is read by its id.
const num = (k) => (q.get(k) == null || q.get(k) === '' ? NaN : Number(q.get(k)));
const own = { run: q.get('run'), lat: num('lat'), lon: num('lon'), r: num('r') };
own.on = !target && CONFIG.CUSTOM_BODIES.includes(body) && !!CONFIG.API_BASE && (!!own.run || (Math.abs(own.lat) <= 90 && Math.abs(own.lon) <= 360 && own.r > 0));
const ownWhere = () => `${Math.abs(own.lat).toFixed(2)}°${own.lat < 0 ? 'S' : 'N'}, ${Math.abs(own.lon).toFixed(2)}°${own.lon < 0 ? 'W' : 'E'}`;
const ownBack = () => `explore.html?body=${body}` + (isFinite(own.lat) ? `&lat=${own.lat}&lon=${own.lon}&r=${own.r}` : '');
// The live engine's state: busy = a search is running; loading = a stored result is being read. Only one of them at a time.
const live = { online: null, busy: false, stop: false, loading: false };
const lockSwitches = (on) => { for (const b of $('switches').querySelectorAll('button')) b.disabled = on; };   // the view cannot change while the engine works on it
const state = { system: CONFIG.MAIN_SYSTEM,   // the page shows the main result only
   construction: q.get('construction'), share: SHARES.indexOf(Number(q.get('share'))) >= 0 ? SHARES.indexOf(Number(q.get('share'))) : -1, place: Number(q.get('place')) || 0 };
let summary, doc, map, runs;

function setUrl() {
  const p = new URLSearchParams({ body });
  if (own.on) { if (own.run) p.set('run', own.run); else { p.set('lat', own.lat); p.set('lon', own.lon); p.set('r', own.r); } }
  else { p.set('target', target); if (state.construction) p.set('construction', state.construction); }
  p.set('share', SHARES[state.share]);
  history.replaceState(null, '', '?' + p);
}
const atFloor = (p, B) => p <= 1 / (B + 1) + 1e-9;

function verdict() {
  const t = doc.null_test, floor = t.p_at_floor || atFloor(t.p, t.B), sig = t.p < 0.05, c = t.positive_control;
  const pct = Math.round(t.p * 100);
  const why = floor ? `None of the ${fmtInt(t.B)} random patches of ${THE[body]} matched Earth as closely as this target.`
    : `Random patches of ${THE[body]} at the same latitude matched Earth at least as closely as this target about ${pct}% of the time.`;
  $('verdict').innerHTML = `<b>Chance test: ${sig ? 'significant' : 'not significant'} <span class="value">(${fmtP(t.p, floor)})</span></b>
    <span>${why}</span>
    <span>Check of the test: the Atacama patch ${c.passed ? 'was found' : 'was NOT found'} <span class="value">(${fmtP(c.p, atFloor(c.p, t.B))})</span>.${c.passed ? '' : ' In this view the test is weak; read p with care.'}</span>`;
}

function switches() {
  const el = $('switches'); el.innerHTML = '';
  const seg = (items, current, onpick) => { const d = document.createElement('div'); d.className = 'seg';
    for (const [value, label] of items) { const b = document.createElement('button'); b.type = 'button'; b.textContent = label; b.setAttribute('aria-pressed', String(value === current)); b.addEventListener('click', () => { if (value !== current && !live.busy && !live.loading) onpick(value); }); d.append(b); }   // a click is ignored while a search or a load is running
    el.append(d); };
  const cons = [...new Set(runs.map((r) => r.construction))];
  if (cons.length > 1) {   // Mars: with and without composition
    const cells = (c) => runs.find((r) => r.construction === c).cells, all = Math.max(...cons.map(cells));
    seg(cons.map((c) => [c, c === 'without_composition' ? 'Without composition' : `With composition, ${fmtInt(cells(c))} of ${fmtInt(all)} cells`]), state.construction, (v) => { state.construction = v; state.place = 0; load(); });
  }
}

function list() {
  const ol = $('placeList'); ol.innerHTML = '';
  doc.sites.forEach((s, i) => {
    const li = document.createElement('li'), b = document.createElement('button'); b.type = 'button'; b.className = 'row';
    b.innerHTML = `<span class="row__n">${s.rank}</span><span>${esc(s.koppen ? s.koppen.description : 'Climate: no data')}</span><span class="value">${fmtSig3(s.patch_area_km2)} km²</span>`;
    b.addEventListener('click', () => choose(i));
    b.addEventListener('pointerenter', () => { map.hover = i; map.draw(); }); b.addEventListener('pointerleave', () => { map.hover = -1; map.draw(); });
    li.append(b); ol.append(li); s.row = b;
  });
  $('listNote').textContent = doc.sites.length
    ? `The ${doc.sites.length} best of ${fmtInt(doc.run.patches_total)} places. A place is one connected area of Earth's best ${fmtSig3(doc.run.site_top_share * 100)}%. The slider changes the map only.`
    : 'No places in this result.';
}

function share() {
  const X = SHARES[state.share];
  $('share').value = state.share; $('shareOut').textContent = X + '%'; $('legendShare').textContent = X + '%';
  map.setShare(X / 100);
}

// The list panel folds to its title line when its title is pressed.
function side(open) {
  document.body.classList.toggle('side-off', !open);
  $('sideToggle').setAttribute('aria-expanded', String(open));
  map.inset.left = open ? 388 : 24; map.resize();
}

// A place opens on its own page: the picture on top, the data under it.
function choose(i) {
  if (i < 0) return;
  const p = own.on ? new URLSearchParams({ body, run: own.run }) : new URLSearchParams({ body, target });
  if (!own.on && state.construction) p.set('construction', state.construction);
  p.set('place', i + 1);
  location.href = 'place.html?' + p;
}

function foot() {
  $('foot').hidden = false;
  $('footLimits').innerHTML = doc.earths_limits.map((e) => `<li><b>${esc(e.what)}.</b> ${esc(e.numbers)}. This rules out: ${esc(e.invalidates)}.</li>`).join('');
  $('footRun').textContent = doc.limits;
  $('footSources').innerHTML = doc.sources.map((s) => `<li>${s.url ? `<a href="${esc(s.url)}" rel="noopener">${esc(s.name)}</a>` : esc(s.name)}: ${esc(s.used_for)}</li>`).join('');
  $('footAi').textContent = doc.ai_disclosure;
}

// Draws one result: the stored one from the site's files, or a fresh one from the engine. rankUrl: its rank picture.
async function show(result, rankUrl) {
  if (result.contract_version !== '2.4') throw new Error(`contract version is ${result.contract_version}, expected 2.4`);
  await map.load(CONFIG.BASEMAP('earth'), rankUrl);
  doc = result;
  if (state.share < 0) state.share = Math.max(0, SHARES.indexOf(doc.run.rank_bands[0] * 100));
  verdict(); switches(); list();
  map.setSites(doc.sites.map((s) => ({ lat: s.lat, lon: s.lon, label: String(s.rank) })), doc.run.site_top_share);
  share(); foot(); setUrl();
  $('statusRun').textContent = `Computed ${doc.run.run_utc.replace('T', ' ').replace('Z', ' UTC')} · code ${doc.run.code_version}`;
}

// the stored run for this target: the construction asked for, else "without composition", else the only one
const storedRun = () => runs.find((r) => r.construction === state.construction) || runs.find((r) => r.construction === 'without_composition') || runs[0];

async function load() {
  if (live.busy || live.loading) return;   // one thing at a time: a live search or another load is still running
  live.loading = true; $('liveGo').disabled = true;
  try { await loadStored(); } finally { live.loading = false; }
  liveReady();
}
async function loadStored() {
  $('proc').hidden = false; $('procText').textContent = `Reading the result for ${target}…`; $('bar').hidden = true;
  runs = summary.filter((r) => r.target === target && r.system === state.system);
  if (!runs.length) throw new Error(`no result for ${target}`);
  const run = storedRun();
  state.construction = runs.length > 1 ? run.construction : null;
  const stored = await json(`${run.out_dir}/output.json`);
  await show(stored, CONFIG.DATA_BASE + stored.rasters.find((r) => r.name === 'rank_combined').views.global);
  $('proc').hidden = true; $('bar').hidden = false;
  document.title = `${target} · places on Earth · Terrestrial Analog Finder`;
}

// ---------------------------------------------------------------- the live engine (optional)
// The stored result is always shown first. A live search replaces it only when it succeeds; any failure leaves the stored one.
const API = CONFIG.API_BASE, LIVE_TIME = { moon: 'under a minute', mars: 'under a minute' };

async function api(path, opts = {}, ms = 15000) {
  const c = new AbortController(), t = setTimeout(() => c.abort(), ms);
  try {
    const r = await fetch(API + path, { ...opts, signal: c.signal });
    if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(typeof d.detail === 'string' ? d.detail : `the engine answered ${r.status}`); }
    return await r.json();
  } catch (e) { throw new Error(e.name === 'AbortError' ? 'the engine did not answer in time' : e.message === 'Failed to fetch' ? 'the engine could not be reached' : e.message); }
  finally { clearTimeout(t); }
}
async function liveReady() {   // the text and the button under the chance test
  if (!API) return;
  $('live').hidden = false; $('liveGo').textContent = 'Run this search live';
  if (live.online === null) {
    $('liveGo').disabled = true; $('liveState').textContent = 'This is the stored result. Checking the engine…'; $('liveNote').textContent = '';
    try { await api('/health', {}, 8000); live.online = true; } catch (e) { live.online = false; }
  }
  $('liveGo').hidden = !live.online; $('liveGo').disabled = live.busy;
  $('liveState').textContent = live.online ? 'This is the stored result. The engine is online.' : 'This is the stored result. The engine is not reachable right now.';
  $('liveNote').textContent = live.online ? `A live search scores all of Earth again for this target. It takes ${LIVE_TIME[body]}.` : '';
}
// Sends one search to the engine and waits for it. key: remembers the job in this tab, so a reload goes on waiting and does not start a second search.
async function liveJob(req, clock, key) {
  let id = null;
  try { id = key ? sessionStorage.getItem(key) : null; } catch (e) { /* no storage: start a new job */ }
  if (id) { try { await api('/jobs/' + id); } catch (e) { id = null; } }   // the engine forgot it (a restart): start again
  if (!id) {
    id = (await api('/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(req) })).job_id;
    try { if (key) sessionStorage.setItem(key, id); } catch (e) { /* fine */ }
  }
  let s = { status: 'queued' }, missed = 0;
  try {
    while (s.status !== 'done' && s.status !== 'failed') {
      await new Promise((r) => setTimeout(r, 2500));
      if (live.stop) throw new Error('stopped');
      try { s = await api('/jobs/' + id); missed = 0; } catch (e) { if (++missed >= 6) throw e; }   // one missed answer is not a failure
      $('procText').textContent = s.status === 'queued' ? `Another search is running on the engine. Yours is next · ${clock()}`
        : `The engine is scoring all of Earth against ${target} · ${clock()}`;
    }
  } finally { try { if (key && (s.status === 'done' || s.status === 'failed')) sessionStorage.removeItem(key); } catch (e) { /* fine */ } }
  if (s.status === 'failed') throw new Error(s.error || 'the search failed');
  return s;
}
const clockFrom = (t0) => () => { const s = Math.round((Date.now() - t0) / 1000); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };

// "Your place": search it live (or read the finished run named in the address), then show it like any other result.
async function ownLoad() {
  const fail = (msg) => { $('proc').hidden = false; $('proc').innerHTML = `<b>No result</b><span>${esc(msg)}</span><a class="btn btn--tile proc__stop" href="${esc(ownBack())}">Choose another place</a>`; };
  $('bar').hidden = true; $('proc').hidden = false;
  // while the engine works, the panel says what is being searched and how long it takes
  const waitNote = () => { $('verdict').innerHTML = `<b>Searching Earth for your place</b>
    <span>A circle of <span class="value">${fmtSig3(own.r)} km</span> radius at <span class="value">${ownWhere()}</span> on ${THE[body]}.</span>
    <span>A new place takes about a minute. The engine also draws ${fmtInt(1000)} random patches of ${THE[body]} for the chance test.</span>`; };
  try {
    let seconds = null;
    if (!own.run) {
      waitNote(); $('procStop').hidden = false; $('procStop').textContent = 'Choose another place'; $('procText').textContent = 'Sending your place to the engine…';
      const req = { body, system: state.system, selection: { method: 'circle', params: { lat: own.lat, lon: own.lon, radius_km: own.r } }, name: `Custom circle ${ownWhere().replace(',', '')}, radius ${own.r} km` };
      const s = await liveJob(req, clockFrom(Date.now()), `job:${body}:${own.lat}:${own.lon}:${own.r}`);
      own.run = s.run_id; seconds = s.seconds;
    }
    $('procStop').hidden = true; $('procText').textContent = 'Reading the result…';
    const id = encodeURIComponent(own.run), fresh = await api('/runs/' + id, {}, 30000);
    const sel = fresh.run.target.selection;
    if (sel && sel.method === 'circle') { own.lat = Number(sel.params.lat); own.lon = Number(sel.params.lon); own.r = Number(sel.params.radius_km); names(); }
    await show(fresh, `${API}/runs/${id}/files/rank_combined_global.png`);
    $('proc').hidden = true; $('bar').hidden = false;
    $('live').hidden = false; $('liveGo').hidden = true;
    $('liveState').innerHTML = seconds != null ? `<b>Live result.</b> The engine searched your place just now in <span class="value">${fmtSig3(seconds)} s</span>.`
      : '<b>Live result.</b> The engine searched this place when it was picked on the globe.';
    $('liveNote').textContent = `Your place is a circle of ${fmtSig3(own.r)} km radius: ${fmtInt(fresh.run.target.cells)} cells of the engine's grid. It is not one of NASA's listed targets.`;
    document.title = `Your place · places on Earth · Terrestrial Analog Finder`;
  } catch (e) {
    if (e.message === 'stopped') { location.href = ownBack(); return; }
    $('verdict').innerHTML = '<b>No result for this place</b><span>The engine could not search it. Choose another place on the globe.</span>';
    fail(`${e.message.replace(/^[A-Za-z]+Error: /, '')}.`.replace(/^./, (c) => c.toUpperCase()));
  }
}

async function liveRun() {
  if (live.busy || live.loading) return;
  live.busy = true; live.stop = false; $('liveGo').disabled = true; lockSwitches(true);
  const clock = clockFrom(Date.now());
  $('proc').hidden = false; $('procStop').hidden = false; $('procText').textContent = 'Sending the target to the engine…';
  try {
    const req = { body, system: state.system, preset: { name: target } };
    if (runs.length > 1) req.preset.construction = storedRun().construction;
    const s = await liveJob(req, clock);
    $('procText').textContent = 'Reading the new result…';
    const fresh = await api('/runs/' + s.run_id, {}, 30000);
    await show(fresh, `${API}/runs/${s.run_id}/files/rank_combined_global.png?t=${Date.now()}`);
    $('liveState').innerHTML = `<b>Live result.</b> The engine computed it just now in <span class="value">${fmtSig3(s.seconds)} s</span>.`;
    $('liveNote').textContent = 'The chance test reuses its 1,000 random draws from the first run of this target. The seed is fixed, so the draws are the same every time.';
    $('liveGo').textContent = 'Run it again';
  } catch (e) {
    $('liveState').textContent = e.message === 'stopped' ? 'You stopped waiting. The stored result is shown.' : `The live search did not finish: ${e.message}. The stored result is shown.`;
    $('liveNote').textContent = '';
  } finally { live.busy = false; $('liveGo').disabled = false; lockSwitches(false); $('proc').hidden = true; $('procStop').hidden = true; }
}

// The names and links in the header and the panel title. For "your place" they are set again when its circle is read from the run.
function names() {
  if (own.on) target = isFinite(own.lat) ? `the place at ${ownWhere()}` : 'your place';
  const back = own.on ? ownBack() : `explore.html?body=${body}&target=${encodeURIComponent(target)}`;
  $('pathTarget').textContent = own.on ? 'Your place' : target; $('pathTarget').href = back; $('changeTarget').href = back;
  $('sideTitle').textContent = `Places on Earth like ${target}`;
}

async function start() {
  if (!NAMES[body] || !CONFIG.ENABLED_BODIES.includes(body) || (!target && !own.on)) { location.replace('./#worlds'); return; }
  $('pathBody').textContent = NAMES[body]; $('pathBody').href = `explore.html?body=${body}`;
  names();
  map = new EarthMap($('map'), { left: 388, right: 72, top: 72, bottom: 48 });   // the bottom of the map stays clear
  map.onhover = (h) => {
    $('statusPos').textContent = !h || h.lat == null ? 'Move the pointer over the map'
      : `Latitude ${fmtCoord(h.lat)}° · Longitude ${fmtCoord(h.lon)}° · ${h.rank == null ? 'no rank' : `in the best ${fmtSig3(Math.max(h.rank * 100, 0.01))}% of Earth`}`;
    const i = h ? h.site : -1; if (i !== map.hover) { map.hover = i; map.draw(); doc && doc.sites.forEach((s, j) => s.row.classList.toggle('is-hover', j === i)); }
    map.cv.classList.toggle('is-place', i >= 0);
  };
  map.onpick = (i) => { if (i >= 0) choose(i); };
  $('zoomIn').addEventListener('click', () => map.zoomBy(1.6)); $('zoomOut').addEventListener('click', () => map.zoomBy(1 / 1.6)); $('resetView').addEventListener('click', () => map.reset());
  $('sideToggle').addEventListener('click', () => side(document.body.classList.contains('side-off')));
  $('share').addEventListener('input', (e) => { state.share = Number(e.target.value); share(); setUrl(); });
  $('liveGo').addEventListener('click', liveRun);
  $('procStop').addEventListener('click', () => { live.stop = true; });
  if (own.on) { runs = []; await ownLoad(); return; }
  summary = await json(`runs/${body}_summary.json`);
  await load();
}

start().catch((e) => { console.error(e); $('proc').hidden = false; $('proc').innerHTML = `<b>Error</b><span>${esc(e.message)}. Check that the data folder is in place and reload.</span>`; });
