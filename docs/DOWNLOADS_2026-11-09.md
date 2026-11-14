# Downloads and installs for Sherozbek — 9 Nov 2026

Rule: every file goes under `D:\NASA hacathon\sources\<dataset>\` (write-once,
then read-only). Nothing goes into `D:\Projects`. Keep the original file
names. Where a site needs a login it is yours (Earthdata); nothing of mine
ever touches a credential. Sizes are from the hosting pages where stated.

## A. Install (needed for the Mars temperature model)

| what | why | how |
|---|---|---|
| **MSYS2 + gfortran** | build KRC, the Mars 1-D thermal model (Fortran) | https://www.msys2.org/ — install, open the "MSYS2 UCRT64" shell, run `pacman -S mingw-w64-ucrt-x86_64-gcc-fortran mingw-w64-ucrt-x86_64-gcc make`. Then `gfortran --version` in that shell must answer. |
| *Alternative:* **WSL Ubuntu** | same purpose on Linux, where KRC's build is documented | PowerShell as admin: `wsl --install -d Ubuntu`, reboot, then inside Ubuntu `sudo apt install gfortran make`. The machine currently has only the Docker WSL distribution. |

If neither is possible by tomorrow I continue with the Python port of the
same physics; KRC then serves only as the reference to validate against
through its web tool (https://krc.mars.asu.edu/web_tool/).

## B. Downloads — needed for the decided additions

| dataset | destination folder | link | size | login |
|---|---|---|---|---|
| **MODIS albedo, the 10 months that succeeded** (Jan–May, Aug–Dec 2025 calendar means) | `sources\mcd43a3_albedo\` (Aug–Oct are already there) | your Google Drive folder `mcd43a3_albedo` | ~30–40 MB each | your Google account |
| **MODIS albedo June and July** | same folder | re-run the fixed script in section D | | |
| **Mars TES albedo, 8 ppd** | `sources\tes_albedo\` | https://pds-geosciences.wustl.edu/mgs/mgs-m-tes-special-v1/global_albedo_8ppd.img and https://pds-geosciences.wustl.edu/mgs/mgs-m-tes-special-v1/global_albedo_8ppd.lbl | 16 MB | no |
| **Mars TES dust cover index, 16 ppd** | `sources\tes_dci\` | https://www.mars.asu.edu/~ruff/DCI/dci_lo_ice_dust_16ppd_shifted.pds (also save the page https://www.mars.asu.edu/~ruff/DCI/dci.html as dci_page.html) | 66 MB | no |
| **Moon LOLA albedo 1064 nm** | `sources\lola_albedo\` | from https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/cylindrical/float_img/ take `ldam_8_float.img` + `ldam_8_float.lbl`; from .../lola_gdr/polar/float_img/ take `ldam_50s_1000m_float.img` + `.lbl` and `ldam_50n_1000m_float.img` + `.lbl` | 17 MB + 2 × 26 MB | no |
| **Moon polar illumination** | `sources\lola_illumination\` | https://pgda.gsfc.nasa.gov/data/MoonIllumination/AVGVISIB_65S_240M_201608_COG.TIF and the 65N file beside it; also the permanent-shadow (`LPSR_*`) files in the same directory listing https://pgda.gsfc.nasa.gov/products/69 | ~80 MB each | no |
| **Mars dust storm database MDAD v1.1** | `sources\mdad\` | https://zenodo.org/records/7480334 (all files) | 115 MB | no |
| **Earth dust-storm frequency MODFDS, 0.1°** | `sources\modfds\` | https://disc.gsfc.nasa.gov/datacollection/MODFDS_MON_GLB_L3_1.html → data at https://acdisc.gesdisc.eosdis.nasa.gov/data/DustStorm/MODFDS_MON_GLB_L3.1/ — all monthly files for ONE optical-depth threshold (take the lowest), plus the README | ? | Earthdata |
| **Earth land cover MCD12C1, year 2024** | `sources\mcd12c1\` | https://www.earthdata.nasa.gov/data/catalog/lpcloud-mcd12c1-061 → the single 2024 granule | ~ 1 GB total for all years; one file needed | Earthdata |
| **Earth aridity index v3.1** | `sources\aridity\` | https://figshare.com/articles/dataset/Global_Aridity_Index_and_Potential_Evapotranspiration_ET0_Climate_Database_v2/7504448 → `Global-AI_ET0__annual_v3_1.zip` | 646 MB | no |

## C. Downloads — optional, characterization and later work

| dataset | destination | link | size | note |
|---|---|---|---|---|
| Mars geologic map, Tanaka 2014 SIM 3292 GIS | `sources\tanaka2014\` | https://pubs.usgs.gov/sim/3292/ → `SIM3292_database.zip` | ~790 MB | USGS blocks scripts; browser only |
| Unified Geologic Map of the Moon 2020 GIS v2 | `sources\moon_geology\` | https://astrogeology.usgs.gov/search/map/unified_geologic_map_of_the_moon_1_5m_2020 | 224 MB | browser only |
| Mars dune database MGD3 | `sources\mgd3\` | https://doi.org/10.5066/P9ORPZKL | ? | browser only |
| Earth sand dunes GSDS30 | `sources\gsds30\` | https://zenodo.org/records/10441041 → `GSDS30.zip` | 1.1 GB | only if dune presence is wanted |
| Mars MOLA pulse-width roughness 8 ppd | `sources\mola_roughness\` | https://pgda.gsfc.nasa.gov/data/MOLA/ → `MOLA_roughness_slpcor_8ppd.grd` | ? | only if hectometre roughness is wanted |
| Moon LOLA roughness 16 ppd | `sources\lola_roughness\` | .../lola_gdr/cylindrical/img/ `ldrm_16.img` + `.lbl`; polar `ldrm_85s_40m` + `.lbl` | 33 MB | same |
| Earth permafrost probability 1 km (Obu 2019) | `sources\permafrost\` | https://store.pangaea.de/Publications/ObuJ-etal_2018/UiO_PEX_PERPROB_5.0_20181128_2000_2016_NH.zip | 104 MB | characterization |
| Mars subsurface ice SWIM 2.0 | `sources\swim\` | https://swim.psi.edu/SWIM2Products.php → combined ice consistency GeoTIFFs | ? | characterization |
| Gard et al. 2019 whole-rock database | `sources\gard2019\` | https://doi.org/10.5194/essd-11-1553-2019 → supplement / data link in the paper | ? | verifies the Earth composition lookup values |
| Mars Climate Database, local copy | `sources\mcd\` | register at https://www-mars.lmd.jussieu.fr/mars/access.html (e-mail the LMD contacts on that page) | 2–3 GB minimal | only the dust-opacity cycle is needed; the web interface can supply it if registration is slow |

## D. The albedo export, fixed for June and July — SUPERSEDED 9 Nov night: June and July could not be exported; the ten-month build is accepted as final (VARIABLES B29 addendum)

Why it failed: in June and July the Antarctic is in polar night, so whole
MODIS tiles are empty. `unmask(NODATA)` on an image whose footprint is
undefined in those tiles leaves Earth Engine with nothing to anchor the
export on (the same trap HANDOVER §5 item 13 records). Two changes:

1. give every export image a bounded footprint by clipping it to the globe;
2. keep `crs` + `crsTransform` + `dimensions`, no `region`.

Also exported: Band 2 (858 nm) for the Moon pairing, since LOLA albedo is
1064 nm and MODIS shortwave is not the same quantity.

```javascript
// MCD43A3 -> monthly albedo on MOD11C3's 0.05 deg grid, bounded footprint
var DATE_START = '2025-01-01', DATE_END = '2026-01-01';   // calendar 2025 only, like LST
var DRIVE_FOLDER = 'mcd43a3_albedo';
var OUT_SCALE = 10000, NODATA = -9999;
var CRS = 'EPSG:4326', CRS_TRANSFORM = [0.05, 0, -180, 0, -0.05, 90], DIMS = '7200x3600';
var GLOBE = ee.Geometry.Rectangle([-180, -90, 180, 90], null, false);

var col = ee.ImageCollection('MODIS/061/MCD43A3').filterDate(DATE_START, DATE_END);

function prep(img) {
  var okSW = img.select('BRDF_Albedo_Band_Mandatory_Quality_shortwave').lte(1);
  var okB2 = img.select('BRDF_Albedo_Band_Mandatory_Quality_Band2').lte(1);
  return img.select('Albedo_BSA_shortwave').multiply(0.001).updateMask(okSW).rename('bsa')
    .addBands(img.select('Albedo_WSA_shortwave').multiply(0.001).updateMask(okSW).rename('wsa'))
    .addBands(img.select('Albedo_WSA_Band2').multiply(0.001).updateMask(okB2).rename('wsa_b2'))
    .addBands(okSW.unmask(0).rename('ok'))
    .copyProperties(img, ['system:time_start']);
}
var prepped = col.map(prep);

function buildExport(sub) {
  var mean = sub.select(['bsa', 'wsa', 'wsa_b2']).mean();
  var n = sub.select('ok').sum();
  return mean.multiply(OUT_SCALE).round().toInt16()
             .addBands(n.toInt16().rename('n_composites'))
             .unmask(NODATA)
             .clip(GLOBE);                       // <- bounded footprint
}

function submit(sub, label) {
  Export.image.toDrive({
    image: buildExport(sub), description: 'mcd43a3_albedo_' + label,
    folder: DRIVE_FOLDER, fileNamePrefix: 'mcd43a3_albedo_' + label,
    crs: CRS, crsTransform: CRS_TRANSFORM, dimensions: DIMS,
    maxPixels: 1e13, fileFormat: 'GeoTIFF', formatOptions: {noData: NODATA}
  });
}

// only the two months that failed; change the list to run all twelve
[6, 7].forEach(function (m) {
  var sub = prepped.filter(ee.Filter.calendarRange(m, m, 'month'));
  submit(sub, 'clim_m' + (m < 10 ? '0' : '') + m);
});
```

If June or July still fails, the fallback is to export the two months in
two halves by latitude (`GLOBE` replaced by a rectangle for 90N–0 and one
for 0–90S, dimensions 7200x1800 each, `CRS_TRANSFORM` origin at 90 and at
0) — I then stitch them. Note the ten existing files cover Jan 2025 to
Oct 2026, not calendar 2025; the LST layers are calendar 2025. The twelve
files should ideally all be re-exported with `DATE_END = '2026-01-01'` so
albedo and LST share one year. If that is too much, I use what exists and
record the mismatch.

## E. What I am fetching myself (public, no login, script-readable)

- KRC source and documentation, https://oss.mars.asu.edu/svn/krc/trunk/ →
  `sources\krc\` with a manifest of every file's URL and SHA1.
- MCD dust opacity and surface pressure at the 64 × 49 model nodes, from
  the web interface, if the local MCD does not arrive in time.

## F. Added after the first pass (9 Nov, evening)

| what | why | how |
|---|---|---|
| **Portable GCC + gfortran (winlibs), no installer** | the sandbox refused to let me download an executable toolchain; this is the fastest way to a KRC build | download https://github.com/brechtsanders/winlibs_mingw/releases/download/16.2.0posix-23.1.3-14.0.0-ucrt-r3/winlibs-x86_64-posix-seh-gcc-16.2.0-mingw-w64ucrt-14.0.0-r3.zip (264 MB) and unzip it so that `D:\NASA hacathon\tools\winlibs\mingw64\bin\gfortran.exe` exists. No PATH change needed; I call it by full path. MSYS2 (section A) is the alternative. |
| **Mars dust opacity climatology (Montabone et al. 2015)** | the thermal model needs dust opacity per season and latitude; this is the MEASURED (TES/THEMIS/MCS) climatology the MCD itself is built on | https://www-mars.lmd.jussieu.fr/mars/dust_climatology/ → the gridded netCDF files for MY29–MY32 (a typical year is enough; MY28 and MY34 had global storms) into `sources\dust_climatology\` |
| `pip install numba` (optional) | makes the Python thermal model 20–50× faster if the Fortran build fails | in the Python that runs the pipeline |

Already on disk and now used as the validation target: `sources\krc\doc\prt\Mone.prt`,
KRC's own one-point reference run (22 cases with surface kinetic temperature).
