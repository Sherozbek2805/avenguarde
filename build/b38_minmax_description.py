"""
B38 -- WHAT A MIN-MAX SCALE LOOKS LIKE ON THIS CUBE. Description only.

    python build/b38_minmax_description.py

No distance from an Earth cell to a target is computed here, no DI, no p.
For each pairing and variable, over Earth's complete reference cells and
every finite cell of the body:

    lo, hi          the smallest and largest value on either world
    set by          which world holds each extreme
    10% of scale    what a gap of 0.10 on the 0-1 scale is, in real units
    positions       where the median Earth cell and the median body cell land
    Earth sd        Earth's standard deviation, the unit of the distance

and, for the preset targets, how many Earth standard deviations the target's
median lies from Earth's mean.
"""
import io
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

HP = os.path.join(C.ROOT, "cube", "healpix")
P4 = os.path.join(C.ROOT, "cube", "phase4")
NS = {"earth": 1024, "moon": 256, "mars": 512}


def main():
    cfg = json.load(io.open(os.path.join(P4, "phase4c_summary.json"), encoding="utf-8"))
    epix = np.load(os.path.join(P4, "ref_pixels.npy"))[np.load(os.path.join(P4, "complete_mask.npy"))]
    out = {}
    for tag, body in (("earth_moon", "moon"), ("earth_mars", "mars")):
        dims = cfg[tag]["dimensions"]
        T = json.load(io.open(os.path.join(C.ROOT, "contract", f"targets_{body}.json"), encoding="utf-8"))["targets"]
        print(f"\n=== EARTH + {body.upper()} ===")
        print(f"{'variable':20s} {'lo':>9s} {'hi':>9s} {'lo/hi set by':>13s} {'10% of scale':>13s} "
              f"{'Earth med':>9s} {'body med':>9s} {'Earth sd':>9s} | targets: median in Earth sd from Earth's mean")
        rec = {}
        for d in dims:
            e = np.load(os.path.join(HP, f"earth_{d}_nside1024.npy"))[epix].astype(np.float64)
            ball = np.load(os.path.join(HP, f"{body}_{d}_nside{NS[body]}.npy")).astype(np.float64)
            b = ball[np.isfinite(ball)]
            lo, hi = min(e.min(), b.min()), max(e.max(), b.max())
            by = ("E" if e.min() <= b.min() else body[0].upper() + body[1]) + "/" + ("E" if e.max() >= b.max() else body[0].upper() + body[1])
            pos = lambda v: (v - lo) / (hi - lo)
            mu, sd = e.mean(), e.std()
            tz = []
            for t in T:
                v = ball[np.asarray(t["healpix_pixels"])]
                v = v[np.isfinite(v)]
                if v.size:
                    tz.append((np.median(v) - mu) / sd)
            tz = np.array(tz)
            print(f"{d:20s} {lo:9.3g} {hi:9.3g} {by:>13s} {0.1*(hi-lo):13.3g} "
                  f"{pos(np.median(e)):9.3f} {pos(np.median(b)):9.3f} {sd:9.3g} | {tz.min():+7.1f} .. {tz.max():+7.1f}")
            rec[d] = dict(lo=float(lo), hi=float(hi), set_by=by, tenth_of_scale=float(0.1 * (hi - lo)),
                          earth_median_position=float(pos(np.median(e))), body_median_position=float(pos(np.median(b))),
                          earth_mean=float(mu), earth_sd=float(sd),
                          earth_p1_p99_position=[float(pos(q)) for q in np.percentile(e, [1, 99])],
                          targets_median_in_earth_sd=[float(tz.min()), float(tz.max())])
        out[body] = rec
    io.open(os.path.join(P4, "minmax_description_b38.json"), "w", encoding="utf-8").write(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
