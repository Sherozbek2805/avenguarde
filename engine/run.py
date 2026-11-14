"""
Run one preset target under BOTH ranking systems, with the Atacama control, and check the output.

    python engine/run.py moon Haworth
    python engine/run.py mars "Jezero crater" --construction without_composition

Writes  runs/<body>_<target>__<system>/output.json   (contract 2.4, validated here)
        ... /di_*.png, rank_combined_*.png, *_nside1024.npy, null_draws.npz, run_detail.json
        runs/_controls/<set>.json                      the control, once per variable set
Both systems are always run and both are printed. Never only the better one (TEST_SPEC section 7).
"""
import argparse
import io
import json
import os
import re
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analog_engine as AE

SYSTEMS = ("all_variables", "earth_reachable_only")      # the main result first


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def control_for(P, set_id, parent):
    path = os.path.join(AE.ROOT, "runs", "_controls", f"{set_id}.json")
    if os.path.exists(path):
        d = json.load(io.open(path, encoding="utf-8"))
        if d.get("seed") == AE.SEED and d.get("B") == AE.B_NULL:
            return d["control"], d["detail"]
    t0 = time.perf_counter()
    ctl, det = P.control(set_id, parent)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    io.open(path, "w", encoding="utf-8").write(json.dumps(dict(seed=AE.SEED, B=AE.B_NULL, control=ctl, detail=det,
                                                               seconds=round(time.perf_counter() - t0, 1)), indent=1))
    return ctl, det


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("body", choices=["moon", "mars"])
    ap.add_argument("target")
    ap.add_argument("--construction", default=None)
    ap.add_argument("--no-rasters", action="store_true")
    a = ap.parse_args()
    import jsonschema
    schema = AE.jl(AE.CONTRACT, "output_schema.json")
    P = AE.Pairing(a.body)
    tgt = P.targets[a.target]
    cons = a.construction or tgt["primary_construction"]
    print(f"{a.target} ({a.body}), construction {cons}: {tgt['cells']} cells, |lat| band {tgt['abs_lat_band']}")
    summary = []
    for system in SYSTEMS:
        rk, parent = P.ranking(a.target, cons, system)
        cset = rk["ranking_set"] if system == "all_variables" else P._preset_control_set(parent)
        ctl = control_for(P, cset, parent)
        out_dir = os.path.join("runs", f"{a.body}_{slug(a.target)}" + ("" if cons == tgt["primary_construction"] else "_" + slug(cons)) + f"__{system}")
        doc, det, _ = P.run_preset(a.target, system, construction=cons, out_dir=out_dir, write_rasters=not a.no_rasters, control=ctl)
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(doc)
        nt, run = doc["null_test"], doc["run"]
        print(f"\n=== {system}: {run['dims_used']} variables, set {rk['ranking_set']}   ({det['seconds']} s, output validates)")
        print(f"  control (Atacama): DI {ctl[0]['di_observed']}, p = {ctl[0]['p']:.4g} -> {'PASSED' if ctl[0]['passed'] else 'FAILED'}"
              f"   [null median {ctl[1]['null_median']:.3f}, null minimum {ctl[1]['null_min']:.3f}]")
        print(f"  chance test: di_observed {nt['di_observed']}  null median {nt['null_median']}  p = {nt['p']:.4g}  -> "
              f"{'significant' if nt['p'] < AE.P_SIGNIFICANT else 'not significant'}")
        print(f"  spread: target {det['target_spread']}; random patches p5/p50/p95 {[round(x, 2) for x in det['null_spread_p5_p50_p95']]}; "
              f"north share {det['null_north_share']:.2f}; discards {det['null_discards']}")
        print(f"  best cell on Earth: DI {det['full_map_min']:.3f}; group DI at it {dict((k, None if v is None else round(v, 2)) for k, v in det['best_cells_group_di'].items())}")
        print(f"  places in the best 1%: {run['patches_total']}; listed {len(doc['sites'])}")
        for s in doc["sites"][:8]:
            print(f"   {s['rank']:2d}. {s['lat']:7.2f} {s['lon']:8.2f}  DI {s['di_combined']:.3f}  {s['patch_cells']:4d} cells  "
                  f"{(s['koppen'] or {}).get('symbol', '-'):3s} {((s['lithology'] or {}).get('description', '-'))[:26]:26s} "
                  f"{s['catalogue']['status'] + (': ' + s['catalogue']['name'] if s['catalogue']['name'] else '')}"[:150])
        summary.append(dict(system=system, set=rk["ranking_set"], p=nt["p"], di_observed=nt["di_observed"], null_median=nt["null_median"],
                            control_p=ctl[0]["p"], control_passed=ctl[0]["passed"], patches_total=run["patches_total"], out_dir=out_dir.replace(os.sep, "/")))
    io.open(os.path.join(AE.ROOT, "runs", f"{a.body}_{slug(a.target)}_summary.json"), "w", encoding="utf-8").write(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
