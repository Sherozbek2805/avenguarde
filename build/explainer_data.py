"""
Real numbers for the animated explainer (docs/explainer/).

    python build/explainer_data.py

Writes docs/explainer/data.js  (a single `const DATA = {...};`).

DESCRIPTION ONLY. Everything here is a raw layer value, a position on the
pooled scale, a pixel set or a calibration constant. No distance to a target,
no DI, no p-value and no site is computed: the scenes that show the search,
the null test and site selection use invented data and say so on screen.
"""

import io
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

HP = os.path.join(C.ROOT, "cube", "healpix")
P4 = os.path.join(C.ROOT, "cube", "phase4")
OUT = os.path.join(C.ROOT, "docs", "explainer")
rng = np.random.default_rng(7)


def jl(*p):
    return json.load(io.open(os.path.join(C.ROOT, *p), encoding="utf-8"))


def lay(body, d):
    return np.load(os.path.join(HP, f"{body}_{d}_nside{C.NSIDE[body]}.npy"))


def r(a, nd=2):
    return [round(float(x), nd) for x in a]


def main():
    from astropy_healpix import HEALPix
    os.makedirs(OUT, exist_ok=True)
    ref = np.load(os.path.join(P4, "ref_pixels.npy"))[np.load(os.path.join(P4, "complete_mask.npy"))]
    D = {}

    # ---- raw samples for the pooled-scale scene
    def samp(v, n):
        v = v[np.isfinite(v)]
        return np.sort(rng.choice(v, n, replace=False))

    er, mr, xr = lay("earth", "roughness_21km")[ref], lay("moon", "roughness_21km"), lay("mars", "roughness_21km")
    et, mt = lay("earth", "temp_level")[ref], lay("moon", "temp_level")
    D["rough"] = dict(earth=r(np.log10(samp(er, 220)), 3), moon=r(np.log10(samp(mr, 220)), 3),
                      mars=r(np.log10(samp(xr, 220)), 3),
                      earth_median=round(float(np.median(er)), 1), moon_median=round(float(np.nanmedian(mr)), 1),
                      mars_median=round(float(np.nanmedian(xr)), 1))
    D["temp"] = dict(earth=r(samp(et, 180), 1), moon=r(samp(mt, 180), 1),
                     earth_median=round(float(np.median(et)), 0), moon_median=round(float(np.nanmedian(mt)), 0))
    # ---- B38: the MIN-MAX scale. Real values on a straight axis, lo and hi from the summary.
    pool = jl("cube", "phase4", "minmax_scale_summary.json")
    names = pool["pairings"]["moon"]["names"]
    mmr = pool["pairings"]["moon"]["variables"]["roughness_21km"]
    D["mm"] = dict(lo=round(mmr["lo"], 1), hi=round(mmr["hi"], 1), hi_set_by=mmr["hi_set_by"],
                   earth=r(samp(er, 260), 1), moon=r(samp(mr, 260), 1),
                   earth_median=round(float(np.median(er)), 1), moon_median=round(float(np.nanmedian(mr)), 1))

    # ---- whitening scene: two correlated Earth variables, in units of Earth's own spread
    ZE = np.load(os.path.join(P4, "minmax_earth_moon.npy"), mmap_mode="r")
    MU = {d: float(np.asarray(ZE[names.index(d)], dtype=np.float64).mean()) for d in ("slope", "roughness_42km", "roughness_21km", "tpi_21km")}
    SD = {d: float(np.asarray(ZE[names.index(d)], dtype=np.float64).std()) for d in MU}
    std = lambda d, v: (np.asarray(v, dtype=np.float64) - MU[d]) / SD[d]
    full_a = np.asarray(ZE[names.index("slope")], dtype=np.float64)
    full_b = np.asarray(ZE[names.index("roughness_42km")], dtype=np.float64)
    corr = float(np.corrcoef(full_a, full_b)[0, 1])
    sub = np.sort(rng.choice(ZE.shape[1], 700, replace=False))
    a, b = std("slope", full_a[sub]), std("roughness_42km", full_b[sub])
    keep = (np.abs(a) < 3.1) & (np.abs(b) < 3.1)          # the picture shows the middle of the cloud; the tail cells are real too
    D["whiten"] = dict(x=r(a[keep][:420]), y=r(b[keep][:420]), corr=round(corr, 2))

    # ---- feature space scene: Earth cells and the Haworth cells, two variables, pooled z
    ZM = np.load(os.path.join(P4, "minmax_moon.npy"), mmap_mode="r")
    tm = jl("contract", "targets_moon.json")["targets"]
    hw = [t for t in tm if t["name"] == "Haworth"][0]
    # B36: both axes are variables that RANK Haworth (temperature no longer does)
    i_r, i_t = names.index("roughness_21km"), names.index("tpi_21km")
    sub2 = np.sort(rng.choice(ZE.shape[1], 380, replace=False))
    # both axes in units of Earth's own spread (what step 4 measures in)
    D["space"] = dict(ex=r(std("roughness_21km", ZE[i_r][sub2])), ey=r(std("tpi_21km", ZE[i_t][sub2])),
                      tx=r(std("roughness_21km", ZM[i_r][hw["healpix_pixels"]])), ty=r(std("tpi_21km", ZM[i_t][hw["healpix_pixels"]])))

    # ---- the lunar south pole: real cells, real temperature, real regions
    hp = HEALPix(nside=256, order="nested")
    lon, lat = hp.healpix_to_lonlat(np.arange(hp.npix))
    lat, lon = lat.deg, np.radians(lon.deg)
    R = 1737.4
    rho = 2 * R * np.tan(np.radians(90 + lat) / 2)
    px, py = rho * np.sin(lon), rho * np.cos(lon)
    near = (lat < -80) & (np.hypot(px, py) < 215)
    ids = np.flatnonzero(near)
    t = mt[ids]
    D["pole"] = dict(x=[int(round(v)) for v in px[ids]], y=[int(round(v)) for v in py[ids]],
                     t=[int(round(v)) if np.isfinite(v) else -1 for v in t], tmin=40, tmax=240)
    idx_of = {int(pid): j for j, pid in enumerate(ids)}
    regs = []
    for tg in tm:
        v = np.array(tg["geometry"]["vertices_lonlat"])
        rh = 2 * R * np.tan(np.radians(90 + v[:, 1]) / 2)
        vx, vy = rh * np.sin(np.radians(v[:, 0])), rh * np.cos(np.radians(v[:, 0]))
        regs.append(dict(name=tg["name"], cells=tg["cells"], vx=r(vx, 1), vy=r(vy, 1),
                         idx=[idx_of[q] for q in tg["healpix_pixels"] if q in idx_of]))
    D["regions"] = regs

    # ---- an Earth layer as dots, for the "cube" beat
    hpe = HEALPix(nside=1024, order="nested")
    from astropy import units as u
    glon, glat = np.meshgrid(np.arange(-178.5, 180, 3.0), np.arange(-58.5, 84, 3.0))
    pe = hpe.lonlat_to_healpix(glon.ravel() * u.deg, glat.ravel() * u.deg)
    refmask = np.load(os.path.join(HP, "earth_reference_mask_nside1024.npy"))[pe] > 0.5
    rr = np.log10(np.clip(lay("earth", "roughness_21km")[pe], 1, None))
    tt = lay("earth", "temp_level")[pe]
    ok = refmask & np.isfinite(rr) & np.isfinite(tt)
    D["earth"] = dict(lon=r(glon.ravel()[ok], 1), lat=r(glat.ravel()[ok], 1),
                      rough=[int(round(255 * np.clip((v - 0.3) / 2.6, 0, 1))) for v in rr[ok]],
                      temp=[int(round(255 * np.clip((v - 240) / 70, 0, 1))) for v in tt[ok]])

    # ---- characterization: one real pair, read from the contract example
    rkd = jl("contract", "targets_ranking.json")
    hk = [t for t in rkd["targets"]["moon"] if t["name"] == "Haworth"][0]["constructions"]["all_dimensions"]
    ex = [q for q in jl("contract", "example_output.json")["sites"] if abs(q["lat"] + 77.52) < 0.01][0]
    keep = ["slope", "roughness_21km", "roughness_42km", "svf_30km", "temp_level", "temp_range_diurnal", "SiO2", "FeO"]
    lab = {"slope": "Slope", "roughness_21km": "Roughness 21 km", "roughness_42km": "Roughness 42 km",
           "svf_30km": "Sky view", "temp_level": "Temperature", "temp_range_diurnal": "Day–night swing",
           "SiO2": "Silica", "FeO": "Iron oxide"}
    un = {"degrees": "°", "m": " m", "K": " K", "wt%": "%", "dimensionless": ""}
    D["pair"] = [dict(name=lab[v["name"]], unit=un.get(v["units"], ""), earth=v["earth"], target=v["target_median"],
                      pe=v["earth_position"], pt=v["target_position"], verdict=v["verdict"],
                      ranked=not any(o["variable"] == v["name"] for o in hk["out_of_range"]))
                 for v in ex["variables"] if v["name"] in keep]

    # ---- calibration and counts
    c = jl("cube", "phase4", "phase4c_summary.json")
    rk = dict(n_ranked=hk["n_ranked"], limits=[dict(variable=o["variable"], target=o["target_median"], earth_min=o["earth_min"],
                                                    earth_max=o["earth_max"], gap=o["gap"], side=o["side"]) for o in hk["out_of_range"]])
    D["num"] = dict(
        cells=dict(earth=12 * 1024 ** 2, moon=12 * 256 ** 2, mars=12 * 512 ** 2),
        cell_km=dict(earth=6.4, moon=6.9, mars=6.8),
        ref_cells=int(c["earth_moon"]["n_reference"]),
        dims=dict(moon=len(c["earth_moon"]["dimensions"]), mars=len(c["earth_mars"]["dimensions"]),
                  mars_nocomp=len(c["earth_mars_no_composition"]["dimensions"])),
        share={g: round(100 * v["share_of_squared_distance_between_earth_cells"]) for g, v in c["earth_moon"]["groups"].items()},
        haworth_cells=hw["cells"], ranking=rk)
    txt = "const DATA = " + json.dumps(D, separators=(",", ":")) + ";\n"
    io.open(os.path.join(OUT, "data.js"), "w", encoding="utf-8", newline="\n").write(txt)
    print(f"wrote data.js: {len(txt)/1024:.0f} KB; pole cells {len(ids)}, earth dots {int(ok.sum())}, "
          f"whiten corr {D['whiten']['corr']}, Haworth cells on map {len(regs[1]['idx'])}")
    print("pair:", [(p["name"], p["earth"], p["target"], p["verdict"]) for p in D["pair"]])
    print("num:", D["num"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
