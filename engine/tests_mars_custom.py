"""
A user-drawn target on MARS, end to end: a circle and a rectangle, both ranking systems, and a click.

    python engine/tests_mars_custom.py
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analog_engine as AE
from run import control_for

RES = []


def check(tag, ok, detail=""):
    RES.append((tag, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {tag}" + (f"  -- {detail}" if detail else ""), flush=True)


def main():
    import jsonschema
    out_schema = AE.jl(AE.CONTRACT, "output_schema.json")
    pt_schema = AE.jl(AE.CONTRACT, "point_schema.json")
    t0 = time.perf_counter()
    P = AE.Pairing("mars")
    cases = [("circle in Valles Marineris, 30 km", "circle", dict(lat=-13.9, lon=-59.2, radius_km=30.0)),
             ("rectangle north-west of Jezero, 1 x 1 degree", "rectangle", dict(lat_min=18.5, lat_max=19.5, lon_min=75.0, lon_max=76.0))]
    state = None
    for label, method, params in cases:
        n = P.select_pixels(method, params).size
        for system in ("all_variables", "earth_reachable_only"):
            t1 = time.perf_counter()
            try:
                # the same choice run_custom makes, to fetch the cached control of that variable set
                import numpy as np
                px = P.select_pixels(method, params)
                comp = np.isfinite(P.Bd[[P.names.index(d) for d in P.parents["earth_mars"]["dimensions"]]][:, px]).all(0)
                parent = "earth_mars" if comp.mean() >= 0.9 else "earth_mars_no_composition"
                cset = parent if system == "all_variables" else P._preset_control_set(parent)
                doc, det, st = P.run_custom(method, params, system, name=label, control=control_for(P, cset, parent),
                                            out_dir=os.path.join("runs", "_tests", f"mars_{method}__{system}"))
                jsonschema.Draft202012Validator(out_schema, format_checker=jsonschema.FormatChecker()).validate(doc)
                run, nt = doc["run"], doc["null_test"]
                s1 = doc["sites"][0]
                check(f"Mars {method}, {system}", True,
                      f"{n} cells selected, {run['target']['cells']} used ({det['construction']}), {run['dims_used']} variables, set {run['ranking']['ranking_set']}; "
                      f"beyond Earth {[o['variable'] for o in run['ranking']['out_of_range']]}; p = {nt['p']:.3f}; control {'passed' if nt['positive_control']['passed'] else 'FAILED'}; "
                      f"best site {s1['lat']}, {s1['lon']}; modelled rows {sum(1 for v in run['variables'] if v['modelled'])}; {time.perf_counter() - t1:.0f} s")
                state = st
            except Exception as e:
                check(f"Mars {method}, {system}", False, f"{type(e).__name__}: {e}")
    if state is not None:
        pp = P.point(state, -24.05, -69.92)
        jsonschema.Draft202012Validator(pt_schema).validate(pp)
        check("a click on Earth against the Mars rectangle validates", pp["in_reference_population"], f"DI {pp['di_combined']}, groups {pp['di_group']}")
    nf = [t for t, ok, _ in RES if not ok]
    print(f"\n{len(RES) - len(nf)} of {len(RES)} passed in {time.perf_counter() - t0:.0f} s" + (f"; FAILED: {nf}" if nf else ""))
    json.dump([dict(test=t, passed=ok, detail=d) for t, ok, d in RES], open(os.path.join(AE.ROOT, "engine", "test_results_mars_custom.json"), "w"), indent=1)
    return 1 if nf else 0


if __name__ == "__main__":
    sys.exit(main())
