"""
PHASE 2b -- TPI AT 7 km, one body at a time. DECIDED by Sherozbek, 9 Nov 2026.

    python build/phase2b_tpi7.py --body moon|mars|earth

WHAT IT IS
    Topographic position index over a 7 km FULL-FOOTPRINT window:
        TPI_7km = z - mean(z within the window)
    The same quantity as tpi_21km at a third of the scale. VARIABLES.md B1
    named this as the secondary recommendation: TPI is strongly
    scale-dependent, a 7 km window separates small craters and rille floors
    that a 21 km window averages away, and with a summed-area table the
    marginal cost is one extra pass. The 7 km window matches the slope
    baseline, so the terrain family now has form at two scales (7, 21 km) and
    texture at four (5.25 .. 42 km).

SAME CODE PATH AS tpi_21km -- deliberately
    sat3 -> window_stats_from_sat(want_mean=True) -> z - mean, imported from
    phase2_terrain and called with a different window. The band loop, the
    halo, the east-west widening as 1/cos(lat), the 50% validity rule, the
    cos(lat)-weighted binning and the three gates are all phase 2's. Nothing
    here is a second implementation of anything.

WHAT IT CHANGES DOWNSTREAM
    One more candidate in BOTH pairings: Earth-Moon 10 -> 11, Earth-Mars
    6 -> 7. The B8 rule applies: measure correlation and lambda_min with the
    new column (build/tpi7_dimension_check.py) before trusting the count.
    Recorded in VARIABLES.md B26.
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
from phase1_dems import GRIDS, PEAK_CAP_GIB, peak_rss_gib, say_peak
from phase2_terrain import (DEM_FILE, OUT_DIR, PHASE2_DISK_FLOOR_GIB, ROOT,
                            HealpixAccumulator, achieved_window_km, band_plan,
                            cell_km_ns, ew_halves, half_for_window, sat3,
                            show, validate, window_stats_from_sat)
from phase1_dems import DEM_DIR

TPI7_WINDOW_KM = 7.0
NAME = "tpi_7km"
DECISION = ("Added 9 Nov 2026 on Sherozbek's decision, after the clean-data "
            "pass (VARIABLES.md B25) and against the recommendation to add "
            "nothing before the hackathon. The option itself is B1's secondary "
            "recommendation. Built by build/phase2b_tpi7.py through phase 2's "
            "own functions; see VARIABLES.md B26 for the measurements.")


def build_body(body):
    nside = C.NSIDE[body]
    dem_path = os.path.join(DEM_DIR, DEM_FILE[body])
    if not os.path.exists(dem_path):
        raise SystemExit(f"STOP: {dem_path} missing -- Phase 1 must run first")
    z_all = np.load(dem_path, mmap_mode="r")
    Hh, Ww = z_all.shape
    if (Hh, Ww) != tuple(GRIDS[body]["shape"]):
        raise SystemExit(f"STOP: DEM is {Hh}x{Ww}, expected "
                         f"{GRIDS[body]['shape']}")
    cell = cell_km_ns(body)
    half = half_for_window(TPI7_WINDOW_KM, cell)
    ach = achieved_window_km(half, cell)
    print(f"  grid {Hh} x {Ww}, cell {cell:.4f} km, Nside {nside}")
    print(f"  TPI window 7 km requested -> half {half} cells -> ACHIEVED "
          f"{ach:.3f} km full footprint (2h+1)*cell")

    halo = half
    core_rows = band_plan(Ww, halo)
    nbands = (Hh + core_rows - 1) // core_rows
    print(f"  bands: {core_rows} core rows + {halo} halo -> {nbands} bands")

    acc = HealpixAccumulator(nside, [NAME])
    lat_all = 90.0 - (np.arange(Hh) + 0.5) * (180.0 / Hh)
    lon = -180.0 + (np.arange(Ww) + 0.5) * (360.0 / Ww)
    cos_all = np.maximum(np.cos(np.radians(lat_all)), 1e-9)
    ew, cap = ew_halves(lat_all, cell, TPI7_WINDOW_KM, Ww)
    sat_rows = int((np.rint((TPI7_WINDOW_KM / (cell * cos_all) - 1.0) / 2.0)
                    > cap).sum())
    print(f"  east-west stencil capped on {sat_rows} of {Hh} rows "
          f"(window / (pi * cell) = {TPI7_WINDOW_KM/(np.pi*cell):.2f})")

    t0 = time.perf_counter()
    nbytes = 0
    for bi, c0 in enumerate(range(0, Hh, core_rows)):
        c1 = min(Hh, c0 + core_rows)
        e0 = max(0, c0 - halo); e1 = min(Hh, c1 + halo)
        z = np.asarray(z_all[e0:e1], dtype=np.float32)
        nbytes += z.nbytes
        k0, k1 = c0 - e0, c1 - e0
        S, S2, N, off = sat3(z)
        _, mean = window_stats_from_sat(S, S2, N, off, half, ew[e0:e1],
                                        k0, k1, Ww, want_mean=True)
        del S, S2, N
        tpi = (z[k0:k1] - mean).astype(np.float32)
        del mean, z
        idx = acc.index_for_band(lat_all[c0:c1], lon).ravel()
        wt = np.repeat(cos_all[c0:c1], Ww)
        acc.add_reference(idx, wt)
        acc.add(NAME, tpi, idx, wt)
        del tpi, idx, wt
        if bi % 8 == 0 or c1 == Hh:
            el = time.perf_counter() - t0
            eta = el / (bi + 1) * (nbands - bi - 1)
            pk = peak_rss_gib()
            print(f"    band {bi+1}/{nbands}  row {c1}/{Hh}  {el/60:5.1f} min"
                  f"  eta {eta/60:5.1f} min  peak "
                  f"{'?' if pk is None else f'{pk:.2f}'} GiB", flush=True)
    el = time.perf_counter() - t0
    say_peak(f"{body} tpi_7km band loop")

    arr, nfilled, sup = acc.finish(NAME)
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{body}_{NAME}_nside{nside}.npy")
    C.atomic_save(path, arr)

    # support: the geometric layers came out CONSTANT 1.0 on every valid pixel
    # (the DEMs cover their spheres), and the 8 Nov cleanup replaced such
    # arrays by the recorded constant. Apply the same rule here, measured.
    v = np.isfinite(arr)
    sv = sup[v]
    const = (sv.size > 0 and np.all(sv == sv[0]))
    sup_entry = {}
    if const:
        sup_entry = dict(
            support_constant=float(sv[0]),
            support_valid_pixels=int(v.sum()),
            support_file_removed=(
                f"support was CONSTANT at {float(sv[0]):g} on every valid "
                f"pixel and carried no information, so no array was written "
                f"and the value is recorded here -- the same rule the 8 Nov "
                f"cleanup applied to the other geometric layers."))
        print(f"  support constant {float(sv[0]):g} on all {int(v.sum()):,} "
              f"valid pixels -- not written, recorded")
    else:
        spath = os.path.join(OUT_DIR, f"{body}_{NAME}_support_nside{nside}.npy")
        C.atomic_save(spath, sup)
        sup_entry = dict(support_file=os.path.relpath(spath, ROOT).replace(os.sep, "/"))
        print(f"  support varies: min {sv.min():.4f} -- array written")

    extra = dict(healpix_pixels_filled=nfilled,
                 requested_window_km=TPI7_WINDOW_KM,
                 achieved_window_km=round(ach, 4), half_cells=half,
                 sign_convention=C.TPI_SIGN_NOTE, ew_rows_saturated=sat_rows)
    vres = validate(arr, nside, f"{body}_{NAME}", "m", extra, support=sup)
    show(vres)

    # the manifest entry mirrors tpi_21km's exactly, then overrides what differs
    man = json.load(io.open(C.MANIFEST, encoding="utf-8"))["layers"]
    base = dict(man[f"{body}_tpi_21km"])
    for k in ("support_file", "support_constant", "support_valid_pixels",
              "support_file_removed", "provenance_file", "support_warning",
              "validation", "elapsed_s", "bytes_read", "throughput_MB_s",
              "throughput_note", "peak_rss_gib", "build_utc"):
        base.pop(k, None)
    base.update(
        variable=NAME,
        file=os.path.relpath(path, ROOT).replace(os.sep, "/"),
        window_km=TPI7_WINDOW_KM,
        shares_window_with="slope (7 km baseline); tpi_21km shares its window with roughness_21km",
        relation_to_tpi_21km=(
            "Same quantity, same code path (phase2_terrain.sat3 and "
            "window_stats_from_sat with want_mean=True), different window. "
            "TPI is strongly scale-dependent: 7 km separates small craters "
            "and rille floors that the 21 km window averages away; 21 km "
            "reads Shackleton-scale basins. Two radii give a crude landform "
            "decomposition for one extra pass (VARIABLES.md B1)."),
        decision=DECISION,
        validation=vres,
        elapsed_s=round(el, 1), bytes_read=nbytes,
        throughput_MB_s=round(nbytes / 2 ** 20 / max(el, 1e-9), 1),
        peak_rss_gib=peak_rss_gib(),
        build_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    base.update(sup_entry)
    C.manifest_write(f"{body}_{NAME}", base)
    io.open(os.path.join(OUT_DIR, f"phase2b_{body}_summary.json"), "w",
            encoding="utf-8").write(json.dumps(vres, indent=1, default=str))
    return vres


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", required=True, choices=["moon", "mars", "earth"])
    a = ap.parse_args(argv)
    print("=" * 78)
    print(f"PHASE 2b -- TPI 7 km: {a.body.upper()}")
    print("=" * 78)
    C.require_disk(PHASE2_DISK_FLOOR_GIB, ROOT)
    t0 = time.perf_counter()
    build_body(a.body)
    pk = peak_rss_gib()
    print(f"\n{a.body.upper()}: {(time.perf_counter()-t0)/60:.1f} min   peak RAM "
          f"{'?' if pk is None else f'{pk:.2f}'} GiB (cap {PEAK_CAP_GIB})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
