"""
THE B8 CHECK FOR A NEW CANDIDATE: correlation and lambda_min WITH tpi_7km.

    python build/tpi7_dimension_check.py

B8 / HANDOVER: VIF is a diagnostic, not a pruning rule. Whitening handles
redundancy; what it cannot handle is near-singularity, so a variable is
dropped only if the smallest eigenvalue of the rank-correlation matrix falls
below 0.10 -- and B24 already floors eigenvalues at 0.10 in the whitening.
This script measures what adding tpi_7km does to that matrix, for both
pairings, WITHOUT touching the phase 4 artifacts (percentiles.npy and
phase4a_summary.json stay as B24 left them; phase4a_percentile.py carries the
new candidate for the next full run).

Also measured, per body: rank correlation of tpi_7km with tpi_21km and with
slope over all valid pixels, so the Moon and Mars are not assumed to behave
like Earth.
"""

import io
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

HP = os.path.join(C.ROOT, "cube", "healpix")
P4 = os.path.join(C.ROOT, "cube", "phase4")
OUT = os.path.join(P4, "tpi7_dimension_check.json")
NEW = "tpi_7km"
BASE = ["slope", "roughness_5.25km", "roughness_10.5km", "roughness_21km",
        "roughness_42km", "tpi_21km", "temp_level", "temp_range_diurnal",
        "temp_range_seasonal", "SiO2", "FeO"]
EARTH_MOON = [c for c in BASE if c != "temp_range_seasonal"] + [NEW]
EARTH_MARS = ["slope", "roughness_5.25km", "roughness_10.5km",
              "roughness_21km", "roughness_42km", "tpi_21km", NEW]
LAMBDA_FLOOR = 0.10


def rank_pct(v):
    """Average ranks for ties, as phase4a does it, vectorised."""
    n = v.size
    o = np.argsort(v, kind="stable")
    sv = v[o]
    # group boundaries of equal values
    new = np.ones(n, dtype=bool)
    new[1:] = sv[1:] != sv[:-1]
    gid = np.cumsum(new) - 1
    starts = np.flatnonzero(new)
    ends = np.append(starts[1:], n)
    avg = (starts + ends - 1) / 2.0
    r = np.empty(n, dtype=np.float64)
    r[o] = avg[gid]
    return (r + 0.5) / n


def load(body, name):
    p = os.path.join(HP, f"{body}_{name}_nside{C.NSIDE[body]}.npy")
    if not os.path.exists(p):
        raise SystemExit(f"STOP: {p} missing")
    return np.load(p)


def eig_report(R, names):
    ev, vec = np.linalg.eigh(R)
    i = int(np.argmin(ev))
    load_ = {names[j]: round(float(vec[j, i]), 3) for j in range(len(names))}
    return dict(lambda_min=float(ev.min()), lambda_max=float(ev.max()),
                condition=float(ev.max() / max(ev.min(), 1e-12)),
                n_below_floor=int((ev < LAMBDA_FLOOR).sum()),
                variance_below_floor_pct=round(
                    100.0 * float(ev[ev < LAMBDA_FLOOR].sum()) / float(ev.sum()), 4),
                eigenvalues=[round(float(e), 4) for e in ev],
                smallest_eigenvector=load_)


def main():
    t0 = time.perf_counter()
    print("=" * 78)
    print("B8 CHECK -- what tpi_7km does to the correlation matrix")
    print("=" * 78)
    out = dict(new_candidate=NEW, lambda_floor=LAMBDA_FLOOR, per_body={},
               earth_reference={})

    # ---- per body: tpi_7km against tpi_21km and slope, all valid pixels
    for body in ("moon", "mars", "earth"):
        a = load(body, NEW)
        res = {}
        for other in ("tpi_21km", "slope", "roughness_5.25km"):
            b = load(body, other)
            v = np.isfinite(a) & np.isfinite(b)
            r = float(np.corrcoef(rank_pct(a[v]), rank_pct(b[v]))[0, 1])
            res[f"spearman_vs_{other}"] = round(r, 4)
            del b
        fa = a[np.isfinite(a)]
        res.update(n_valid=int(fa.size), p1=float(np.percentile(fa, 1)),
                   p50=float(np.median(fa)), p99=float(np.percentile(fa, 99)),
                   iqr=float(np.percentile(fa, 75) - np.percentile(fa, 25)))
        out["per_body"][body] = res
        print(f"  {body:5s} tpi_7km: rho(tpi_21km) {res['spearman_vs_tpi_21km']:+.4f}"
              f"  rho(slope) {res['spearman_vs_slope']:+.4f}  "
              f"rho(roughness_5.25km) {res['spearman_vs_roughness_5.25km']:+.4f}"
              f"  IQR {res['iqr']:.2f} m")
        del a

    # ---- Earth reference population: the full matrix, with and without
    ref_idx = np.load(os.path.join(P4, "ref_pixels.npy"))
    names = BASE + [NEW]
    cols = {}
    for c in names:
        cols[c] = load("earth", c)[ref_idx]
    M = np.vstack([cols[c] for c in names])
    complete = np.all(np.isfinite(M), axis=0)
    n_complete = int(complete.sum())
    print(f"\n  Earth reference: {ref_idx.size:,} pixels, complete across "
          f"{len(names)} candidates: {n_complete:,} "
          f"({100*n_complete/ref_idx.size:.3f}%)")
    lost_new = int(np.sum(np.isfinite(cols[NEW]) == False))
    print(f"  tpi_7km NaN inside the reference population: {lost_new:,}")
    P = np.vstack([rank_pct(M[i][complete]) for i in range(len(names))])
    R = np.corrcoef(P)
    iqr = np.percentile(P, 75, axis=1) - np.percentile(P, 25, axis=1)
    out["earth_reference"] = dict(
        reference_pixels=int(ref_idx.size), complete_cases=n_complete,
        tpi_7km_nan_in_reference=lost_new,
        tpi_7km_percentile_iqr=float(iqr[names.index(NEW)]),
        correlation_row_tpi_7km={names[j]: round(float(R[names.index(NEW), j]), 4)
                                 for j in range(len(names))})
    print(f"\n  rank correlation of tpi_7km with each candidate (Earth reference):")
    for j, c in enumerate(names):
        if c != NEW:
            print(f"     {c:22s} {R[names.index(NEW), j]:+.4f}")

    for tag, sub in (("earth_moon", EARTH_MOON), ("earth_mars", EARTH_MARS)):
        old = [c for c in sub if c != NEW]
        io_ = [names.index(c) for c in old]
        in_ = [names.index(c) for c in sub]
        before = eig_report(R[np.ix_(io_, io_)], old)
        after = eig_report(R[np.ix_(in_, in_)], sub)
        out["earth_reference"][tag] = dict(
            without=dict(n=len(old), **before), with_tpi_7km=dict(n=len(sub), **after),
            verdict=("KEEP -- lambda_min of the set did not fall below the floor "
                     "because of tpi_7km; the floored directions are the "
                     "roughness family, as before"
                     if after["n_below_floor"] <= before["n_below_floor"]
                     else "EXAMINE -- tpi_7km adds a direction below the floor"))
        print(f"\n  {tag}: {len(old)} -> {len(sub)} candidates")
        print(f"     lambda_min {before['lambda_min']:.4f} -> {after['lambda_min']:.4f}"
              f"   eigenvalues below {LAMBDA_FLOOR}: {before['n_below_floor']} -> "
              f"{after['n_below_floor']}   variance below floor "
              f"{before['variance_below_floor_pct']:.3f}% -> "
              f"{after['variance_below_floor_pct']:.3f}%")
        print(f"     smallest eigenvector loadings (with): "
              f"{after['smallest_eigenvector']}")
        print(f"     {out['earth_reference'][tag]['verdict']}")

    out["elapsed_s"] = round(time.perf_counter() - t0, 1)
    out["run_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    out["note"] = ("Measured on the SAME reference population and rank "
                   "transform as phase4a, over complete cases across all 12 "
                   "candidates. phase 4 artifacts were not modified; "
                   "percentiles.npy still holds the 11-candidate B24 run.")
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, indent=1))
    print(f"\nwrote {OUT}  ({out['elapsed_s']} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
