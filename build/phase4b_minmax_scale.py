"""
PHASE 4b -- THE MIN-MAX SCALE. Step 3 as decided on 11 Nov 2026, night (B38).

    python build/phase4b_minmax_scale.py

THE DECISION (Sherozbek, 11 Nov 2026, VARIABLES.md B38)
    "The ranking system is min-max instead of percentile ranking", because
    the real structure of the values is kept. This replaces the pooled
    percentile and the normal score of B33 (phase4b_pooled_scale.py, which
    is now frozen). What B33 decided about SHARING stays: one scale per
    variable for Earth and the target body together, Earth-Moon and
    Earth-Mars separately.

THE TRANSFORM
    For one variable and one pairing, with Earth values E (the reference
    population, complete cases) and body values B (every finite cell):

        lo = the smallest value in E or B
        hi = the largest value in E or B
        position(x) = (x - lo) / (hi - lo)            0 .. 1

    One straight-line function of the physical value, applied to BOTH
    bodies. Equal physical values get equal positions. Equal physical
    differences get equal position differences: that is what "the structure
    is kept" means, and it is what the rank transform did not do.

    There is no pooling weight any more (B33 needed "one half each").
    There is no normal score: the position itself goes to step 4.

WHAT THIS DOES AND DOES NOT CHANGE IN THE DISTANCE
    Step 4 standardises every variable by Earth's mean and standard
    deviation and whitens within groups. A straight-line rescaling cancels
    there. So lo and hi do NOT enter any distance: the distance is the same
    as on the raw physical values. lo and hi matter for what is SHOWN
    (positions, gaps, verdicts). One absurd extreme cell can therefore
    squeeze the display of a variable, but cannot move a ranking.

GATES, stated before running
    G1  both layers carry the SAME unit string in the manifest (as B33).
    G2  hi > lo, and every position lies in [0, 1], with 0 and 1 attained.
    G3  position * (hi - lo) + lo gives back the physical value to 1e-5 of
        the range, on both bodies (the scale is one straight line).

OUTPUT (cube/phase4)
    minmax_earth_<body>.npy     float32 (dims, complete Earth cells)
    minmax_<body>.npy           float32 (dims, all cells of the body), NaN
                                where the layer has no value
    minmax_scale_summary.json   lo, hi, which world sets each, Earth's mean
                                and sd, how far apart the two worlds are
    A cell that is not in the stored arrays (a click on an ice pixel) is
    placed with lo and hi from the summary; its position may fall outside
    0..1 and is shown as it is.
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
NS = {"earth": 1024, "moon": 256, "mars": 512}

# every variable the pairing COULD rank; G1 decides which can share a scale
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
    lo = np.searchsorted(sorted_vals, x, side="left")
    hi = np.searchsorted(sorted_vals, x, side="right")
    return (lo + hi) / (2.0 * sorted_vals.size)


def main():
    t0 = time.perf_counter()
    man = json.load(io.open(C.MANIFEST, encoding="utf-8"))["layers"]
    epix = np.load(os.path.join(P4, "ref_pixels.npy"))[np.load(os.path.join(P4, "complete_mask.npy"))]
    print("=" * 78)
    print("PHASE 4b -- THE MIN-MAX SCALE (one scale per variable, per pairing)")
    print("=" * 78)
    print(f"Earth: {epix.size:,} complete reference cells")
    summary = dict(
        decided="Sherozbek, 11 Nov 2026; VARIABLES.md B38 (replaces the pooled percentile of B33)",
        transform="position = (x - lo) / (hi - lo); lo and hi are the smallest and largest value on Earth or the body",
        earth_population="reference population, complete cases (phase4a)",
        body_population="every finite cell of the layer",
        note=("lo and hi cancel in step 4 (standardising by Earth's mean and sd): no distance depends on them. "
              "They set what is displayed."),
        earth_cells=int(epix.size), pairings={})
    ok_all = True
    for body, cands in CANDIDATES.items():
        ns = NS[body]
        print(f"\n--- EARTH + {body.upper()} ---")
        print(f"{'variable':20s} {'unit':>10s} {'lo':>10s} {'hi':>10s} {'set by':>8s} "
              f"{'Earth 1..99%':>15s} {'body 1..99%':>15s}  gates")
        used, pe_all, pb_all, rec, refused = [], [], [], {}, {}
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
            lo, hi = float(min(e.min(), b.min())), float(max(e.max(), b.max()))
            pe, pb = (e - lo) / (hi - lo), (b - lo) / (hi - lo)
            g2 = bool(hi > lo and min(pe.min(), pb.min()) == 0.0 and max(pe.max(), pb.max()) == 1.0)
            pe32, pb32 = pe.astype(np.float32), pb.astype(np.float32)
            err = max(np.abs(pe32.astype(np.float64) * (hi - lo) + lo - e).max(),
                      np.abs(pb32.astype(np.float64) * (hi - lo) + lo - b).max()) / (hi - lo)
            g3 = bool(err < 1e-5)
            ok = g2 and g3
            ok_all &= ok
            qe, qb = np.percentile(pe, [1, 50, 99]), np.percentile(pb, [1, 50, 99])
            by = ("Earth" if e.min() <= b.min() else body) + " / " + ("Earth" if e.max() >= b.max() else body)
            print(f"{d:20s} {ue[:10]:>10s} {lo:10.4g} {hi:10.4g} {by.replace('Earth','E').replace(body, body[:2]):>8s} "
                  f"{qe[0]:6.3f}..{qe[2]:6.3f} {qb[0]:6.3f}..{qb[2]:6.3f}  "
                  f"G2 {'ok' if g2 else 'FAIL'} G3 {'ok' if g3 else 'FAIL'} ({err:.1e})")
            full = np.full(b_all.size, np.nan, dtype=np.float32)
            full[fin] = pb32
            used.append(d)
            pe_all.append(pe32)
            pb_all.append(full)
            se = np.sort(e)
            rec[d] = dict(
                units=ue, lo=lo, hi=hi, lo_set_by=by.split(" / ")[0], hi_set_by=by.split(" / ")[1],
                body_cells=int(b.size),
                earth_mean_value=float(e.mean()), earth_sd_value=float(e.std()),
                earth_position_p1_p50_p99=[float(x) for x in qe],
                body_position_p1_p50_p99=[float(x) for x in qb],
                earth_value_p1_p50_p99=[float(x) for x in np.percentile(e, [1, 50, 99])],
                body_value_p1_p50_p99=[float(x) for x in np.percentile(b, [1, 50, 99])],
                tenth_of_scale_in_units=float(0.1 * (hi - lo)),
                # how separate the two bodies are on this variable:
                # 0.5 = fully mixed, 0 or 1 = no overlap at all
                prob_body_above_earth=float(fmid(se, b).mean()),
                gates=dict(G2=g2, G3=g3, G3_max_error_share_of_range=float(err)))
            del e, b_all, b, pe, pb, se
        if not ok_all:
            print("A GATE FAILED -- nothing written")
            return 1
        np.save(os.path.join(P4, f"minmax_earth_{body}.npy"), np.vstack(pe_all))
        np.save(os.path.join(P4, f"minmax_{body}.npy"), np.vstack(pb_all))
        summary["pairings"][body] = dict(
            names=used, refused=refused, body_nside=ns, variables=rec,
            files=dict(earth=f"cube/phase4/minmax_earth_{body}.npy",
                       body=f"cube/phase4/minmax_{body}.npy"))
        print(f"wrote min-max positions for Earth + {body}: {len(used)} variables"
              + (f"; REFUSED {list(refused)}" if refused else ""))
    summary["built_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    io.open(os.path.join(P4, "minmax_scale_summary.json"), "w",
            encoding="utf-8").write(json.dumps(summary, indent=1))
    print(f"\ndone in {time.perf_counter()-t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
