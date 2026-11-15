// The only place that names a body, a run or an address.
// On this computer (127.0.0.1) the engine is reached at its public address; on the server it is the same site, under /api.
const LOCAL = ['127.0.0.1', 'localhost', ''].includes(location.hostname);

export const CONFIG = {
  ENABLED_BODIES: ['moon', 'mars'],   // PENDING: the team decides Moon, Mars or both.
  DEFAULT_TARGET: { moon: 'Haworth', mars: 'Jezero crater' },   // names as written in the summary files
  MAIN_SYSTEM: 'all_variables',       // the team's decision of 14 November 2026 (contract/README.md)
  DATA_BASE: './data/',               // the copy of the backend files, same paths as in the repository
  // The live engine (optional). Empty text switches every live feature off; the stored results still work.
  API_BASE: LOCAL ? 'https://54-252-12-127.sslip.io/api' : './api',
  // The large relief picture of each world, as shown on the globe and under the Earth map. These are light copies (WebP)
  // of export/site_assets/<body>/basemap_global.png, made for fast loading; they are pictures only, never read as data.
  // Bodies where the visitor may pick any place on the globe (a circle). It needs the live engine; [] switches it off.
  CUSTOM_BODIES: ['moon'],
  CUSTOM_RADIUS_KM: { min: 10, max: 30, step: 5, start: 15 },   // measured on the server: 20 km takes 47 s, 50 km takes 129 s
  BASEMAP: (body) => `./img/basemaps/${body}.webp`,
  // The picture on a place's page: the sources tried, in order. 'sentinel' = Sentinel-2 cloudless 2020 by EOX (sharp, 10 m;
  // free for non-commercial use with credit). 'bluemarble' = NASA Blue Marble (500 m). For NASA pictures only: ['bluemarble'].
  PLACE_PICTURES: ['sentinel', 'bluemarble'],                       // address of the engine API. Empty = drawing your own target is switched off.
};
export const NSIDE = { earth: 1024, moon: 256, mars: 512 };   // the engine's grid (NSIDE in engine/analog_engine.py)
export const RADIUS_KM = { earth: 6371.0, moon: 1737.4, mars: 3389.5 };   // as in engine/analog_engine.py
