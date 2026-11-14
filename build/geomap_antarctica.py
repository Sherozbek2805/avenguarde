"""
ANTARCTIC OUTCROP LITHOLOGY FROM SCAR GeoMAP -- B31.

    python -I build/geomap_antarctica.py [--test]

SOURCE
    Cox S.C. et al. (2023) SCAR GeoMAP v.2022-08, PANGAEA,
    doi:10.1594/PANGAEA.951482, CC-BY-4.0. 99,080 polygons of exposed rock
    and surficial deposits, compiled at 1:250,000, EPSG:3031.
    Paper: Cox et al. (2023) Sci. Data 10, 250, doi:10.1038/s41597-023-02152-9.

WHY
    GLiM covers Antarctica from a continental-scale source. GeoMAP is the
    dedicated compilation of what is actually exposed there. Where GeoMAP
    maps rock inside a HEALPix pixel, it describes that pixel's rock better
    than GLiM does.

METHOD -- the same convention as build/lithology.py, never a second one
    CATEGORICAL, so MAJORITY VOTE by true area. Polygons are rasterised at
    100 m in EPSG:3031 in 400 km tiles. No intermediate raster is written.
    Each 100 m cell contributes its TRUE ground area: the polar stereographic
    grid inflates area by k^2, and k depends on latitude, so every cell is
    weighted by 1/k^2. The winning LITHCODE per pixel is stored and its share
    of the classified area is the support.

    The vote runs over polygons with a KNOWN lithology: POLYGTYPE rock or
    moraine, LITHCODE not '?'. 'ice' polygons are seasonal water and refrozen
    melt, not rock, and never vote. Unknown rock ('?') is counted and
    reported but cannot win, because it has no composition.

OUTPUT (cube/healpix, Nside 1024 nested)
    earth_geomap_lithcode       uint8   winning LITHCODE as its ASCII code, 0 none
    earth_geomap_simpcode       uint8   winning SIMPCODE (10..70), 0 none
    earth_geomap_support        float32 winning LITHCODE share of classified area
    earth_geomap_rock_fraction  float32 (rock + moraine) true area / pixel area

GATES, stated before running
    G1  rasterised PLANAR area per POLYGTYPE within 2% of the polygon planar
        area summed from the geometries themselves
    G2  every pixel that receives data lies south of 53 S
        CORRECTION, 10 Nov: the gate was first stated as "south of 60 S" and
        FAILED on the first run (northernmost pixel -53.96). The premise was
        wrong, not the data: GeoMAP includes South Georgia (1,285 polygons,
        source Curtis 2011a, 54-55 S). The failed run wrote nothing. The gate
        is restated at 53 S and the first failure is kept in the summary.
    G3  rock fraction <= 1.02 everywhere
    G4  the analytic area scale agrees with pyproj's to 1e-6 at three latitudes
"""

import argparse
import io
import json
import os
import sys
import time
import zipfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

SRC_DIR = os.path.join(C.ROOT, "sources", "geomap")
ZIP = os.path.join(SRC_DIR, "ATA_SCAR_GeoMAP_v2022_08_QGIS.zip")
ZIP_MD5 = "b955696dd8ad5fce4ee514d362787db9"      # from the PANGAEA record
MEMBER = "ATA_SCAR_GeoMAP_v2022_08_QGIS/Data/ATA_SCAR_GeoMAP_Geology_v2022_08.gpkg"
EXTRACT = os.path.join(SRC_DIR, "extracted")
GPKG = os.path.join(EXTRACT, "ATA_SCAR_GeoMAP_Geology_v2022_08.gpkg")
LAYER = "ATA_GeoMAP_geological_units_v2022_08"
HP = os.path.join(C.ROOT, "cube", "healpix")
NSIDE = 1024
CELL = 100.0
TILE = 4000
A_WGS, F_WGS = 6378137.0, 1.0 / 298.257223563
LAT_TS = -71.0


def md5(path):
    import hashlib
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def extract():
    if os.path.exists(GPKG):
        return
    got = md5(ZIP)
    if got != ZIP_MD5:
        raise SystemExit(f"zip md5 {got} != PANGAEA {ZIP_MD5}")
    os.makedirs(EXTRACT, exist_ok=True)
    with zipfile.ZipFile(ZIP) as z:
        if MEMBER not in z.namelist():
            raise SystemExit("gpkg member not found in the zip")
        tmp = GPKG + ".part"
        with z.open(MEMBER) as src, open(tmp, "wb") as dst:
            for b in iter(lambda: src.read(1 << 22), b""):
                dst.write(b)
        os.replace(tmp, GPKG)
    print(f"extracted {os.path.getsize(GPKG):,} bytes")


def k_polar(lat_deg):
    """Point scale factor of EPSG:3031 (polar stereographic, true at 71 S)."""
    e = np.sqrt(F_WGS * (2.0 - F_WGS))
    phi = np.radians(np.abs(lat_deg))

    def m(p):
        return np.cos(p) / np.sqrt(1.0 - (e * np.sin(p)) ** 2)

    def t(p):
        s = e * np.sin(p)
        return np.tan(np.pi / 4.0 - p / 2.0) / ((1.0 - s) / (1.0 + s)) ** (e / 2.0)

    pts = np.radians(abs(LAT_TS))
    with np.errstate(invalid="ignore", divide="ignore"):
        k = (m(pts) / t(pts)) * t(phi) / m(phi)
    return k


def geom_planar_area(g):
    """Shoelace area of a GeoJSON Polygon / MultiPolygon, m^2."""
    def ring(r):
        a = np.asarray(r, dtype=np.float64)
        x, y = a[:, 0], a[:, 1]
        return 0.5 * abs(np.dot(x[:-1], y[1:]) - np.dot(x[1:], y[:-1]))

    def poly(p):
        return ring(p[0]) - sum(ring(h) for h in p[1:])

    if g["type"] == "Polygon":
        return poly(g["coordinates"])
    return sum(poly(p) for p in g["coordinates"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="census and gates only")
    a = ap.parse_args()

    import fiona
    import pyproj
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    from astropy_healpix import HEALPix
    from astropy import units as u

    t0 = time.perf_counter()
    print("=" * 78)
    print("B31 -- ANTARCTIC OUTCROP LITHOLOGY FROM SCAR GeoMAP")
    print("=" * 78)
    C.require_disk(3.0, C.ROOT)
    extract()

    # G4 -- analytic scale against pyproj
    pj = pyproj.Proj("EPSG:3031")
    for la in (-62.0, -77.5, -89.0):
        want = pj.get_factors(30.0, la).areal_scale
        got = float(k_polar(la)) ** 2
        if abs(want - got) > 1e-6:
            raise SystemExit(f"G4 FAIL at {la}: pyproj {want} analytic {got}")
    print("G4 pass: analytic area scale agrees with pyproj at -62, -77.5, -89")

    # ---- census: vocabulary and planar area from the geometries
    with fiona.open(GPKG, layer=LAYER) as src:
        crs = src.crs
        bounds = src.bounds
        n_feat = len(src)
        fields = list(src.schema["properties"].keys())
        print(f"{n_feat:,} features, CRS {crs}, bounds {tuple(round(b) for b in bounds)}")
        need = ("POLYGTYPE", "LITHCODE", "SIMPCODE")
        up = {f.upper(): f for f in fields}
        miss = [n for n in need if n not in up]
        if miss:
            raise SystemExit(f"fields missing {miss}; have {fields}")
        fP, fL, fS = (up[n] for n in need)
        vocab, planar, desc = {}, {}, {}
        fD = up.get("SIMPDESC")
        for f in src:
            p = f["properties"]
            key = ((p.get(fP) or "").strip().lower(), (p.get(fL) or "").strip(),
                   int(p.get(fS) or 0))
            if key not in vocab:
                vocab[key] = len(vocab)
            g = f["geometry"]
            if g is not None:
                planar[key] = planar.get(key, 0.0) + geom_planar_area(
                    g.__geo_interface__ if hasattr(g, "__geo_interface__") else g)
            if fD and key[2] not in desc:
                desc[key[2]] = (p.get(fD) or "").strip()
    K = len(vocab)
    inv = {v: k for k, v in vocab.items()}
    by_type = {}
    for k_, v in planar.items():
        by_type[k_[0]] = by_type.get(k_[0], 0.0) + v
    print(f"{K} distinct (POLYGTYPE, LITHCODE, SIMPCODE) classes "
          f"({time.perf_counter()-t0:.0f} s)")
    for tname, v in sorted(by_type.items()):
        print(f"   polygon planar area  {tname or '(blank)':8s} {v/1e6:12,.0f} km2")
    if a.test:
        print("TEST MODE -- nothing rasterised, nothing written")
        return 0

    hp = HEALPix(nside=NSIDE, order="nested")
    npix = int(hp.npix)
    to_ll = pyproj.Transformer.from_crs("EPSG:3031", "EPSG:4326", always_xy=True)
    x_lo = np.floor(bounds[0] / (TILE * CELL)) * TILE * CELL
    y_lo = np.floor(bounds[1] / (TILE * CELL)) * TILE * CELL
    nx = int(np.ceil((bounds[2] - x_lo) / (TILE * CELL)))
    ny = int(np.ceil((bounds[3] - y_lo) / (TILE * CELL)))
    print(f"tiles {nx} x {ny} of {TILE} cells at {CELL:.0f} m")

    pairs = []
    ras_planar = np.zeros(K)
    n_tiles = 0
    with fiona.open(GPKG, layer=LAYER) as src:
        for iy in range(ny):
            for ix in range(nx):
                x0 = x_lo + ix * TILE * CELL
                y0 = y_lo + iy * TILE * CELL
                bbox = (x0, y0, x0 + TILE * CELL, y0 + TILE * CELL)
                shapes = []
                for f in src.filter(bbox=bbox):
                    g = f["geometry"]
                    if g is None:
                        continue
                    p = f["properties"]
                    key = ((p.get(fP) or "").strip().lower(),
                           (p.get(fL) or "").strip(), int(p.get(fS) or 0))
                    shapes.append((g.__geo_interface__ if hasattr(
                        g, "__geo_interface__") else g, vocab[key] + 1))
                if not shapes:
                    continue
                n_tiles += 1
                tr = from_origin(x0, y0 + TILE * CELL, CELL, CELL)
                ras = rasterize(shapes, out_shape=(TILE, TILE), transform=tr,
                                fill=0, dtype=np.int32)
                rr, cc = np.nonzero(ras)
                if rr.size == 0:
                    continue
                cls = (ras[rr, cc] - 1).astype(np.int64)
                ras_planar += np.bincount(cls, minlength=K) * CELL * CELL
                x = x0 + (cc + 0.5) * CELL
                y = y0 + TILE * CELL - (rr + 0.5) * CELL
                lon, lat = to_ll.transform(x, y)
                idx = hp.lonlat_to_healpix(lon * u.deg, lat * u.deg).astype(np.int64)
                wt = CELL * CELL / k_polar(lat) ** 2
                key = idx * K + cls
                o = np.argsort(key, kind="stable")
                uk, st = np.unique(key[o], return_index=True)
                pairs.append((uk, np.add.reduceat(wt[o], st)))
                del ras, rr, cc, cls, x, y, lon, lat, idx, wt, key, o
            print(f"   row {iy+1}/{ny}  tiles with data {n_tiles}  "
                  f"{(time.perf_counter()-t0)/60:5.1f} min", flush=True)

    allk = np.concatenate([p[0] for p in pairs])
    allw = np.concatenate([p[1] for p in pairs])
    o = np.argsort(allk, kind="stable")
    uk, st = np.unique(allk[o], return_index=True)
    uw = np.add.reduceat(allw[o], st)
    pix = uk // K
    cls = uk % K
    print(f"{uk.size:,} distinct (pixel, class) pairs over "
          f"{np.unique(pix).size:,} pixels")

    # ---- G1
    ras_type = {}
    for c in range(K):
        ras_type[inv[c][0]] = ras_type.get(inv[c][0], 0.0) + ras_planar[c]
    g1 = {}
    for tname, v in by_type.items():
        r = ras_type.get(tname, 0.0)
        g1[tname or "(blank)"] = dict(polygon_km2=round(v / 1e6, 1),
                                      raster_km2=round(r / 1e6, 1),
                                      ratio=round(r / v, 5) if v else None)
        print(f"   G1 {tname or '(blank)':8s} polygons {v/1e6:10,.0f} km2  "
              f"raster {r/1e6:10,.0f} km2  ratio {r/v:.4f}")
    g1_pass = all(abs(d["ratio"] - 1.0) <= 0.02 for d in g1.values() if d["ratio"])
    print("G1", "pass" if g1_pass else "FAIL")

    # ---- per-pixel sums
    ptype = np.array([inv[c][0] for c in range(K)])
    lcode = np.array([inv[c][1] for c in range(K)])
    scode = np.array([inv[c][2] for c in range(K)])
    is_rock = (ptype == "rock") | (ptype == "moraine")
    known = is_rock & (lcode != "?") & (lcode != "")
    pix_area = 4.0 * np.pi * C.BODY_RADIUS_M["earth"] ** 2 / npix

    rock_area = np.bincount(pix[is_rock[cls]], weights=uw[is_rock[cls]],
                            minlength=npix)
    frac = (rock_area / pix_area).astype(np.float32)

    def vote(labels):
        """winner of a per-pixel majority vote over 'known' classes."""
        m = known[cls]
        lab_ids, lab_inv = np.unique(labels, return_inverse=True)
        key = pix[m] * lab_ids.size + lab_inv[cls[m]]
        w = uw[m]
        o2 = np.argsort(key, kind="stable")
        k2, s2 = np.unique(key[o2], return_index=True)
        w2 = np.add.reduceat(w[o2], s2)
        p2 = k2 // lab_ids.size
        l2 = k2 % lab_ids.size
        up_, ps = np.unique(p2, return_index=True)
        gmax = np.maximum.reduceat(w2, ps)
        gsum = np.add.reduceat(w2, ps)
        gid = np.repeat(np.arange(up_.size), np.diff(np.append(ps, k2.size)))
        first = np.minimum.reduceat(
            np.where(w2 == gmax[gid], np.arange(k2.size), k2.size), ps)
        return up_, lab_ids[l2[first]], gmax / gsum, gsum

    up_, win_l, share, classified = vote(lcode)
    lith = np.zeros(npix, dtype=np.uint8)
    lith[up_] = np.array([ord(c) for c in win_l], dtype=np.uint8)
    sup = np.full(npix, np.nan, dtype=np.float32)
    sup[up_] = share.astype(np.float32)
    us_, win_s, _, _ = vote(scode)
    simp = np.zeros(npix, dtype=np.uint8)
    simp[us_] = win_s.astype(np.uint8)

    lat_hp = C.healpix_lat(NSIDE)
    has = frac > 0
    g2_pass = bool(np.all(lat_hp[has] < -53.0))
    n_north_60 = int(np.sum(has & (lat_hp >= -60.0)))
    g3_pass = bool(frac.max() <= 1.02)
    print(f"G2 {'pass' if g2_pass else 'FAIL'}: northernmost pixel with data "
          f"{lat_hp[has].max():.2f}")
    print(f"G3 {'pass' if g3_pass else 'FAIL'}: max rock fraction {frac.max():.4f}")

    true_km2 = {}
    for c in range(K):
        true_km2[inv[c][0]] = true_km2.get(inv[c][0], 0.0) + float(
            uw[cls == c].sum()) / 1e6
    lc_area = {}
    for c in range(K):
        if is_rock[c]:
            lc_area[inv[c][1] or "(blank)"] = lc_area.get(
                inv[c][1] or "(blank)", 0.0) + float(uw[cls == c].sum()) / 1e6
    win_counts = {chr(k_): int(v) for k_, v in zip(
        *np.unique(lith[lith > 0], return_counts=True))}

    names = {
        "earth_geomap_lithcode": (lith, "winning GeoMAP LITHCODE, ASCII code; 0 none"),
        "earth_geomap_simpcode": (simp, "winning GeoMAP SIMPCODE (10..70); 0 none"),
        "earth_geomap_support": (sup, "winning LITHCODE share of the classified true area (0..1)"),
        "earth_geomap_rock_fraction": (frac, "(rock + moraine) true area / pixel area"),
    }
    summary = dict(
        source="SCAR GeoMAP v.2022-08, Cox et al. (2023), doi:10.1594/PANGAEA.951482, CC-BY-4.0",
        zip_md5=ZIP_MD5, features=n_feat, classes=K, cell_m=CELL,
        aggregation="majority vote by TRUE area (planar cell area / k^2)",
        gates=dict(G1=g1, G1_pass=g1_pass, G2_pass=g2_pass, G3_pass=g3_pass,
                   G4_pass=True,
                   G2_gate="every pixel with data south of 53 S",
                   G2_first_statement_failed=(
                       "stated as south of 60 S; failed, northernmost pixel "
                       "-53.96: GeoMAP includes South Georgia. Restated, "
                       "nothing was written by the failed run."),
                   pixels_with_data_north_of_60S=n_north_60),
        true_area_km2_by_polygtype={k_: round(v, 1) for k_, v in true_km2.items()},
        true_area_km2_by_lithcode={k_: round(v, 1) for k_, v in sorted(lc_area.items())},
        pixels_with_any_rock=int(has.sum()),
        pixels_with_classified_winner=int((lith > 0).sum()),
        pixels_rock_fraction_gt_0p5=int((frac > 0.5).sum()),
        winning_lithcode_pixels=win_counts,
        support_p10_p50_p90=[round(float(q), 4) for q in np.nanpercentile(sup, [10, 50, 90])],
        simpcode_descriptions={str(k_): v for k_, v in sorted(desc.items())},
        elapsed_s=round(time.perf_counter() - t0, 1))
    if not (g1_pass and g2_pass and g3_pass):
        print("A GATE FAILED -- nothing written")
        print(json.dumps(summary["gates"], indent=1))
        return 1

    for key, (arr, units) in names.items():
        path = os.path.join(HP, f"{key}_nside{NSIDE}.npy")
        C.atomic_save(path, arr)
        valid = np.isfinite(arr) if arr.dtype.kind == "f" else (arr > 0)
        C.manifest_write(key, dict(
            file=f"cube/healpix/{key}_nside{NSIDE}.npy", nside=NSIDE,
            order="nested", dtype=str(arr.dtype), n_pixels=int(arr.size),
            phase="3g", body="earth", variable=key.replace("earth_", ""),
            units=units,
            role=("diagnostic: exposed-rock fraction of the pixel"
                  if key.endswith("rock_fraction")
                  else "filter and composition route"),
            matching_eligible=False, nodata=(None if arr.dtype.kind == "f" else 0),
            **({"support_file":
                f"cube/healpix/earth_geomap_support_nside{NSIDE}.npy"}
               if key.endswith("code") else {}),
            built_by="build/geomap_antarctica.py",
            source=summary["source"],
            source_files=["sources/geomap/ATA_SCAR_GeoMAP_v2022_08_QGIS.zip"],
            binning=("MAJORITY VOTE by true area, rasterised at 100 m in "
                     "EPSG:3031 with each cell weighted by 1/k^2; no "
                     "intermediate raster written"),
            what_it_feeds=("earth_SiO2 and earth_FeO south of 60 S, through "
                           "sources/geomap_composition_lookup.csv; the "
                           "lithology shown for an Antarctic site in step 9. "
                           "It never ranks."),
            summary_file="cube/healpix/geomap_summary.json",
            validation=dict(n_valid=int(valid.sum()), gates_pass=True),
            built_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
        print(f"wrote {key}: valid {int(valid.sum()):,}")
    with io.open(os.path.join(HP, "geomap_summary.json"), "w",
                 encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)
    print(json.dumps({k_: summary[k_] for k_ in (
        "true_area_km2_by_polygtype", "pixels_with_any_rock",
        "pixels_with_classified_winner", "pixels_rock_fraction_gt_0p5",
        "winning_lithcode_pixels", "support_p10_p50_p90")}, indent=1))
    print(f"done in {(time.perf_counter()-t0)/60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
