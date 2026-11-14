"""
Tests for custom targets and the click payload (spec step 5 tests, TEST_SPEC 2, 10, 12, 39; contract tests).

    python engine/tests_custom.py
"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analog_engine as AE
from run import control_for

RES = []


def check(tag, ok, detail=""):
    RES.append((tag, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {tag}" + (f"  -- {detail}" if detail else ""), flush=True)


def main():
    import jsonschema
    t0 = time.perf_counter()
    out_schema = AE.jl(AE.CONTRACT, "output_schema.json")
    pt_schema = AE.jl(AE.CONTRACT, "point_schema.json")
    V = lambda sch, d: jsonschema.Draft202012Validator(sch, format_checker=jsonschema.FormatChecker()).validate(d)
    P = AE.Pairing("moon")

    print("=== THE RULE, applied by the engine, against the calibration's record")
    bad = []
    for t in P.targets_ranking["targets"]["moon"]:
        rec = t["constructions"]["all_dimensions"]
        ranked, out = P.out_of_range(P.parents["earth_moon"]["dimensions"], np.asarray(P.targets[t["name"]]["healpix_pixels"]))
        same = sorted(ranked) == sorted(rec["ranked_dimensions"]) and all(
            abs(a["target_median"] - b["target_median"]) < 0.01 and abs(a["gap"] - b["gap"]) < 0.01 and a["side"] == b["side"]
            for a, b in zip(sorted(out, key=lambda o: o["variable"]), sorted(rec["out_of_range"], key=lambda o: o["variable"])))
        if not same:
            bad.append(t["name"])
    check("the engine's out-of-range rule gives the recorded list and gaps for all nine Artemis regions", not bad, str(bad))

    print("=== SELECTING CELLS (spec step 5)")
    n_pole = P.select_pixels("circle", dict(lat=-89.5, lon=0, radius_km=10)).size
    n_eq = P.select_pixels("circle", dict(lat=0, lon=0, radius_km=10)).size
    check("[12] a 10 km disc near the pole and at the equator have the same cell count (within two)", abs(n_pole - n_eq) <= 2, f"{n_pole} and {n_eq}")
    c = P.select_pixels("circle", dict(lat=10, lon=179.9, radius_km=40))
    lon = P.geo()["lon_deg"][c]
    check("a disc centred at longitude 179.9 includes cells on both sides of the 180 line", lon.min() < -179 and lon.max() > 179, f"{c.size} cells, lon {lon.min():.2f} .. {lon.max():.2f}")
    r = P.select_pixels("rectangle", dict(lat_min=5, lat_max=7, lon_min=178, lon_max=-178))
    lr = P.geo()["lon_deg"][r]
    check("a rectangle crossing the 180 line selects the intended cells, not their complement", r.size > 0 and np.all((lr >= 178) | (lr <= -178)), f"{r.size} cells")
    n1 = P.select_pixels("circle", dict(lat=20, lon=30, radius_km=30)).size
    n2 = P.select_pixels("circle", dict(lat=20, lon=30, radius_km=60)).size
    check("doubling the radius gives about four times the cells", 3.3 < n2 / n1 < 4.7, f"{n1} -> {n2}")
    pl = P.select_pixels("pixel_list", dict(nside=256, pixels=c.tolist()))
    check("the same area given as a pixel list selects the same cells", np.array_equal(pl, np.sort(c)))

    print("=== A CUSTOM TARGET, END TO END (Tycho, 43 km disc), both systems")
    tycho = dict(lat=-43.31, lon=-11.36, radius_km=43.0)
    state = {}
    for system in ("earth_reachable_only", "all_variables"):
        t1 = time.perf_counter()
        ranked, out = P.out_of_range(P.parents["earth_moon"]["dimensions"], P.select_pixels("circle", tycho))
        cset = "earth_moon" if system == "all_variables" else P._preset_control_set("earth_moon")
        doc, det, st = P.run_custom("circle", tycho, system, name="Tycho crater (custom circle)", control=control_for(P, cset, "earth_moon"),
                                    out_dir=os.path.join("runs", "_tests", "tycho__" + system))
        V(out_schema, doc)
        state[system] = st
        run, nt = doc["run"], doc["null_test"]
        check(f"custom circle runs and validates ({system})", True,
              f"{run['target']['cells']} cells, {run['dims_used']} variables, set {run['ranking']['ranking_set']}, "
              f"Earth's limits {[o['variable'] for o in run['ranking']['out_of_range']]}, p = {nt['p']:.3f}, "
              f"best site {doc['sites'][0]['lat']}, {doc['sites'][0]['lon']}; {time.perf_counter() - t1:.0f} s")
    one = P.select_pixels("circle", tycho)[:1]
    doc1, _, _ = P.run_custom("pixel_list", dict(nside=256, pixels=one.tolist()), "all_variables", name="one cell",
                              control=control_for(P, "earth_moon", "earth_moon"), out_dir=os.path.join("runs", "_tests", "one_cell"))
    V(out_schema, doc1)
    check("[10] a one-cell target runs end to end", doc1["run"]["d_bar_target"] is None and doc1["run"]["target"]["spread"] == 0.0,
          f"p = {doc1['null_test']['p']:.3f}, {len(doc1['sites'])} sites")
    try:
        P.run_custom("circle", dict(lat=0, lon=0, radius_km=0.5), "all_variables")
        check("a shape too small to hold a cell centre is refused with a clear message", False)
    except ValueError as e:
        check("a shape too small to hold a cell centre is refused with a clear message", True, str(e))

    print("=== CLICK ANYWHERE (point_schema.json)")
    st = state["all_variables"]
    for label, la, lo, want_ref, want_reason in (("Atacama", -24.05, -69.92, True, None), ("mid-Atlantic", 0.0, -30.0, False, "ocean"),
                                                  ("Greenland ice sheet", 72.0, -40.0, False, "ice")):
        pp = P.point(st, la, lo)
        V(pt_schema, pp)
        check(f"a click on {label} validates", pp["in_reference_population"] == want_ref and pp["reason_excluded"] == want_reason,
              f"in population {pp['in_reference_population']}, reason {pp['reason_excluded']}, DI {pp['di_combined']}, koppen {(pp['koppen'] or {}).get('symbol')}")
    from astropy import units as u
    pp = P.point(st, -24.05, -69.92)
    back = int(P._describers()["hp"].lonlat_to_healpix(pp["lon"] * u.deg, pp["lat"] * u.deg))
    check("[39] the click's printed lat/lon gives back its cell", back == pp["healpix_pixel"])

    nf = [t for t, ok, _ in RES if not ok]
    print(f"\n{len(RES) - len(nf)} of {len(RES)} passed in {time.perf_counter() - t0:.0f} s" + (f"; FAILED: {nf}" if nf else ""))
    json.dump([dict(test=t, passed=ok, detail=d) for t, ok, d in RES], open(os.path.join(AE.ROOT, "engine", "test_results_custom.json"), "w"), indent=1)
    return 1 if nf else 0


if __name__ == "__main__":
    sys.exit(main())
