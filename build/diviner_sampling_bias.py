"""
Is the lunar diurnal-range layer carrying a MANUFACTURED LATITUDE GRADIENT?

    python build/diviner_sampling_bias.py

The worry, stated precisely: fewer local-time samples means a lower chance of
catching the true daily maximum AND the true daily minimum. So tbol_max is
biased DOWN and tbol_min is biased UP where sampling is sparse, and the range
(max - min) is biased DOWN twice over. That is a bias, not noise; it does not
average out. LRO flies a polar orbit, so if local-time coverage varies with
latitude the bias becomes a latitude gradient that looks like physics.

METHOD NOTE -- why the raw correlation is not the test.
    Diurnal range varies enormously with latitude for real physical reasons:
    the equator swings ~300 K, the poles far less. n_local_time also varies
    with latitude. A raw corr(n_lt, range) therefore measures mostly that both
    depend on latitude, and would "confirm" a bias that might not exist.
    Every test below is run WITHIN narrow latitude bands, where latitude is
    effectively held constant, and the within-band results are what decide it.
"""

import io
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

D = os.path.join(C.ROOT, "cube", "diviner")


def load(n):
    return np.load(os.path.join(D, f"diviner_{n}_0p5deg.npy")).astype(np.float64)


tmax = load("tbol_max")
tmin = load("tbol_min")
rng = load("tbol_range")
nlt = load("tbol_nlt")
H, W = nlt.shape
lat = 90.0 - (np.arange(H) + 0.5) * (180.0 / H)
LAT = np.repeat(lat[:, None], W, axis=1)
ok = np.isfinite(rng) & (nlt > 0)

print("=" * 78)
print("DIVINER LOCAL-TIME SAMPLING BIAS")
print("=" * 78)
print(f"cells {int(ok.sum()):,}   n_local_time: min {nlt[ok].min():.0f}  "
      f"p25 {np.percentile(nlt[ok],25):.0f}  p50 {np.percentile(nlt[ok],50):.0f}"
      f"  p75 {np.percentile(nlt[ok],75):.0f}  max {nlt[ok].max():.0f}  of 96")

print()
print("1. DOES SAMPLING VARY WITH LATITUDE?")
r_abs = np.corrcoef(np.abs(LAT[ok]), nlt[ok])[0, 1]
r_sig = np.corrcoef(LAT[ok], nlt[ok])[0, 1]
print(f"   corr(n_local_time, |latitude|) = {r_abs:+.4f}")
print(f"   corr(n_local_time,  latitude)  = {r_sig:+.4f}")
print()
print("   zonal profile of n_local_time (10-degree bands):")
print(f"   {'band':>12s} {'n cells':>8s} {'min':>5s} {'p50':>6s} {'max':>5s} "
      f"{'median range K':>15s}")
for lo in range(-90, 90, 10):
    m = ok & (LAT >= lo) & (LAT < lo + 10)
    if not m.any():
        continue
    print(f"   {lo:+4d}..{lo+10:+4d} {int(m.sum()):>8,} "
          f"{nlt[m].min():>5.0f} {np.median(nlt[m]):>6.1f} {nlt[m].max():>5.0f} "
          f"{np.median(rng[m]):>15.2f}")

print()
print("2. SOUTH POLE SPECIFICALLY -- where the targets are")
for lo, hi, lbl in ((-90, -85, "85-90 S"), (-90, -80, "80-90 S"),
                    (-5, 5, "equator +/-5 (reference)")):
    m = ok & (LAT >= lo) & (LAT < hi)
    print(f"   {lbl:26s} n {int(m.sum()):>7,}  n_lt min {nlt[m].min():>3.0f} "
          f"p50 {np.median(nlt[m]):>5.1f} max {nlt[m].max():>3.0f}   "
          f"median range {np.median(rng[m]):>7.2f} K")

print()
print("3. RAW correlations -- CONFOUNDED BY LATITUDE, shown for completeness")
for nm, a in (("range", rng), ("tbol_max", tmax), ("tbol_min", tmin)):
    print(f"   corr(n_local_time, {nm:9s}) = "
          f"{np.corrcoef(nlt[ok], a[ok])[0,1]:+.4f}")

print()
print("4. WITHIN-BAND correlations -- THIS IS THE TEST")
print("   latitude held effectively constant inside each 2-degree band.")
print(f"   {'band':>12s} {'n':>7s} {'r(nlt,range)':>13s} {'r(nlt,max)':>11s} "
      f"{'r(nlt,min)':>11s}")
acc = {"range": [], "max": [], "min": []}
wts = []
for lo in range(-90, 90, 2):
    m = ok & (LAT >= lo) & (LAT < lo + 2)
    if m.sum() < 200 or nlt[m].std() == 0:
        continue
    rr = np.corrcoef(nlt[m], rng[m])[0, 1]
    rx = np.corrcoef(nlt[m], tmax[m])[0, 1]
    rn = np.corrcoef(nlt[m], tmin[m])[0, 1]
    acc["range"].append(rr); acc["max"].append(rx); acc["min"].append(rn)
    wts.append(int(m.sum()))
    if lo % 20 == 0 or lo in (-90, -86, 88):
        print(f"   {lo:+4d}..{lo+2:+4d} {int(m.sum()):>7,} {rr:>13.4f} "
              f"{rx:>11.4f} {rn:>11.4f}")
wts = np.array(wts, dtype=float)
print()
for k in ("range", "max", "min"):
    a = np.array(acc[k])
    print(f"   {k:6s}: mean within-band r = {np.average(a, weights=wts):+.4f}"
          f"   median {np.median(a):+.4f}   "
          f"bands positive {int((a>0).sum())}/{a.size}")

print()
print("5. IS THE EFFECT MONOTONIC IN SAMPLING? -- medians by n_local_time")
print("   computed WITHIN 2-degree latitude bands, then averaged over bands,")
print("   so latitude cannot produce the trend.")
edges = [40, 50, 55, 60, 65, 70, 80, 97]
rows = {k: [[] for _ in range(len(edges) - 1)] for k in ("range", "max", "min")}
for lo in range(-90, 90, 2):
    m0 = ok & (LAT >= lo) & (LAT < lo + 2)
    if m0.sum() < 200:
        continue
    base = {k: np.median(v[m0]) for k, v in
            (("range", rng), ("max", tmax), ("min", tmin))}
    for i, (a, b) in enumerate(zip(edges[:-1], edges[1:])):
        m = m0 & (nlt >= a) & (nlt < b)
        if m.sum() < 20:
            continue
        for k, v in (("range", rng), ("max", tmax), ("min", tmin)):
            rows[k][i].append(np.median(v[m]) - base[k])
print(f"   {'n_lt bin':>12s} {'bands':>6s} {'d range K':>11s} "
      f"{'d max K':>9s} {'d min K':>9s}")
out = {}
for i, (a, b) in enumerate(zip(edges[:-1], edges[1:])):
    if not rows["range"][i]:
        continue
    dr = float(np.mean(rows["range"][i]))
    dx = float(np.mean(rows["max"][i]))
    dn = float(np.mean(rows["min"][i]))
    print(f"   {a:>5d}-{b-1:<6d} {len(rows['range'][i]):>6d} {dr:>11.3f} "
          f"{dx:>9.3f} {dn:>9.3f}")
    out[f"{a}-{b-1}"] = dict(bands=len(rows["range"][i]), d_range=dr,
                             d_max=dx, d_min=dn)
print()
print("   (values are deviations from each band's own median, in K, so a")
print("    rising d_range with sampling IS the bias)")

keys = sorted(out, key=lambda s: int(s.split("-")[0]))
dr = [out[k]["d_range"] for k in keys]
dx = [out[k]["d_max"] for k in keys]
dn = [out[k]["d_min"] for k in keys]
mono = all(y >= x - 0.05 for x, y in zip(dr, dr[1:]))
print(f"   median range rises monotonically with sampling: {mono}")
print(f"   total swing across the sampling range: range {dr[-1]-dr[0]:+.2f} K, "
       f"max {dx[-1]-dx[0]:+.2f} K, min {dn[-1]-dn[0]:+.2f} K")
print(f"   max and min move in OPPOSITE directions as predicted: "
      f"{(dx[-1]-dx[0]) * (dn[-1]-dn[0]) < 0}")

print()
print("6. WHAT A MINIMUM-SAMPLING CUT WOULD COST")
for thr in (50, 60, 70, 80):
    g = ok & (nlt >= thr)
    sp = ok & (LAT < -85)
    spg = sp & (nlt >= thr)
    print(f"   n_lt >= {thr:2d}: keeps {100*g.sum()/ok.sum():6.2f}% globally, "
          f"{100*spg.sum()/max(sp.sum(),1):6.2f}% of 85-90 S "
          f"({int(spg.sum()):,} of {int(sp.sum()):,} cells)")

io.open(os.path.join(D, "sampling_bias.json"), "w", encoding="utf-8").write(
    json.dumps(dict(
        corr_nlt_abslat=float(r_abs), corr_nlt_lat=float(r_sig),
        within_band_mean_r={k: float(np.average(np.array(acc[k]), weights=wts))
                            for k in acc},
        deviations_by_nlt=out, monotonic=bool(mono),
        swing_K=dict(range=dr[-1]-dr[0], max=dx[-1]-dx[0], min=dn[-1]-dn[0]),
    ), indent=1))
