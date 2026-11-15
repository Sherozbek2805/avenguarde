# SOURCES — context sources and what they are NOT for

Written 2026-11-08. This file exists so that a source logged for one purpose
is not later mistaken for a route to another.

## Stratigraphic geologic maps — CONTEXT ONLY, NOT A COMPOSITION ROUTE

| source | what it is | what it is NOT |
|---|---|---|
| **USGS Unified Geologic Map of the Moon** — Fortezzo, Spudis & Harrel (2020) | Stratigraphic units: age-based geologic mapping of the lunar surface | **NOT compositional.** It carries no SiO2 and no FeO and cannot be converted to them. |
| **Geologic Map of Mars** — Tanaka et al. (2014), USGS SIM 3292 | Stratigraphic units: age-based geologic mapping of the martian surface | **NOT compositional.** Same limitation. |

**Purpose in this project:** describing and naming target sites in Step 5 and
in the write-up — "this candidate sits in the Imbrian-aged ejecta of ...".
They give a unit NAME and an AGE, which is what a reader of the results
wants, and they give nothing a distance metric can consume.

**The composition route is elsewhere and is already built:**

- Earth: GLiM lithology -> `sources/glim_composition_lookup.csv` ->
  `earth_SiO2`, `earth_FeO`. See VARIABLES.md B16, B19.
- Moon: Lunar Prospector GRS 2 degree -> `moon_SiO2`, `moon_FeO`, with the
  published error matrix. See VARIABLES.md B20, B22.
- Mars: MGS TES mineral maps (Bandfield 2002) -> `mars_SiO2`, `mars_FeO`, where the maps have data. See VARIABLES.md B27c and the table of 9 Nov below. ~~NOT BUILT. Option (b) was chosen; see VARIABLES.md B20.~~

**Do not attempt to derive oxide abundances from either geologic map.** Age is
not composition. A Hesperian lava plain and an Amazonian lava plain can have
the same chemistry, and two Noachian units can differ completely.

## Dead files

See `cube/dead_files.json` for files on disk that look like data and are not —
most importantly the Clementine FeO GeoTIFF, which is an RGB colour rendering
covering only +/-70 degrees.

## Köppen-Geiger — CHARACTERIZATION ONLY, NEVER A DIMENSION

| source | what it is | what it is NOT |
|---|---|---|
| **Beck et al. (2023)**, Scientific Data 10, 724, doi:10.1038/s41597-023-02549-6 — 1991–2020 period, 30 arc-second GeoTIFF, uint8 codes 1..30 | The standard climate classification: BWh hot desert, ET tundra, EF ice cap. Makes a found site readable in one phrase in step 9. | **NOT a matching dimension, permanently.** The Moon and Mars have no Köppen class. `matching_eligible: false` on the manifest entry. |

On disk: `sources/koppen_geiger/` (copied from `D:\Projects\koppen_geiger_tif\1991_2020`,
SHA1 verified, manifest beside it). Built as `earth_koppen_class` by
`build/koppen.py` — majority vote, winning share as support, 100.000% of the
reference population classified. Legend in `cube/koppen_legend.json`.
The 2041–2070 and 2071–2099 folders in the original are CMIP6 projections and
are not used. See VARIABLES.md B25(b).

## GLiM lithology — FILTER and composition ROUTE, not a dimension itself

`earth_lithology_l3` / `earth_lithology_l1` (manifest entries written 9 Nov,
VARIABLES.md B25(c)) are the categorical class layers. They serve the water
mask, the SiO₂/FeO lookup and a step-9 filter. The class id itself never
ranks: Moon and Mars have no map in this vocabulary.

## Added 9 Nov 2026 — Mars thermal and composition, Earth albedo (VARIABLES.md B27)

| source | what it is | used for | what it is NOT |
|---|---|---|---|
| **MGS TES thermal inertia**, Putzig & Mellon (2007), PDS MGS-M-TES-5-TIMAP-V1.0, `mgst_9001 (2)/.../data/global_ti_{night,day}_2007.img` + masks, 20 ppd (2.96 km), MSB int16, tiu | measured-then-modelled thermal inertia, three Mars years, nightside and dayside | `mars_thermal_inertia` (candidate dimension), `mars_thermal_inertia_day` (diagnostic) | not a temperature; infilled pixels (mask = 0) excluded |
| **MGS TES mineral maps**, Bandfield (2002), JMARS exports `Mars lithology/TES_*_numeric`, 4 ppd (14.8 km), VICAR float32, −1 = no data; official 13-band file at http://tes.asu.edu/mineral_map/TES_mineral_maps_4_ppd.envi (sulfate, carbonate bands not on disk) | areal end-member fractions on warm, dust-free surfaces | `mars_SiO2`, `mars_FeO` through the tagged end-member table in `build/composition_mars.py` | not wt% chemistry; coarser than the pixel; dust is a mask not a component |
| **MODIS MCD43A3 albedo**, GEE export, `sources/mcd43a3_albedo/mcd43a3_albedo_clim_mMM.tif`, 0.05°, int16 ×1e-4, bands bsa/wsa/n_composites | monthly 2025 blue-sky shortwave albedo | Earth apparent thermal inertia, `build/phase3e_earth_ati.py` — **built 9 Nov night from 10 months (June, July missing; B29)** | valid where n_composites > 0 only; scale is 1e-4 on this export, not MCD43A3's 0.001 |

### Examined and declined (reasons in VARIABLES.md B27d)

OMEGA Ody 2012 global band-depth maps (40 ppd) · OMEGA Riu 2019 M3 abundance maps (links dead, partial) · CRISM MRDR v4 summary products (181 m, indices, ~1 TB) · Odyssey GRS elements (2–10° bins) · TES Dust Cover Index (16 ppd; a candidate characterization layer, not chemistry) · THEMIS Day/Night IR mosaics (stretched 8-bit) · THEMIS 100 m quantitative TI (±60°, 60 GB, redundant with TES at this pixel) · MCS and EMIRS surface temperature (degrees-scale).

## Added 9 Nov 2026, late — inputs of the modelled Mars temperature (VARIABLES.md B28)

| source | what it is | used for | what it is NOT |
|---|---|---|---|
| **KRC thermal model**, Kieffer (2013) JGR Planets 118:451, `sources/krc/` (public svn trunk, 235 files, manifest with SHA1) | Fortran 1-D surface heat-balance model, the one the TES thermal-inertia maps were made with; `doc/prt/Mone.prt` is its one-point reference output | the physics ported to `build/mars_thermal_1d.py`; `Mone.prt` is the validation target (median 1.4 K) | not built here (no compiler); licence not stated, "available for general use" |
| **MGS TES bolometric albedo 8 ppd**, Christensen et al. (2001), `sources/tes_albedo/` | 7.41 km, PC_REAL, global, clipped by its producers to 0.06–0.32 | thermal-model input; `mars_albedo` characterization layer | not a ranking dimension (decision of 9 Nov) |
| **Dust optical depth climatology v2**, Montabone et al. (2015) Icarus 251:65, `sources/dust_climatology/` MY29–MY32 | daily 3° kriged maps of 9.3 µm absorption CDOD at 610 Pa, the MCD's own dust scenarios | per-season dust opacity in the model, converted to visible at 546 Pa by an ASSUMED ×2.6 | not the observed year; storm years (MY25, MY28, MY34) deliberately not used |
| **Mars Climate Database** (web, v6.1 design document) | GCM surface temperature on a 5.6 × 3.75° grid | the coarse-scale check of the modelled layers (r ≈ 0.98); its three layers were overwritten | cannot be sharpened: its high-resolution mode leaves surface temperature untouched (DDD §7.3.1) |

## Added 10 Nov 2026 — Antarctic geology and the check of the composition lookup (VARIABLES.md B31)

| source | what it is | used for | what it is NOT |
|---|---|---|---|
| **SCAR GeoMAP v.2022-08**, Cox et al. (2023) Sci. Data 10, 250, doi:10.1038/s41597-023-02152-9; data doi:10.1594/PANGAEA.951482, CC-BY-4.0. `sources/geomap/ATA_SCAR_GeoMAP_v2022_08_QGIS.zip` (196,265,158 bytes, MD5 b955696dd8ad5fce4ee514d362787db9, matches PANGAEA) | 99,080 polygons of exposed rock and surficial deposits in Antarctica **and South Georgia**, compiled at 1:250,000, EPSG:3031. 41,648 km² rock, 8,925 km² moraine, 1,007 km² seasonal water and ice (planar) | `earth_geomap_lithcode`, `_simpcode`, `_support`, `_rock_fraction` (`build/geomap_antarctica.py`); the rock class behind `earth_SiO2` / `earth_FeO` on 15,587 pixels south of 53°S | not a map of the ice sheet; "ice" polygons are seasonal water and refrozen melt; 549 km² is "unknown rock" and gets no composition |
| **Gard, Hasterok & Halpin (2019)** global whole-rock geochemical database, Earth Syst. Sci. Data 11, 1553–1566, doi:10.5194/essd-11-1553-2019; data v1.1.0 doi:10.5281/zenodo.3359791, CC-BY-4.0. `sources/gard2019/complete.zip` (192,615,473 bytes, MD5 9b97b54887ee7184c6650c845b4e92d4, matches Zenodo), plus `rockgroup.csv` and the Zenodo record JSON | 1,022,092 analysed rock samples with major oxides, rock names and classes; 665,114 usable SiO₂ and 430,750 usable total-iron values | the CHECK of the lookup values (`build/gard_verify.py` → `cube/gard_verification.json`); the measured median for the two GeoMAP classes GLiM has no row for (quartzite, metavolcanic) | not a map; samples are where geologists went, not an area-weighted average of the crust |

Derived tables, both in `sources/` (write-once): `glim_composition_lookup_v2.csv` (the 98 v1 rows, **no value changed**, with the measured p25 / median / p75 and a verdict per row) and `geomap_composition_lookup.csv` (25 GeoMAP rock classes → wt%). Written by `build/composition_lookup_v2.py`. `glim_composition_lookup.csv` (v1) is kept untouched.

Download note: Zenodo's API file links closed two transfers abruptly on 10 Nov. `build/fetch_gard2019.sh` resumes and accepts the file only on a matching MD5. Two truncated partial files from the first attempt (`major.csv`, `computed.csv`) were deleted; they were never read.

## Added 10 Nov 2026, late — the preset targets (VARIABLES.md B32)

| source | what it is | used for | what it is NOT |
|---|---|---|---|
| **Artemis III candidate landing regions, 2024**, LROC QuickMap layer "A3: Candidate Landing Regions 2024", https://files.actgate.com/lunar/A3_9regions-lonlat-simplified.geojson (3,545 bytes, Last-Modified 28 Oct 2024, MD5 9d7a9b2c296dca3da3c4ba8463f7027e). `sources/artemis3_regions_2024/`, with the 2022 thirteen-region file beside it | the nine regions of NASA's 28 Oct 2024 update as four-corner polygons, rectangles in south polar stereographic | `sources/targets_moon_artemis3_v2.csv` → `contract/targets_moon.json` | not hosted on nasa.gov; no licence stated in the file; NASA's release itself has a map image and no coordinates. The USGS navigational-grid release (doi:10.5066/P1MEQ6UK, CC0) says its regions came from the same QuickMap layer; it was not opened |
| **NASA First Landing Site / Exploration Zone Workshop for Human Missions to the Surface of Mars**, LPI Houston, October 2015; abstracts at https://www.hou.usra.edu/meetings/explorationzone2015/pdf/NNNN.pdf; EZ definition in NASA's First Announcement | 44 proposed Exploration Zones with a centre written in the abstract | `sources/mars_site_candidates_v1.csv` (all), `sources/targets_mars_v1.csv` (six presets) → `contract/targets_mars.json`. Text extracts of the six abstracts in `sources/mars_ez_2015/` | conference abstracts, not a NASA decision; no abstract states the latitude type; NASA never down-selected these zones |
| **Golombek et al. (2021)**, LPSC abstract 2420, Table 1 | seven SpaceX / JPL candidate Starship landing sites in Arcadia, Erebus and Phlegra | listed in `mars_site_candidates_v1.csv`; the reason Erebus Montes was chosen over the other Arcadia proposals | not a preset itself |

`sources/artemis3_regions.csv` (IAU feature centres as proxies, B24) is kept and superseded.

## Added 15 Nov 2026 — the primary datasets in one table

Every ranking layer comes from one of these. The sections above say what the other sources are for and what they are not for. Each provider's own terms of use apply.

| world | dataset and product | reference | used for | where it enters |
|---|---|---|---|---|
| Moon | LRO LOLA global elevation model, `LOLA_Global_LDEM_118m_Mar2014` (118 m) | Smith et al. (2010), NASA PDS / USGS Astrogeology | the eight terrain measures | `build/phase1_dems.py` |
| Moon | LRO Diviner global cumulative products, `LRO-L-DLRE-5-GCP-V1.0` | Paige et al. (2010); Williams et al. (2017), NASA PDS | temperature level, day–night swing | `build/fetch_diviner_gcp.py` |
| Moon | Lunar Prospector GRS element abundances, `lp-l-grs-5-elem-abundance-v1`, 2° | Prettyman et al. (2006), NASA PDS | SiO2, FeO | VARIABLES.md B20, B22 |
| Mars | MOLA – HRSC blended elevation model, `Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2` (200 m; MGS MOLA with ESA Mars Express HRSC) | Fergason et al. (2018), USGS Astrogeology | the eight terrain measures | `build/phase1_dems.py` |
| Mars | MGS TES thermal inertia, `MGS-M-TES-5-TIMAP-V1.0`; TES bolometric albedo; dust climatology v2; KRC thermal model | Putzig & Mellon (2007); Christensen et al. (2001); Montabone et al. (2015); Kieffer (2013) | temperature level and swings, MODELLED | VARIABLES.md B27, B28 |
| Mars | MGS TES mineral maps | Bandfield (2002) | SiO2, FeO, where the maps have data | VARIABLES.md B27c |
| Earth | ETOPO 2022, 15 arc-second | NOAA NCEI (2022) | the eight terrain measures | `build/phase1_dems.py` |
| Earth | MODIS land surface temperature, MOD11C3 and MYD11C3 (Terra, Aqua), monthly, 0.05° | Wan et al., NASA LP DAAC | temperature level and swings | `build/` thermal scripts |
| Earth | MODIS albedo MCD43A3 | Schaaf & Wang, NASA LP DAAC | apparent thermal inertia (stored, not ranked) | VARIABLES.md B27 |
| Earth | WorldClim 2.1 | Fick & Hijmans (2017) | the land mask | `build/phase1_dems.py` |
| Earth | GLiM lithological map; SCAR GeoMAP; global whole-rock geochemical database | Hartmann & Moosdorf (2012); Cox et al. (2023); Gard et al. (2019) | SiO2 and FeO per rock class, and the check of those values | VARIABLES.md B16, B19, B31 |
| Earth | Köppen–Geiger climate classes | Beck et al. (2023) | describing sites; never ranked | `build/koppen.py` |
| Earth | USGS terrestrial analog sites catalogue, doi:10.5066/P9J72921 | USGS Astrogeology | the 'known site' label within 100 km | `sources/tier4_catalogues/` |
| targets | NASA Artemis III candidate landing regions, update of 28 October 2024; region polygons as published by LROC QuickMap | NASA; LROC | the nine lunar targets | VARIABLES.md B32 |
| targets | NASA First Landing Site / Exploration Zone Workshop for Human Missions to the Surface of Mars, 2015 | NASA; LPI | the six Mars targets | VARIABLES.md B32 |

