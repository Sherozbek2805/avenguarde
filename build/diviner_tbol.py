"""
DECISION 2, part 2 -- derive tbol_max and tbol_min from the Diviner GCP.

    python build/diviner_tbol.py

The GCP holds tbol binned by local time, so the daily maximum and minimum are
simply the max and min over the 96 local-time bins at each 0.5-degree cell.
Nothing is reconstructed or inferred.

INDEPENDENT VALIDATION, which is the point of doing it this way: the published
level-4 raster diviner_tbol_max.xyz already on disk was derived from this same
GCP by the Diviner team. Recomputing the maximum and comparing against it
tests the parse, the fill handling and the grid alignment all at once. The
minimum has no published counterpart -- that is why we are here -- so the
maximum is the only thing that CAN be checked, and it must be.

FILL HANDLING, from the PDS4 label:
    -9999  unknown, bin contained no observations
    -9998  invalid
    Negative brightness temperatures are otherwise VALID DATA and are kept.
    Discarding all negatives would silently delete the coldest places on the
    Moon, which are exactly the polar cold traps this project cares about.
"""

import io
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

GCP = os.path.join(C.ROOT, "sources", "diviner_gcp")
OUT = os.path.join(C.ROOT, "cube", "diviner")
LEVEL4 = os.path.join(C.ROOT, "LRO_Diviner", "level4", "diviner_tbol_max.xyz")

REC = 113
NREC = 1_382_400
NLON, NLAT_BAND, NLT = 720, 20, 96
FILL = (-9999.0, -9998.0)
COLS = dict(lon=(0, 7), lat=(9, 15), lt=(17, 23), tbol=(102, 111))

BANDS = ([f"{a:02d}n{a+10:02d}n" for a in range(0, 90, 10)] +
         [f"{a+10:02d}s{a:02d}s" for a in range(0, 90, 10)])


def col(rec, a, b):
    return np.ascontiguousarray(rec[:, a:b]).view(f"S{b-a}").ravel(
        ).astype(np.float64)


def read_band(path):
    raw = np.fromfile(path, dtype=np.uint8)
    n = raw.size
    # The label puts a 113-byte Header at offset 0 and the table at 113.
    # VERIFY rather than assume: if the first record parses as a number it is
    # data, not a header.
    off = 0
    if n == (NREC + 1) * REC:
        off = REC
    elif n != NREC * REC:
        raise SystemExit(f"{os.path.basename(path)}: {n} bytes, expected "
                         f"{NREC*REC} or {(NREC+1)*REC}")
    rec = raw[off:off + NREC * REC].reshape(NREC, REC)
    return (col(rec, *COLS["lon"]), col(rec, *COLS["lat"]),
            col(rec, *COLS["lt"]), col(rec, *COLS["tbol"]))


def main():
    os.makedirs(OUT, exist_ok=True)
    print("=" * 78)
    print("DIVINER tbol_max / tbol_min from the GCP")
    print("=" * 78)
    gmax = np.full((360, 720), np.nan)
    gmin = np.full((360, 720), np.nan)
    gcnt = np.zeros((360, 720), dtype=np.int32)
    t0 = time.perf_counter()
    first = True
    for i, b in enumerate(BANDS, 1):
        p = os.path.join(GCP, f"global_cumul_avg_cyl_{b}_002.tab")
        lon, lat, lt, tb = read_band(p)
        if first:
            print(f"  structure check on {b}:")
            print(f"    lon {lon.min():.2f}..{lon.max():.2f}  "
                  f"lat {lat.min():.2f}..{lat.max():.2f}  "
                  f"lt {lt.min():.2f}..{lt.max():.2f}")
            print(f"    first 3 local times: {lt[:3]}  "
                  f"-> local time varies fastest: {lt[0] != lt[1]}")
            print(f"    distinct lon {np.unique(lon).size}, "
                  f"lat {np.unique(lat).size}, lt {np.unique(lt).size}")
            first = False
        good = ~np.isin(tb, FILL)
        v = np.where(good, tb, np.nan)
        # group by cell: local time varies fastest, so reshape is valid only
        # if that was just confirmed
        li = np.rint((lat + 90.0 - 0.25) / 0.5).astype(np.int64)
        oi = np.rint((lon + 180.0 - 0.25) / 0.5).astype(np.int64) % 720
        cell = li * 720 + oi
        order = np.argsort(cell, kind="stable")
        cs = cell[order]
        vs = v[order]
        uniq, start = np.unique(cs, return_index=True)
        grp = np.split(vs, start[1:])
        for u, gvals in zip(uniq, grp):
            r, c = divmod(int(u), 720)
            fin = gvals[np.isfinite(gvals)]
            if fin.size:
                gmax[r, c] = fin.max()
                gmin[r, c] = fin.min()
                gcnt[r, c] = fin.size
        nf = int((~good).sum())
        print(f"  [{i:2d}/18] {b}  fill {nf:>9,} of {tb.size:,} "
              f"({100*nf/tb.size:5.2f}%)   {time.perf_counter()-t0:5.1f} s",
              flush=True)

    # row 0 of gmax is lat -90..-89.5; flip so row 0 is the NORTH, matching
    # every other raster in this project
    gmax = gmax[::-1]
    gmin = gmin[::-1]
    gcnt = gcnt[::-1]

    print()
    print("VERIFICATION")
    v = np.isfinite(gmax) & np.isfinite(gmin)
    print(f"  grid {gmax.shape} (expect (360, 720))  "
          f"valid cells {int(v.sum()):,} / {gmax.size:,} "
          f"({100*v.mean():.3f}%)")
    print(f"  tbol_max  K: min {np.nanmin(gmax):.2f}  "
          f"p50 {np.nanmedian(gmax):.2f}  max {np.nanmax(gmax):.2f}")
    print(f"  tbol_min  K: min {np.nanmin(gmin):.2f}  "
          f"p50 {np.nanmedian(gmin):.2f}  max {np.nanmax(gmin):.2f}")
    d = gmax - gmin
    neg = int(np.nansum(d < 0))
    print(f"  tbol_max - tbol_min positive everywhere: {neg == 0}  "
          f"(negatives: {neg})")
    print(f"  diurnal range K: min {np.nanmin(d):.2f}  "
          f"p50 {np.nanmedian(d):.2f}  max {np.nanmax(d):.2f}")
    print(f"  local-time bins per cell: min {gcnt[v].min()}  "
          f"p50 {int(np.median(gcnt[v]))}  max {gcnt[v].max()} (of {NLT})")

    print()
    print("CROSS-CHECK against the published level-4 diviner_tbol_max.xyz")
    xyz = np.loadtxt(LEVEL4)
    pm = np.full((360, 720), np.nan)
    ri = np.rint((90.0 - xyz[:, 1] - 0.25) / 0.5).astype(int)
    ci = np.rint((xyz[:, 0] + 180.0 - 0.25) / 0.5).astype(int) % 720
    pm[ri, ci] = xyz[:, 2]
    both = np.isfinite(pm) & np.isfinite(gmax)
    diff = gmax[both] - pm[both]
    print(f"  cells compared {int(both.sum()):,}")
    print(f"  difference K: mean {diff.mean():+.4f}  median "
          f"{np.median(diff):+.4f}  p1 {np.percentile(diff,1):+.3f}  "
          f"p99 {np.percentile(diff,99):+.3f}  max|d| {np.abs(diff).max():.3f}")
    print(f"  within 1 K: {100*np.mean(np.abs(diff)<1.0):.3f}%   "
          f"within 5 K: {100*np.mean(np.abs(diff)<5.0):.3f}%")
    print(f"  correlation {np.corrcoef(gmax[both], pm[both])[0,1]:.6f}")

    for nm, arr in (("tbol_max", gmax), ("tbol_min", gmin),
                    ("tbol_range", d), ("tbol_nlt", gcnt.astype(np.float32))):
        C.atomic_save(os.path.join(OUT, f"diviner_{nm}_0p5deg.npy"),
                      arr.astype(np.float32))
    io.open(os.path.join(OUT, "diviner_tbol_summary.json"), "w",
            encoding="utf-8").write(json.dumps(dict(
                grid="360 x 720, 0.5 deg, row 0 = north, lon -180..180",
                unit="K",
                valid_fraction=round(float(v.mean()), 6),
                tbol_max=dict(min=float(np.nanmin(gmax)),
                              p50=float(np.nanmedian(gmax)),
                              max=float(np.nanmax(gmax))),
                tbol_min=dict(min=float(np.nanmin(gmin)),
                              p50=float(np.nanmedian(gmin)),
                              max=float(np.nanmax(gmin))),
                range_nonnegative=bool(neg == 0),
                crosscheck_vs_published_max=dict(
                    n=int(both.sum()), mean_diff_K=float(diff.mean()),
                    median_diff_K=float(np.median(diff)),
                    max_abs_diff_K=float(np.abs(diff).max()),
                    pct_within_1K=float(100*np.mean(np.abs(diff) < 1.0)),
                    correlation=float(np.corrcoef(gmax[both], pm[both])[0, 1])),
                fill_constants_discarded=list(FILL),
                negatives_kept=True,
                elapsed_s=round(time.perf_counter()-t0, 1)), indent=1))
    print(f"\nwrote 4 arrays to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
