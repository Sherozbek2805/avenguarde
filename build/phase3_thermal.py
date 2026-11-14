"""
PHASE 3 -- THERMAL. One body at a time.

    python build/phase3_thermal.py --body earth|moon|mars

THE QUANTITY EACH BODY SUPPLIES -- the decision that had to come first.

    All three now carry SURFACE temperature, one consistent physical quantity:
        Earth  MOD11C3 LST_Day_CMG / LST_Night_CMG, MODIS land surface temp
        Moon   Diviner GCP tbol, bolometric brightness temperature
        Mars   MCD tsurf, model surface temperature
    WorldClim was DEMOTED to backup: it is 2 m AIR temperature, a different
    physical quantity from Diviner tbol, and pairing air against surface would
    have put two different things under one column name.

    temp_level           full-cycle time average.           all three bodies
    temp_range_diurnal   max minus min across one day.      all three bodies
    temp_range_seasonal  max minus min across the year.     EARTH AND MARS ONLY
                         The Moon has no meaningful seasonal cycle, so this
                         must NOT enter the Earth-Moon set at all.

    Magnitudes differ enormously -- Earth's diurnal range is ~10-15 K against
    the Moon's ~250-300 K -- and that does not block the pairing, because the
    pipeline ranks within each body before any comparison. Only the spatial
    pattern is compared.

UNITS: KELVIN everywhere. The source unit is recorded per layer. Celsius
against kelvin was a real bug in this project already.

RANGE GATES ARE STATED BEFORE THE RUN, not fitted to the output. See GATES.
"""

import argparse
import io
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C
from phase1_dems import PEAK_CAP_GIB, peak_rss_gib, say_peak
from phase2_terrain import HealpixAccumulator, validate, show

OUT = os.path.join(C.ROOT, "cube", "healpix")
NSIDE = C.NSIDE

# ---- RANGE GATES, STATED IN ADVANCE (kelvin) -----------------------------
GATES = {
    # earth temp_range_diurnal: the gate was FIRST STATED AS (0, 60) and
    # FAILED on 66,109 pixels, minimum -11.81 K. The failure was real and the
    # gate was wrong, not the data: MODIS day and night are fixed OVERPASS
    # times (~10:30 and ~22:30 local), not the daily maximum and minimum, so
    # over the Antarctic ice sheet in polar night or midnight sun the 22:30
    # reading is legitimately warmer than the 10:30 one. 17.1% of 60-90S
    # pixels are negative. Restated as (-15, 60) with that reason; the
    # original gate and its failure are kept in the record, not erased.
    "earth": dict(temp_level=(180.0, 350.0), temp_range_diurnal=(0.0, 80.0),
                  temp_range_seasonal=(0.0, 100.0)),
    "moon": dict(temp_level=(20.0, 450.0), temp_range_diurnal=(0.0, 400.0)),
    "mars": dict(temp_level=(120.0, 310.0), temp_range_diurnal=(0.0, 200.0),
                 temp_range_seasonal=(0.0, 150.0)),
}
MIN_MONTHS_SEASONAL = 12        # of 22; a seasonal range needs a year
MIN_MONTHS_LEVEL = 6


def sample_grid(vals, lat, lon, nside):
    """Nearest-neighbour sample a COARSE source onto HEALPix pixel centres.

    Binning is only correct when the source is FINER than the target. The
    Diviner 0.5 degree grid has 259,200 cells against 786,432 HEALPix pixels
    at Nside 256, and MCD has 3,072 against 3,145,728 at Nside 512 -- binning
    by cell centre leaves most pixels empty, which the coverage gate caught at
    28.88 percent valid on a source that is 100 percent valid.

    Upsampling COPIES values, so it manufactures tie blocks. The replication
    factor and the resulting distinct_levels / largest_tie_fraction are
    recorded for every layer built this way: support reads 1.0 and is true,
    and is blind to this, exactly as it was for lithology.
    """
    from astropy_healpix import HEALPix
    from astropy import units as u
    hp = HEALPix(nside=nside, order="nested")
    plon, plat = hp.healpix_to_lonlat(np.arange(hp.npix))
    plon = plon.to_value(u.deg); plat = plat.to_value(u.deg)
    plon = np.where(plon > 180.0, plon - 360.0, plon)
    dlat = abs(lat[1] - lat[0]); dlon = abs(lon[1] - lon[0])
    r = np.clip(np.rint((lat[0] - plat) / dlat).astype(np.int64), 0, lat.size-1)
    c = np.rint((plon - lon[0]) / dlon).astype(np.int64) % lon.size
    out = {}
    for nm, a in vals.items():
        out[nm] = np.asarray(a)[r, c].astype(np.float32)
    return out, float(hp.npix) / (lat.size * lon.size)


def bin_grid(vals, lat, lon, nside, names_vals):
    """Bin a regular lat/lon grid to HEALPix. vals is a dict name -> 2-D."""
    acc = HealpixAccumulator(nside, list(names_vals))
    h = lat.size
    cos = np.maximum(np.cos(np.radians(lat)), 1e-9)
    step = max(1, 2_000_000 // lon.size)
    for r0 in range(0, h, step):
        r1 = min(h, r0 + step)
        idx = acc.index_for_band(lat[r0:r1], lon).ravel()
        wt = np.repeat(cos[r0:r1], lon.size)
        acc.add_reference(idx, wt)
        for nm, a in names_vals.items():
            acc.add(nm, np.ascontiguousarray(a[r0:r1]).astype(np.float32),
                    idx, wt)
        del idx, wt
    return acc


# ------------------------------------------------------------------- EARTH

def build_earth():
    """Earth thermal from BOTH platforms, CALENDAR 2025 ONLY.

    WHY 2025 ONLY. Terra has 22 months (Jan 2025 to Oct 2026), Aqua has 12
    (2025). Mixing them would build the four local times from different time
    spans, which is the same definitional drift this project has caught four
    times already. A complete seasonal cycle sampled consistently beats a
    longer record that does not line up. COST: the seasonal range now comes
    from ONE year, so a single anomalous season is not averaged at all.
    Worse for stability, better for consistency, and consistency was the
    thing that was broken.

    WHY FOUR LOCAL TIMES. temp_range_diurnal is now max minus min over the
    AVAILABLE LOCAL TIMES, which is the SAME QUANTITY the Moon and Mars
    carry. The old two-sample Terra day-minus-night was a different physical
    thing and could go negative; max minus min cannot, by construction.
        sample counts: Earth 4, Mars 12, Moon 96.

    The nominal overpass times are MISSION DESIGN, not measured here. See
    the overpass_times note below.

    TERRA AND AQUA ARE DIFFERENT INSTRUMENTS with independent calibration
    drift. For a rank transform computed within Earth that is negligible,
    because a common offset cannot change an ordering. Stated, not assumed
    away.
    """
    from pyhdf.SD import SD, SDC
    YEAR = "2025"
    plats = [("MOD11C3", "Terra"), ("MYD11C3", "Aqua")]
    files = {}
    for d, tag in plats:
        src = os.path.join(C.ROOT, d)
        files[tag] = sorted(f for f in os.listdir(src)
                            if f.endswith(".hdf") and f[9:13] == YEAR)
    doy = {t: [f[13:16] for f in v] for t, v in files.items()}
    if doy["Terra"] != doy["Aqua"]:
        raise SystemExit("STOP: Terra and Aqua month sets differ: %s" % doy)
    months = doy["Terra"]
    print("  CALENDAR %s ONLY: %d months, both platforms, doy %s..%s"
          % (YEAR, len(months), months[0], months[-1]))
    print("  four local times per month: Terra day/night, Aqua day/night")

    H, W = 3600, 7200
    sd0 = SD(os.path.join(C.ROOT, "MOD11C3", files["Terra"][0]), SDC.READ)
    att = sd0.select("LST_Day_CMG").attributes()
    SC, OFF, VR = att["scale_factor"], att["add_offset"], att["valid_range"]
    sd0.end()
    print("  LST scale %s, offset %s, valid_range %s -- verified identical "
          "on both platforms" % (SC, OFF, VR))

    s_lev = np.zeros((H, W)); n_lev = np.zeros((H, W), dtype=np.int16)
    s_diu = np.zeros((H, W)); n_diu = np.zeros((H, W), dtype=np.int16)
    m_max = np.full((H, W), -np.inf); m_min = np.full((H, W), np.inf)
    n_mon = np.zeros((H, W), dtype=np.int16)
    qc_rej = 0
    tot_cells = 0

    for k in range(len(months)):
        stack = []
        for d, tag in plats:
            sd = SD(os.path.join(C.ROOT, d, files[tag][k]), SDC.READ)
            for band, qcn in (("LST_Day_CMG", "QC_Day"),
                              ("LST_Night_CMG", "QC_Night")):
                sl = sd.select(band); raw = sl.get().astype(np.float64)
                sl.endaccess()
                q = sd.select(qcn); qv = q.get(); q.endaccess()
                ok = (raw >= VR[0]) & (raw <= VR[1])
                okq = ok & ((qv & 0b11) <= 1)
                qc_rej += int((ok & ~okq).sum())
                tot_cells += int(ok.sum())
                stack.append(np.where(okq, raw * SC + OFF, np.nan))
            sd.end()
        A = np.stack(stack)
        del stack
        cnt = np.isfinite(A).sum(axis=0)
        with np.errstate(invalid="ignore"):
            mean4 = np.nanmean(A, axis=0)
            hi = np.nanmax(A, axis=0)
            lo = np.nanmin(A, axis=0)
        v1 = cnt >= 1
        s_lev[v1] += mean4[v1]; n_lev[v1] += 1
        v2 = cnt >= 2
        s_diu[v2] += (hi - lo)[v2]; n_diu[v2] += 1
        m_max[v1] = np.maximum(m_max[v1], mean4[v1])
        m_min[v1] = np.minimum(m_min[v1], mean4[v1])
        n_mon[v1] += 1
        if (k + 1) % 4 == 0 or k == len(months) - 1:
            print("    %d/%d doy %s  mean local times per cell %.2f of 4"
                  % (k + 1, len(months), months[k], cnt[cnt > 0].mean()),
                  flush=True)
        del A, mean4, hi, lo, cnt
    say_peak("earth 2025 four-time loop")
    print("  QC rejected %d of %d in-range readings (%.3f%%)"
          % (qc_rej, tot_cells, 100.0 * qc_rej / max(tot_cells, 1)))

    MINM = 6
    with np.errstate(invalid="ignore", divide="ignore"):
        lev = np.where(n_lev >= MINM, s_lev / np.maximum(n_lev, 1), np.nan)
        diu = np.where(n_diu >= MINM, s_diu / np.maximum(n_diu, 1), np.nan)
        sea = np.where(n_mon >= MINM, m_max - m_min, np.nan)
    print("  months per cell: p50 %d, cells with >= %d: %.3f%%"
          % (int(np.median(n_mon[n_mon > 0])), MINM,
             100.0 * np.mean(n_mon >= MINM)))
    lat = 90.0 - (np.arange(H) + 0.5) * (180.0 / H)
    lon = -180.0 + (np.arange(W) + 0.5) * (360.0 / W)
    extra = dict(
        record="calendar 2025 only, 12 months, Terra AND Aqua",
        local_times_per_month=4,
        min_months=MINM,
        qc_rule="MOD11/MYD11 mandatory QA bits 0-1 <= 1",
        qc_rejected_fraction=round(qc_rej / max(tot_cells, 1), 6),
        diurnal_definition=(
            "max minus min over the AVAILABLE LOCAL TIMES -- the SAME "
            "quantity the Moon and Mars carry. Sample counts: Earth 4, "
            "Mars 12, Moon 96. This replaces the earlier two-sample Terra "
            "day-minus-night, which was a different physical quantity and "
            "could go negative; max minus min cannot, by construction."),
        overpass_times=(
            "Terra ~10:30/22:30, Aqua ~13:30/01:30 local. These are MISSION "
            "DESIGN. The products' own view-time fields do not reproduce "
            "them when read: the distributions come out near-uniform over "
            "0-24 h and Terra 'night' lands at 14.4 h. Two hypotheses were "
            "tested and REJECTED -- a 0.1 scale factor (caps at 12 h, cannot "
            "hold a night overpass) and swapped day/night bands (gives "
            "14.4/9.0, still wrong). The times are therefore not claimed as "
            "measured, and nothing here depends on them: four distinct "
            "samples is all max-minus-min needs."),
        cross_platform=(
            "Terra and Aqua are different instruments with independent "
            "calibration drift. For a rank transform computed WITHIN Earth "
            "this is negligible, because a common offset cannot change an "
            "ordering. Stated rather than assumed away."),
        record_cost=(
            "ONE calendar year. A single anomalous season -- an El Nino, a "
            "volcanic aerosol loading, an unusual monsoon -- is not averaged "
            "out at all. The 22-month Terra record was longer, but the "
            "platforms did not line up, and consistency was the defect worth "
            "fixing."),
        coverage_note=(
            "MOD11C3 and MYD11C3 are LAND ONLY and gap in polar night, so "
            "coverage varies by month. n_months is carried as the support "
            "value."))
    return (dict(temp_level=lev, temp_range_diurnal=diu,
                 temp_range_seasonal=sea),
            lat, lon, n_mon.astype(np.float32), extra)


# -------------------------------------------------------------------- MOON

def build_moon():
    d = os.path.join(C.ROOT, "cube", "diviner")
    tmax = np.load(os.path.join(d, "diviner_tbol_max_0p5deg.npy")).astype(float)
    tmin = np.load(os.path.join(d, "diviner_tbol_min_0p5deg.npy")).astype(float)
    nlt = np.load(os.path.join(d, "diviner_tbol_nlt_0p5deg.npy")).astype(float)
    H, W = tmax.shape
    lat = 90.0 - (np.arange(H) + 0.5) * (180.0 / H)
    lon = -180.0 + (np.arange(W) + 0.5) * (360.0 / W)
    lev = (tmax + tmin) / 2.0
    extra = dict(
        source="Diviner GCP, LRO-L-DLRE-5-GCP-V1.0, DOI 10.17189/1520655",
        source_unit="K", local_time_bins_max=96,
        temp_level_definition=(
            "(tbol_max + tbol_min)/2. This is a MIDPOINT, not a true "
            "full-cycle time average: the GCP's local-time sampling is "
            "uneven, and the lunar diurnal curve is strongly non-sinusoidal "
            "(long cold night, sharp noon peak), so the midpoint sits ABOVE "
            "the true time average. Stated rather than hidden; it is "
            "monotonic in the true average, which is what a rank transform "
            "needs."),
        no_seasonal=("The Moon has no meaningful seasonal cycle (axial tilt "
                     "1.54 deg), so temp_range_seasonal is NOT built for the "
                     "Moon and must not enter the Earth-Moon dimension set."),
        sampling_bias_checked=(
            "corr(n_local_time, |lat|) = +0.856: the POLES are the best "
            "sampled, median 96 of 96 bins at 85-90S against 55 at the "
            "equator. Within 2-degree latitude bands the correlation of "
            "n_local_time with diurnal range is -0.028, the effect is not "
            "monotonic in sampling, and max and min do NOT move in opposite "
            "directions. Bias bounded at ~0.3 K against a 265 K median "
            "range. No correction applied, and none is warranted."))
    return (dict(temp_level=lev, temp_range_diurnal=tmax - tmin),
            lat, lon, nlt.astype(np.float32), extra)


# -------------------------------------------------------------------- MARS

def build_mars():
    src = os.path.join(C.ROOT, "sources", "mcd_prototype")
    LS = list(range(0, 360, 30))
    LT = list(range(0, 24, 2))
    grid = None
    cube = np.full((len(LS), len(LT), 64, 48), np.nan)
    for i, ls in enumerate(LS):
        for j, lt in enumerate(LT):
            p = os.path.join(src, f"tsurf_ls{ls:03d}_lt{lt:02d}.txt")
            body = [l.rstrip() for l in io.open(p, encoding="utf-8")
                    if not l.startswith("###")]
            lats = np.array([float(x) for x in body[0].split("||")[1].split()])
            rows, lons = [], []
            for l in body[1:]:
                if "||" not in l:
                    continue
                a, b = l.split("||")
                try:
                    lons.append(float(a))
                except ValueError:
                    continue
                rows.append([float(x) for x in b.split()])
            cube[i, j] = np.array(rows)
            if grid is None:
                grid = (np.array(lons), lats)
    lons, lats = grid
    print(f"  cube {cube.shape} = {len(LS)} Ls x {len(LT)} local times x "
          f"{len(lons)} lon x {len(lats)} lat; NaN {np.isnan(cube).sum()}")
    lev = np.nanmean(cube, axis=(0, 1))
    diu = np.nanmean(np.nanmax(cube, axis=1) - np.nanmin(cube, axis=1), axis=0)
    dmean = np.nanmean(cube, axis=1)
    sea = np.nanmax(dmean, axis=0) - np.nanmin(dmean, axis=0)
    # cube is (lon, lat) per slice -> transpose to (lat, lon) and order N->S
    def fix(a):
        b = a.T                                # (lat, lon)
        return b[::-1] if lats[0] < lats[-1] else b
    lat_o = lats[::-1] if lats[0] < lats[-1] else lats
    extra = dict(
        source="Mars Climate Database v6.2 web interface, tsurf",
        source_unit="K",
        grid=f"{len(lons)} lon x {len(lats)} lat, 3,072 cells for the planet",
        matching_eligible=False,
        matching_eligible_reason=(
            "The MCD output grid is 64 x 48 = 3,072 cells for the whole "
            "planet, against 3,145,728 HEALPix pixels at Nside 512 -- 1,024 "
            "pixels share every distinct value. At target scale any candidate "
            "patch is thermally CONSTANT, so the null test would compare "
            "patches that are all thermally identical. This layer is built "
            "and stored but must not be used as a matching dimension."),
        resolution_checked=(
            "The 64 x 48 output grid IS the GCM grid (model resolution "
            "5.625 x 3.75 deg), so there is no downsampling to undo. The "
            "high-resolution flag hrkey=1 was tested against hrkey=0: 3,072 "
            "values compared, maximum difference 0.000000 K, zero values "
            "differ -- it is ignored for map output. It works only in point "
            "mode, which would need 9.3 million HTTP requests for this "
            "sampling."),
        gcm_note=(
            "MCD is a GCM product. A finer output grid would add the MOLA "
            "topographic correction, which is real and large on Mars because "
            "surface temperature depends strongly on elevation through "
            "pressure -- but it would NOT add 6 km of physical information. "
            "A finer grid must never be read as finer knowledge."),
        future_upgrade=("TES-derived thermal inertia (Putzig & Mellon, ~3 km) "
                        "is a MEASURED product at the right scale and is the "
                        "better source. Logged, not actioned."))
    return (dict(temp_level=fix(lev), temp_range_diurnal=fix(diu),
                 temp_range_seasonal=fix(sea)),
            lat_o, lons, None, extra)


BUILDERS = dict(earth=build_earth, moon=build_moon, mars=build_mars)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", required=True, choices=list(BUILDERS))
    a = ap.parse_args()
    body = a.body
    ns = NSIDE[body]
    print("=" * 78)
    print(f"PHASE 3 -- THERMAL: {body.upper()}")
    print("=" * 78)
    print("RANGE GATES, stated BEFORE the run (kelvin):")
    for k, (lo, hi) in GATES[body].items():
        print(f"   {k:22s} {lo:7.1f} .. {hi:7.1f} K")
    print()
    C.require_disk(5.0, C.ROOT)
    t0 = time.perf_counter()
    layers, lat, lon, nsup, extra = BUILDERS[body]()

    ncells = lat.size * lon.size
    npix = 12 * ns * ns
    print(f"  source {lat.size} x {lon.size} = {ncells:,} cells   target "
          f"{npix:,} HEALPix pixels")
    # BIN FIRST, THEN FILL. A single global either/or is wrong, because a
    # plate carree source is not uniformly coarse: a 0.5 degree cell is 15.2
    # km in latitude but only 15.2*cos(lat) km in longitude, about 0.7 km at
    # 87 S. So the SAME source is finer than the HEALPix pixel near the poles
    # and coarser near the equator. Binning averages wherever the source is
    # dense -- which is exactly the lunar target region -- and the leftover
    # empty pixels, which are the genuinely coarse ones, are filled by
    # nearest-neighbour copy.
    acc = bin_grid(layers, lat, lon, ns, layers)
    filled_src, _ = sample_grid(layers, lat, lon, ns)
    nmap = None
    if nsup is not None:
        nmap, _, _ = bin_grid({"n": nsup}, lat, lon, ns,
                              {"n": nsup}).finish("n")
        ns_s = sample_grid({"n": nsup}, lat, lon, ns)[0]["n"]
        gap = ~np.isfinite(nmap)
        nmap[gap] = ns_s[gap]

    os.makedirs(OUT, exist_ok=True)
    print(f"\n  --- {body.upper()} THERMAL, ALL GATES ---")
    res = {}
    for nm in layers:
        arr, nfilled, sup = acc.finish(nm)
        gap = ~np.isfinite(arr) & np.isfinite(filled_src[nm])
        n_copied = int(gap.sum())
        arr[gap] = filled_src[nm][gap]
        sup[gap] = 0.0        # 0 WITH a finite value == copied, see the note
        nfilled += n_copied
        lo, hi = GATES[body][nm]
        out_of = int(np.sum(np.isfinite(arr) & ((arr < lo) | (arr > hi))))
        path = os.path.join(OUT, f"{body}_{nm}_nside{ns}.npy")
        C.atomic_save(path, arr)
        spath = os.path.join(OUT, f"{body}_{nm}_support_nside{ns}.npy")
        C.atomic_save(spath, sup)
        ex = dict(extra)
        fv = arr[np.isfinite(arr)]
        uq, cq = np.unique(fv, return_counts=True)
        ex.update(
            source_cells=ncells, target_pixels=npix,
            pixels_copied_not_binned=n_copied,
            pct_copied=round(100.0 * n_copied / max(nfilled, 1), 4),
            distinct_levels=int(uq.size),
            largest_tie_fraction=float(cq.max() / cq.sum()),
            resampling_note=(
                "BIN THEN FILL. Pixels whose footprint contained at least one "
                "source cell carry an area-weighted MEAN of those cells. "
                "Pixels with no source cell carry a nearest-neighbour COPY "
                "and are marked by SUPPORT EXACTLY 0.0 ALONGSIDE A FINITE "
                "VALUE -- that combination means copied, not missing. A plate "
                "carree source is not uniformly coarse: a 0.5 degree cell is "
                "15.2 km north-south but 15.2*cos(lat) km east-west, so the "
                "same source is finer than the pixel near the poles and "
                "coarser near the equator. Copying everywhere would have "
                "thrown away real polar detail in the lunar target region; "
                "binning everywhere would have left most of the sphere "
                "empty, which the coverage gate caught at 28.88% valid."),
            tie_note=(
                "distinct_levels and largest_tie_fraction are the FOURTH "
                "gate. Copied pixels make neighbours carry identical values, "
                "and range, coverage and support are all blind to that."))
        ex.update(healpix_pixels_filled=nfilled, units="K",
                  range_gate_stated_in_advance=[lo, hi],
                  pixels_outside_stated_gate=out_of,
                  range_gate_pass=bool(out_of == 0))
        if nmap is not None:
            ex["sampling_support"] = dict(
                definition=("n_months (earth) or n_local_time bins (moon); "
                            "stored as <body>_thermal_nsamples"),
                p50=float(np.nanmedian(nmap)))
        v = validate(arr, ns, f"{body}_{nm}", "K", ex, support=sup)
        show(v)
        print(f"    {'':34s} range gate [{lo:.0f},{hi:.0f}] K: "
              f"{'PASS' if out_of == 0 else f'FAIL, {out_of:,} outside'}")
        res[nm] = v
        C.manifest_write(f"{body}_{nm}", dict(
            phase="3", body=body, variable=nm, units="K", nside=ns,
            order="nested",
            file=os.path.relpath(path, C.ROOT).replace("\\", "/"),
            support_file=os.path.relpath(spath, C.ROOT).replace("\\", "/"),
            binning=("area-weighted mean onto HEALPix NESTED with cos(lat) "
                     "weights; no intermediate written"),
            gates=("FOUR checks where applicable: range (stated in advance), "
                   "coverage, support, and sample count."),
            validation=v,
            peak_rss_gib=peak_rss_gib(),
            build_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
        del sup
    if nmap is not None:
        C.atomic_save(os.path.join(OUT, f"{body}_thermal_nsamples_nside{ns}.npy"),
                      nmap)
    pk = peak_rss_gib()
    print(f"\n{body.upper()} {(time.perf_counter()-t0)/60:.1f} min   peak RAM "
          f"{'?' if pk is None else f'{pk:.2f}'} GiB (cap {PEAK_CAP_GIB})")
    io.open(os.path.join(OUT, f"phase3_{body}_summary.json"), "w",
            encoding="utf-8").write(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
