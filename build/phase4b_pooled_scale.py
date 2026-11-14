"""
PHASE 4b -- THE POOLED SCALE. Step 3 as decided on 11 Nov 2026 (B33).

    python build/phase4b_pooled_scale.py

THE DECISION (Sherozbek, 11 Nov 2026)
    One combined scale per variable, for the Earth-Moon system and the
    Earth-Mars system separately. It is the main result and the only result.
    Per-body ranking is no longer used for matching.

WHY
    Ranking each body against itself asks "does this place play the same
    ROLE on its own world". It does not ask "is this place physically
    alike". His example: 40 units is the 95th percentile on Mars and 50 is
    the 95th on Earth. Separate scales match the Mars place to the Earth
    place at 50, and rank the Earth place that really is at 40 as a worse
    match. Measured on the cube (B33): median lunar roughness at 21 km is
    356 m, Earth's is 35 m; separate scales pair them.

THE TRANSFORM
    For one variable and one pairing, with Earth values E (the reference
    population, complete cases) and body values B (every finite cell):

        F_E(x) = share of E below x, counting ties as half
        F_B(x) = the same for B
        p(x)   = 0.5 * F_E(x) + 0.5 * F_B(x)        the pooled percentile
        z(x)   = inverse normal of p(x)             the normal score

    One function of the physical value, applied to BOTH bodies. Two cells
    with the same physical value get the same z whichever body they are on.

    EQUAL WEIGHT PER BODY. Earth has 3.2 million cells, the Moon 0.8
    million. Pooling by cell count would let the grid sizes set the scale.

    The normal score is in the method spec (step 3, z = inverse normal of
    p) and was missing from the calibration until today.

GATES, stated before running
    G1  both layers carry the SAME unit string in the manifest. A variable
        whose two layers are different quantities CANNOT be pooled and the
        script refuses it (Earth apparent thermal inertia in K^-1 against
        Mars thermal inertia in tiu is the known case).
    G2  0 < p < 1 everywhere, so every z is finite.
    G3  z never decreases when the physical value increases.
    G4  mean of p over Earth plus mean of p over the body equals 1 to 1e-6.
        This is an identity of the equal-weight pool and fails if a weight
        or a tie is handled wrongly.

OUTPUT (cube/phase4)
    pooled_z_earth_<body>.npy   float32 (dims, complete Earth cells)
    pooled_z_<body>.npy         float32 (dims, all cells of the body), NaN
                                where the layer has no value
    pooled_scale_<body>.npz     value -> p knots per variable, for a cell
                                that is not in the stored arrays (a click on
                                an ice pixel); accurate to about 1e-4 in p
    pooled_scale_summary.json   what was pooled, the gates, how much of the
                                scale each body occupies
"""

import io
import json
import os
import sys
import time

import numpy as np
from scipy.special import ndtri

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

HP = os.path.join(C.ROOT, "cube", "healpix")
P4 = os.path.join(C.ROOT, "cube", "phase4")
NS = {"earth": 1024, "moon": 256, "mars": 512}
N_KNOTS = 5001

# every variable the pairing COULD rank; G1 decides which can be pooled
CANDIDATES = {
    "moon": ["slope", "roughness_5.25km", "roughness_10.5km", "roughness_21km",
             "roughness_42km", "tpi_21km", "tpi_7km", "svf_30km",
             "temp_level", "temp_range_diurnal", "SiO2", "FeO"],
    "mars": ["slope", "roughness_5.25km", "roughness_10.5km", "roughness_21km",
             "roughness_42km", "tpi_21km", "tpi_7km", "svf_30km", "SiO2", "FeO",
             "thermal_inertia", "temp_level", "temp_range_diurnal",
             "temp_range_seasonal"],
}


def fmid(sorted_vals, x):
    """share of sorted_vals below x, ties counted as half."""
    lo = np.searchsorted(sorted_vals, x, side="left")
    hi = np.searchsorted(sorted_vals, x, side="right")
    return (lo + hi) / (2.0 * sorted_vals.size)


def main():
    if "--force" not in sys.argv:
        raise SystemExit("FROZEN (B38, 11 Nov 2026): step 3 is the min-max scale, build/phase4b_minmax_scale.py. "
                         "This script is kept as the record of B33. Pass --force only to reproduce B33.")
    t0 = time.perf_counter()
    man = json.load(io.open(C.MANIFEST, encoding="utf-8"))["layers"]
    ref_pix = np.load(os.path.join(P4, "ref_pixels.npy"))
    complete = np.load(os.path.join(P4, "complete_mask.npy"))
    epix = ref_pix[complete]
    print("=" * 78)
    print("PHASE 4b -- THE POOLED SCALE (one scale per variable, per pairing)")
    print("=" * 78)
    print(f"Earth: {epix.size:,} complete reference cells")
    summary = dict(
        decided="Sherozbek, 11 Nov 2026; VARIABLES.md B33",
        transform="p = 0.5*F_earth(x) + 0.5*F_body(x), ties as half; z = inverse normal of p",
        earth_population="reference population, complete cases (phase4a)",
        body_population="every finite cell of the layer",
        earth_cells=int(epix.size), pairings={})
    ok_all = True
    for body, cands in CANDIDATES.items():
        ns = NS[body]
        print(f"\n--- EARTH + {body.upper()} ---")
        print(f"{'variable':20s} {'unit':>10s} {'body cells':>11s} "
              f"{'Earth p 1..99%':>16s} {'body p 1..99%':>16s} "
              f"{'Earth z mean/sd':>16s}  gates")
        used, ze, zb, knots, rec = [], [], [], {}, {}
        refused = {}
        for d in cands:
            ue = str(man[f"earth_{d}"].get("units"))
            ub = str(man[f"{body}_{d}"].get("units"))
            if ue != ub:
                refused[d] = dict(earth_units=ue, body_units=ub,
                                  reason="G1: different quantities; cannot share one scale")
                print(f"{d:20s} REFUSED by G1: Earth '{ue}' against {body} '{ub}'")
                continue
            e = np.load(os.path.join(HP, f"earth_{d}_nside1024.npy"))[epix].astype(np.float64)
            b_all = np.load(os.path.join(HP, f"{body}_{d}_nside{ns}.npy")).astype(np.float64)
            fin = np.isfinite(b_all)
            b = b_all[fin]
            se, sb = np.sort(e), np.sort(b)
            pe = 0.5 * fmid(se, e) + 0.5 * fmid(sb, e)
            pb = 0.5 * fmid(se, b) + 0.5 * fmid(sb, b)
            g2 = bool(pe.min() > 0 and pe.max() < 1 and pb.min() > 0 and pb.max() < 1)
            z_e, z_b = ndtri(pe), ndtri(pb)
            allx = np.concatenate([e, b])
            allz = np.concatenate([z_e, z_b])
            o = np.argsort(allx, kind="stable")
            g3 = bool(np.all(np.diff(allz[o]) >= -1e-12))
            g4 = float(pe.mean() + pb.mean())
            g4ok = abs(g4 - 1.0) < 1e-6
            ok = g2 and g3 and g4ok and bool(np.isfinite(z_e).all() and np.isfinite(z_b).all())
            ok_all &= ok
            qe = np.percentile(pe, [1, 99])
            qb = np.percentile(pb, [1, 99])
            print(f"{d:20s} {ue[:10]:>10s} {b.size:11,d} "
                  f"{qe[0]:7.3f}..{qe[1]:6.3f} {qb[0]:7.3f}..{qb[1]:6.3f} "
                  f"{z_e.mean():7.2f}/{z_e.std():5.2f}   "
                  f"G2 {'ok' if g2 else 'FAIL'} G3 {'ok' if g3 else 'FAIL'} "
                  f"G4 {g4:.7f} {'ok' if g4ok else 'FAIL'}")
            full = np.full(b_all.size, np.nan, dtype=np.float32)
            full[fin] = z_b.astype(np.float32)
            used.append(d)
            ze.append(z_e.astype(np.float32))
            zb.append(full)
            qs = np.linspace(0.0, 1.0, N_KNOTS)
            kx = np.unique(np.concatenate([np.quantile(se, qs), np.quantile(sb, qs)]))
            knots[d + "__x"] = kx
            knots[d + "__p"] = 0.5 * fmid(se, kx) + 0.5 * fmid(sb, kx)
            rec[d] = dict(
                units=ue, body_cells=int(b.size),
                earth_p_p1_p99=[float(qe[0]), float(qe[1])],
                body_p_p1_p99=[float(qb[0]), float(qb[1])],
                earth_z_mean=float(z_e.mean()), earth_z_sd=float(z_e.std()),
                body_z_mean=float(z_b.mean()), body_z_sd=float(z_b.std()),
                # how separate the two bodies are on this variable:
                # 0.5 = fully mixed, 0 or 1 = no overlap at all
                prob_body_above_earth=float(pb.mean() - 0.25) * 2.0,
                gates=dict(G2=g2, G3=g3, G4_sum=g4, G4=g4ok))
            del e, b_all, b, se, sb, pe, pb, allx, allz
        if not ok_all:
            print("A GATE FAILED -- nothing written")
            return 1
        np.save(os.path.join(P4, f"pooled_z_earth_{body}.npy"), np.vstack(ze))
        np.save(os.path.join(P4, f"pooled_z_{body}.npy"), np.vstack(zb))
        np.savez_compressed(os.path.join(P4, f"pooled_scale_{body}.npz"), **knots)
        summary["pairings"][body] = dict(
            names=used, refused=refused, body_nside=ns, variables=rec,
            files=dict(earth=f"cube/phase4/pooled_z_earth_{body}.npy",
                       body=f"cube/phase4/pooled_z_{body}.npy",
                       knots=f"cube/phase4/pooled_scale_{body}.npz"))
        print(f"wrote pooled z for Earth + {body}: {len(used)} variables"
              + (f"; REFUSED {list(refused)}" if refused else ""))
    summary["built_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    io.open(os.path.join(P4, "pooled_scale_summary.json"), "w",
            encoding="utf-8").write(json.dumps(summary, indent=1))
    print(f"\ndone in {time.perf_counter()-t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
