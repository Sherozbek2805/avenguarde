"""
The tests of docs/TEST_SPEC_2026-11-10.md that can run before any result is published.

    python engine/tests.py

Each line prints PASS or FAIL with the measured number. A FAIL is reported, not hidden.
Numbers in brackets are the test numbers of the specification.
"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analog_engine as AE

RES = []


def check(tag, ok, detail=""):
    RES.append((tag, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {tag}" + (f"  -- {detail}" if detail else ""), flush=True)


def w64(P, c, pos):
    return ((np.asarray(pos, dtype=np.float64) - c["mean"]) / c["sd"]) @ c["W"]


def pair64(V):
    d = np.sqrt(np.maximum(((V[:, None, :] - V[None, :, :]) ** 2).sum(-1), 0.0))
    return float(d[np.triu_indices(V.shape[0], 1)].mean())


def main():
    t0 = time.perf_counter()
    P = AE.Pairing("moon")
    par = P.parents["earth_moon"]
    RSID = "earth_moon__minus__temp_level__temp_range_diurnal"
    rs = P.rsets["sets"][RSID]

    print("=== LOAD TESTS (section 1)")
    check("variables 12, complete Earth cells 3,245,417", len(par["dimensions"]) == 12 and P.n == 3245417, f"{len(par['dimensions'])}, {P.n:,}")
    check("layer sizes: Moon 786,432 cells", P.Bd.shape[1] == 786432)
    check("Moon cells complete in all 12 = 786,176", int(np.isfinite(P.Bd).all(0).sum()) == 786176, str(int(np.isfinite(P.Bd).all(0).sum())))
    c = P.cal("earth_moon")
    rng = np.random.default_rng(20261108)
    rng.choice(P.n, 200000, replace=False)                      # phase4c draws its correlation sample first
    s = rng.choice(P.n, size=5000, replace=False)
    d = pair64(w64(P, c, P.E[c["rows"]][:, s].T))
    check("parent d_bar reproduced from the loaded files (1e-6)", abs(d - c["d_bar"]) / c["d_bar"] < 1e-6, f"{d:.6f} vs {c['d_bar']:.6f}")
    c2 = P.cal(RSID)
    s2 = np.random.default_rng(20261108).choice(P.n, size=5000, replace=False)
    d2 = pair64(w64(P, c2, P.E[c2["rows"]][:, s2].T))
    check("ranking-set d_bar reproduced (1e-6)", abs(d2 - c2["d_bar"]) / c2["d_bar"] < 1e-6, f"{d2:.6f} vs {c2['d_bar']:.6f}")
    for g, v in c["groups"].items():
        dg = pair64(w64(P, c, P.E[c["rows"]][:, s].T)[:, v["a"]:v["b"]])
        check(f"d_bar of group {g} reproduced", abs(dg - v["d_bar"]) / v["d_bar"] < 1e-6, f"{dg:.6f}")
    W = c["W"].copy()
    for v in c["groups"].values():
        W[v["a"]:v["b"], v["a"]:v["b"]] = 0.0
    check("whitening matrix is zero outside the group blocks", np.abs(W).max() == 0.0)
    check("floored eigenvalues: parent 4, ranking set 4", c["floored"] == 4 and c2["floored"] == 4)
    VE64 = np.empty((P.n, 12))
    for i in range(0, P.n, 400000):
        VE64[i:i + 400000] = w64(P, c, P.E[c["rows"], i:i + 400000].T)
    worst = max(float(np.linalg.eigvalsh(np.cov(VE64[:, v["a"]:v["b"]], rowvar=False)).max()) for v in c["groups"].values())
    check("within each group the whitened Earth cloud has eigenvalues <= 1", worst <= 1.0 + 1e-5, f"largest {worst:.6f}")
    del VE64

    print("=== THE SCALE [1, 1a, 1b]")
    lay = os.path.join(AE.HP, "earth_slope_nside1024.npy")
    if os.path.exists(lay):
        v = P.var["slope"]
        pos = (np.load(lay, mmap_mode="r")[P.epix].astype(np.float64) - v["lo"]) / (v["hi"] - v["lo"])
        e = float(np.abs(pos - P.E[P.names.index("slope")]).max())
        check("[1] stored positions equal recomputed ones (slope)", e < 1e-6, f"max error {e:.1e}")
        mp = (np.load(os.path.join(AE.HP, "moon_slope_nside256.npy")).astype(np.float64) - v["lo"]) / (v["hi"] - v["lo"])
        e2 = float(np.nanmax(np.abs(mp - P.Bd[P.names.index("slope")])))
        check("[1a] one formula for both bodies (Moon slope through the same lo, hi)", e2 < 1e-6, f"max error {e2:.1e}")
    else:
        check("[1] skipped: cube/healpix layers not on this machine", True, "kit-only install")
    tgt = np.asarray(P.targets["Haworth"]["healpix_pixels"])
    VT, _ = P.body_vectors(c2, tgt)
    sub = np.random.default_rng(1).choice(P.n, 3000, replace=False)
    di_pos = AE.mean_dist(P.whiten(c2, P.E[c2["rows"]][:, sub].T), VT) / c2["d_bar"]
    lo = np.array([P.var[x]["lo"] for x in c2["dims"]]); rg = np.array([P.var[x]["hi"] - P.var[x]["lo"] for x in c2["dims"]])
    raw_e = lo + P.E[c2["rows"]][:, sub].T.astype(np.float64) * rg
    raw_t = lo + P.Bd[c2["rows"]][:, tgt].T.astype(np.float64) * rg
    m_raw, s_raw = lo + c2["mean"] * rg, c2["sd"] * rg
    Ve = ((raw_e - m_raw) / s_raw) @ c2["W"]; Vt = ((raw_t - m_raw) / s_raw) @ c2["W"]
    di_raw = np.sqrt(((Ve[:, None, :] - Vt[None, :, :]) ** 2).sum(-1)).mean(1) / c2["d_bar"]
    e = float(np.abs(di_raw - di_pos).max())
    check("[1b] lo and hi enter no distance: DI from raw values = DI from positions", e < 1e-4, f"max difference {e:.1e}")

    print("=== DISTANCE AND DI [3-11]")
    maps = P.di_maps(RSID, VT)
    di = maps["combined"]
    VE = P.earth_vectors(RSID)
    hand = [float(np.mean([np.linalg.norm(VE[j].astype(np.float64) - t.astype(np.float64)) for t in VT])) / c2["d_bar"] for j in (0, 123456, P.n - 1)]
    e = max(abs(h - float(di[j])) for h, j in zip(hand, (0, 123456, P.n - 1)))
    check("[3] DI of three cells equals a plain loop over all target cells", e < 1e-4, f"max difference {e:.1e}")
    j = 777777
    one = AE.mean_dist(VE[j:j + 1], VE[j:j + 1])[0]
    check("[4] a one-cell Earth target scores 0 at that cell", one == 0.0, f"{one}")
    check("[4] a 15-cell target never scores 0", float(di.min()) > 0, f"smallest DI on Earth {di.min():.3f}; target's own spread {AE.mean_pairwise(VT)/c2['d_bar']:.2f}")
    VTs, _ = P.body_vectors(c2, np.concatenate([tgt[::-1], tgt[:5]]))
    check("[5] shuffled and duplicated target cells change nothing", np.array_equal(VTs, VT))
    check("[6] DI >= 0 and no NaN", bool(np.isfinite(di).all() and di.min() >= 0))
    check("[7] the map computed twice is bit-identical", np.array_equal(di, P.di_maps(RSID, VT)["combined"]))
    a, b = VE[10].astype(np.float64), VE[2000000].astype(np.float64)
    tot = ((a - b) ** 2).sum(); parts = sum(((a[v["a"]:v["b"]] - b[v["a"]:v["b"]]) ** 2).sum() for v in c2["groups"].values())
    check("[8] combined squared distance = sum of the group squared distances", abs(tot - parts) < 1e-9, f"{abs(tot-parts):.1e}")
    check("[9] a group with no ranked variable has no map", "thermal" not in maps and set(maps) == {"combined", "terrain", "composition"})

    print("=== THE TWO RANKING SYSTEMS [13-17]")
    VT1, _ = P.body_vectors(c, tgt)
    maps1 = P.di_maps("earth_moon", VT1)
    check("[14] all_variables ranks 12, with a thermal map", len(c["dims"]) == 12 and "thermal" in maps1)
    r1, _ = P.ranking("Haworth", "all_dimensions", "all_variables"); r2, _ = P.ranking("Haworth", "all_dimensions", "earth_reachable_only")
    check("[15] earth_reachable_only ranks terrain 8 + SiO2 + FeO", sorted(r2["ranked_variables"]) == sorted(c2["dims"]) and len(c2["dims"]) == 10)
    check("[16] out_of_range is the same list in both systems", r1["out_of_range"] == r2["out_of_range"], str([o["variable"] for o in r1["out_of_range"]]))
    ta, tb = c["groups"]["terrain"], c2["groups"]["terrain"]
    raw1 = maps1["terrain"] * ta["d_bar"]; raw2 = maps["terrain"] * tb["d_bar"]
    e = float(np.abs(raw1 - raw2).max())
    check("[17] the terrain distance is the same in both systems", e < 1e-3, f"max difference {e:.1e}")
    check("[17] ... and so is di_terrain", abs(ta["d_bar"] / tb["d_bar"] - 1) < 1e-6,
          f"NO: the two calibrations estimated terrain d_bar on different 5,000-cell subsamples: {ta['d_bar']:.4f} vs {tb['d_bar']:.4f} ({100*(ta['d_bar']/tb['d_bar']-1):+.2f}%)")

    print("=== THE CHANCE TEST [19-25]")
    band = P.targets["Haworth"]["abs_lat_band"]
    n1 = P.null(RSID, "earth_moon", 15, band, P.sample, B=120, seed=5, keep_pixels=True)
    n2 = P.null(RSID, "earth_moon", 15, band, P.sample, B=120, seed=5)
    n3 = P.null(RSID, "earth_moon", 15, band, P.sample, B=120, seed=6)
    check("[19] every random patch has exactly N distinct cells", all(len(set(q.tolist())) == 15 for q in n1["pixels"]))
    G = P.geo()
    U = G["U"]
    rad = max(float(np.degrees(np.arccos(np.clip(U[q] @ U[q].mean(0) / np.linalg.norm(U[q].mean(0)), -1, 1))).max()) for q in n1["pixels"])
    check("[19] patches are compact blobs (largest radius, degrees of arc)", rad < 3 * np.degrees(n1["patch_radius_km"] / AE.RADIUS_KM["moon"]),
          f"{rad:.2f} deg; nominal radius {np.degrees(n1['patch_radius_km']/AE.RADIUS_KM['moon']):.2f} deg")
    check("[20] same seed, identical null; different seed, different null", np.array_equal(n1["minima"], n2["minima"]) and not np.array_equal(n1["minima"], n3["minima"]))
    share = float(np.mean(n1["hemispheres"] > 0))
    check("[21] patches come from BOTH hemispheres", 0.25 < share < 0.75, f"north share {share:.2f}")
    cl = np.array([G["abs_lat"][q].mean() for q in n1["pixels"]])
    check("[21] ... inside the target's |latitude| band", cl.min() > band[0] - 1.0 and cl.max() < band[1] + 1.0, f"patch mean |lat| {cl.min():.2f} to {cl.max():.2f}; band {band}")
    pv = [AE.Pairing.p_value(x, n1["minima"]) for x in (0.0, float(np.median(n1["minima"])), 1e9)]
    check("[22] p is never 0 and never above 1", pv[0] > 0 and pv[2] <= 1.0, f"{pv[0]:.4f}, {pv[1]:.3f}, {pv[2]:.3f}")
    check("[23] di_observed on the Earth sample >= the minimum of the full map", float(di[P.sample].min()) >= float(di.min()), f"{di[P.sample].min():.3f} >= {di.min():.3f}")
    check("[25] each random patch's own spread is recorded", n1["spreads"].size == 120 and np.isfinite(n1["spreads"]).all(), f"median {np.median(n1['spreads']):.2f}; Haworth {AE.mean_pairwise(VT)/c2['d_bar']:.2f}")

    print("=== RANKS AND BANDS [26-29]")
    rank = AE.rank_of(di)
    check("[26] the best cell has rank 0", float(rank[int(np.argmin(di))]) == 0.0)
    n1pct = int((rank < 0.01).sum())
    check("[27] the best 1% holds 1% of the cells", abs(n1pct - 32454) <= 50, f"{n1pct:,} cells")
    r = np.array([0.001, 0.01, 0.05, 0.2]); v8 = np.round(255 * np.sqrt(r)); back = (v8 / 255) ** 2
    check("[28] rank survives the 8-bit image", abs(back[1] - 0.01) < 0.001 and abs(back[2] - 0.05) < 0.005, f"0.01 -> {back[1]:.4f}; 0.05 -> {back[2]:.4f}")

    print("=== SITES: PATCHES [30-34]")
    pt = P.patches(di, rank, 0.01); pt5 = P.patches(di, rank, 0.05)
    allc = np.concatenate([q["cells"] for q in pt])
    check("[30] every cell of the best 1% is in exactly one patch", allc.size == n1pct and np.unique(allc).size == n1pct, f"{len(pt)} patches")
    pt_again = P.patches(di, rank, 0.01)
    check("[31] same map, same list", [q["best"] for q in pt] == [q["best"] for q in pt_again])
    lab5 = np.full(P.n, -1); [lab5.__setitem__(q["cells"], k) for k, q in enumerate(pt5)]
    check("[32] every 1% patch lies inside one 5% patch", all(np.unique(lab5[q["cells"]]).size == 1 and lab5[q["cells"]][0] >= 0 for q in pt), f"{len(pt5)} patches at 5%")
    check("[34] the first entry is the best cell on Earth", pt[0]["best"] == int(np.argmin(di)))

    print("=== DESCRIBING A SITE [35-39]")
    check("[35] verdict boundaries: 0.10 and 0.25 are partial", [AE.verdict_of(x) for x in (0.0999, 0.10, 0.25, 0.2501, -0.3)] == ["agrees", "partial", "partial", "differs", "differs"])
    order = [x for x in AE.GROUP if x in par["dimensions"]]
    t_pos = {x: float(np.nanmedian(P.Bd[P.names.index(x), tgt])) for x in order}
    beyond = {o["variable"] for o in r2["out_of_range"]}
    site = P.describe(pt[0]["best"], maps, order, t_pos, set(c2["dims"]), beyond, AE.mean_pairwise(VT), c2["d_bar"])
    ok36 = all(abs(v["physical_gap"] - v["position_gap"] * (P.var[v["name"]]["hi"] - P.var[v["name"]]["lo"])) <= 6e-5 * (P.var[v["name"]]["hi"] - P.var[v["name"]]["lo"]) for v in site["variables"])
    check("[36] physical gap = position gap x the range of the variable", ok36)
    check("[16] every variable has a row; unranked ones are counted nowhere", len(site["variables"]) == 12 and not (beyond & set(site["agrees"] + site["partial"] + site["differs"] + site["best3"] + site["worst3"])))
    keys = {q["key"] for k in ("succeeds", "fails", "beyond_earth") for q in site["use"][k]}
    check("[38] the use block: beyond-Earth rows are temperature and day-night", {q["key"] for q in site["use"]["beyond_earth"]} == {"temperature", "day_night"} and keys <= {q["key"] for q in P.use_table["rows"]})
    from astropy import units as u
    back = int(P._describers()["hp"].lonlat_to_healpix(site["lon"] * u.deg, site["lat"] * u.deg))
    check("[39] the printed lat/lon gives back the scored cell", back == site["healpix_pixel"], f"{site['lat']}, {site['lon']}")

    nf = [t for t, ok, _ in RES if not ok]
    print(f"\n{len(RES) - len(nf)} of {len(RES)} passed in {time.perf_counter() - t0:.0f} s" + (f"; FAILED: {nf}" if nf else ""))
    json.dump([dict(test=t, passed=ok, detail=d) for t, ok, d in RES], open(os.path.join(AE.ROOT, "engine", "test_results.json"), "w"), indent=1)
    return 1 if nf else 0


if __name__ == "__main__":
    sys.exit(main())
