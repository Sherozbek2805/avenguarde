"""
MOON COMPOSITION from Lunar Prospector GRS, option (b).

    python build/composition_moon.py

SOURCE: PDS lp-l-grs-5-elem-abundance-v1, 2 degree EQUAL-AREA table,
        11,306 cells, W_SIO2 and W_FEO as weight fractions (g/g), plus a
        45-element error matrix. Prettyman et al. (2006).

WHY LP GRS AND NOT THE DIVINER CF MAP
    NOT because the CF map is unavailable -- it exists. Lucey et al. (2021,
    JGR Planets, doi 10.1029/2020JE006777) calibrated the Christiansen
    Feature against synthetic glasses spanning 0.5-97.6 wt% and produced a
    global lunar SiO2 map, stated uncertainty +/-3.4 wt%. An earlier note in
    this project called that product non-existent and was WRONG.
    LP GRS was chosen because it supplies BOTH oxides from one instrument,
    on one grid, with a PUBLISHED PER-CELL ERROR MATRIX. The CF map gives
    SiO2 only and would need a second, differently-calibrated source for FeO.

RESAMPLING
    LP cells are EQUAL-AREA polygons and HEALPix pixels are EQUAL-AREA, so
    this is an exact point-in-cell assignment: no area weighting, no
    projection distortion. The source is COARSER EVERYWHERE -- a 2 degree
    equal-area cell is about 61 km against a 6.95 km pixel, roughly 70 pixels
    per cell -- so by the bin-where-finer / copy-where-coarser rule this is
    COPY everywhere, and every pixel is provenance COPIED_FROM_COARSER.
    That is the copied-value defect, so distinct_levels and
    largest_tie_fraction are recorded, exactly as for the thermal layers.
"""

import io
import json
import os
import re
import sys
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

TAB = os.path.join(C.ROOT, "sources", "lp_grs",
                   "lpgrs_high1_elem_abundance_2deg.tab")
FMT = os.path.join(C.ROOT, "sources", "lp_grs", "lpgrs_elem_abundance.fmt")
OUT = os.path.join(C.ROOT, "cube", "healpix")
NSIDE = 256
RL = 880

# ---- RANGE GATES, STATED BEFORE THE RUN (wt%) ---------------------------
GATES = {"SiO2": (15.0, 70.0), "FeO": (0.0, 32.0)}

WEAK_MOON = (
    "WEAK DIMENSION, MOON SIDE: across the 85-90S target region this layer "
    "takes only 24 distinct values over ~1,512 HEALPix pixels, about 63 "
    "pixels per value, and the SiO2 spread there is 4.8 wt% -- 10.4% of the "
    "global range (FeO 1.5 wt%, 4.9%). It therefore acts as a near-fixed "
    "offset pointing Earth matches at mafic terrain, NOT as a discriminator "
    "between lunar targets.")
WEAK_EARTH = (
    "WEAK DIMENSION, EARTH SIDE: the Earth counterpart is derived from GLiM, "
    "whose published ground truth is 40% of independent rock points matching "
    "the mapped class exactly and 64% allowing similar lithologies "
    "(Hartmann & Moosdorf 2012). That is the ceiling on any composition "
    "comparison using this pair.")


def columns():
    fmt = io.open(FMT, encoding="utf-8", errors="replace").read()
    cols = {}
    for blk in fmt.split("OBJECT")[1:]:
        nm = re.search(r'NAME\s*=\s*"([^"]+)"', blk)
        sb = re.search(r"START_BYTE\s*=\s*(\d+)", blk)
        by = re.search(r"BYTES\s*=\s*(\d+)", blk)
        if nm and sb and by:
            cols[nm.group(1)] = (int(sb.group(1)), int(by.group(1)))
    return cols


def main():
    cols = columns()
    for need in ("MIN_LAT", "MAX_LAT", "MIN_LON", "MAX_LON",
                 "W_SIO2", "W_FEO", "E[2,2]", "E[5,5]"):
        if need not in cols:
            raise SystemExit(f"STOP: column {need} not in the format file")
    raw = open(TAB, "rb").read()
    n = len(raw) // RL
    m = np.frombuffer(raw[:n * RL], dtype=np.uint8).reshape(n, RL)

    def col(k):
        s, b = cols[k]
        return np.ascontiguousarray(m[:, s - 1:s - 1 + b]).view(
            f"S{b}").ravel().astype(np.float64)

    mn, mx = col("MIN_LAT"), col("MAX_LAT")
    lo, hi = col("MIN_LON"), col("MAX_LON")
    si = col("W_SIO2") * 100.0          # g/g -> wt%
    fe = col("W_FEO") * 100.0
    # the label: "the square root of the diagonal of the error matrix gives
    # the propagated uncertainty". Index 2 is SiO2, index 5 is FeO.
    sg_si = np.sqrt(np.maximum(col("E[2,2]"), 0.0)) * 100.0
    sg_fe = np.sqrt(np.maximum(col("E[5,5]"), 0.0)) * 100.0

    print("=" * 78)
    print("MOON COMPOSITION from Lunar Prospector GRS 2 deg")
    print("=" * 78)
    print("RANGE GATES, stated BEFORE the run (wt%):")
    for k, (a, b) in GATES.items():
        print(f"   {k:6s} {a:6.1f} .. {b:6.1f}")
    print(f"\n{n:,} equal-area cells; lat {mn.min():.1f}..{mx.max():.1f}, "
          f"lon {lo.min():.1f}..{hi.max():.1f}")
    z = int((fe <= 0).sum())
    print(f"   FeO exactly 0 in {z} cells ({100*z/n:.3f}%) -- kept, the label "
          f"declares no fill constant")

    from astropy_healpix import HEALPix
    from astropy import units as u
    hp = HEALPix(nside=NSIDE, order="nested")
    npix = int(hp.npix)
    plon, plat = hp.healpix_to_lonlat(np.arange(npix))
    plon = plon.to_value(u.deg); plat = plat.to_value(u.deg)
    plon = np.where(plon > 180.0, plon - 360.0, plon)

    t0 = time.perf_counter()
    out = {k: np.full(npix, np.nan, dtype=np.float32)
           for k in ("SiO2", "FeO", "SiO2_sigma", "FeO_sigma")}
    cellid = np.full(npix, -1, dtype=np.int32)
    for i in range(n):
        s_ = ((plat >= mn[i]) & (plat < mx[i]) &
              (plon >= lo[i]) & (plon < hi[i]))
        if s_.any():
            out["SiO2"][s_] = si[i]; out["FeO"][s_] = fe[i]
            out["SiO2_sigma"][s_] = sg_si[i]; out["FeO_sigma"][s_] = sg_fe[i]
            cellid[s_] = i
    dt = time.perf_counter() - t0
    hit = cellid >= 0
    print(f"   assigned {int(hit.sum()):,} of {npix:,} pixels "
          f"({100*hit.mean():.3f}%) in {dt:.1f} s")

    lat_hp = C.healpix_lat(NSIDE)
    pol = hit & (lat_hp <= -85.0)
    os.makedirs(OUT, exist_ok=True)
    summary = {}
    for k in ("SiO2", "FeO"):
        a = out[k]
        sg = out[k + "_sigma"]
        glo, ghi = GATES[k]
        v = np.isfinite(a)
        bad = int(np.sum(v & ((a < glo) | (a > ghi))))
        uq, cq = np.unique(a[v], return_counts=True)
        # provenance: coarser everywhere -> COPIED_FROM_COARSER (2), else ABSENT
        prov = np.where(v, 2, 0).astype(np.uint8)
        sup = np.where(v, 0.0, np.nan).astype(np.float32)
        C.atomic_save(os.path.join(OUT, f"moon_{k}_nside{NSIDE}.npy"), a)
        C.atomic_save(os.path.join(OUT, f"moon_{k}_sigma_nside{NSIDE}.npy"), sg)
        C.atomic_save(os.path.join(OUT, f"moon_{k}_support_nside{NSIDE}.npy"),
                      sup)
        C.atomic_save(os.path.join(OUT,
                                   f"moon_{k}_provenance_nside{NSIDE}.npy"),
                      prov)
        print(f"\n  moon_{k}")
        print(f"    valid {100*v.mean():7.3f}%   gate [{glo},{ghi}] "
              f"{'PASS' if bad == 0 else f'FAIL {bad:,} outside'}")
        print(f"    global  min {a[v].min():6.2f}  p50 {np.median(a[v]):6.2f} "
              f"  max {a[v].max():6.2f} wt%")
        print(f"    85-90S  min {a[pol].min():6.2f}  p50 "
              f"{np.median(a[pol]):6.2f}   max {a[pol].max():6.2f} wt%  "
              f"({np.unique(a[pol]).size} distinct over {int(pol.sum()):,} px)")
        print(f"    UNCERTAINTY at 85-90S: sigma min {sg[pol].min():.3f}  "
              f"median {np.median(sg[pol]):.3f}  max {sg[pol].max():.3f} wt%")
        print(f"    uncertainty globally : sigma median "
              f"{np.median(sg[v]):.3f} wt%")
        print(f"    distinct_levels {uq.size:,}   largest_tie_fraction "
              f"{cq.max()/cq.sum():.4f}")
        summary[k] = dict(
            valid_pct=round(100 * float(v.mean()), 4),
            gate=[glo, ghi], outside_gate=bad,
            global_min=float(a[v].min()), global_p50=float(np.median(a[v])),
            global_max=float(a[v].max()),
            polar_min=float(a[pol].min()), polar_p50=float(np.median(a[pol])),
            polar_max=float(a[pol].max()),
            polar_distinct=int(np.unique(a[pol]).size),
            polar_pixels=int(pol.sum()),
            sigma_polar_median=float(np.median(sg[pol])),
            sigma_polar_min=float(sg[pol].min()),
            sigma_polar_max=float(sg[pol].max()),
            sigma_global_median=float(np.median(sg[v])),
            distinct_levels=int(uq.size),
            largest_tie_fraction=float(cq.max() / cq.sum()))

        C.manifest_write(f"moon_{k}", dict(
            phase="3b", body="moon", variable=k, units="wt%",
            nside=NSIDE, order="nested",
            file=f"cube/healpix/moon_{k}_nside{NSIDE}.npy",
            sigma_file=f"cube/healpix/moon_{k}_sigma_nside{NSIDE}.npy",
            support_file=f"cube/healpix/moon_{k}_support_nside{NSIDE}.npy",
            provenance_file=(f"cube/healpix/moon_{k}_provenance_"
                             f"nside{NSIDE}.npy"),
            provenance_encoding="cube/provenance_encoding.json",
            provenance_encoding_name="cube_provenance_v1",
            source=("PDS lp-l-grs-5-elem-abundance-v1, "
                    "lpgrs_high1_elem_abundance_2deg.tab; "
                    "Prettyman et al. (2006)"),
            source_unit="weight fraction g/g, converted to wt% by x100",
            uncertainty=("per-cell, from the square root of the diagonal of "
                         "the published 45-element error matrix; index 2 is "
                         "SiO2, index 5 is FeO"),
            resampling=("exact point-in-cell assignment. LP cells and HEALPix "
                        "pixels are BOTH equal-area, so no area weighting and "
                        "no projection distortion. The source is coarser "
                        "EVERYWHERE (~61 km cell against a 6.95 km pixel, "
                        "~70 pixels per cell), so every pixel is "
                        "COPIED_FROM_COARSER."),
            why_lp_grs_not_diviner_cf=(
                "NOT because the Diviner CF map is unavailable -- it exists: "
                "Lucey et al. (2021, doi 10.1029/2020JE006777) derived a "
                "global lunar SiO2 map from the Christiansen Feature, "
                "+/-3.4 wt%. LP GRS was chosen because it gives BOTH oxides "
                "from one instrument on one grid WITH a published per-cell "
                "error matrix; the CF map is SiO2 only."),
            weak_dimension_moon=WEAK_MOON,
            weak_dimension_earth=WEAK_EARTH,
            support_warning=("support is 0.0 on every pixel of this layer "
                             "because every value is copied. Do NOT read "
                             "that as unusable -- read provenance_file."),
            validation=summary[k],
            build_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))

    io.open(os.path.join(OUT, "moon_composition_summary.json"), "w",
            encoding="utf-8").write(json.dumps(summary, indent=1))
    print(f"\nwrote 8 arrays to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
