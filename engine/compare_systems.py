"""
The three questions of TEST_SPEC section 7, answered for BOTH ranking systems from finished runs.

    python engine/compare_systems.py moon

  1. Does the answer depend on the target?   share of best-1% cells two targets have in common
  2. Does the control behave?
  3. Which group carries the result?         di_group at the best cell

Writes runs/<body>_system_comparison.json. It names no winner: the team does.
"""
import io
import itertools
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analog_engine as AE


def main():
    body = sys.argv[1]
    rows = AE.jl(AE.ROOT, "runs", f"{body}_summary.json")
    out = {}
    for system in ("earth_reachable_only", "all_variables"):
        R = [r for r in rows if r["system"] == system and r["construction"] in ("all_dimensions", "without_composition")
             and not r["out_dir"].endswith("_all_dimensions__" + system)]
        if body == "moon":
            R = [r for r in rows if r["system"] == system]
        top = {}
        for r in R:
            rk = np.load(os.path.join(AE.ROOT, r["out_dir"], "rank_combined_nside1024.npy"), mmap_mode="r")
            top[r["target"]] = np.flatnonzero(np.asarray(rk) < 0.01)
        pairs = {}
        for a, b in itertools.combinations(top, 2):
            inter = np.intersect1d(top[a], top[b], assume_unique=True).size
            pairs[f"{a} | {b}"] = round(inter / max(1, min(top[a].size, top[b].size)), 3)
        names = list(top)
        union = np.unique(np.concatenate(list(top.values())))
        in_all = top[names[0]]
        for n in names[1:]:
            in_all = np.intersect1d(in_all, top[n], assume_unique=True)
        gd = {r["target"]: AE.jl(AE.ROOT, r["out_dir"], "run_detail.json")["best_cells_group_di"] for r in R}
        key = "Haworth | Mons Mouton Plateau"
        out[system] = dict(
            targets=len(R), variables=sorted({r["variables"] for r in R}),
            q1_shared_best1pct_haworth_vs_mons_mouton_plateau=pairs.get(key),
            q1_shared_best1pct_all_pairs_min_median_max=[float(x) for x in np.round(np.percentile(list(pairs.values()), [0, 50, 100]), 3)],
            q1_cells_in_best1pct_of_every_target=int(in_all.size), q1_cells_in_best1pct_of_any_target=int(union.size),
            q2_control_passed=bool(all(r["control_passed"] for r in R)), q2_control_p=sorted({r["control_p"] for r in R}),
            q3_group_di_at_best_cell=gd,
            significant_targets=[r["target"] for r in R if r["significant"]],
            p_values={r["target"]: r["p"] for r in R},
            target_spread_vs_null_median={r["target"]: [r["target_spread"], r["null_spread_median"]] for r in R},
            best_sites={r["target"]: r["best_site"] for r in R})
        o = out[system]
        print(f"\n=== {system}: {o['targets']} targets, {o['variables']} variables")
        print(f"  1. best-1% cells shared, Haworth vs Mons Mouton Plateau: {o['q1_shared_best1pct_haworth_vs_mons_mouton_plateau']}")
        print(f"     over all pairs of targets (min / median / max): {o['q1_shared_best1pct_all_pairs_min_median_max']}")
        print(f"     cells in the best 1% of EVERY target: {o['q1_cells_in_best1pct_of_every_target']:,}; of ANY target: {o['q1_cells_in_best1pct_of_any_target']:,}")
        print(f"  2. control passed: {o['q2_control_passed']} (p = {o['q2_control_p']})")
        print("  3. group DI at the best cell:")
        for t, g in gd.items():
            print(f"       {t[:24]:24s} " + "  ".join(f"{k} {v:.2f}" if v is not None else f"{k} -" for k, v in g.items()))
        print(f"  significant targets: {o['significant_targets'] or 'none'}")
        print("  p-values: " + ", ".join(f"{t.split()[0]} {p:.2f}" for t, p in o["p_values"].items()))
    io.open(os.path.join(AE.ROOT, "runs", f"{body}_system_comparison.json"), "w", encoding="utf-8").write(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
