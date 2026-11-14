"""
THE B8 CHECK FOR THE WHOLE CANDIDATE SET: rank correlation and lambda_min,
for each pairing, with and without each candidate added after B24.

    python build/dimension_check.py

Generalises tpi7_dimension_check.py. Reads the candidate lists from
phase4a_percentile.py so the two cannot disagree, uses phase 4a's reference
population (cube/phase4/ref_pixels.npy) and its average-rank percentile
transform, and leaves every phase 4 artifact untouched. For each pairing it
reports the correlation row of every NEW candidate, lambda_min and the
eigenvalues below the 0.10 floor with and without the new set, and the
loadings of the smallest eigenvector. A candidate whose Earth layer is not
on disk is reported as missing and left out, as phase 4a does.
"""

import io
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C
import phase4a_percentile as P4A

HP = os.path.join(C.ROOT, "cube", "healpix")
P4 = os.path.join(C.ROOT, "cube", "phase4")
OUT = os.path.join(P4, "dimension_check.json")
B24_SETS = {   # the sets B24's results were computed on
    "earth_moon": ["slope", "roughness_5.25km", "roughness_10.5km", "roughness_21km",
                   "roughness_42km", "tpi_21km", "temp_level", "temp_range_diurnal",
                   "SiO2", "FeO"],
    "earth_mars": ["slope", "roughness_5.25km", "roughness_10.5km", "roughness_21km",
                   "roughness_42km", "tpi_21km"],
}
FLOOR = 0.10


def rank_pct(v):
    n = v.size
    o = np.argsort(v, kind="stable")
    sv = v[o]
    new = np.ones(n, dtype=bool)
    new[1:] = sv[1:] != sv[:-1]
    gid = np.cumsum(new) - 1
    starts = np.flatnonzero(new)
    ends = np.append(starts[1:], n)
    r = np.empty(n)
    r[o] = ((starts + ends - 1) / 2.0)[gid]
    return (r + 0.5) / n


def eig_report(R, names):
    ev, vec = np.linalg.eigh(R)
    i = int(np.argmin(ev))
    return dict(n=len(names), lambda_min=float(ev.min()),
                n_below_floor=int((ev < FLOOR).sum()),
                variance_below_floor_pct=round(100.0 * float(ev[ev < FLOOR].sum()) /
                                               float(ev.sum()), 4),
                eigenvalues=[round(float(e), 4) for e in ev],
                smallest_eigenvector={names[j]: round(float(vec[j, i]), 3)
                                      for j in range(len(names))})


def main():
    t0 = time.perf_counter()
    print("=" * 78)
    print("B8 CHECK -- the full candidate set, with and without the post-B24 additions")
    print("=" * 78)
    ref = np.load(os.path.join(P4, "ref_pixels.npy"))
    present, missing, cols = [], [], {}
    for c in P4A.CANDIDATES:
        p = os.path.join(HP, f"earth_{c}_nside{P4A.NSIDE}.npy")
        if not os.path.exists(p):
            missing.append(c)
            continue
        cols[c] = np.load(p)[ref]
        present.append(c)
    print(f"  candidates on disk: {present}")
    if missing:
        print(f"  MISSING (left out, as phase 4a would): {missing}")
    M = np.vstack([cols[c] for c in present])
    complete = np.all(np.isfinite(M), axis=0)
    n_c = int(complete.sum())
    print(f"  reference {ref.size:,} pixels; complete across {len(present)}: {n_c:,} "
          f"({100*n_c/ref.size:.3f}%)")
    per_layer_nan = {c: int((~np.isfinite(cols[c])).sum()) for c in present}
    P = np.vstack([rank_pct(M[i][complete]) for i in range(len(present))])
    R = np.corrcoef(P)
    out = dict(candidates=present, missing=missing, reference_pixels=int(ref.size),
               complete_cases=n_c, nan_in_reference=per_layer_nan,
               correlation={present[i]: {present[j]: round(float(R[i, j]), 4)
                                         for j in range(len(present))}
                            for i in range(len(present))},
               pairings={})
    sets = {"earth_moon": [c for c in P4A.EARTH_MOON if c in present],
            "earth_mars": [c for c in P4A.EARTH_MARS if c in present]}
    for tag, sub in sets.items():
        base = [c for c in B24_SETS[tag] if c in present]
        new = [c for c in sub if c not in B24_SETS[tag]]
        ib = [present.index(c) for c in base]
        ia = [present.index(c) for c in sub]
        before = eig_report(R[np.ix_(ib, ib)], base)
        after = eig_report(R[np.ix_(ia, ia)], sub)
        rows = {c: {d: round(float(R[present.index(c), present.index(d)]), 4)
                    for d in sub if d != c} for c in new}
        out["pairings"][tag] = dict(set=sub, added_since_B24=new,
                                    without=before, with_additions=after,
                                    new_candidate_correlations=rows)
        print(f"\n  {tag}: {len(base)} -> {len(sub)} candidates; added {new}")
        print(f"     lambda_min {before['lambda_min']:.4f} -> {after['lambda_min']:.4f}; "
              f"eigenvalues below {FLOOR}: {before['n_below_floor']} -> "
              f"{after['n_below_floor']}; variance below floor "
              f"{before['variance_below_floor_pct']:.3f}% -> "
              f"{after['variance_below_floor_pct']:.3f}%")
        for c in new:
            top = sorted(rows[c].items(), key=lambda kv: -abs(kv[1]))[:4]
            print(f"     {c:16s} strongest |rho|: " +
                  ", ".join(f"{d} {r:+.3f}" for d, r in top))
        print(f"     smallest eigenvector (with): {after['smallest_eigenvector']}")
    out["elapsed_s"] = round(time.perf_counter() - t0, 1)
    out["run_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, indent=1))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
