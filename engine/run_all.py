"""
Run EVERY preset target of a body under BOTH ranking systems (and, on Mars, both constructions).

    python engine/run_all.py moon
    python engine/run_all.py mars

The pairing is loaded once. A run that already has an output.json from the same code version and
seed is skipped, so the batch can be stopped and started again. Writes runs/<body>_summary.json:
one line per run, both systems side by side. Nothing is left out because it is not significant.
"""
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analog_engine as AE
from run import SYSTEMS, slug, control_for


def main():
    body = sys.argv[1]
    import jsonschema
    schema = AE.jl(AE.CONTRACT, "output_schema.json")
    P = AE.Pairing(body)
    cv = AE.code_version()
    rows, t0 = [], time.perf_counter()
    for name, tgt in P.targets.items():
        cons_list = [tgt["primary_construction"]] + ([tgt["second_construction"]] if tgt.get("second_construction") else [])
        for cons in cons_list:
            for system in SYSTEMS:
                out_dir = os.path.join("runs", f"{body}_{slug(name)}" + ("" if cons == tgt["primary_construction"] else "_" + slug(cons)) + f"__{system}")
                path = os.path.join(AE.ROOT, out_dir, "output.json")
                t1 = time.perf_counter()
                if os.path.exists(path) and AE.jl(path)["run"]["code_version"] == cv and AE.jl(path)["null_test"]["seed"] == AE.SEED:
                    doc, det = AE.jl(path), AE.jl(AE.ROOT, out_dir, "run_detail.json")
                    note = "kept"
                else:
                    rk, parent = P.ranking(name, cons, system)
                    cset = rk["ranking_set"] if system == "all_variables" else P._preset_control_set(parent)
                    doc, det, _ = P.run_preset(name, system, construction=cons, out_dir=out_dir, control=control_for(P, cset, parent))
                    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(doc)
                    note = f"{time.perf_counter() - t1:.0f} s"
                nt, run, s1 = doc["null_test"], doc["run"], (doc["sites"][0] if doc["sites"] else None)
                rows.append(dict(target=name, construction=cons, system=system, variables=run["dims_used"], cells=run["target"]["cells_distinct"],
                                 target_spread=run["target"]["spread"], null_spread_median=round(det["null_spread_p5_p50_p95"][1], 3),
                                 di_observed=nt["di_observed"], null_median=nt["null_median"], p=nt["p"],
                                 significant=bool(nt["p"] < AE.P_SIGNIFICANT), control_p=nt["positive_control"]["p"],
                                 control_passed=nt["positive_control"]["passed"], best_di=round(det["full_map_min"], 3),
                                 patches_total=run["patches_total"],
                                 best_site=None if s1 is None else dict(lat=s1["lat"], lon=s1["lon"], koppen=(s1["koppen"] or {}).get("symbol"),
                                                                        catalogue=s1["catalogue"]["name"] or s1["catalogue"]["status"]),
                                 out_dir=out_dir.replace(os.sep, "/")))
                r = rows[-1]
                print(f"{name[:26]:26s} {cons[:11]:11s} {system[:15]:15s} cells {r['cells']:4d} spread {r['target_spread']:5.2f} "
                      f"DIobs {r['di_observed']:6.3f} null {r['null_median']:6.3f} p {r['p']:.3f} {'SIG' if r['significant'] else '   '} "
                      f"control {'ok  ' if r['control_passed'] else 'FAIL'} best {r['best_site']['lat']:7.2f} {r['best_site']['lon']:8.2f} [{note}]", flush=True)
                io.open(os.path.join(AE.ROOT, "runs", f"{body}_summary.json"), "w", encoding="utf-8").write(json.dumps(rows, indent=1, ensure_ascii=False))
    print(f"done: {len(rows)} runs in {(time.perf_counter() - t0) / 60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
