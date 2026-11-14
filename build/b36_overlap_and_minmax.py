"""DESCRIPTION ONLY. (1) For each preset target and variable: does the target's
median lie outside the WHOLE range of Earth's reference population?
(2) What would min-max scaling do: how much of the 0..1 scale would the
middle 98% of cells occupy? No distance, no search."""
import json

import numpy as np

import os
ROOT = (os.environ.get("ANALOG_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).replace(chr(92), "/")
P4, HP = ROOT + "/cube/phase4/", ROOT + "/cube/healpix/"
NS = {"earth": 1024, "moon": 256, "mars": 512}
cfg = json.load(open(P4 + "phase4c_summary.json"))
pool = json.load(open(P4 + "pooled_scale_summary.json"))
ref = np.load(P4 + "ref_pixels.npy")[np.load(P4 + "complete_mask.npy")]

print("(1) OUT OF EARTH'S WHOLE RANGE, per preset target (blank = inside)")
for tag, body, tf in (("earth_moon", "moon", "targets_moon.json"), ("earth_mars", "mars", "targets_mars.json")):
    dims = cfg[tag]["dimensions"]
    E = {d: np.load(HP + f"earth_{d}_nside1024.npy")[ref] for d in dims}
    lo = {d: float(E[d].min()) for d in dims}
    hi = {d: float(E[d].max()) for d in dims}
    q = {d: np.percentile(E[d], [0.1, 99.9]) for d in dims}
    B = {d: np.load(HP + f"{body}_{d}_nside{NS[body]}.npy") for d in dims}
    T = json.load(open(ROOT + "/contract/" + tf, encoding="utf-8"))["targets"]
    print(f"\n{body.upper()}  Earth whole range and 0.1-99.9% range:")
    for d in dims:
        if d.startswith("temp") or d in ("SiO2", "FeO", "slope"):
            print(f"   {d:20s} whole [{lo[d]:8.2f}, {hi[d]:8.2f}]   0.1-99.9% [{q[d][0]:8.2f}, {q[d][1]:8.2f}]")
    for t in T:
        px = np.array(t["healpix_pixels"])
        out_whole, out_q, share = [], [], []
        for d in dims:
            v = B[d][px]
            v = v[np.isfinite(v)]
            if v.size == 0:
                continue
            m = float(np.median(v))
            if m < lo[d] or m > hi[d]:
                out_whole.append(f"{d}({m:.0f})")
            if m < q[d][0] or m > q[d][1]:
                out_q.append(d)
            frac = float(np.mean((v < lo[d]) | (v > hi[d])))
            if frac > 0:
                share.append(f"{d} {100*frac:.0f}%")
        print(f"   {t['name'][:28]:28s} median outside whole range: {', '.join(out_whole) or '-':34s} | outside 0.1-99.9%: {', '.join(out_q) or '-'}")
        print(f"   {'':28s} share of its cells outside whole range: {', '.join(share) or '-'}")

print("\n(2) MIN-MAX on the pooled values: share of the 0..1 scale holding the middle 98% of cells, and where the median lands")
for body in ("moon", "mars"):
    names = pool["pairings"][body]["names"]
    print(f"\nEarth + {body}:")
    for d in names:
        e = np.load(HP + f"earth_{d}_nside1024.npy")[ref].astype(np.float64)
        b = np.load(HP + f"{body}_{d}_nside{NS[body]}.npy").astype(np.float64)
        b = b[np.isfinite(b)]
        allv = np.concatenate([e, b])
        mn, mx = allv.min(), allv.max()
        p1, p50, p99 = np.percentile(allv, [1, 50, 99])
        print(f"   {d:20s} min {mn:9.2f} max {mx:9.2f} | middle 98% uses {100*(p99-p1)/(mx-mn):5.1f}% of the scale | median at {(p50-mn)/(mx-mn):.3f}")
