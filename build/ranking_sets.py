"""
RANK ONLY ON WHAT EARTH CAN MATCH -- B36, Sherozbek's decision, 11 Nov 2026.

    python build/ranking_sets.py

Run after phase4a, phase4b, phase4c and targets.py.

THE RULE, stated before any search exists
    For one target and one variable, take the MEDIAN of the target's cells in
    physical units. If that median lies outside the WHOLE range of Earth's
    reference population -- below Earth's smallest value or above its
    largest -- then no place on Earth reaches it. The variable cannot say
    which Earth site is the better match; it can only say all of them are
    far. So it is

        REPORTED  as one of Earth's limits, with the gap in physical units
        LEFT OUT  of the distance that ranks Earth's cells

    Everything else ranks as before. The rule reads the data; it has no
    parameter to tune. "Whole range" is the most permissive choice: a
    variable stays in unless literally no Earth cell reaches the target.

WHY (measured, VARIABLES.md B36)
    Every one of the nine Artemis regions sits below Earth's coldest cell in
    temperature level and above Earth's largest day-night swing. Such a
    variable adds a large distance to EVERY Earth cell. With no weights in
    version 1 (B35) it would push every ranking the same way without saying
    anything about which site is better. (How much the list would move was
    not measured: no search exists before the hackathon.)

WHAT THIS SCRIPT DOES -- calibration only, no distance to any target
    1. applies the rule to every preset target (and both constructions of a
       Mars zone) and writes which variables rank
    2. finds the distinct variable sets that result and calibrates each one
       exactly as phase4c does: group-wise whitening on the min-max scale (B38),
       Earth's mean and sd, d_bar, d_bar per group
    3. writes cube/phase4/ranking_sets.json, one whiten/center pair per set,
       and contract/targets_ranking.json for the engine and the website

    `out_of_range()` and `calibrate()` are importable, so the engine applies
    the identical rule and calibration to a custom target on the day.
"""

import io
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C
from phase4c_di import SETS, LAMBDA_FLOOR, SEED, N_DBAR, whiten_matrix, mean_pairwise

P4 = os.path.join(C.ROOT, "cube", "phase4")
HP = os.path.join(C.ROOT, "cube", "healpix")
NS = {"earth": 1024, "moon": 256, "mars": 512}
CONSTRUCTION_SET = {("moon", "all_dimensions"): "earth_moon",
                    ("mars", "all_dimensions"): "earth_mars",
                    ("mars", "without_composition"): "earth_mars_no_composition"}
RULE = ("A variable is left out of the ranking, and reported as one of Earth's "
        "limits, when the median of the target's cells lies outside the whole "
        "range of Earth's reference population in physical units.")

_cache = {}


def earth_range(d):
    if d not in _cache:
        ref = np.load(os.path.join(P4, "ref_pixels.npy"))[np.load(os.path.join(P4, "complete_mask.npy"))]
        v = np.load(os.path.join(HP, f"earth_{d}_nside1024.npy"))[ref]
        _cache[d] = (float(v.min()), float(v.max()))
    return _cache[d]


def out_of_range(body, dims, pixels):
    """the rule. Returns (ranked dims, list of out-of-range records)."""
    man = json.load(io.open(C.MANIFEST, encoding="utf-8"))["layers"]
    ranked, out = [], []
    for d in dims:
        v = np.load(os.path.join(HP, f"{body}_{d}_nside{NS[body]}.npy"), mmap_mode="r")[np.asarray(pixels)]
        v = v[np.isfinite(v)]
        if v.size == 0:
            continue
        lo, hi = earth_range(d)
        m = float(np.median(v))
        if m < lo or m > hi:
            out.append(dict(variable=d, units=str(man[f"{body}_{d}"].get("units")),
                            target_median=round(m, 3), earth_min=round(lo, 3), earth_max=round(hi, 3),
                            side="below Earth's range" if m < lo else "above Earth's range",
                            gap=round(lo - m if m < lo else m - hi, 3),
                            share_of_target_cells_outside=round(float(np.mean((v < lo) | (v > hi))), 3)))
        else:
            ranked.append(d)
    return ranked, out


def set_id(base, dropped):
    return base if not dropped else base + "__minus__" + "__".join(dropped)


def calibrate(base, dims):
    """group-wise whitening and d_bar for a subset of a base set's dimensions."""
    body, groups = SETS[base]
    pooled = json.load(io.open(os.path.join(P4, "minmax_scale_summary.json"), encoding="utf-8"))
    pnames = pooled["pairings"][body]["names"]
    groups = [(g, [d for d in ds if d in dims]) for g, ds in groups]
    groups = [(g, ds) for g, ds in groups if ds]
    used = [d for _, ds in groups for d in ds]
    P = np.load(os.path.join(P4, f"minmax_earth_{body}.npy"), mmap_mode="r")
    X = np.asarray(P[[pnames.index(d) for d in used]]).T.astype(np.float64)
    mu, sd = X.mean(axis=0), X.std(axis=0)
    U = (X - mu) / sd
    D = len(used)
    W = np.zeros((D, D))
    ginfo, a = {}, 0
    for g, ds in groups:
        b = a + len(ds)
        if len(ds) == 1:
            Wg, ev, raised = np.ones((1, 1)), np.array([1.0]), 0
        else:
            Wg, ev, raised, _ = whiten_matrix(np.corrcoef(U[:, a:b], rowvar=False), LAMBDA_FLOOR)
        W[a:b, a:b] = Wg
        ginfo[g] = dict(dimensions=list(ds), index_range=[a, b], eigenvalues_floored=int(raised))
        a = b
    Z = U @ W
    n = Z.shape[0]
    A = Z[np.random.default_rng(SEED).choice(n, size=min(N_DBAR, n), replace=False)]
    alt = [mean_pairwise(Z[np.random.default_rng(SEED + 1 + k).choice(n, size=min(N_DBAR, n), replace=False)]) for k in range(5)]
    for g in ginfo:
        i0, i1 = ginfo[g]["index_range"]
        ginfo[g]["d_bar"] = mean_pairwise(A[:, i0:i1])
    return dict(base_set=base, pooled_with=body, dimensions=used, n_dims=D, n_reference=int(n),
                groups=ginfo, group_order=[g for g, _ in groups], lambda_floor=LAMBDA_FLOOR,
                eigenvalues_floored=int(sum(v["eigenvalues_floored"] for v in ginfo.values())),
                d_bar=mean_pairwise(A), d_bar_seed=SEED, d_bar_subsample=int(A.shape[0]),
                d_bar_5seed_min=float(min(alt)), d_bar_5seed_max=float(max(alt))), W, np.vstack([mu, sd])


def main():
    t0 = time.perf_counter()
    print("=" * 78)
    print("B36 -- RANK ONLY ON WHAT EARTH CAN MATCH: sets and calibration")
    print("=" * 78)
    cfg = json.load(io.open(os.path.join(P4, "phase4c_summary.json"), encoding="utf-8"))
    targets, need = {}, {}
    for body in ("moon", "mars"):
        T = json.load(io.open(os.path.join(C.ROOT, "contract", f"targets_{body}.json"), encoding="utf-8"))["targets"]
        targets[body] = []
        print(f"\n{body.upper()}")
        for t in T:
            rec = dict(name=t["name"], constructions={})
            for cons in ([t["primary_construction"]] + ([t["second_construction"]] if t.get("second_construction") else [])):
                base = CONSTRUCTION_SET[(body, cons)]
                dims = cfg[base]["dimensions"]
                pix = np.asarray(t["healpix_pixels"])
                if cons == "all_dimensions" and body == "mars":
                    ok = np.ones(pix.size, dtype=bool)
                    for d in dims:
                        ok &= np.isfinite(np.load(os.path.join(HP, f"mars_{d}_nside512.npy"), mmap_mode="r")[pix])
                    pix = pix[ok]
                ranked, out = out_of_range(body, dims, pix)
                sid = set_id(base, [o["variable"] for o in out])
                need[sid] = (base, ranked)
                rec["constructions"][cons] = dict(
                    is_primary=(cons == t["primary_construction"]), cells=int(pix.size), base_set=base,
                    ranking_set=sid, ranked_dimensions=ranked, n_ranked=len(ranked), out_of_range=out)
                print(f"  {t['name'][:28]:28s} {cons:20s} ranks {len(ranked):2d} of {len(dims):2d}; "
                      f"Earth's limit: " + (", ".join(f"{o['variable']} {o['target_median']:g} ({o['side'].split()[0]} {o['earth_min'] if o['side'].startswith('below') else o['earth_max']:g})" for o in out) or "none"))
            targets[body].append(rec)

    # THE ONE CONTROL (B38, Sherozbek, 11 Nov 2026: "controls are stripped
    # except for Atacama"). The Atacama patch is Earth ground: every one of
    # its variables is inside Earth's range, so under the overlap rule it
    # would rank on all dimensions and pass only because the Moon is cold.
    # It therefore runs on the ranking sets the preset targets use.
    preset_sets = sorted({c["ranking_set"] for b in targets for t in targets[b] for c in t["constructions"].values()})
    controls = [dict(control="positive_atacama", body="earth", ranking_sets=preset_sets,
                     note="The only control. Under earth_reachable_only it runs once on each ranking set a preset target "
                          "uses; under all_variables on the parent set of the pairing.")]

    sets = {}
    print(f"\n{len(need)} distinct ranking sets")
    for sid, (base, dims) in sorted(need.items()):
        info, W, cen = calibrate(base, dims)
        np.save(os.path.join(P4, f"whiten_{sid}.npy"), W)
        np.save(os.path.join(P4, f"center_{sid}.npy"), cen)
        info["whiten_file"] = f"cube/phase4/whiten_{sid}.npy"
        info["center_file"] = f"cube/phase4/center_{sid}.npy"
        info["input_file"] = f"cube/phase4/minmax_earth_{info['pooled_with']}.npy"
        info["target_file"] = f"cube/phase4/minmax_{info['pooled_with']}.npy"
        sets[sid] = info
        print(f"  {sid}\n     {info['n_dims']} dims, groups "
              + ", ".join(f"{g} {len(v['dimensions'])}" for g, v in info["groups"].items())
              + f"; floored {info['eigenvalues_floored']}; d_bar {info['d_bar']:.4f} "
              f"(five seeds {info['d_bar_5seed_min']:.3f}-{info['d_bar_5seed_max']:.3f})")
    systems = dict(
        decided="Sherozbek, 11 Nov 2026 (VARIABLES.md B37): BOTH systems are built and one is chosen on the hackathon day after testing both.",
        all_variables="Every variable of the target's parent set ranks, also those Earth cannot reach. Calibration: the parent "
                      "set (base_set) in cube/phase4/phase4c_summary.json, whiten_<base_set>.npy, center_<base_set>.npy.",
        earth_reachable_only="The rule below: a variable Earth cannot reach is reported and left out. Calibration: ranking_set "
                             "in this file.",
        both="out_of_range is reported in BOTH systems. For every preset target both systems are run and both results printed.")
    doc = dict(decided="Sherozbek, 11 Nov 2026; VARIABLES.md B36, B37, B38", systems=systems, rule=RULE,
               earth_range_population="reference population, complete cases; whole range (minimum to maximum)",
               sets=sets, targets=targets, controls=controls,
               built_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    for path in (os.path.join(P4, "ranking_sets.json"), os.path.join(C.ROOT, "contract", "targets_ranking.json")):
        tmp = path + ".part"
        io.open(tmp, "w", encoding="utf-8").write(json.dumps(doc, indent=1, ensure_ascii=False))
        os.replace(tmp, path)
        print("wrote", path)
    print(f"done in {time.perf_counter()-t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
