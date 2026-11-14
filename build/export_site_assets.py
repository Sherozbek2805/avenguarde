"""
EXPORT STATIC ASSETS FOR THE WEBSITE -- map tiles of the cube and the catalogues.

    python build/export_site_assets.py

Writes export/site_assets/:
    <body>/<layer>_global.png        2880 x 1440, plate carree, lon -180..180, lat 90..-90, RGBA
    <body>/<layer>_north.png         1200 x 1200, polar azimuthal equidistant, 60..90 N, RGBA
    <body>/<layer>_south.png         same for 60..90 S
    <body>/basemap_{global,north,south}.png   shaded relief from the working DEM (RGB)
    catalogue/known_analog_sites.geojson, apollo_training_sites.geojson,
              targets_moon_artemis3.geojson
    layers.json                      everything a frontend needs: files, units, colour
                                     range, colormap, projection formulas, flags

Six display layers per body where they exist: roughness_21km, tpi_21km, svf_30km,
temp_level, temp_range_diurnal, SiO2. They are the six a human can read; the
engine still uses all 12 / 14. Earth layers are shown over the REFERENCE
POPULATION only (what ranks). Absent or masked pixels are TRANSPARENT, never a
colour that could pass for a value. Colour ranges are the atlas's (p2..p98 or
the layer's physical range) and are written into layers.json.

POLAR PROJECTION (stated so markers can be placed): azimuthal equidistant,
pole at the centre, radius of the image = 30 degrees of latitude.
    north: x = 0.5 + 0.5 * ((90 - lat) / 30) * sin(lon),  y = 0.5 + 0.5 * ((90 - lat) / 30) * cos(lon)   [lon 0 points DOWN]
    south: x = 0.5 + 0.5 * ((90 + lat) / 30) * sin(lon),  y = 0.5 - 0.5 * ((90 + lat) / 30) * cos(lon)   [lon 0 points UP]
x, y are fractions of image width and height from the top-left corner.
"""

import csv
import io
import json
import os
import sys
import time

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C
import atlas as A
from figures import PLAN, downsample_mean, hillshade, shade_rgb
from phase1_dems import DEM_DIR

OUT = os.path.join(C.ROOT, "export", "site_assets")
HP = os.path.join(C.ROOT, "cube", "healpix")
DISPLAY = ["roughness_21km", "tpi_21km", "svf_30km", "temp_level", "temp_range_diurnal", "SiO2"]
GW, GH, PN, PRAD = 2880, 1440, 1200, 30.0


def hp_of(nside):
    from astropy_healpix import HEALPix
    return HEALPix(nside=nside, order="nested")


def polar_lonlat(north, n=PN, rad=PRAD):
    g = (np.arange(n) + 0.5) / n * 2.0 - 1.0
    X, Y = np.meshgrid(g, g)                 # X right, Y down, both -1..1
    r = np.hypot(X, Y)
    inside = r <= 1.0
    if north:
        lat = 90.0 - r * rad; lon = np.degrees(np.arctan2(X, Y))
    else:
        lat = -90.0 + r * rad; lon = np.degrees(np.arctan2(X, -Y))
    return lon, lat, inside


def sample_healpix(vals, nside, lon, lat):
    from astropy import units as u
    idx = hp_of(nside).lonlat_to_healpix(lon.ravel() * u.deg, lat.ravel() * u.deg)
    return vals[idx].reshape(lon.shape)


def to_rgba(arr, vmin, vmax, log, cmap):
    a = np.log10(np.where(arr > 0, arr, np.nan)) if log else arr
    lo, hi = (np.log10(vmin), np.log10(vmax)) if log else (vmin, vmax)
    t = np.clip((a - lo) / (hi - lo), 0, 1)
    rgba = (plt.get_cmap(cmap)(np.nan_to_num(t, nan=0.0)) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(np.isfinite(a), 255, 0)
    return rgba


def save(rgba, path, mode="RGBA"):
    Image.fromarray(rgba, mode=mode).save(path, optimize=True)


def basemap(body, out_dir):
    pl = PLAN[body]
    native_w = {"moon": 23040, "mars": 46080, "earth": 86400}[body]
    f = native_w // GW
    z, native = downsample_mean(os.path.join(DEM_DIR, pl["file"]), f)
    cell_m = (180.0 / native[0]) * (np.pi * C.BODY_RADIUS_M[body] / 180.0) * f
    rgb = shade_rgb(hillshade(z, cell_m, 315.0, 45.0, pl["z"]), z)
    save(rgb, os.path.join(out_dir, "basemap_global.png"), "RGB")
    h, w = rgb.shape[:2]
    for tag, north in (("north", True), ("south", False)):
        lon, lat, inside = polar_lonlat(north)
        r = np.clip(((90.0 - lat) / 180.0 * h).astype(int), 0, h - 1)
        c = np.clip(((lon + 180.0) / 360.0 * w).astype(int), 0, w - 1)
        img = rgb[r, c]
        rgba = np.dstack([img, np.where(inside, 255, 0).astype(np.uint8)])
        save(rgba, os.path.join(out_dir, f"basemap_{tag}.png"))
    return dict(**{"global": f"{body}/basemap_global.png", "north_polar": f"{body}/basemap_north.png",
                   "south_polar": f"{body}/basemap_south.png"},
                source=pl["file"], vertical_exaggeration=pl["z"], note="shaded relief, block-mean then shade; a picture, not data")


def main():
    t0 = time.perf_counter()
    man = json.load(io.open(C.MANIFEST, encoding="utf-8"))["layers"]
    ref = A.earth_ref()
    out = dict(generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               contract_version="2.4",
               projections=dict(
                   **{"global": "plate carree, 2880 x 1440, lon -180..180 left to right, lat 90..-90 top to bottom"},
                   north_polar="azimuthal equidistant, 1200 x 1200, pole at centre, edge at 60 N; x = 0.5 + 0.5*((90-lat)/30)*sin(lon), y = 0.5 + 0.5*((90-lat)/30)*cos(lon)",
                   south_polar="azimuthal equidistant, 1200 x 1200, pole at centre, edge at 60 S; x = 0.5 + 0.5*((90+lat)/30)*sin(lon), y = 0.5 - 0.5*((90+lat)/30)*cos(lon)"),
               masked="transparent (alpha 0); draw as neutral grey, never as a low value",
               bodies={}, catalogue={})
    for body, nside in A.BODY_ORDER:
        d = os.path.join(OUT, body); os.makedirs(d, exist_ok=True)
        entry = dict(nside=nside, pixel_km={"earth": 6.37, "moon": 6.95, "mars": 6.79}[body],
                     shown_population=("reference population: ice-free, water-free land (what ranks)" if body == "earth" else "all pixels"),
                     basemap=basemap(body, d), layers=[])
        print(f"  {body}: basemap", flush=True)
        for nm in DISPLAY:
            a = A.load(body, nside, nm)
            if a is None:
                continue
            a = a.copy()
            if body == "earth":
                a[~ref] = np.nan
            label, units, spec, cmap = A.LAYERS[nm]
            vmin, vmax, log = A.stretch(a, spec)
            save(to_rgba(A.to_platecarree(a, nside, GW, GH), vmin, vmax, log, cmap), os.path.join(d, f"{nm}_global.png"))
            for tag, north in (("north", True), ("south", False)):
                lon, lat, inside = polar_lonlat(north)
                s = sample_healpix(a, nside, lon, lat); s[~inside] = np.nan
                save(to_rgba(s, vmin, vmax, log, cmap), os.path.join(d, f"{nm}_{tag}.png"))
            e = man.get(f"{body}_{nm}", {})
            entry["layers"].append(dict(
                name=nm, label=label, units=units.split(" (")[0], scale="log10" if log else "linear",
                vmin=float(vmin), vmax=float(vmax), colormap=cmap,
                files=dict(**{"global": f"{body}/{nm}_global.png", "north_polar": f"{body}/{nm}_north.png", "south_polar": f"{body}/{nm}_south.png"}),
                modelled=bool(e.get("modelled", False)),
                weak=bool("weak_dimension_mars" in e or "weak_dimension_moon" in e or nm in ("SiO2", "FeO")),
                coverage_pct=round(100.0 * float(np.isfinite(a).mean()), 2),
                stands_for={"roughness_21km": "terrain texture: slope and the four roughness scales",
                            "tpi_21km": "terrain form: TPI 21 km and 7 km", "svf_30km": "openness",
                            "temp_level": "temperature level", "temp_range_diurnal": "diurnal temperature range",
                            "SiO2": "composition: SiO2 and FeO"}[nm]))
            print(f"    {body} {nm}: {vmin:.3g}..{vmax:.3g} {'log' if log else 'lin'}", flush=True)
        out["bodies"][body] = entry

    # ---- catalogues
    cd = os.path.join(OUT, "catalogue"); os.makedirs(cd, exist_ok=True)

    def geojson(features):
        return dict(type="FeatureCollection", features=features)

    def pt(lon, lat, props):
        return dict(type="Feature", geometry=dict(type="Point", coordinates=[round(float(lon), 5), round(float(lat), 5)]), properties=props)

    rows = list(csv.DictReader(io.open(os.path.join(C.ROOT, "sources", "tier4_catalogues", "known_analog_sites_v2.csv"), encoding="utf-8")))
    feats = [pt(r["lon"], r["lat"], dict(name=r["name"], analog_for=r["body"], what_it_analogs=r["what_it_analogs"], source=r["source"],
                                         coord_verified=r["coord_verified"])) for r in rows if r["lat"].strip() and r["lon"].strip()]
    io.open(os.path.join(cd, "known_analog_sites.geojson"), "w", encoding="utf-8").write(json.dumps(geojson(feats), ensure_ascii=False))
    out["catalogue"]["known_analog_sites"] = dict(file="catalogue/known_analog_sites.geojson", body="earth", n=len(feats),
                                                  n_without_coordinates=len(rows) - len(feats),
                                                  use="second map layer and the known / new label (100 km); a label, never a filter")
    rows = list(csv.DictReader(io.open(os.path.join(C.ROOT, "sources", "tier4_catalogues", "lunar_analog_sites.csv"), encoding="utf-8")))
    feats = [pt(r["lon"], r["lat"], dict(name=r["name"], reason=r["reason"], citation=r["citation"], lunar_attribution=r["lunar_attribution"])) for r in rows]
    io.open(os.path.join(cd, "apollo_training_sites.geojson"), "w", encoding="utf-8").write(json.dumps(geojson(feats), ensure_ascii=False))
    out["catalogue"]["apollo_training_sites"] = dict(file="catalogue/apollo_training_sites.geojson", body="earth", n=len(feats),
                                                     use="second positive control for lunar targets")
    # Preset targets: read from contract/targets_<body>.json (build/targets.py),
    # the one place that says which pixels a target is. Replaced the IAU-centre
    # placeholders on 10 Nov 2026.
    for body, fname in (("moon", "targets_moon_artemis3.geojson"), ("mars", "targets_mars.geojson")):
        tp = os.path.join(C.ROOT, "contract", f"targets_{body}.json")
        key = "targets_moon_artemis3" if body == "moon" else "targets_mars"
        if not os.path.exists(tp):
            out["catalogue"][key] = dict(file=None, body=body, n=0, caveat="PENDING: run build/targets.py")
            continue
        td = json.load(io.open(tp, encoding="utf-8"))
        feats = []
        for t in td["targets"]:
            g = t["geometry"]
            props = dict(name=t["name"], geometry_type=g["type"], area_km2=g["area_km2"], cells=t["cells"],
                         dims_available=t["dims_available"], source_kind=t["source_kind"],
                         geometry_source=t["geometry_source"], source_url=t["source_url"], notes=t["notes"])
            if g["type"] == "disc":
                props["radius_km"] = g["radius_km"]
            else:
                props["vertices_lonlat"] = g["vertices_lonlat"]
            for extra in ("kind", "selection_basis", "ez_radius_km"):
                if extra in t:
                    props[extra] = t[extra]
            feats.append(pt(t["center_lon"], t["center_lat"], props))
        io.open(os.path.join(cd, fname), "w", encoding="utf-8").write(json.dumps(geojson(feats), ensure_ascii=False))
        out["catalogue"][key] = dict(
            file="catalogue/" + fname, body=body, n=len(feats),
            use="preset targets; pixel sets and data coverage are in contract/targets_%s.json" % body,
            caveat="Points with a radius or polygon in the properties. Draw the shape from the properties, not a fixed marker size.")
    io.open(os.path.join(OUT, "layers.json"), "w", encoding="utf-8").write(json.dumps(out, indent=1, ensure_ascii=False))
    size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(OUT) for f in fs)
    print(f"wrote {OUT}: {size/2**20:.0f} MB, {(time.perf_counter()-t0)/60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
