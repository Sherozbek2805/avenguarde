"""
PHASE 4a -- percentile transform and the correlation matrix.

    python build/phase4a_percentile.py

WHAT THIS IS
    Every candidate dimension is rank-transformed WITHIN Earth's reference
    population, then the correlation matrix of those ranks is formed. That
    matrix is the input B8's VIF / smallest-eigenvalue selection needs, and
    it is also the thing that reveals redundancy before any distance is
    computed.

WHY THE REFERENCE POPULATION AND NOT THE GLOBE
    The percentile transform must be taken over the population the
    dissimilarity index will actually compare against -- Earth's ice-free,
    water-free land. Ranking over the whole sphere would put every land
    pixel in the upper tail of layers that are land-only and would make the
    ocean define the scale for layers that have ocean values.

    Pearson correlation of ranks IS Spearman correlation of the raw values,
    so this matrix is rank-based throughout and no layer's distribution
    shape can dominate it.

NOTHING IS DROPPED HERE. 4a measures. 4b decides.
"""

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
HP = os.path.join(C.ROOT, "cube", "healpix")
P4 = os.path.join(C.ROOT, "cube", "phase4")
MASK = os.path.join(HP, f"earth_reference_mask_nside{NSIDE}.npy")

# every Earth candidate. Pairing subsets are applied later, not here.
CANDIDATES = [
    "slope", "roughness_5.25km", "roughness_10.5km", "roughness_21km",
    "roughness_42km", "tpi_21km",
    "temp_level", "temp_range_diurnal", "temp_range_seasonal",
    "SiO2", "FeO",
    "tpi_7km",            # added 9 Nov 2026, Sherozbek's decision; VARIABLES B26
    "svf_30km",           # added 9 Nov 2026, B27
    # thermal_inertia REMOVED 11 Nov 2026 (B33): Earth's layer is an apparent
    # proxy in K^-1, Mars's is in tiu. Two different quantities cannot share
    # one pooled scale, so it no longer ranks; it is a characterization layer.
]
EARTH_MOON = [c for c in CANDIDATES if c != "temp_range_seasonal"]
EARTH_MARS = ["slope", "roughness_5.25km", "roughness_10.5km",
              "roughness_21km", "roughness_42km", "tpi_21km", "tpi_7km",
              "svf_30km", "SiO2", "FeO",   # thermal_inertia removed, B33
              "temp_level", "temp_range_diurnal", "temp_range_seasonal"]   # B28: Mars thermal MODELLED at pixel scale


def build_mask():
    """Load the reference mask. It has ONE builder: build/reference_mask.py.

    Until 10 Nov 2026 this function binned the mask itself when the file was
    missing. Since B31(e) the mask follows two rules (ice thickness north of
    60 S, SCAR GeoMAP exposed rock south of it), so rebuilding it here would
    silently drop the Antarctic rule. Refuse instead.
    """
    if not os.path.exists(MASK):
        raise SystemExit("the reference mask is missing: run "
                         "python build/reference_mask.py first")
    return np.load(MASK)


def rank_pct(v):
    """Percentile in [0,1] with AVERAGE ranks for ties.

    Average ranks matter here: composition is a lookup with large tie
    blocks, and ordinal ranking would impose an arbitrary order inside them.
    """
    n = v.size
    o = np.argsort(v, kind="stable")
    r = np.empty(n, dtype=np.float64)
    sv = v[o]
    i = 0
    while i < n:
        j = i + 1
        while j < n and sv[j] == sv[i]:
            j += 1
        r[o[i:j]] = (i + j - 1) / 2.0
        i = j
    return (r + 0.5) / n


def main():
    os.makedirs(P4, exist_ok=True)
    print("=" * 78)
    print("PHASE 4a -- PERCENTILE TRANSFORM AND CORRELATION MATRIX")
    print("=" * 78)
    frac = build_mask()
    ref = np.isfinite(frac) & (frac > 0.5)
    print(f"\nEarth reference population: {int(ref.sum()):,} HEALPix pixels "
          f"({100*ref.mean():.3f}% of the sphere)")

    vals = {}
    print(f"\n{'layer':22s} {'valid in ref':>14s} {'%':>8s}")
    for c in CANDIDATES:
        p = os.path.join(HP, f"earth_{c}_nside{NSIDE}.npy")
        if not os.path.exists(p):
            print(f"  MISSING {p}")
            continue
        a = np.load(p)
        v = a[ref]
        vals[c] = v
        ok = np.isfinite(v)
        print(f"{c:22s} {int(ok.sum()):>14,} {100*ok.mean():>7.3f}%")
        del a

    names = [c for c in CANDIDATES if c in vals]
    M = np.vstack([vals[c] for c in names])
    complete = np.all(np.isfinite(M), axis=0)
    print(f"\ncomplete cases (every candidate present): {int(complete.sum()):,}"
          f" of {int(ref.sum()):,} ({100*complete.mean():.3f}%)")
    for c in names:
        lost = int(np.sum(np.isfinite(vals[c]) & ~complete))
        if lost:
            print(f"   {c:22s} loses {lost:>9,} pixels to other layers' gaps")

    # ---- percentile transform on the complete cases
    P = np.empty((len(names), int(complete.sum())), dtype=np.float32)
    for i, c in enumerate(names):
        P[i] = rank_pct(M[i][complete]).astype(np.float32)
    print(f"\npercentile transform: {P.shape[0]} layers x {P.shape[1]:,} "
          f"complete pixels, average ranks for ties")
    iqr = np.percentile(P, 75, axis=1) - np.percentile(P, 25, axis=1)
    print(f"\n{'layer':22s} {'pct IQR':>9s}  {'B8 >= 0.15':>11s}")
    for i, c in enumerate(names):
        print(f"{c:22s} {iqr[i]:9.4f}  {'PASS' if iqr[i] >= 0.15 else 'REJECT':>11s}")

    R = np.corrcoef(P)
    print("\nCORRELATION MATRIX (Pearson of ranks = Spearman of raw)")
    hdr = "".join(f"{c[:7]:>8s}" for c in names)
    print(f"{'':22s}{hdr}")
    for i, c in enumerate(names):
        print(f"{c:22s}" + "".join(f"{R[i,j]:8.3f}" for j in range(len(names))))

    print("\nPAIRS WITH |r| >= 0.70")
    hi = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if abs(R[i, j]) >= 0.70:
                hi.append((abs(R[i, j]), names[i], names[j], R[i, j]))
    for a_, x, y, r in sorted(hi, reverse=True):
        print(f"   {r:+.4f}  {x} <-> {y}")
    if not hi:
        print("   none")

    for tag, sub in (("EARTH-MOON", EARTH_MOON), ("EARTH-MARS", EARTH_MARS)):
        idx = [names.index(c) for c in sub if c in names]
        Rs = R[np.ix_(idx, idx)]
        ev = np.linalg.eigvalsh(Rs)
        print(f"\n{tag}: {len(idx)} candidates, lambda_min "
              f"{ev.min():.4f}, lambda_max {ev.max():.4f}, "
              f"condition {ev.max()/max(ev.min(),1e-12):.1f}")

    np.save(os.path.join(P4, "percentiles.npy"), P)
    np.save(os.path.join(P4, "complete_mask.npy"), complete)
    np.save(os.path.join(P4, "ref_pixels.npy"), np.where(ref)[0].astype(np.int32))
    io.open(os.path.join(P4, "phase4a_summary.json"), "w",
            encoding="utf-8").write(json.dumps(dict(
                nside=NSIDE, names=names,
                reference_pixels=int(ref.sum()),
                complete_cases=int(complete.sum()),
                percentile_iqr={c: float(iqr[i]) for i, c in enumerate(names)},
                correlation={names[i]: {names[j]: float(R[i, j])
                                        for j in range(len(names))}
                             for i in range(len(names))},
                status=("DIAGNOSTIC ONLY since 11 Nov 2026 (B33). percentiles.npy "
                        "holds PER-BODY Earth ranks and is used for the Spearman "
                        "redundancy check alone. Matching uses the POOLED scale: "
                        "pooled_z_earth_<body>.npy from phase4b_pooled_scale.py. "
                        "The engine must never read percentiles.npy."),
                note=("percentile transform uses AVERAGE ranks for ties, and "
                      "is taken over Earth's reference population (ice-free, "
                      "water-free land) -- NOT the globe. Pearson of ranks "
                      "is Spearman of the raw values."),
                built_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
                indent=1))
    print(f"\nwrote {P4}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
