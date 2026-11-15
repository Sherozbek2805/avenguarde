// Explore, stage A: choose a target on the globe or in the list.
// Shapes, names, areas and cell counts come from the backend's catalogue files; nothing is typed by hand.
import { CONFIG, RADIUS_KM, NSIDE } from './config.js';
import { GlobeView, loadImage, pixels, circlePoints } from './globe.js';
import { fmtCoord, fmtSig3, fmtInt } from './format.js';

const $ = (id) => document.getElementById(id);
const RAD = Math.PI / 180;
const BODIES = {
  moon: { name: 'Moon', the: 'the Moon', catalogue: 'catalogue/targets_moon_artemis3.geojson', kind: 'Artemis III candidate regions',
          filter: 'grayscale(1) contrast(1.15) brightness(1.12)', tint: null, maxZoom: 10 },
  mars: { name: 'Mars', the: 'Mars', catalogue: 'catalogue/targets_mars.geojson', kind: 'NASA Exploration Zones',
          filter: 'grayscale(1) contrast(1.1) brightness(1.2)', tint: [232, 168, 124], maxZoom: 9 },   // the design system's Mars colour
};
const params = new URLSearchParams(location.search);
const body = params.get('body');
if (!BODIES[body] || !CONFIG.ENABLED_BODIES.includes(body)) location.replace('./#worlds');   // unknown body, or switched off in js/config.js
const B = BODIES[body], assets = CONFIG.DATA_BASE + 'export/site_assets/';
const state = { chosen: null, hover: null };
let globe, targets = [];
// "Your place": any point of the globe, as a circle. It is searched live by the engine (no stored result).
const CUSTOM = CONFIG.CUSTOM_BODIES.includes(body) && !!CONFIG.API_BASE, RK = CONFIG.CUSTOM_RADIUS_KM;
const CELL_KM2 = 4 * Math.PI * RADIUS_KM[body] ** 2 / (12 * NSIDE[body] ** 2);   // the area of one cell of the engine's grid
let own = null, ghost = null;   // ghost: the circle under the pointer, before a click
const allShapes = () => [...targets.map((t) => t.shape), ...(own ? [own.shape] : []), ...(ghost ? [ghost] : [])];
function ownPlace(lon, lat, r) {
  const points = circlePoints(lon, lat, r, RADIUS_KM[body]), area = Math.PI * r * r;
  if (!own) { own = { custom: true, name: 'Your place', shape: { label: 'Your place', state: 'idle', nohit: true } }; own.shape.target = own; }   // nohit: a click on it moves it
  Object.assign(own, { lon, lat, r, area, cells: Math.max(1, Math.round(area / CELL_KM2)) });
  Object.assign(own.shape, { points, center: [lon, lat] });
  ghost = null; globe.setShapes(allShapes());
  return own;
}

function setUrl() {
  const q = new URLSearchParams({ body }), c = state.chosen;
  if (c && c.custom) { q.set('lat', c.lat.toFixed(2)); q.set('lon', c.lon.toFixed(2)); q.set('r', c.r); } else if (c) q.set('target', c.name);
  history.replaceState(null, '', '?' + q);
}

function paint() {
  for (const t of own ? [...targets, own] : targets) {
    t.shape.state = t === state.chosen ? 'chosen' : t === state.hover ? 'hover' : 'idle';
    if (!t.row) continue;
    t.row.setAttribute('aria-pressed', String(t === state.chosen));
    t.row.classList.toggle('is-hover', t === state.hover && t !== state.chosen);
  }
  globe.dirty = true;
  const c = state.chosen;
  $('pathTarget').textContent = c ? c.name : 'Choose a target';
  $('goSearch').disabled = !c;
  $('chosenLine').innerHTML = c
    ? c.custom ? `<b>${c.name}</b> <span class="value">· ${fmtSig3(c.area)} km² · about ${fmtInt(c.cells)} cells</span>`   // its coordinates are in the two boxes below
      : `<b>${c.name}</b><br><span class="value">${fmtCoord(c.lat)}°, ${fmtCoord(c.lon)}° · ${fmtSig3(c.area)} km² · ${fmtInt(c.cells)} cells</span>`
    : 'No target chosen yet.';
  document.title = `${c ? c.name + ' · ' : ''}${B.name} · Terrestrial Analog Finder`;
  const mine = !!(c && c.custom);
  $('pickBox').hidden = !mine; $('chosenLine').classList.toggle('chosen--one', mine);
  if (mine) {
    $('pickRadius').value = c.r; $('pickOut').textContent = `${c.r} km`;
    for (const [el, v] of [[$('pickLat'), c.lat], [$('pickLon'), c.lon]]) if (document.activeElement !== el) el.value = v.toFixed(2);
    $('pickNote').textContent = 'Click the globe to move the circle. A new place is searched live in about a minute.';
  }
}

function choose(t, fly = true) {
  state.chosen = t; setUrl(); paint();
  if (!t || !fly) return;
  if (t.custom) {   // come close enough to see the circle, and never move away from a closer view
    const a = t.r / RADIUS_KM[body];
    globe.flyTo(t.lat, t.lon, Math.max(globe.zoom, Math.min(5, 34 / (0.42 * Math.min(globe.w, globe.h) * a))));
    return;
  }
  // turn to the target and come closer, but stay far enough that the globe still reads as a sphere
  const angle = Math.sqrt(t.area / Math.PI) / RADIUS_KM[body];
  globe.flyTo(t.lat, t.lon, Math.max(globe.home.zoom, Math.min(1.5, 64 / (0.42 * Math.min(globe.w, globe.h) * angle))));
  t.row?.scrollIntoView({ block: 'nearest' });
}

function status(lonlat) {
  $('statusPos').textContent = lonlat ? `Latitude ${fmtCoord(lonlat[1])}°  ·  Longitude ${fmtCoord(lonlat[0])}°` : 'Move the pointer over the globe';
}
function scale() {   // a bar of a round number of kilometres, about 120 px long
  const kmPerPx = RADIUS_KM[body] / globe.R, raw = 120 * kmPerPx, p = Math.pow(10, Math.floor(Math.log10(raw)));
  const km = [1, 2, 5, 10].map((k) => k * p).filter((k) => k <= raw).pop();
  $('scaleBar').style.width = `${km / kmPerPx}px`; $('scaleText').textContent = `${fmtInt(km)} km`;
}

async function start() {
  $('pathBody').textContent = B.name;
  const other = body === 'moon' ? 'mars' : 'moon', sw = $('switchBody');
  if (CONFIG.ENABLED_BODIES.includes(other)) { sw.textContent = `Switch to ${BODIES[other].name}`; sw.href = `?body=${other}`; } else sw.hidden = true;

  const cat = await (await fetch(assets + B.catalogue)).json();
  $('sideIntro').textContent = `${cat.features.length} ${B.kind} on ${B.the}. Pick one on the globe or in the list.${CUSTOM ? ' Or click any other place on the globe to search your own.' : ''}`;
  targets = cat.features.map((f, i) => {
    const p = f.properties, [lon, lat] = f.geometry.coordinates;
    const points = p.geometry_type === 'polygon' ? p.vertices_lonlat : circlePoints(lon, lat, p.radius_km, RADIUS_KM[body]);
    const t = { name: p.name, lon, lat, area: p.area_km2, cells: p.cells, shape: { points, center: [lon, lat], label: String(i + 1), state: 'idle' } };
    t.shape.target = t;
    const li = document.createElement('li'), row = document.createElement('button');
    row.type = 'button'; row.className = 'row';
    row.innerHTML = `<span class="row__n">${i + 1}</span><span>${p.name}</span><span class="value">${fmtSig3(p.area_km2)} km²</span>`;
    row.setAttribute('aria-label', `Target ${i + 1}: ${p.name}, ${fmtSig3(p.area_km2)} square kilometres`);
    row.addEventListener('click', () => choose(t));
    row.addEventListener('pointerenter', () => { state.hover = t; paint(); });
    row.addEventListener('pointerleave', () => { state.hover = null; paint(); });
    row.addEventListener('focus', () => { state.hover = t; paint(); });
    row.addEventListener('blur', () => { state.hover = null; paint(); });
    li.append(row); $('targetList').append(li); t.row = row;
    return t;
  });

  // Opening view: the whole globe, as a lit sphere, turned so the default target faces the viewer.
  // A target near a pole is kept a little away from the edge, so it is not seen edge-on.
  const def = targets.find((t) => t.name === CONFIG.DEFAULT_TARGET[body]) || targets[0];
  const view = { lat: Math.max(-62, Math.min(62, def.lat)), lon: def.lon, zoom: 1.12 };
  globe = new GlobeView($('globe'), { ...view, minZoom: 0.8, maxZoom: B.maxZoom, offsetX: 372 });
  globe.setShapes(targets.map((t) => t.shape));
  globe.onhover = (shape, lonlat) => {
    const t = shape ? shape.target : null; if (t !== state.hover) { state.hover = t; paint(); }
    globe.over.classList.toggle('is-target', !!t); globe.over.classList.toggle('can-pick', CUSTOM && !t && !!lonlat); status(lonlat);
    if (!CUSTOM) return;   // the circle that a click would place, at the chosen radius
    ghost = !t && lonlat ? { points: circlePoints(lonlat[0], lonlat[1], own ? own.r : RK.start, RADIUS_KM[body]), center: lonlat, label: null, state: 'hover', nohit: true } : null;
    globe.setShapes(allShapes());
  };
  globe.onpick = (shape, lonlat) => {
    if (shape) choose(shape.target);
    else if (CUSTOM && lonlat) choose(ownPlace(lonlat[0], lonlat[1], own ? own.r : RK.start));   // any other point: your own place
  };
  if (CUSTOM) {
    const pr = $('pickRadius'); pr.min = RK.min; pr.max = RK.max; pr.step = RK.step;
    pr.addEventListener('input', () => { if (own) { ownPlace(own.lon, own.lat, Number(pr.value)); setUrl(); paint(); } });
    $('pickTicks').innerHTML = [0, 1, 2, 3, 4].map((i) => `<span>${RK.min + (RK.max - RK.min) * i / 4}${i === 4 ? ' km' : ''}</span>`).join('');
    const typed = () => {   // coordinates typed by hand
      const la = Number($('pickLat').value), lo = Number($('pickLon').value);
      if (own && $('pickLat').value !== '' && $('pickLon').value !== '' && Math.abs(la) <= 90 && Math.abs(lo) <= 180) choose(ownPlace(lo, la, own.r));
    };
    $('pickLat').addEventListener('change', typed); $('pickLon').addEventListener('change', typed);
  }
  globe.onview = scale;
  $('zoomIn').addEventListener('click', () => globe.zoomBy(1.6));
  $('zoomOut').addEventListener('click', () => globe.zoomBy(1 / 1.6));
  $('resetView').addEventListener('click', () => globe.reset());

  $('goSearch').addEventListener('click', () => {
    const c = state.chosen; if (!c) return;
    location.href = c.custom ? `results.html?body=${body}&lat=${c.lat.toFixed(2)}&lon=${c.lon.toFixed(2)}&r=${c.r}` : `results.html?body=${body}&target=${encodeURIComponent(c.name)}`;
  });
  const asked = targets.find((t) => t.name === params.get('target'));
  paint();

  // the picture: the body's global relief, wrapped on the sphere
  globe.setTextures({ global: pixels(await loadImage(CONFIG.BASEMAP(body)), 2880, 1440, B.filter, B.tint) });
  // a target is always chosen, so the search button is ready at once. The default one does not move the globe: the whole sphere stays in view.
  const la = Number(params.get('lat')), lo = Number(params.get('lon')), rr = Number(params.get('r'));   // a link back to "your place"
  if (CUSTOM && params.get('lat') != null && params.get('lon') != null && Math.abs(la) <= 90 && Math.abs(lo) <= 360 && rr >= RK.min && rr <= RK.max) choose(ownPlace(lo, la, rr));
  else if (asked) choose(asked); else choose(def, false);
}

start().catch((e) => { console.error(e); $('sideIntro').textContent = 'Error: the target list could not be read. Check that the data folder is in place and reload.'; });
