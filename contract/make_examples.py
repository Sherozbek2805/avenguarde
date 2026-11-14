"""
Build the contract's example files from the REAL cube, with PLACEHOLDER distances.

    python contract/make_examples.py

Writes contract/example_output.json (a "significant" shape), example_output_null.json
(a non-significant shape) and example_point.json (the click payload), and validates
all three against the schemas.

WHAT IS REAL: every physical value, percentile, Koppen class, lithology class,
catalogue distance and coordinate is read from the cube and the catalogues.
WHAT IS NOT: di_combined, di_group, di_target, p, null_median, ranks and the
controls. The engine does not exist yet. Those fields are filled with the mean
absolute percentile gap (a stand-in with the right shape and range) and the file
says so in code_version and limits. Do not quote any distance from these files.
"""

import csv
import io
import json
import os
import sys
import time

import numpy as np

ROOT = os.environ.get("ANALOG_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "build"))
import cubelib as C
from astropy import units as u
from astropy_healpix import HEALPix

HP = os.path.join(ROOT, "cube", "healpix")
OUT = os.path.join(ROOT, "contract")
GROUP = {"slope": "terrain", "roughness_5.25km": "terrain", "roughness_10.5km": "terrain",
         "roughness_21km": "terrain", "roughness_42km": "terrain", "tpi_21km": "terrain",
         "tpi_7km": "terrain", "svf_30km": "terrain", "temp_level": "thermal",
         "temp_range_diurnal": "thermal", "temp_range_seasonal": "thermal",
         "thermal_inertia": "thermal", "SiO2": "composition", "FeO": "composition"}
UNITS = {"slope": "degrees", "roughness_5.25km": "m", "roughness_10.5km": "m", "roughness_21km": "m",
         "roughness_42km": "m", "tpi_21km": "m", "tpi_7km": "m", "svf_30km": "dimensionless",
         "temp_level": "K", "temp_range_diurnal": "K", "temp_range_seasonal": "K",
         "thermal_inertia": "tiu (Mars) / K^-1 apparent (Earth)", "SiO2": "wt%", "FeO": "wt%"}
EARTHS_LIMITS = [
    dict(what="Gravity", numbers="Moon 1.62 m/s2, Mars 3.72 m/s2, Earth 9.81 m/s2",
         invalidates="Regolith mechanics, dust settling, drill reaction forces, lander dynamics, human gait and load testing"),
    dict(what="Atmospheric pressure", numbers="Moon ~1e-12 bar, Mars ~0.006 bar, Earth 1 bar",
         invalidates="Vacuum seals, boiling points, convective heat rejection, anything pneumatic"),
    dict(what="Radiation", numbers="No global magnetic field and no thick atmosphere on either target",
         invalidates="Electronics tolerance, crew dose planning, material ageing"),
    dict(what="Day length", numbers="Lunar day about 29.5 Earth days; Mars 24.66 h",
         invalidates="Power and thermal cycling on the Moon; Mars is close enough that the swing is ranked"),
    dict(what="Weathering history", numbers="Earth's surfaces are water- and life-altered; the targets' are not",
         invalidates="Grain shape, soil chemistry, mineral alteration products"),
]


def hp_of(nside):
    return HEALPix(nside=nside, order="nested")


def load(body, name):
    p = os.path.join(HP, f"{body}_{name}_nside{C.NSIDE[body]}.npy")
    return np.load(p) if os.path.exists(p) else None


def pct_of(value, sorted_ref):
    if value is None or not np.isfinite(value):
        return None
    lo = np.searchsorted(sorted_ref, value, side="left"); hi = np.searchsorted(sorted_ref, value, side="right")
    return float((0.5 * (lo + hi)) / sorted_ref.size)


def nearest_catalogue(lat, lon, cat):
    la, lo = np.radians(lat), np.radians(lon)
    cl, co = np.radians(cat["lat"]), np.radians(cat["lon"])
    d = 2 * 6371.0 * np.arcsin(np.sqrt(np.sin((cl - la) / 2) ** 2 + np.cos(la) * np.cos(cl) * np.sin((co - lo) / 2) ** 2))
    i = int(np.argmin(d))
    return cat["name"][i], cat["source"][i], float(d[i])


def main():
    man = json.load(io.open(os.path.join(ROOT, "cube", "cube_manifest.json"), encoding="utf-8"))["layers"]
    cv = json.load(io.open(os.path.join(ROOT, "cube", "cube_validation.json"), encoding="utf-8"))
    p4c = json.load(io.open(os.path.join(ROOT, "cube", "phase4", "phase4c_summary.json"), encoding="utf-8"))
    legend = json.load(io.open(os.path.join(ROOT, "cube", "koppen_legend.json"), encoding="utf-8"))["classes"]
    lith = man["earth_lithology_l1"]
    l1vocab, l1mean = lith["vocabulary"], lith["l1_meaning"]
    dims = cv["pairings"]["earth_moon"]
    order = [d for d in GROUP if d in dims]
    refmask = np.load(os.path.join(HP, "earth_reference_mask_nside1024.npy")); ref = np.isfinite(refmask) & (refmask > 0.5)
    hp_e, hp_m = hp_of(1024), hp_of(256)
    kop = np.load(os.path.join(HP, "earth_koppen_class_nside1024.npy"))
    l1 = np.load(os.path.join(HP, "earth_lithology_l1_nside1024.npy"))
    # B31: where SCAR GeoMAP names the rock (Antarctica, South Georgia) it is the lithology source
    gmc = np.load(os.path.join(HP, "earth_geomap_lithcode_nside1024.npy"))
    gm_mean = {r["code"]: r["rock_type"] for r in csv.DictReader(io.open(os.path.join(ROOT, "sources", "geomap_composition_lookup.csv"), encoding="utf-8"))}
    rows = list(csv.DictReader(io.open(os.path.join(ROOT, "sources", "tier4_catalogues", "known_analog_sites_v2.csv"), encoding="utf-8")))
    n_all = len(rows)
    rows = [r for r in rows if r["lat"].strip() and r["lon"].strip()]      # entries without coordinates cannot be matched
    print(f"catalogue: {len(rows)} of {n_all} entries carry coordinates")
    cat = dict(name=[r["name"] for r in rows], source=[r["source"] for r in rows],
               lat=np.array([float(r["lat"]) for r in rows]), lon=np.array([float(r["lon"]) for r in rows]))

    # target: Haworth, the Artemis III region, from the published polygon (contract/targets_moon.json,
    # build/targets.py). Until 10 Nov this was an 8.46 km disc at the IAU crater centre, 80 km of proxy.
    tgt = [t for t in json.load(io.open(os.path.join(ROOT, "contract", "targets_moon.json"), encoding="utf-8"))["targets"] if t["name"] == "Haworth"][0]
    t_lat, t_lon = tgt["center_lat"], tgt["center_lon"]
    tpix = np.array(tgt["healpix_pixels"], dtype=np.int64)
    t_abs = np.abs(hp_m.healpix_to_lonlat(tpix)[1].deg)
    # B38, 11 Nov 2026: ONE MIN-MAX scale per variable for Earth + Moon. lo and hi are in
    # cube/phase4/minmax_scale_summary.json (phase4b_minmax_scale.py).
    MM = json.load(io.open(os.path.join(ROOT, "cube", "phase4", "minmax_scale_summary.json"), encoding="utf-8"))["pairings"]["moon"]["variables"]
    USE_TABLE = json.load(io.open(os.path.join(ROOT, "contract", "use_table.json"), encoding="utf-8"))

    def pooled(d, value):
        if value is None or not np.isfinite(value):
            return None
        return float((value - MM[d]["lo"]) / (MM[d]["hi"] - MM[d]["lo"]))

    earth, moon = {}, {}
    for d in order:
        earth[d] = load("earth", d); moon[d] = load("moon", d)
    t_med = {d: float(np.nanmedian(moon[d][tpix])) for d in order}
    t_pct = {d: pooled(d, t_med[d]) for d in order}
    feat = np.vstack([moon[d][tpix] for d in order]).T
    distinct = int(np.unique(np.round(feat, 6), axis=0).shape[0])
    # B36: rank only on what Earth can match. Which variables rank, and which are Earth's limits, come from build/ranking_sets.py.
    RKDOC = json.load(io.open(os.path.join(ROOT, "contract", "targets_ranking.json"), encoding="utf-8"))
    RK = [t for t in RKDOC["targets"]["moon"] if t["name"] == "Haworth"][0]["constructions"]["all_dimensions"]
    RSET = RKDOC["sets"][RK["ranking_set"]]
    RANKED = set(RK["ranked_dimensions"])

    def variable_rows(pix):
        out = []
        for d in order:
            v = float(earth[d][pix]) if np.isfinite(earth[d][pix]) else None
            ep = pooled(d, v) if v is not None else None
            gap = None if ep is None else ep - t_pct[d]
            verdict = "withheld" if gap is None else ("agrees" if abs(gap) < 0.10 else ("differs" if abs(gap) > 0.25 else "partial"))
            out.append(dict(name=d, group=GROUP[d], units=UNITS[d], earth=None if v is None else round(v, 4),
                            target_median=round(t_med[d], 4), earth_position=None if ep is None else round(ep, 4),
                            target_position=round(t_pct[d], 4), position_gap=None if gap is None else round(gap, 4),
                            physical_gap=None if v is None else round(v - t_med[d], 4), verdict=verdict, modelled=False, ranked=d in RANKED))
        return out

    def use_block(vr):
        """the rule written in contract/use_table.json, applied to one site's variable rows."""
        by = {r["name"]: r for r in vr}
        beyond_vars = {o["variable"] for o in RK["out_of_range"]}
        out = dict(succeeds=[], fails=[], beyond_earth=[])
        for row in USE_TABLE["rows"]:
            vs = [v for v in row["variables"] if v in by]
            if not vs:
                continue
            line = dict(key=row["key"], group=row["group"], label=row["label"], variables=vs)
            verdicts = [by[v]["verdict"] for v in vs]
            if any(v in beyond_vars for v in vs):
                out["beyond_earth"].append(dict(line, text=row["if_beyond_earth"]))
            elif all(v == "agrees" for v in verdicts):
                out["succeeds"].append(dict(line, text=row["if_agrees"]))
            elif any(v == "differs" for v in verdicts):
                out["fails"].append(dict(line, text=row["if_differs"]))
        out["general"] = None if out["succeeds"] else USE_TABLE["general_sentence"]
        return out

    def place(lat, lon):
        pix = int(hp_e.lonlat_to_healpix(lon * u.deg, lat * u.deg))
        vr = variable_rows(pix)
        gaps = {g: [abs(r["position_gap"]) for r in vr if r["group"] == g and r["ranked"] and r["position_gap"] is not None] for g in ("terrain", "thermal", "composition")}
        dg = {g: (round(float(np.mean(v)), 4) if v else None) for g, v in gaps.items()}
        allg = [abs(r["position_gap"]) for r in vr if r["ranked"] and r["position_gap"] is not None]
        worst = max(((g, v) for g, v in dg.items() if v is not None), key=lambda t: t[1])
        ranked = sorted([r for r in vr if r["ranked"] and r["position_gap"] is not None], key=lambda r: abs(r["position_gap"]))
        nm, src, dist = nearest_catalogue(lat, lon, cat)
        k = int(kop[pix]); li = int(l1[pix])
        return pix, dict(
            lat=round(lat, 4), lon=round(lon, 4), healpix_pixel=pix,
            di_combined=round(float(np.mean(allg)), 4), di_target=round(float(np.mean(allg)) * 1.3, 4),
            di_group=dg, worst_group=dict(name=worst[0], di=worst[1]),
            dims_used_here=len(allg),
            catalogue=dict(status="known" if dist <= 100 else "new candidate", name=nm if dist <= 100 else None,
                           citation=src if dist <= 100 else None, distance_km=round(dist, 1)),
            koppen=None if k == 0 else dict(code=k, symbol=legend[str(k)]["symbol"], description=legend[str(k)]["description"]),
            lithology=(dict(l1_code=chr(int(gmc[pix])), description=gm_mean.get(chr(int(gmc[pix])), chr(int(gmc[pix]))), source="GeoMAP") if gmc[pix] > 0
                       else None if li == 255 else dict(l1_code=l1vocab[str(li)], description=l1mean.get(l1vocab[str(li)], l1vocab[str(li)]), source="GLiM")),
            variables=vr, agrees=[r["name"] for r in vr if r["ranked"] and r["verdict"] == "agrees"],
            partial=[r["name"] for r in vr if r["ranked"] and r["verdict"] == "partial"], differs=[r["name"] for r in vr if r["ranked"] and r["verdict"] == "differs"],
            best3=[r["name"] for r in ranked[:3]], worst3=[r["name"] for r in ranked[-3:][::-1]],
            use=use_block(vr))

    places = [(67.0033, -146.61), (64.5267, 125.8861), (-77.52, 161.85)]   # interior Alaska, Yakutia, Dry Valleys
    sites = []
    for i, (la, lo) in enumerate(places):
        pix, s = place(la, lo)
        s.update(rank=i + 1)
        sites.append({k: s[k] for k in ["rank", "lat", "lon", "healpix_pixel", "di_combined", "di_target", "di_group", "worst_group",
                                        "dims_used_here", "catalogue", "koppen",
                                        "lithology", "variables", "agrees", "partial", "differs", "best3", "worst3", "use"]})
    sites.sort(key=lambda s: s["di_combined"])
    for i, s in enumerate(sites):
        s["rank"] = i + 1
        s["patch_cells"] = [212, 61, 9][i]                      # PLACEHOLDER patch sizes
        s["patch_area_km2"] = round(s["patch_cells"] * 40.54, 1)

    groups = {g: dict(n_variables=sum(1 for d in order if GROUP[d] == g and d in RANKED)) for g in ("terrain", "thermal", "composition")}
    PLACEHOLDER = ("EXAMPLE FILE, NOT A RESULT. Physical values, percentiles, Koppen and lithology classes, coordinates and catalogue "
                   "distances are real and read from the cube of 10 Nov 2026. Every di_* value, p, null_median, rank and control is a "
                   "PLACEHOLDER (the mean absolute percentile gap), because the engine is written on the hackathon day. ")
    run = dict(
        code_version="EXAMPLE-NOT-A-RESULT", run_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        target=dict(body="moon", name="Haworth (Artemis III candidate region)",
                    selection=dict(method="named_feature", params=dict(catalogue="targets_moon", feature_id="Haworth")),
                    cells=int(tpix.size), cells_distinct=distinct, spread=0.0 if distinct == 1 else 0.85,
                    abs_lat_range=[round(float(t_abs.min()), 2), round(float(t_abs.max()), 2)]),
        variables=[dict(name=d, group=GROUP[d], units=UNITS[d], modelled=False, weak=d in ("SiO2", "FeO"), ranked=d in RANKED) for d in order],
        groups=groups, grid=dict(scheme="healpix_nested", nside_target=256, nside_earth=1024),
        target_cells_used="all",
        ranking=dict(system="earth_reachable_only", rule=RKDOC["rule"], ranking_set=RK["ranking_set"], ranked_variables=RK["ranked_dimensions"], out_of_range=RK["out_of_range"]),
        rank_bands=[0.01, 0.05],
        distance="mahalanobis_whitened", scale="minmax", eigen_floor=0.10,
        floored_directions=RSET["eigenvalues_floored"], d_bar_earth=round(RSET["d_bar"], 4), d_bar_target=None if distinct == 1 else 3.1,
        dims_used=len(RANKED), verdict_thresholds=dict(agrees_below=0.10, differs_above=0.25),
        site_rule="patches_of_top_share", site_top_share=0.01, patches_total=14,
        reference_population=dict(pixels=int(ref.sum()), definition="Ice-free, water-free land with every used dimension present. Antarctica enters as exposed rock; the ice sheet is excluded from ranking."))
    rasters = [dict(name=n, file=f"runs/example/{n}_nside1024.npy", format="healpix_npy", units="dimensionless (DI)", vmin=0.0, vmax=1.0,
                    colormap="viridis_r", views=dict(**{"global": f"runs/example/{n}_global.png", "north_polar": f"runs/example/{n}_north.png", "south_polar": f"runs/example/{n}_south.png"}))
               for n in ("di_combined",) + tuple("di_" + g for g in ("terrain", "thermal", "composition") if groups[g]["n_variables"])]
    for r in rasters: r["encoding"] = None
    rasters.append(dict(name="rank_combined", file="runs/example/rank_combined_nside1024.npy", format="healpix_npy", units="rank among reference cells, 0 = best on Earth",
                        vmin=0.0, vmax=1.0, colormap="none (data)", encoding="8-bit grey v; rank = (v / 255) squared",
                        views=dict(**{"global": "runs/example/rank_combined_global.png", "north_polar": "runs/example/rank_combined_north.png", "south_polar": "runs/example/rank_combined_south.png"})))
    sources = [dict(name="LOLA 118 m lunar DEM", url="https://pds-geosciences.wustl.edu/missions/lro/lola.htm", used_for="lunar terrain layers"),
               dict(name="ETOPO 2022 15 arc-second", url="https://www.ncei.noaa.gov/products/etopo-global-relief-model", used_for="Earth terrain layers"),
               dict(name="Diviner GCP", url="https://doi.org/10.17189/1520655", used_for="lunar temperature level and diurnal range"),
               dict(name="MODIS MOD11C3 / MYD11C3", url="https://lpdaac.usgs.gov/products/mod11c3v061/", used_for="Earth temperature level and diurnal range"),
               dict(name="Lunar Prospector GRS", url="https://pds-geosciences.wustl.edu/missions/lunarp/", used_for="lunar SiO2 and FeO"),
               dict(name="GLiM, Hartmann & Moosdorf 2012", url="https://doi.org/10.1029/2012GC004370", used_for="Earth lithology, SiO2 and FeO"),
               dict(name="SCAR GeoMAP v.2022-08, Cox et al. 2023", url="https://doi.org/10.1594/PANGAEA.951482", used_for="rock class of exposed ground in Antarctica and South Georgia"),
               dict(name="Gard, Hasterok & Halpin 2019", url="https://doi.org/10.5281/zenodo.3359791", used_for="check of the class-to-composition lookup")]

    def doc(significant):
        nt = dict(B=1000, statistic="minimum di_combined over the Earth sample", null_source="live",
                  band_abs_lat=tgt["abs_lat_band"], patch_cells=int(tpix.size), earth_sample_n=100000, seed=20261114,
                  di_observed=sites[0]["di_combined"], null_median=round(sites[0]["di_combined"] * (1.6 if significant else 0.9), 4),
                  p=0.000999 if significant else 0.418, p_at_floor=bool(significant),
                  positive_control=dict(name="Atacama, Yungay core (placeholder)", di_observed=0.05, p=0.000999, passed=True))
        return dict(contract_version="2.4", run=run, null_test=nt, sites=sites, rasters=rasters,
                    earths_limits=EARTHS_LIMITS,
                    limits=PLACEHOLDER + "Composition is a weak dimension at both ends. The Haworth region is the polygon LROC QuickMap publishes for NASA's 28 October 2024 update.",
                    ai_disclosure="PLACEHOLDER. The team's AI-use disclosure goes here verbatim (spec Appendix G).", sources=sources)

    import jsonschema
    schema = json.load(io.open(os.path.join(OUT, "output_schema.json"), encoding="utf-8"))
    for name, d in (("example_output.json", doc(True)), ("example_output_null.json", doc(False))):
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(d)
        io.open(os.path.join(OUT, name), "w", encoding="utf-8").write(json.dumps(d, indent=1, ensure_ascii=False))
        print(f"wrote {name}: {len(d['sites'])} sites, validates")
    pschema = json.load(io.open(os.path.join(OUT, "point_schema.json"), encoding="utf-8"))
    pix, s = place(-77.52, 161.85)
    point = dict(contract_version="2.4", target_name=run["target"]["name"], lat=s["lat"], lon=s["lon"],
                 healpix_pixel=pix, in_reference_population=bool(ref[pix]), reason_excluded=None if ref[pix] else "ice",
                 di_combined=s["di_combined"], di_group=s["di_group"], worst_group=s["worst_group"], dims_used_here=s["dims_used_here"],
                 variables=s["variables"], agrees=s["agrees"], partial=s["partial"], differs=s["differs"], best3=s["best3"], worst3=s["worst3"], use=s["use"],
                 koppen=s["koppen"], lithology=s["lithology"], catalogue=s["catalogue"], limits=PLACEHOLDER)
    jsonschema.Draft202012Validator(pschema).validate(point)
    io.open(os.path.join(OUT, "example_point.json"), "w", encoding="utf-8").write(json.dumps(point, indent=1, ensure_ascii=False))
    print("wrote example_point.json, validates")
    for s_ in sites:
        print(f"  site {s_['rank']}: {s_['lat']:.2f},{s_['lon']:.2f}  koppen {s_['koppen']['symbol'] if s_['koppen'] else None}  "
              f"agrees {len(s_['agrees'])} partial {len(s_['partial'])} differs {len(s_['differs'])}  worst group {s_['worst_group']['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
