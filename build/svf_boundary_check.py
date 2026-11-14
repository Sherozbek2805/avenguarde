"""
SVF SEAM CHECK: do the lat/lon pass and the stereographic cap agree where
both can compute the same terrain?

    python build/svf_boundary_check.py --body moon

The built layer takes |lat| <= 80 from the plate carree sweep and |lat| > 80
from the polar caps. The caps were reprojected out to 77.5 deg, so for
78 < |lat| <= 80 the cap can ALSO compute SVF, on different geometry and a
different grid. This script bins that band from the caps into a fresh
accumulator and compares, pixel by pixel, with the built layer (which took
those pixels from the lat/lon pass). If the two methods disagree, the seam
at 80 deg is a step and the polar method is not interchangeable with the
global one. Reads only; writes cube/phase4/svf_seam_<body>.json.
"""

import argparse
import io
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C
import phase2c_svf as S
from phase1_dems import DEM_DIR
from phase2_terrain import DEM_FILE, HealpixAccumulator, cell_km_ns

LO, HI = 78.0, 80.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", required=True, choices=["moon", "mars", "earth"])
    a = ap.parse_args()
    body = a.body
    nside = C.NSIDE[body]
    built = np.load(os.path.join(C.ROOT, "cube", "healpix",
                                 f"{body}_{S.NAME}_nside{nside}.npy"))
    z_all = np.load(os.path.join(DEM_DIR, DEM_FILE[body]), mmap_mode="r")
    land = np.load(S.LAND_MASK, mmap_mode="r") if body == "earth" else None
    cell2 = S.DOWN * cell_km_ns(body)
    K = int(round(S.RADIUS_KM / cell2))
    S.POLAR_LAT = LO                      # let the cap bin 78..90
    acc = HealpixAccumulator(nside, [S.NAME])
    out = dict(body=body, band_deg=[LO, HI], poles={})
    for south in (True, False):
        acc_p = HealpixAccumulator(nside, [S.NAME])
        S.polar_pass(body, z_all, land, acc_p, cell2, K, south, False)
        cap, _, _ = acc_p.finish(S.NAME)
        hlat = C.healpix_lat(nside)
        sel = (np.abs(hlat) > LO + 0.1) & (np.abs(hlat) < HI - 0.1)
        sel &= (hlat < 0) if south else (hlat > 0)
        both = sel & np.isfinite(cap) & np.isfinite(built)
        d = cap[both] - built[both]
        r = float(np.corrcoef(cap[both], built[both])[0, 1])
        res = dict(pixels=int(both.sum()), median_abs_diff=float(np.median(np.abs(d))),
                   p95_abs_diff=float(np.percentile(np.abs(d), 95)),
                   max_abs_diff=float(np.abs(d).max()), mean_diff=float(d.mean()),
                   pearson_r=r, built_p50=float(np.median(built[both])),
                   cap_p50=float(np.median(cap[both])),
                   built_iqr=float(np.subtract(*np.percentile(built[both], [75, 25]))))
        out["poles"]["S" if south else "N"] = res
        print(f"  {'S' if south else 'N'} {LO:g}-{HI:g} deg: {res['pixels']:,} pixels, "
              f"median |diff| {res['median_abs_diff']:.4f}, p95 "
              f"{res['p95_abs_diff']:.4f}, max {res['max_abs_diff']:.4f}, mean diff "
              f"{res['mean_diff']:+.4f}, r {r:.4f}; built IQR {res['built_iqr']:.4f}")
    p = os.path.join(C.ROOT, "cube", "phase4", f"svf_seam_{body}.json")
    io.open(p, "w", encoding="utf-8").write(json.dumps(out, indent=1))
    print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
