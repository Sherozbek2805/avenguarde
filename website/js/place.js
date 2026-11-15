// The page of one place on Earth: the picture on top, the data under it.
// Everything shown is read from the run's output.json (contract 2.4); the outline is traced from the run's rank picture.
import { CONFIG } from './config.js';
import { EarthMap } from './earthmap.js';
import { fmtSig3, fmtInt, fmtP, unit } from './format.js';

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const json = async (path) => { const r = await fetch(CONFIG.DATA_BASE + path); if (!r.ok) throw new Error(`cannot read ${path}`); return r.json(); };
const NAMES = { moon: 'Moon', mars: 'Mars' };
const VAR = { slope: 'Slope', 'roughness_5.25km': 'Roughness, 5.25 km', 'roughness_10.5km': 'Roughness, 10.5 km', 'roughness_21km': 'Roughness, 21 km', 'roughness_42km': 'Roughness, 42 km',
  tpi_7km: 'Landform position, 7 km', tpi_21km: 'Landform position, 21 km', svf_30km: 'Open sky', temp_level: 'Temperature level', temp_range_diurnal: 'Day–night swing',
  temp_range_seasonal: 'Seasonal swing', SiO2: 'Silica (SiO₂)', FeO: 'Iron oxide (FeO)' };
const GROUP = { terrain: 'Terrain', thermal: 'Temperature', composition: 'Rock' };
const VERDICT = { agrees: 'agrees', partial: 'partial', differs: 'differs', withheld: 'no data' };
const atFloor = (p, B) => p <= 1 / (B + 1) + 1e-9;

const q = new URLSearchParams(location.search);
const body = q.get('body'), place = Number(q.get('place')) || 0;
let target = q.get('target');
// "Your place": a run the engine made live for a circle picked on the globe. It is read from the engine by its id, not from the stored files.
const ownRun = !target && CONFIG.CUSTOM_BODIES.includes(body) && CONFIG.API_BASE ? q.get('run') : null;
let countries = null;

function countryAt(lon, lat) {   // from data/countries.json (Natural Earth outlines); null over sea or when the file is missing
  if (!countries) return null;
  const inRing = (ring) => { let c = false; for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) { const [xi, yi] = ring[i], [xj, yj] = ring[j]; if ((yi > lat) !== (yj > lat) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) c = !c; } return c; };
  const hit = countries.find((c) => c.g.some(inRing)); return hit ? hit.n : null;
}

// The picture: a view of the place from space, with the place outlined in white.
// Sources are tried in the order of CONFIG.PLACE_PICTURES. "sentinel" is sharp at any size (10 m); "bluemarble" (NASA, 500 m)
// is only sharp for wide views, so its frame is never narrower than 6 degrees. If none can be loaded (no internet),
// the site's own relief and rank map of the same area is shown, and the caption says so.
const PICTURES = {
  sentinel: { minDeg: 2,
    url: (box, w, h) => `https://tiles.maps.eox.at/wms?service=wms&request=getmap&version=1.1.1&layers=s2cloudless-2020&styles=&format=image/jpeg&srs=epsg:4326&bbox=${box}&width=${w}&height=${h}`,
    credit: 'Picture: <a href="https://s2maps.eu" rel="noopener">Sentinel-2 cloudless</a> by <a href="https://eox.at" rel="noopener">EOX IT Services GmbH</a> (contains modified Copernicus Sentinel data 2020)' },
  bluemarble: { minDeg: 6,
    url: (box, w, h) => `https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&LAYERS=BlueMarble_ShadedRelief_Bathymetry&STYLES=&FORMAT=image/jpeg&SRS=EPSG:4326&BBOX=${box}&WIDTH=${w}&HEIGHT=${h}`,
    credit: 'Picture: NASA Blue Marble' },
};
let pictureRun = 0;
function picture(map, s, n = 0, run = ++pictureRun) {
  if (run !== pictureRun) return;   // a newer drawing has started (the window changed size)
  const W = map.W, H = map.H, cv = $('cardPic'), img = $('cardImg'), cap = $('cardPicCap');
  const cw = cv.clientWidth, ch = cv.clientHeight; if (!cw || !ch) return;   // not on screen yet (a hidden window): drawn when it gets a size
  const src = PICTURES[(CONFIG.PLACE_PICTURES || [])[n]];   // undefined after the last source: the site's own map
  const ratio = cw / ch, pad = 1.8, minPx = (src ? src.minDeg : 12) / 360 * W;   // show 1.8 times the place's box, and never less than the source's smallest sharp view
  let w = Math.max(minPx, (s.box[2] - s.box[0]) * pad), h = Math.max(minPx / ratio, (s.box[3] - s.box[1]) * pad);
  if (w / h < ratio) w = h * ratio; else h = w / ratio;
  if (h > H) { h = H; w = h * ratio; }
  const cx = (s.box[0] + s.box[2]) / 2, cy = Math.max(h / 2, Math.min(H - h / 2, (s.box[1] + s.box[3]) / 2)), x0 = cx - w / 2, y0 = cy - h / 2;
  const lon0 = x0 / W * 360 - 180, lon1 = (x0 + w) / W * 360 - 180, lat1 = 90 - y0 / H * 180, lat0 = 90 - (y0 + h) / H * 180;
  const d = Math.min(2, window.devicePixelRatio || 1); cv.width = cw * d; cv.height = ch * d;
  const g = cv.getContext('2d'); g.setTransform(d, 0, 0, d, 0, 0);
  const outline = () => {
    const k = cw / w; g.lineJoin = 'round'; g.beginPath();
    if (s.edges) { const e = s.edges; for (let j = 0; j < e.length; j += 4) { g.moveTo((e[j] - x0) * k, (e[j + 1] - y0) * k); g.lineTo((e[j + 2] - x0) * k, (e[j + 3] - y0) * k); } }
    else g.arc((s.x - x0) * k, (s.y - y0) * k, 10, 0, 7);
    g.lineWidth = 4.5; g.strokeStyle = 'rgba(0,0,0,0.6)'; g.stroke(); g.lineWidth = 2; g.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue('--white').trim(); g.stroke();
  };
  g.clearRect(0, 0, cw, ch);
  if (!src) {   // no picture from space: the site's own map of the same area
    img.hidden = true; img.onload = img.onerror = null; g.imageSmoothingEnabled = false; g.drawImage(map.off, x0, y0, w, h, 0, 0, cw, ch); outline();
    cap.textContent = 'Our relief and rank map of this area (the picture from space could not be loaded)'; return;
  }
  const next = () => { clearTimeout(slow); if (run === pictureRun) picture(map, s, n + 1, run); };
  const slow = setTimeout(next, 9000);   // a source that does not answer in 9 seconds is skipped
  img.onload = () => { clearTimeout(slow); if (run !== pictureRun) return; img.hidden = false; outline(); cap.innerHTML = 'This place from space, outlined in white. ' + src.credit; };
  img.onerror = next;
  img.hidden = true; cap.textContent = 'Loading the picture from space…';
  img.src = src.url(`${lon0.toFixed(4)},${lat0.toFixed(4)},${lon1.toFixed(4)},${lat1.toFixed(4)}`, Math.min(2048, Math.round(cw * 1.5)), Math.min(1024, Math.round(ch * 1.5)));
}

function data(doc, s) {
  const t = doc.null_test, floor = t.p_at_floor || atFloor(t.p, t.B), cat = s.catalogue, u = s.use;
  const weak = new Set(doc.run.variables.filter((v) => v.weak).map((v) => v.name)), beyond = new Map(doc.run.ranking.out_of_range.map((o) => [o.variable, o]));
  const country = countryAt(s.lon, s.lat), climate = s.koppen ? s.koppen.description : null;
  const n = (k) => s[k].length, th = doc.run.verdict_thresholds, sig = t.p < 0.05;
  const pct = (x) => (Math.max(0, Math.min(1, x)) * 100).toFixed(1) + '%';
  // One row per variable: its name, where this place and the target sit on the shared 0-1 scale, the verdict, the two values.
  const row = (v) => {
    const far = beyond.has(v.name), kind = far ? 'limit' : (v.verdict || 'none'), u1 = unit(v.units);
    const has = v.earth_position != null && v.target_position != null, lo = has ? Math.min(v.earth_position, v.target_position) : 0, hi = has ? Math.max(v.earth_position, v.target_position) : 0;
    const tags = (v.modelled ? '<span class="tagc">Modelled</span>' : '') + (weak.has(v.name) ? '<span class="tagc">Weak</span>' : '') + (v.ranked ? '' : '<span class="tagc">Not ranked</span>');
    return `<li class="vrow vrow--${kind}"><span class="vrow__name">${esc(VAR[v.name] || v.name)}</span>
      <span class="vrow__trk" aria-hidden="true">${has ? `<i class="vrow__gap" style="left:${pct(lo)};width:${((hi - lo) * 100).toFixed(1)}%"></i><i class="vrow__t" style="left:${pct(v.target_position)}"></i><i class="vrow__e" style="left:${pct(v.earth_position)}"></i>` : ''}</span>
      <span class="vrow__verdict">${far ? "Earth's limit" : esc(VERDICT[v.verdict] || v.verdict || 'no data')}</span>
      <span class="vrow__val"><b>${fmtSig3(v.earth)}${v.earth == null ? '' : u1}</b> vs <b>${fmtSig3(v.target_median)}${v.target_median == null ? '' : u1}</b>${tags}</span></li>`;
  };
  const use = (x) => `<li><b>${esc(x.label)}.</b> ${esc(x.text)}</li>`;   // the label, then the sentence exactly as the result file gives it
  const far = (x) => {   // the same, with how far outside Earth's range the target is
    const o = x.variables.map((k) => beyond.get(k)).find(Boolean);
    return `<li><b>${esc(x.label)}${o ? `: <i>${fmtSig3(o.gap)}${unit(o.units)} ${o.side === "below Earth's range" ? 'below' : 'above'}</i> Earth's range (${fmtSig3(o.earth_min)}–${fmtSig3(o.earth_max)}${unit(o.units)})` : ''}.</b> ${esc(x.text)}</li>`;
  };
  const place = country || climate || 'Place ' + s.rank;
  $('pathPlace').textContent = `Place ${s.rank}`;
  document.title = `${place} · ${target} · Terrestrial Analog Finder`;
  $('data').innerHTML = `
    <div class="place__id"><p class="label">Place ${s.rank} · like ${esc(target)}</p>
      <h1 class="place__name">${esc(place)}</h1>
      <p class="place__sub">${[country && climate ? esc(climate) : '', s.lithology ? esc(s.lithology.description) + ' rock' : ''].filter(Boolean).join(' · ')}</p>
      <div class="tiles">
        <div class="tile"><b>${fmtInt(s.rank)}<small> of ${fmtInt(doc.run.patches_total)}</small></b><span>rank among the places found</span></div>
        <div class="tile"><b>${n('agrees')}<small> of ${s.variables.length}</small></b><span>agree · ${n('partial')} partial · ${n('differs')} differ</span></div>
        <div class="tile"><b>${fmtP(t.p, floor)}</b><span>chance test: ${sig ? 'significant' : 'not significant'}${sig ? '' : '. The list alone is not a result'}</span></div>
        <div class="tile"><b>${fmtSig3(cat.distance_km)}<small> km</small></b><span>${cat.status === 'known' ? 'from ' + esc(cat.name) + ', a known analog' : 'to the nearest known analog'}</span></div>
      </div>
      <div class="dist"><h3>Distance to the target <span>lower is closer</span></h3>
        <dl>${Object.keys(GROUP).map((g) => `<div><dt>${GROUP[g]}</dt><dd>${s.di_group[g] == null ? 'no data' : fmtSig3(s.di_group[g])}</dd></div>`).join('')}<div class="dist__all"><dt>All</dt><dd>${fmtSig3(s.di_combined)}</dd></div></dl>
        <p>Target's own spread <b>${fmtSig3(doc.run.target.spread)}</b>, over <b>${fmtInt(doc.run.target.cells)}</b> cells. Read the rank, not the score.</p></div>
    </div>
    <div class="place__vars">
      <h2 class="place__h">Variable by variable</h2>
      <p class="vkey"><span><i class="vrow__e"></i>this place (${esc(place)})</span><span><i class="vrow__t"></i>the target (${esc(target)})</span></p>
      <ul class="vlist">${s.variables.map(row).join('')}</ul>
      <p class="vaxis"><span>0</span><span>shared scale</span><span>1</span></p>
      <p class="vnote">Agrees: under <b>${Number(th.agrees_below).toFixed(2)}</b> apart. Differs: over <b>${Number(th.differs_above).toFixed(2)}</b>. Earth's limit: the target is outside every value on Earth.${s.variables.some((v) => weak.has(v.name)) ? ' Weak: the data for this variable is coarse.' : ''}${s.variables.some((v) => v.modelled) ? ' Modelled: from a model, not measured.' : ''}</p>
    </div>
    <div class="place__uses">
      <h2 class="place__h">Use this place for</h2>
      <ul class="uselist">${u.succeeds.length ? u.succeeds.map(use).join('') : `<li>${esc(u.general || 'Nothing agrees fully.')}</li>`}</ul>
    </div>
    ${u.beyond_earth.length ? `<div class="place__limits">
      <h2 class="place__h">Earth's limits</h2>
      <ul class="uselist uselist--far">${u.beyond_earth.map(far).join('')}</ul>
    </div>` : ''}`;
}

async function start() {
  if (!NAMES[body] || !CONFIG.ENABLED_BODIES.includes(body) || (!target && !ownRun) || !place) { location.replace('./#worlds'); return; }
  $('pathBody').textContent = NAMES[body]; $('pathBody').href = `explore.html?body=${body}`;
  let doc, rankUrl;
  if (ownRun) {   // read from the engine
    const id = encodeURIComponent(ownRun), r = await fetch(`${CONFIG.API_BASE}/runs/${id}`);
    if (!r.ok) throw new Error('the engine does not have this result any more; search the place again');
    doc = await r.json(); rankUrl = `${CONFIG.API_BASE}/runs/${id}/files/rank_combined_global.png`;
    const sel = doc.run.target.selection, c = sel && sel.method === 'circle' ? sel.params : null;
    target = c ? `the place at ${Math.abs(c.lat).toFixed(2)}°${c.lat < 0 ? 'S' : 'N'}, ${Math.abs(c.lon).toFixed(2)}°${c.lon < 0 ? 'W' : 'E'}` : 'your place';
    $('pathTarget').textContent = 'Your place'; $('pathTarget').href = `explore.html?body=${body}` + (c ? `&lat=${c.lat}&lon=${c.lon}&r=${c.radius_km}` : '');
    $('pathPlaces').href = $('backToMap').href = `results.html?body=${body}&run=${id}`;
  } else {        // read from the stored files
    const back = new URLSearchParams({ body, target }); if (q.get('construction')) back.set('construction', q.get('construction'));
    $('pathTarget').textContent = target; $('pathTarget').href = `explore.html?body=${body}&target=${encodeURIComponent(target)}`;
    $('pathPlaces').href = $('backToMap').href = 'results.html?' + back;
    const summary = await json(`runs/${body}_summary.json`);
    const runs = summary.filter((r) => r.target === target && r.system === CONFIG.MAIN_SYSTEM);
    const run = runs.find((r) => r.construction === q.get('construction')) || runs.find((r) => r.construction === 'without_composition') || runs[0];
    if (!run) throw new Error(`no result for ${target}`);
    doc = await json(`${run.out_dir}/output.json`); rankUrl = CONFIG.DATA_BASE + doc.rasters.find((r) => r.name === 'rank_combined').views.global;
  }
  const s = doc.sites[place - 1]; if (!s) throw new Error(`this result has no place ${place}`);
  try { countries = (await json('countries.json')).countries; } catch (e) { countries = null; }   // optional: only names the country
  data(doc, s);
  // the outline of the place: traced from the rank picture, as on the map page
  const map = new EarthMap($('tracer'), { left: 0, right: 0, top: 0, bottom: 0 });
  await map.load(CONFIG.BASEMAP('earth'), rankUrl);
  map.setSites(doc.sites.map((x) => ({ lat: x.lat, lon: x.lon, label: String(x.rank) })), doc.run.site_top_share);
  // drawn now, and again whenever the picture box changes size (a resized or newly shown window)
  let size = '', wait = 0;
  new ResizeObserver(() => { const box = $('cardPic'), now = box.clientWidth + 'x' + box.clientHeight; if (now === size) return; size = now; clearTimeout(wait); wait = setTimeout(() => picture(map, map.sites[place - 1]), 120); }).observe($('cardPic'));
}

start().catch((e) => { console.error(e); $('data').innerHTML = `<p class="body"><b>Error.</b> ${esc(e.message)}. Go back to the map and choose a place again.</p>`; });
