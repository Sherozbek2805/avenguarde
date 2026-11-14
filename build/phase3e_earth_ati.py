"""
PHASE 3e -- EARTH APPARENT THERMAL INERTIA, the Earth partner of Mars TES TI.
DECIDED by Sherozbek, 9 Nov 2026 (Mars thermal must be matchable).

    python build/phase3e_earth_ati.py [--test] [--allow-partial]

THE QUANTITY -- AND WHAT IT IS NOT
    ATI = (1 - A) / dT          Price (1977) J. Geophys. Res. 82:2582
    A   = annual mean blue-sky shortwave albedo, MODIS MCD43A3, 0.05 deg,
          blue-sky taken as (black-sky + white-sky) / 2
    dT  = diurnal LST range, calendar 2025, max minus min over the four
          Terra/Aqua local times, 0.05 deg -- the SAME field that feeds
          earth_temp_range_diurnal, recomputed here at source resolution.
    Units K^-1. ATI is a PROXY: a bright surface that barely changes
    temperature over the day is thermally sluggish. True thermal inertia
    needs a thermal model with the solar forcing, which is what Putzig &
    Mellon ran for Mars. The Earth side is the proxy, the Mars side the
    modelled-from-measurement quantity. The pipeline ranks within each body,
    so what is compared is WHERE each world is thermally sluggish, not the
    number. B23 called this pairing a quantity mismatch and declined it; the
    decision of 9 Nov overrides that, and the mismatch is recorded on both
    manifest entries rather than hidden.

INPUTS, AND THE RULE ABOUT THEM
    sources/mcd43a3_albedo/mcd43a3_albedo_clim_mMM.tif  (write-once copy of
    the GEE export; 3 bands int16: bsa, wsa, n_composites; scale 0.001;
    VALID WHERE n_composites > 0 -- the fill value differs between files and
    is never tested directly, HANDOVER section 6). n_composites is the count
    of daily retrievals in the month (max 31), so each file is ONE month of
    2025, not a multi-year climatology; the scale is x1e-4, measured.
    All twelve months are required so albedo and LST share one annual cycle;
    --allow-partial builds from whatever months exist and RECORDS which.

GATES, STATED BEFORE THE RUN
    range     0 < ATI <= 1 K^-1 (dT is floored at 1 K; (1 - A) <= 1)
    coverage  land only, like every MODIS layer
    support   as the thermal layers: bin, then fill empty pixels by copy,
              support 0.0 on copied pixels, provenance derived afterwards
"""

import argparse
import glob
import hashlib
import io
import json
import os
import re
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C
from phase1_dems import peak_rss_gib, say_peak
from phase2_terrain import show, validate
from phase3_thermal import bin_grid, build_earth, sample_grid

ALB_DIR = os.path.join(C.ROOT, "sources", "mcd43a3_albedo")
OUT = os.path.join(C.ROOT, "cube", "healpix")
NSIDE = C.NSIDE["earth"]
H, W = 3600, 7200
SCALE = 0.0001          # MEASURED on the files: p50 1331-1798, p99 8042-9030, max 9910 -> x1e-4 gives 0.13-0.18 land, 0.8-0.99 snow. NOT the 0.001 of native MCD43A3; the GEE export is x10000.
DT_FLOOR_K = 1.0
GATE = (0.0, 1.0)
MIN_MONTHS_ALBEDO = 1


def sha1(p):
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def load_albedo():
    import rasterio
    files = sorted(glob.glob(os.path.join(ALB_DIR, "mcd43a3_albedo_clim_m*.tif")))
    months = [re.search(r"_m(\d\d)\.tif$", f).group(1) for f in files]
    s_alb = np.zeros((H, W)); n_alb = np.zeros((H, W), dtype=np.int16)
    meta = []
    for f, m in zip(files, months):
        with rasterio.open(f) as s:
            if (s.height, s.width) != (H, W) or s.count != 3:
                raise SystemExit(f"STOP: {f} is {s.height}x{s.width} x {s.count} "
                                 f"bands, expected {H}x{W} x 3")
            if tuple(s.descriptions) != ("bsa", "wsa", "n_composites"):
                raise SystemExit(f"STOP: {f} bands {s.descriptions}")
            t = s.transform
            if not (abs(t.a - 0.05) < 1e-9 and abs(t.c + 180) < 1e-6
                    and abs(t.f - 90) < 1e-6):
                raise SystemExit(f"STOP: {f} geotransform {t}")
            bsa = s.read(1).astype(np.float64); wsa = s.read(2).astype(np.float64)
            n = s.read(3)
        ok = (n > 0) & (bsa >= 0) & (wsa >= 0) & (bsa <= 10000) & (wsa <= 10000)
        a = 0.5 * (bsa + wsa) * SCALE
        s_alb[ok] += a[ok]; n_alb[ok] += 1
        meta.append(dict(file=os.path.relpath(f, C.ROOT).replace(os.sep, "/"),
                         month=m, sha1=sha1(f), pct_valid=round(100 * ok.mean(), 3),
                         albedo_p50=float(np.median(a[ok])) if ok.any() else None))
        print(f"    albedo month {m}: valid {100*ok.mean():6.2f}%  "
              f"p50 {np.median(a[ok]):.3f}")
    with np.errstate(invalid="ignore", divide="ignore"):
        alb = np.where(n_alb >= MIN_MONTHS_ALBEDO, s_alb / np.maximum(n_alb, 1), np.nan)
    return alb, n_alb, months, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--allow-partial", action="store_true",
                    help="build from fewer than 12 albedo months, recorded")
    a = ap.parse_args()
    print("=" * 78)
    print("PHASE 3e -- EARTH APPARENT THERMAL INERTIA (1 - albedo) / diurnal LST range")
    print("=" * 78)
    print(f"RANGE GATE, stated BEFORE the run: {GATE[0]:g} < ATI <= {GATE[1]:g} K^-1; "
          f"dT floored at {DT_FLOOR_K:g} K")
    C.require_disk(2.0, C.ROOT)
    t0 = time.perf_counter()
    print("  albedo:")
    alb, n_alb, months, meta = load_albedo()
    if len(months) < 12 and not a.allow_partial:
        raise SystemExit(f"STOP: only {len(months)} albedo months on disk "
                         f"({months}); twelve are required so albedo and LST "
                         f"share one annual cycle. --allow-partial overrides, "
                         f"and records it.")
    print(f"  albedo annual mean from {len(months)} months {months}: valid "
          f"{100*np.isfinite(alb).mean():.2f}% of cells")
    print("  LST diurnal range, calendar 2025, four local times (phase 3 code):")
    layers, lat, lon, n_mon, lst_extra = build_earth()
    dT = layers["temp_range_diurnal"]
    say_peak("inputs")
    both = np.isfinite(alb) & np.isfinite(dT)
    n_floor = int(np.sum(both & (dT < DT_FLOOR_K)))
    with np.errstate(invalid="ignore", divide="ignore"):
        ati = np.where(both, (1.0 - alb) / np.maximum(dT, DT_FLOOR_K), np.nan)
    print(f"  cells with both inputs {int(both.sum()):,}; dT below the "
          f"{DT_FLOOR_K:g} K floor on {n_floor:,} of them")
    f = ati[both]
    print(f"  ATI at 0.05 deg: p1 {np.percentile(f,1):.4f} p50 {np.median(f):.4f} "
          f"p99 {np.percentile(f,99):.4f} max {f.max():.4f} K^-1")
    if a.test:
        print("\nTEST -- nothing written")
        return 0

    nm = "thermal_inertia"
    acc = bin_grid({nm: ati}, lat, lon, NSIDE, {nm: ati})
    filled, _ = sample_grid({nm: ati}, lat, lon, NSIDE)
    arr, nfilled, sup = acc.finish(nm)
    gap = ~np.isfinite(arr) & np.isfinite(filled[nm])
    arr[gap] = filled[nm][gap]; sup[gap] = 0.0; nfilled += int(gap.sum())
    v = np.isfinite(arr)
    out_of = int(np.sum(v & ((arr <= GATE[0]) | (arr > GATE[1]))))
    uq, cq = np.unique(arr[v], return_counts=True)
    extra = dict(
        healpix_pixels_filled=nfilled, pixels_copied_not_binned=int(gap.sum()),
        range_gate_stated_in_advance=list(GATE),
        pixels_outside_stated_gate=out_of, range_gate_pass=bool(out_of == 0),
        distinct_levels=int(uq.size), largest_tie_fraction=float(cq.max() / cq.sum()),
        albedo_months_used=months, albedo_files=meta,
        albedo_definition="blue-sky shortwave = (BSA + WSA)/2, scale 1e-4 (measured on the export), valid where n_composites > 0",
        dT_definition=lst_extra["diurnal_definition"],
        dT_record=lst_extra["record"], dT_floor_K=DT_FLOOR_K,
        cells_dT_below_floor=n_floor, units="K^-1")
    vres = validate(arr, NSIDE, f"earth_{nm}", "K^-1", extra, support=sup)
    show(vres)
    print(f"    {'':34s} range gate ({GATE[0]:g},{GATE[1]:g}] K^-1: "
          f"{'PASS' if out_of == 0 else f'FAIL, {out_of:,} outside'}")
    path = os.path.join(OUT, f"earth_{nm}_nside{NSIDE}.npy")
    spath = os.path.join(OUT, f"earth_{nm}_support_nside{NSIDE}.npy")
    C.atomic_save(path, arr); C.atomic_save(spath, sup)
    rel = lambda p: os.path.relpath(p, C.ROOT).replace(os.sep, "/")
    C.manifest_write(f"earth_{nm}", dict(
        phase="3e", body="earth", variable=nm, units="K^-1 (apparent thermal inertia)",
        nside=NSIDE, order="nested", file=rel(path), support_file=rel(spath),
        source_files=[m["file"] for m in meta] + ["MOD11C3/*.hdf", "MYD11C3/*.hdf"],
        source_resolves=True,
        source=("MODIS MCD43A3 v6.1 albedo (GEE export, monthly climatology, "
                "0.05 deg) and MOD11C3/MYD11C3 v6.1 LST, calendar 2025"),
        formula="ATI = (1 - A) / dT, Price (1977) JGR 82:2582",
        quantity_caveat=(
            "PROXY. Apparent thermal inertia is a dimensionless ratio of "
            "albedo to diurnal temperature swing; true thermal inertia needs "
            "a thermal model of the solar forcing, which is what the Mars "
            "partner (TES, Putzig & Mellon 2007) has. The pairing compares "
            "WHERE each body is thermally sluggish through the rank "
            "transform, not the physical value. B23 declined this pairing as "
            "a quantity mismatch; the 9 Nov 2026 decision overrides it and "
            "the mismatch is stated here and on mars_thermal_inertia."),
        partial_record=(None if len(months) == 12 else
                        f"BUILT FROM {len(months)} ALBEDO MONTHS {months}, not a "
                        f"full annual cycle, by --allow-partial. Rebuild when "
                        f"all twelve are on disk."),
        binning=("bin then fill, as the Earth thermal layers: area-weighted "
                 "mean where source cells fall in the pixel, nearest-neighbour "
                 "copy where none does (support 0.0, provenance COPIED)"),
        gates="range (stated), coverage, support, ties",
        decision=("Added 9 Nov 2026 on Sherozbek's decision that Mars thermal "
                  "must be matchable; VARIABLES.md B27."),
        validation=vres, peak_rss_gib=peak_rss_gib(),
        build_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
    io.open(os.path.join(OUT, "phase3e_earth_summary.json"), "w",
            encoding="utf-8").write(json.dumps(vres, indent=1, default=str))
    print(f"\nwrote earth_{nm}   {(time.perf_counter()-t0)/60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
