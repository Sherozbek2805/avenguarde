"""
PHASE 5 -- the cross-body null.

    python build/phase5_null.py

THE QUESTION IT ANSWERS
    A target's DI of 0.1408 means nothing on its own. The null asks: if I
    drop a window of the SAME SIZE at a random place on the Moon that is
    otherwise comparable, how often is it at least this Earth-like? That
    fraction is the p-value.

MATCHING IN |LATITUDE|, AND WHY
    Null windows are drawn from the same ABSOLUTE-latitude band as the
    target, from BOTH hemispheres. Two reasons, and the first is a bug this
    project already made once:

      1. A disc of fixed radius covers a number of HEALPix pixels that
         depends on |lat|, not on signed lat. Banding on SIGNED latitude
         makes the matching set two disjoint arcs and the null is then drawn
         from a different population than the target. That produced a 95%
         rejection rate before it was caught.
      2. Lunar polar terrain is systematically unlike equatorial terrain. A
         null drawn from the whole Moon would ask "is this more Earth-like
         than a random lunar place", which any polar window would pass
         trivially. Banding asks the sharper question: "is this more
         Earth-like than a random place AT THE SAME LATITUDE".

PER DIMENSION SET, ALWAYS
    d_bar, the DI threshold and this null all belong to one dimension set.
    A p-value computed here may never be quoted against a DI computed in a
    different set. The output records which set it belongs to.
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
HP = os.path.join(C.ROOT, "cube", "healpix")
NS_MOON = 256
R_MOON = 1737.4
RADIUS_KM = float(np.sqrt(225.0 / np.pi))
BAND_DEG = 2.0
N_NULL = 1000
SEEDS = [20261109, 20261110, 20261111, 20261112, 20261113]


def rank_pct(v):
    n = v.size
    o = np.argsort(v, kind="stable")
    r = np.empty(n, dtype=np.float64)
    sv = v[o]
    i = 0
    while i < n:
        j = i + 1
        while j < n and sv[j] == sv[i]:
            j += 1
        r[o[i:j]] = (i + j - 1) / 2.0
        i = j
    return (r + 0.5) / n


def main():
    cfg = json.load(io.open(os.path.join(P4, "phase4c_summary.json"),
                            encoding="utf-8"))["earth_moon"]
    tg = json.load(io.open(os.path.join(P4, "phase4d_targets.json"),
                           encoding="utf-8"))
    dims, dbar, thr = cfg["dimensions"], cfg["d_bar"], cfg["di_threshold"]
    W = np.load(os.path.join(P4, "whiten_earth_moon.npy"))
    cen = np.load(os.path.join(P4, "center_earth_moon.npy"))
    mu, sd = cen[0], cen[1]

    print("=" * 78)
    print("PHASE 5 -- CROSS-BODY NULL")
    print("=" * 78)
    print(f"dimension set: earth_moon, {len(dims)} dims, d_bar {dbar:.4f}, "
          f"DI threshold {thr:.4f}")
    print(f"N_NULL {N_NULL} per seed, {len(SEEDS)} seeds, "
          f"|lat| band +/-{BAND_DEG} deg, both hemispheres, "
          f"disc radius {RADIUS_KM:.2f} km")

    from astropy_healpix import HEALPix
    from astropy import units as u
    from scipy.spatial import cKDTree
    hp = HEALPix(nside=NS_MOON, order="nested")
    npix = int(hp.npix)

    Lm = np.vstack([np.load(os.path.join(HP, f"moon_{d}_nside{NS_MOON}.npy"))
                    for d in dims])
    good = np.all(np.isfinite(Lm), axis=0)
    LP = np.full_like(Lm, np.nan)
    for i in range(len(dims)):
        LP[i, good] = rank_pct(Lm[i, good])
    del Lm

    P = np.load(os.path.join(P4, "percentiles.npy"))
    meta = json.load(io.open(os.path.join(P4, "phase4a_summary.json"),
                             encoding="utf-8"))
    idx = [meta["names"].index(d) for d in dims]
    ZE = ((P[idx].T.astype(np.float64) - mu) / sd) @ W
    tree = cKDTree(ZE)
    print(f"Earth reference cloud: {ZE.shape[0]:,} pixels\n")

    def di_of(sel):
        ok = sel & good
        if not ok.any():
            return None
        v = np.median(LP[:, ok], axis=1)
        return float(tree.query(((v - mu) / sd) @ W, k=1)[0] / dbar)

    rad = np.radians(RADIUS_KM / R_MOON) * u.rad
    out = []
    print(f"{'region':22s} {'DI':>7s} {'p (5 seeds)':>22s} {'spread':>8s} "
          f"{'verdict':>12s}")
    for t in tg["targets"]:
        obs = t["DI"]
        L = abs(t["center_lat"])
        lo_s = np.sin(np.radians(max(0.0, L - BAND_DEG)))
        hi_s = np.sin(np.radians(min(90.0, L + BAND_DEG)))
        ps = []
        allnull = []
        for sd_ in SEEDS:
            rng = np.random.default_rng(sd_)
            dis = []
            tries = 0
            while len(dis) < N_NULL and tries < N_NULL * 6:
                tries += 1
                s = rng.uniform(lo_s, hi_s)
                la = np.degrees(np.arcsin(s)) * rng.choice([-1.0, 1.0])
                lo = rng.uniform(-180.0, 180.0)
                pix = hp.cone_search_lonlat(lo * u.deg, la * u.deg, rad)
                if pix.size == 0:
                    continue
                sel = np.zeros(npix, dtype=bool)
                sel[pix] = True
                d = di_of(sel)
                if d is not None:
                    dis.append(d)
            dis = np.array(dis)
            allnull.append(dis)
            ps.append(float(np.mean(dis <= obs)))
        ps = np.array(ps)
        cat = np.concatenate(allnull)
        spread = ps.max() - ps.min()
        pm = float(ps.mean())
        verdict = ("SIGNIFICANT" if pm < 0.05 else
                   "marginal" if pm < 0.10 else "not significant")
        pstr = f"{pm:.4f} [{ps.min():.4f},{ps.max():.4f}]"
        print(f"{t['nasa_region']:22s} {obs:7.4f} {pstr:>22s} "
              f"{spread:8.4f} {verdict:>12s}")
        out.append(dict(
            nasa_region=t["nasa_region"], DI=obs,
            p_mean=pm, p_min=float(ps.min()), p_max=float(ps.max()),
            p_per_seed=[float(x) for x in ps], p_spread=float(spread),
            verdict=verdict,
            null_n_per_seed=int(N_NULL), seeds=SEEDS,
            null_DI_p05=float(np.percentile(cat, 5)),
            null_DI_p50=float(np.percentile(cat, 50)),
            null_DI_p95=float(np.percentile(cat, 95)),
            abs_lat_band=[max(0.0, L - BAND_DEG), min(90.0, L + BAND_DEG)],
            covered=t["covered"], offset_class=t["offset_class"]))

    io.open(os.path.join(P4, "phase5_null.json"), "w",
            encoding="utf-8").write(json.dumps(dict(
                dimension_set="earth_moon", dimensions=dims,
                d_bar=dbar, di_threshold=thr,
                n_null_per_seed=N_NULL, seeds=SEEDS,
                abs_latitude_band_deg=BAND_DEG,
                radius_km=RADIUS_KM,
                method=("null windows drawn in the same ABSOLUTE-latitude "
                        "band as the target, from BOTH hemispheres, same "
                        "disc radius. Banding on SIGNED latitude would make "
                        "the matching set two disjoint arcs, because a "
                        "disc's pixel count depends on |lat|; that error "
                        "produced a 95% rejection rate before it was caught."),
                p_definition="fraction of null windows with DI <= observed DI",
                warning=("This null belongs to the earth_moon dimension set "
                         "ONLY. A p-value from here may not be quoted "
                         "against a DI computed in any other set."),
                targets=out,
                built_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                        time.gmtime())), indent=1))
    print(f"\nwrote {P4}/phase5_null.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
