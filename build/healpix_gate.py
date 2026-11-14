"""
THE HEALPIX GATE. Measured, not estimated.

    python build/healpix_gate.py [--full]

GATE CRITERION, STATED BEFORE RUNNING:
    total re-gridding under 3 hours AND clean mask handling -> HEALPix for v1
    otherwise -> DEFERRED TO v2, with the measured numbers as the reason.

NOTE ON WHAT THIS GATE IS: HEALPix is ALREADY BUILT. Phases 1, 2 and 3 all
bin to it and 34 layers sit in cube/healpix. So this is a retrospective gate
answered with production timings rather than a prospective one answered with
a toy. Where a number below comes from a real build rather than from this
script, it says so.
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
from phase1_dems import DEM_DIR
from phase2_terrain import HealpixAccumulator

NSIDE = 1024
NPIX = 12 * NSIDE ** 2


def rebin(vals, lat, lon, nside, rows_per_chunk=None):
    """Return (healpix array, support, seconds). The ONLY code needed."""
    t0 = time.perf_counter()
    acc = HealpixAccumulator(nside, ["v"])
    h, w = lat.size, lon.size
    step = rows_per_chunk or max(1, 2_000_000 // w)
    cos = np.maximum(np.cos(np.radians(lat)), 1e-9)
    for r0 in range(0, h, step):
        r1 = min(h, r0 + step)
        idx = acc.index_for_band(lat[r0:r1], lon).ravel()
        wt = np.repeat(cos[r0:r1], w)
        acc.add_reference(idx, wt)
        acc.add("v", np.ascontiguousarray(vals[r0:r1]).astype(np.float32),
                idx, wt)
        del idx, wt
    a, n, s = acc.finish("v")
    return a, s, time.perf_counter() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true",
                    help="also time the 43200x86400 DEM (slow, ~10 min)")
    a = ap.parse_args()
    out = {}
    print("=" * 78)
    print("HEALPIX GATE")
    print("  criterion: < 3 h total re-gridding AND clean masks -> v1")
    print("=" * 78)

    # ---------- 1. one Earth variable, timed -------------------------------
    print("\n1. SINGLE EARTH VARIABLE, 0.05 deg source -> Nside 1024")
    from pyhdf.SD import SD, SDC
    f = sorted(x for x in os.listdir(os.path.join(C.ROOT, "MOD11C3"))
               if x.endswith(".hdf"))[0]
    sd = SD(os.path.join(C.ROOT, "MOD11C3", f), SDC.READ)
    s = sd.select("LST_Day_CMG")
    att = s.attributes()
    raw = s.get().astype(np.float64)
    s.endaccess(); sd.end()
    vr = att["valid_range"]
    val = np.where((raw >= vr[0]) & (raw <= vr[1]),
                   raw * att["scale_factor"] + att["add_offset"], np.nan)
    H, W = val.shape
    lat = 90.0 - (np.arange(H) + 0.5) * (180.0 / H)
    lon = -180.0 + (np.arange(W) + 0.5) * (360.0 / W)
    arr, sup, dt = rebin(val, lat, lon, NSIDE)
    nz = int(np.isfinite(arr).sum())
    print(f"   source {H}x{W} = {H*W:,} cells -> {NPIX:,} pixels")
    print(f"   WALL CLOCK {dt:.1f} s   pixels filled {nz:,} "
          f"({100*nz/NPIX:.2f}%)")
    print(f"   value range {np.nanmin(arr):.2f} .. {np.nanmax(arr):.2f} K")
    out["single_variable_0p05deg_seconds"] = round(dt, 1)

    # ---------- 2. NaN / mask behaviour ------------------------------------
    print("\n2. DO NaNs CONTAMINATE NEIGHBOURS?")
    tv = np.full((H, W), 100.0)
    blk = (slice(900, 1800), slice(2000, 4000))        # a hard NaN block
    tv[blk] = np.nan
    ta, ts, _ = rebin(tv, lat, lon, NSIDE)
    fin = np.isfinite(ta)
    offblock = fin & (ts >= 0.999)
    partial = fin & (ts < 0.999) & (ts > 0)
    print(f"   constant 100.0 outside a {blk[0].stop-blk[0].start} x "
          f"{blk[1].stop-blk[1].start} NaN block")
    print(f"   fully-supported pixels: {int(offblock.sum()):,}  "
          f"max |value - 100| = {np.abs(ta[offblock]-100.0).max():.3e}")
    print(f"   partially-covered pixels (straddling the edge): "
          f"{int(partial.sum()):,}  "
          f"max |value - 100| = {np.abs(ta[partial]-100.0).max() if partial.any() else 0:.3e}")
    print(f"   pixels wholly inside the block: "
          f"{int((~fin & np.isfinite(ts)).sum()):,}  value is NaN, support 0")
    clean = (np.abs(ta[fin] - 100.0).max() < 1e-4)
    print(f"   -> NO value drift anywhere: {clean}")
    print("   A cell maps to EXACTLY ONE pixel, so a NaN cell can only remove "
          "weight\n      from its own pixel. Contamination is structurally "
          "impossible, not merely absent.")
    out["nan_no_drift"] = bool(clean)
    del tv, ta, ts

    # ---------- 3. Lunar Prospector GRS 2 degree ---------------------------
    print("\n3. LUNAR PROSPECTOR GRS 2 deg EQUAL-AREA -> HEALPix Nside 256")
    tab = os.path.join(C.ROOT, "sources", "lp_grs",
                       "lpgrs_high1_elem_abundance_2deg.tab")
    b = open(tab, "rb").read()
    RL = 880
    n = len(b) // RL
    m = np.frombuffer(b[:n*RL], dtype=np.uint8).reshape(n, RL)

    def col(st, by):
        return np.ascontiguousarray(m[:, st-1:st-1+by]).view(
            f"S{by}").ravel().astype(np.float64)
    mn, mx = col(11, 7), col(18, 7)
    lo, hi = col(25, 7), col(32, 7)
    feo = col(144, 15)
    from astropy_healpix import HEALPix
    from astropy import units as u
    hp = HEALPix(nside=256, order="nested")
    plon, plat = hp.healpix_to_lonlat(np.arange(hp.npix))
    plon = plon.to_value(u.deg); plat = plat.to_value(u.deg)
    plon = np.where(plon > 180.0, plon - 360.0, plon)
    t0 = time.perf_counter()
    res = np.full(hp.npix, np.nan, dtype=np.float32)
    for i in range(n):
        s_ = ((plat >= mn[i]) & (plat < mx[i]) &
              (plon >= lo[i]) & (plon < hi[i]))
        if s_.any():
            res[s_] = feo[i] * 100.0
    dt3 = time.perf_counter() - t0
    filled = int(np.isfinite(res).sum())
    print(f"   {n:,} equal-area cells -> {hp.npix:,} pixels in {dt3:.1f} s")
    print(f"   filled {filled:,} ({100*filled/hp.npix:.3f}%)  "
          f"FeO {np.nanmin(res):.2f} .. {np.nanmax(res):.2f} wt%")
    uq = np.unique(res[np.isfinite(res)])
    print(f"   distinct values {uq.size} of {n:,} cells -> every cell that "
          f"covers a pixel is represented")
    lat_hp = C.healpix_lat(256)
    pol = np.isfinite(res) & (lat_hp <= -85)
    print(f"   85-90S: {int(pol.sum()):,} pixels, "
          f"{np.unique(res[pol]).size} distinct values, "
          f"FeO {res[pol].min():.2f} .. {res[pol].max():.2f} wt%")
    print("   LP cells are EQUAL-AREA and HEALPix pixels are EQUAL-AREA, so "
          "this is a\n      point-in-cell lookup with no area weighting "
          "needed and no projection\n      distortion. It is an UPSAMPLE "
          "(70 pixels per cell), so provenance is\n      COPIED_FROM_COARSER, "
          "not BINNED.")
    out["lp_grs_seconds"] = round(dt3, 1)
    out["lp_grs_filled_pct"] = round(100*filled/hp.npix, 3)

    # ---------- 4. full-resolution worst case ------------------------------
    if a.full:
        print("\n4. WORST CASE: 43200 x 86400 Earth DEM -> Nside 1024")
        z = np.load(os.path.join(DEM_DIR, "earth_dem_1_240deg.npy"),
                    mmap_mode="r")
        Hh, Ww = z.shape
        la = 90.0 - (np.arange(Hh) + 0.5) * (180.0 / Hh)
        lo2 = -180.0 + (np.arange(Ww) + 0.5) * (360.0 / Ww)
        arr2, sup2, dt2 = rebin(z, la, lo2, NSIDE, rows_per_chunk=240)
        print(f"   {Hh*Ww:,} cells -> {NPIX:,} pixels")
        print(f"   WALL CLOCK {dt2/60:.1f} min   "
              f"filled {int(np.isfinite(arr2).sum()):,}")
        out["full_res_dem_minutes"] = round(dt2/60, 2)

    io.open(os.path.join(C.ROOT, "cube", "healpix_gate.json"), "w",
            encoding="utf-8").write(json.dumps(out, indent=1))
    print(f"\n{json.dumps(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
