// Names for a place on Earth. Nothing is typed by hand here: a name comes from a file, or the place has none.
//   data/known_regions.json  a copy of runs/known_regions.json: the backend's rough boxes around known analog regions
//   data/countries.json      country outlines (Natural Earth)
// Both files are optional. Without them a place is shown by its coordinates.
import { CONFIG } from './config.js';

let countries = null, regions = null, ready = null;
const get = (f) => fetch(CONFIG.DATA_BASE + f).then((r) => (r.ok ? r.json() : null)).catch(() => null);

export function loadNames() {
  ready = ready || Promise.all([get('countries.json'), get('known_regions.json')]).then(([c, k]) => { countries = c ? c.countries : null; regions = k ? k.regions : null; });
  return ready;
}
// "19.43°N, 155.57°W"
export const coords = (lat, lon) => `${Math.abs(lat).toFixed(2)}°${lat < 0 ? 'S' : 'N'}, ${Math.abs(lon).toFixed(2)}°${lon < 0 ? 'W' : 'E'}`;
// the known analog region whose box holds the point, or null
export function regionAt(lon, lat) {
  if (!regions) return null;
  for (const [name, b] of Object.entries(regions)) if (lat >= b.lat_min && lat <= b.lat_max && lon >= b.lon_min && lon <= b.lon_max) return name;
  return null;
}
// the country whose outline holds the point, or null (sea, or no file)
export function countryAt(lon, lat) {
  if (!countries) return null;
  const inRing = (ring) => {
    let lo = 180, hi = -180; for (const p of ring) { if (p[0] < lo) lo = p[0]; if (p[0] > hi) hi = p[0]; }
    const wrap = hi - lo > 180, X = (x) => (wrap && x < 0 ? x + 360 : x), px = X(lon);   // an outline that crosses the 180° line (Fiji, Russia) is unwrapped first
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) { const xi = X(ring[i][0]), yi = ring[i][1], xj = X(ring[j][0]), yj = ring[j][1]; if ((yi > lat) !== (yj > lat) && px < (xj - xi) * (lat - yi) / (yj - yi) + xi) inside = !inside; }
    return inside;
  };
  const hit = countries.find((c) => c.g.some(inRing)); return hit ? hit.n : null;
}
