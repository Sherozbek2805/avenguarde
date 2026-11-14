"""
DECISION 4 -- water bodies are not removed by the ice-free land mask.

    python build/wb_impact.py            measure only, write nothing
    python build/wb_impact.py --write    also write the corrected mask

A lake surface is FLAT. Those pixels therefore read as extremely smooth
terrain in slope, roughness_* and TPI -- a false analog signal already sitting
in the eight geometric layers. This measures how large that signal is before
anything is rebuilt.

CAVEAT STATED UP FRONT: the wb class is taken from the 0.5-degree GLiM raster,
which is 55 km. Every lake is therefore surrounded by a 55 km block. The
measurement below is an UPPER BOUND on how much land the exclusion removes and
a blurred estimate of which pixels are affected. The LiMW vector (median
polygon 3.01 km) is the correct source and should replace this once Decision 3
is built.
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
from phase1_dems import DEM_DIR, peak_rss_gib, say_peak
from phase2_terrain import HealpixAccumulator

NSIDE = 1024
GLIM = os.path.join(C.ROOT, "hartmann-moosdorf_2012",
                    "glim_wgs84_0point5deg.txt.asc")
WB_VALUE = 11
IG_VALUE = 16
H, W = 43200, 86400
F = 120                      # 1/240 deg cells per 0.5 deg GLiM cell


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    print("=" * 78)
    print("DECISION 4 -- wb (water bodies) impact on the geometric layers")
    print("=" * 78)
    g = np.loadtxt(GLIM, skiprows=6)
    assert g.shape == (360, 720), g.shape
    wb_g = (g == WB_VALUE)
    print(f"GLiM 0.5 deg: wb cells {int(wb_g.sum()):,} of {g.size:,} "
          f"({100*wb_g.mean():.4f}% of cells)")

    ifl = np.load(os.path.join(DEM_DIR, "earth_ice_free_land_1_240deg.npy"),
                  mmap_mode="r")
    acc = HealpixAccumulator(NSIDE, ["ifl", "wb_in_ifl"])
    lat_all = 90.0 - (np.arange(H) + 0.5) * (180.0 / H)
    lon = -180.0 + (np.arange(W) + 0.5) * (360.0 / W)
    cos_all = np.maximum(np.cos(np.radians(lat_all)), 1e-9)

    out = None
    if a.write:
        op = os.path.join(DEM_DIR,
                          "earth_ice_free_land_nowater_1_240deg.npy") + ".part"
        out = np.lib.format.open_memmap(op, mode="w+", dtype=np.uint8,
                                        shape=(H, W))

    band = 240
    t0 = time.perf_counter()
    n_ifl = 0.0
    n_wb = 0.0
    for r0 in range(0, H, band):
        r1 = min(H, r0 + band)
        ib = np.asarray(ifl[r0:r1]) > 0
        # NEAREST upsample of the 0.5 deg class grid -- exact 120x replication,
        # the same rule phase 1b used for the ice mask
        gi = np.repeat(np.repeat(wb_g[r0 // F:(r1 + F - 1) // F], F, axis=0),
                       F, axis=1)[:r1 - r0, :W]
        keep = ib & ~gi
        wrow = cos_all[r0:r1]
        n_ifl += float((ib * wrow[:, None]).sum())
        n_wb += float(((ib & gi) * wrow[:, None]).sum())
        idx = acc.index_for_band(lat_all[r0:r1], lon).ravel()
        wt = np.repeat(wrow, W)
        acc.add_reference(idx, wt)
        acc.add("ifl", ib.astype(np.float32), idx, wt)
        acc.add("wb_in_ifl", (ib & gi).astype(np.float32), idx, wt)
        if out is not None:
            out[r0:r1] = keep.astype(np.uint8)
        del ib, gi, keep, idx, wt
        if (r0 // band) % 40 == 0:
            el = time.perf_counter() - t0
            print(f"   row {r1}/{H}  {el/60:.1f} min", flush=True)
    say_peak("wb scan")

    if out is not None:
        out.flush()
        del out
        op = os.path.join(DEM_DIR,
                          "earth_ice_free_land_nowater_1_240deg.npy")
        os.replace(op + ".part", op)
        print(f"\nwrote {op}")

    iflf, _, _ = acc.finish("ifl")
    wbf, _, _ = acc.finish("wb_in_ifl")
    print(f"\narea-weighted, at 1/240 deg:")
    print(f"   ice-free land removed by the wb exclusion: "
          f"{100.0*n_wb/n_ifl:.4f}%")

    # ---- which HEALPix pixels are affected, and what do they look like?
    D = os.path.join(C.ROOT, "cube", "healpix")
    sl = np.load(os.path.join(D, f"earth_slope_nside{NSIDE}.npy"))
    rg = np.load(os.path.join(D, f"earth_roughness_21km_nside{NSIDE}.npy"))
    land = iflf > 0.5                      # pixel is majority ice-free land
    wbp = wbf > 0.5                        # pixel is majority water body
    aff = land & wbp
    clean = land & ~wbp
    print(f"\nHEALPix Nside {NSIDE} pixels:")
    print(f"   majority ice-free land          {int(land.sum()):>9,}")
    print(f"   of those, majority water body   {int(aff.sum()):>9,}  "
          f"({100.0*aff.sum()/max(land.sum(),1):.4f}%)")
    print(f"   clean land                      {int(clean.sum()):>9,}")

    rep = {}
    print(f"\n{'layer':16s} {'set':12s} {'n':>9s} {'p1':>9s} {'p25':>9s} "
          f"{'p50':>9s} {'p75':>9s} {'p99':>9s}")
    for nm, arr in (("slope", sl), ("roughness_21km", rg)):
        for sname, m in (("water", aff), ("clean land", clean)):
            v = arr[m & np.isfinite(arr)]
            if v.size == 0:
                continue
            q = np.percentile(v, [1, 25, 50, 75, 99])
            print(f"{nm:16s} {sname:12s} {v.size:>9,} " +
                  " ".join(f"{x:9.4f}" for x in q))
            rep[f"{nm}|{sname}"] = dict(n=int(v.size),
                                        p1=float(q[0]), p25=float(q[1]),
                                        p50=float(q[2]), p75=float(q[3]),
                                        p99=float(q[4]))
        a_, c_ = arr[aff & np.isfinite(arr)], arr[clean & np.isfinite(arr)]
        if a_.size and c_.size:
            # where do water pixels sit in the land distribution?
            pr = 100.0 * np.searchsorted(np.sort(c_), np.median(a_)) / c_.size
            print(f"{'':16s} -> the median water pixel sits at the "
                  f"{pr:.2f}th percentile of clean land")
            rep[f"{nm}|percentile_of_median_water_in_land"] = round(float(pr), 3)

    io.open(os.path.join(C.ROOT, "cube", "wb_impact.json"), "w",
            encoding="utf-8").write(json.dumps(dict(
                glim_source="0.5 degree raster; see the caveat in the docstring",
                pct_ice_free_land_removed=round(100.0 * n_wb / n_ifl, 4),
                healpix_pixels_land=int(land.sum()),
                healpix_pixels_water=int(aff.sum()),
                distributions=rep,
                peak_rss_gib=peak_rss_gib()), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
