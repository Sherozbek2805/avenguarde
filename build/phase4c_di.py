"""
PHASE 4c -- GROUP-WISE (block-diagonal) whitening, d_bar, and the DI threshold.

    python build/phase4c_di.py

WHAT CHANGED ON 11 NOV 2026 (VARIABLES.md B34)
    Until today this script whitened ALL dimensions of a set together. The
    method spec decides otherwise (step 4, "The group-weight conflict"):

        "DECISION: block-diagonal whitening. Terrain variables are
         decorrelated among themselves, thermal among themselves, and
         cross-group correlation is left alone."

    The reason is in the spec too. After a joint whitening every axis is a
    blend of all variables, so "which group is this difference in" has no
    answer. Group weights, the four presets, the per-group index and
    "worst group" in the output contract all need the groups kept apart.
    The joint calibration could not serve them. Sherozbek confirmed the
    rebuild on 11 Nov.

WHAT THE DI IS (Meyer & Pebesma 2021)
    For a query point, DI = (distance to the reference set) / d_bar, where
    d_bar is the MEAN pairwise distance within the reference set. The
    reference set is Earth's ice-free, water-free land; the queries are
    lunar and martian target cells.

THE DISTANCE, exactly
    Input: min-max positions z (phase4b_minmax_scale.py, B38), per pairing.
    Until 11 Nov 2026, night, the input was the pooled normal score (B33).
    The min-max position is a straight-line function of the physical value,
    so step 1 below makes the distance identical to one on the raw values.
    1. standardise by Earth:      u = (z - mean_E) / sd_E
    2. whiten WITHIN each group:  v_g = u_g @ W_g
       W_g = inverse square root of that group's Earth correlation matrix,
       eigenvalues below LAMBDA_FLOOR raised to the floor (B8).
    3. per-group distance:        d_g(a, b) = || v_g(a) - v_g(b) ||
    4. combined distance:         d(a, b) = sqrt( sum_g  d_g(a, b)^2 )

    whiten_<set>.npy stores the block-diagonal matrix W with the W_g on its
    diagonal, so steps 2-4 are one matrix product and one Euclidean
    distance.

    GROUPS  terrain: slope, roughness, landform position, sky view
            thermal: the temperature variables
            composition: SiO2, FeO

NO GROUP WEIGHTS IN v1 (B35, Sherozbek, 11 Nov 2026)
    The weight check of step 10 and the four weight presets are removed
    from the method and listed as future work. Every group counts with
    weight 1, so the combined distance is the plain distance between
    block-whitened vectors. The groups are still kept apart, because the
    per-group index and "worst group" need them.

WHAT IS STORED, per set
    d_bar, d_bar per group (for the per-group index, which divides by its
    own group's d_bar), the floored
    eigenvalue count per group, and the within-reference DI threshold.

d_bar AND THE THRESHOLD ARE PER DIMENSION SET. A DI computed in one is not
comparable with a DI computed in another.
"""

import io
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

P4 = os.path.join(C.ROOT, "cube", "phase4")
SEED = 20261108
LAMBDA_FLOOR = 0.10          # the B8 threshold, reused as the floor
N_DBAR = 5000                # subsample for d_bar
N_CAL = 200000               # subsample for threshold calibration

TERRAIN = ["slope", "roughness_5.25km", "roughness_10.5km", "roughness_21km",
           "roughness_42km", "tpi_21km", "tpi_7km", "svf_30km"]
# B33 / B38: one shared scale per pairing (now min-max). Each set names the body it shares the scale with. Thermal
# inertia is not here: its two layers are different quantities.
# The ORDER of groups in a set is the order of its dimensions on disk.
SETS = {
    "earth_moon": ("moon", [
        ("terrain", TERRAIN),
        ("thermal", ["temp_level", "temp_range_diurnal"]),
        ("composition", ["SiO2", "FeO"])]),
    "earth_mars": ("mars", [
        ("terrain", TERRAIN),
        ("composition", ["SiO2", "FeO"]),
        ("thermal", ["temp_level", "temp_range_diurnal", "temp_range_seasonal"])]),
    # B32: the PRIMARY construction of the Mars preset zones.
    "earth_mars_no_composition": ("mars", [
        ("terrain", TERRAIN),
        ("thermal", ["temp_level", "temp_range_diurnal", "temp_range_seasonal"])]),
}


def whiten_matrix(R, floor):
    """Inverse square root of R with eigenvalues floored."""
    ev, V = np.linalg.eigh(R)
    raised = int(np.sum(ev < floor))
    var_touched = float(np.sum(ev[ev < floor]) / np.sum(ev))
    evf = np.maximum(ev, floor)
    W = V @ np.diag(evf ** -0.5) @ V.T
    return W, ev, raised, var_touched


def mean_pairwise(A):
    d = np.sqrt(np.maximum(((A[:, None, :] - A[None, :, :]) ** 2).sum(-1), 0.0))
    return float(d[np.triu_indices(A.shape[0], 1)].mean())


def main():
    from scipy.spatial import cKDTree
    rng = np.random.default_rng(SEED)
    pooled = json.load(io.open(os.path.join(P4, "minmax_scale_summary.json"),
                               encoding="utf-8"))
    n = int(pooled["earth_cells"])
    print("=" * 78)
    print("PHASE 4c -- GROUP-WISE WHITENING, d_bar, DI THRESHOLD")
    print("=" * 78)
    print(f"Earth reference population: {n:,} complete cells, min-max scale (B38)")
    print(f"seed {SEED}, lambda floor {LAMBDA_FLOOR}")

    out = {}
    for tag, (body, groups) in SETS.items():
        pnames = pooled["pairings"][body]["names"]
        used = [d for _, ds in groups for d in ds]
        missing = [c for c in used if c not in pnames]
        if missing:
            raise SystemExit(f"{tag}: {missing} not on the shared scale")
        idx = [pnames.index(c) for c in used]
        P = np.load(os.path.join(P4, f"minmax_earth_{body}.npy"), mmap_mode="r")
        X = np.asarray(P[idx]).T.astype(np.float64)          # (n, d) min-max positions
        mu, sd = X.mean(axis=0), X.std(axis=0)
        U = (X - mu) / sd
        D = len(used)
        W = np.zeros((D, D))
        ginfo, sl = {}, {}
        print(f"\n--- {tag.upper()}: {D} dimensions in {len(groups)} groups ---")
        a = 0
        for g, ds in groups:
            b = a + len(ds)
            Rg = np.corrcoef(U[:, a:b], rowvar=False)
            Wg, ev, raised, vt = whiten_matrix(Rg, LAMBDA_FLOOR)
            W[a:b, a:b] = Wg
            sl[g] = (a, b)
            ginfo[g] = dict(dimensions=list(ds), index_range=[a, b],
                            eigenvalues=[float(x) for x in ev],
                            eigenvalues_floored=raised,
                            variance_fraction_floored=vt)
            print(f"  {g:12s} {len(ds)} dims  eigenvalues {ev.min():.4f} .. "
                  f"{ev.max():.4f}  floored {raised}")
            a = b
        Z = U @ W                                            # block-whitened

        # cross-group correlation that is deliberately LEFT ALONE
        Rz = np.corrcoef(Z[rng.choice(n, 200000, replace=False)], rowvar=False)
        cross = {}
        gl = list(sl)
        for i in range(len(gl)):
            for j in range(i + 1, len(gl)):
                (a1, b1), (a2, b2) = sl[gl[i]], sl[gl[j]]
                cross[f"{gl[i]}|{gl[j]}"] = float(np.abs(Rz[a1:b1, a2:b2]).max())
        print("  largest |correlation| left between groups: "
              + ", ".join(f"{k} {v:.2f}" for k, v in cross.items()))

        # ---- d_bar: combined and per group; one subsample
        s = rng.choice(n, size=min(N_DBAR, n), replace=False)
        A = Z[s]
        dbar = mean_pairwise(A)
        alt = np.array([mean_pairwise(Z[np.random.default_rng(SEED + 1 + k).choice(
            n, size=min(N_DBAR, n), replace=False)]) for k in range(5)])
        share = {}
        iu = np.triu_indices(A.shape[0], 1)
        tot = 0.0
        gsq = {}
        for g, (a1, b1) in sl.items():
            ginfo[g]["d_bar"] = mean_pairwise(A[:, a1:b1])
            dg = ((A[:, None, a1:b1] - A[None, :, a1:b1]) ** 2).sum(-1)[iu]
            gsq[g] = float(dg.sum())
            tot += gsq[g]
            del dg
        for g in sl:
            share[g] = gsq[g] / tot
            ginfo[g]["share_of_squared_distance_between_earth_cells"] = share[g]
        print(f"  d_bar = {dbar:.4f}; five further seeds "
              f"{alt.min():.4f} .. {alt.max():.4f}")
        print("  d_bar by group:  " + ", ".join(
            f"{g} {ginfo[g]['d_bar']:.4f}" for g in sl))
        print("  share of the squared distance between Earth cells: "
              + ", ".join(f"{g} {100*v:.0f}%" for g, v in share.items()))

        # ---- within-reference nearest-neighbour DI, balanced
        cal = rng.choice(n, size=min(N_CAL, n), replace=False)
        nn, _ = cKDTree(Z[cal]).query(Z[cal], k=2, workers=-1)
        di = nn[:, 1] / dbar
        q = np.percentile(di, [50, 75, 90, 95, 99])
        thr = float(q[3])
        print(f"  within-reference DI p50 {q[0]:.4f} p95 {q[3]:.4f}; "
              f"DI THRESHOLD = {thr:.4f}")

        np.save(os.path.join(P4, f"whiten_{tag}.npy"), W)
        np.save(os.path.join(P4, f"center_{tag}.npy"), np.vstack([mu, sd]))
        out[tag] = dict(
            dimensions=used, n_reference=int(n),
            whitening=("GROUP-WISE (block-diagonal): each group is whitened "
                       "by the inverse square root of its own Earth "
                       "correlation matrix, eigenvalues floored at "
                       f"{LAMBDA_FLOOR}; correlation BETWEEN groups is left "
                       "alone (spec step 4; B34)"),
            scale=("MIN-MAX: position = (x - lo) / (hi - lo), lo and hi over "
                   "Earth + %s, one scale per variable (B38; replaces the pooled percentile of B33)" % body),
            pooled_with=body,
            input_file=f"cube/phase4/minmax_earth_{body}.npy",
            target_file=f"cube/phase4/minmax_{body}.npy",
            pooled_names=pnames,
            centre_note=("center_<set>.npy holds Earth's mean and sd of the "
                         "min-max position per dimension; a cell's vector is "
                         "((z - mean) / sd) @ whiten_<set>.npy. Combined "
                         "distance: the plain distance between two such "
                         "vectors. No group weights (B35)."),
            groups=ginfo, group_order=list(sl),
            cross_group_max_abs_correlation=cross,
            lambda_floor=LAMBDA_FLOOR,
            eigenvalues_floored=int(sum(g["eigenvalues_floored"] for g in ginfo.values())),
            d_bar=dbar,
            d_bar_definition=("mean pairwise block-whitened distance between "
                              "Earth reference cells"),
            group_weights="none in v1; the weight check and the presets are future work (B35)",
            d_bar_seed=SEED, d_bar_subsample=int(A.shape[0]),
            d_bar_5seed_min=float(alt.min()), d_bar_5seed_max=float(alt.max()),
            d_bar_5seed_spread_pct=float(100 * (alt.max() - alt.min()) / dbar),
            di_threshold=thr,
            di_threshold_rule=("95th percentile of within-reference "
                               "nearest-neighbour DI"),
            di_percentiles=dict(p50=float(q[0]), p75=float(q[1]),
                                p90=float(q[2]), p95=float(q[3]),
                                p99=float(q[4])),
            calibration_subsample=int(len(cal)),
            warning=("d_bar and the DI threshold are PER DIMENSION SET. A DI "
                     "from one is not comparable with a DI from another, and "
                     "no null computed for one may be reused for another."))
        del X, U, Z, A

    io.open(os.path.join(P4, "phase4c_summary.json"), "w",
            encoding="utf-8").write(json.dumps(out, indent=1))
    print(f"\nwrote {P4}/phase4c_summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
