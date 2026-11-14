"""
PHASE 1b -- the ice mask, and ice-free land as the Earth reference population.

THE GAP THIS CLOSES
    The land mask is the WorldClim valid-data footprint, which is the right
    definition of "where Earth climate data exists". But WorldClim covers
    Antarctica and Greenland, so that mask INCLUDES both ice sheets. A step-3
    reference population containing two ice sheets would compute every Earth
    percentile over a population that is ~10 percent ice.

    ice           = (ETOPO 60s surface - ETOPO 60s bed) > threshold
    ice_free_land = land_mask AND NOT ice

BOTH GATES ON EVERY VALIDATION
    Phase 1 taught this the hard way: the Mars scale gate PASSED on a DEM that
    was 99.7 percent nodata. So every check here reports plausibility AND
    coverage, never one alone.

    python build/phase1b_ice.py
"""

import io
import json
import os
import sqlite3
import struct
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C
from phase1_dems import (DEM_DIR, DISK_FLOOR_GIB, GRIDS, PEAK_CAP_GIB,
                         CONVENTION_WARNING, SLOPE_CONVENTION, WINDOW_CONVENTION,
                         band_rows_for_width, finish_part, open_memmap_part,
                         peak_rss_gib, say_peak)

ROOT = C.ROOT
SURF = os.path.join(ROOT, "ETOPO_2022_v1_60s_N90W180_surface.tif")
BED = os.path.join(ROOT, "ETOPO_2022_v1_60s_N90W180_bed.tif")
SCAR = os.path.join(ROOT, "sources", "tier3_composition",
                    "add_rock_outcrop_high_res_polygon_v7_11.gpkg")

ICE_H, ICE_W = 10800, 21600          # 1/60 deg
H, W = GRIDS["earth"]["shape"]        # 1/240 deg
UPSAMPLE = 4                          # 1/60 -> 1/240, EXACT

THRESHOLDS = (5.0, 20.0, 50.0)
CHOSEN = 20.0

THRESHOLD_RATIONALE = (
    "surface minus bed is a difference of two float32 rasters, so it is not "
    "exactly zero over bare rock: a few metres of noise and of genuine "
    "surface-versus-bedrock disagreement (sediment, water bodies, build-up) are "
    "expected. A threshold of exactly 0 would therefore classify noise as ice. "
    "Ice sheets are hundreds to thousands of metres thick, so any threshold "
    "between a few metres and a few tens of metres separates them from noise by "
    "two orders of magnitude. 20 m is chosen as the middle of that range; the "
    "area at 5, 20 and 50 m is reported so the insensitivity is visible rather "
    "than asserted.")

# Region boxes for splitting the ice area. Deliberately crude and stated as
# such: the point is to confirm the two ice sheets dominate, not to delineate
# them.
REGIONS = {
    "antarctica": dict(lat=(-90.0, -60.0), lon=(-180.0, 180.0)),
    "greenland": dict(lat=(59.0, 84.0), lon=(-73.0, -11.0)),
}


def row_lat(h):
    cell = 180.0 / h
    return 90.0 - (np.arange(h) + 0.5) * cell


def col_lon(w):
    cell = 360.0 / w
    return -180.0 + (np.arange(w) + 0.5) * cell


# ---------------------------------------------------------------- thickness

def build_ice(force=False):
    import rasterio
    out60 = os.path.join(DEM_DIR, "_earth_ice_1_60deg.npy")
    thick_stats = {}
    if C.is_complete(out60, (ICE_H, ICE_W), "bool") and not force:
        print("  1/60 ice mask already present, reusing")
        return np.load(out60, mmap_mode="r"), {}, out60

    lat60 = row_lat(ICE_H)
    cosw = np.cos(np.radians(lat60))
    band = band_rows_for_width(ICE_W, 4, budget=256 * 2 ** 20)
    print(f"  thickness = surface - bed over {ICE_H}x{ICE_W}, bands of {band} rows")

    # area accumulators per threshold, plus per region
    area = {t: 0.0 for t in THRESHOLDS}
    area_reg = {t: {r: 0.0 for r in list(REGIONS) + ["other"]} for t in THRESHOLDS}
    area_total = 0.0
    area_land_total = 0.0
    neg_cells = 0
    n_valid = 0
    tsamp = []

    land = np.load(os.path.join(DEM_DIR, "earth_land_mask_1_240deg.npy"), mmap_mode="r")
    arr, part = open_memmap_part(out60, (ICE_H, ICE_W), np.bool_)
    lon60 = col_lon(ICE_W)
    t0 = time.perf_counter()
    nbytes = 0

    with rasterio.open(SURF) as ss, rasterio.open(BED) as sb:
        for r0 in range(0, ICE_H, band):
            r1 = min(ICE_H, r0 + band)
            s = ss.read(1, window=((r0, r1), (0, ICE_W)))
            b = sb.read(1, window=((r0, r1), (0, ICE_W)))
            nbytes += s.nbytes + b.nbytes
            good = (s > -1e30) & (b > -1e30) & np.isfinite(s) & np.isfinite(b)
            th = np.where(good, s - b, np.nan).astype(np.float32)
            n_valid += int(good.sum())
            neg_cells += int(np.sum(th < -1.0))
            # land fraction on the SAME 1/60 grid, by taking the 1/240 mask's
            # matching block -- used only for the "ice as a share of land" figure
            lm = np.asarray(land[r0 * UPSAMPLE:r1 * UPSAMPLE])
            lm60 = lm.reshape(r1 - r0, UPSAMPLE, ICE_W, UPSAMPLE).any(axis=(1, 3))
            wrow = cosw[r0:r1]
            area_total += float(ICE_W * wrow.sum())
            area_land_total += float((lm60.sum(axis=1) * wrow).sum())
            for t in THRESHOLDS:
                ice = good & (th > t)
                area[t] += float((ice.sum(axis=1) * wrow).sum())
                for rname, box in REGIONS.items():
                    rm = (lat60[r0:r1] >= box["lat"][0]) & (lat60[r0:r1] <= box["lat"][1])
                    if not rm.any():
                        continue
                    cm = (lon60 >= box["lon"][0]) & (lon60 <= box["lon"][1])
                    sub = ice[rm][:, cm]
                    area_reg[t][rname] += float((sub.sum(axis=1) * wrow[rm]).sum())
                area_reg[t]["other"] += float((ice.sum(axis=1) * wrow).sum())
            arr[r0:r1] = good & (th > CHOSEN)
            if (r0 // band) % 4 == 0:
                arr.flush()
                el = time.perf_counter() - t0
                print(f"    {r1}/{ICE_H} rows  {el/60:.1f} min  "
                      f"{nbytes/2**20/max(el,1e-9):.0f} MB/s", flush=True)
            s2 = th[good][::997]
            if s2.size:
                tsamp.append(s2.copy())
            del s, b, good, th, lm, lm60
    arr.flush()
    del arr
    finish_part(part, out60)
    el = time.perf_counter() - t0
    say_peak("ice thickness")

    for t in THRESHOLDS:
        area_reg[t]["other"] -= area_reg[t]["antarctica"] + area_reg[t]["greenland"]

    ts = np.concatenate(tsamp) if tsamp else np.array([0.0], dtype=np.float32)
    thick_stats = dict(
        n_valid=n_valid,
        percent_valid=round(100.0 * n_valid / (ICE_H * ICE_W), 4),
        negative_thickness_cells=neg_cells,
        negative_note=("surface < bed by more than 1 m should not happen; a nonzero "
                       "count means the two products disagree somewhere and is "
                       "reported rather than clipped away"),
        thickness_sample_n=int(ts.size),
        thickness_p50=float(np.percentile(ts, 50)),
        thickness_p99=float(np.percentile(ts, 99)),
        thickness_max=float(ts.max()),
        area_fraction_by_threshold={
            str(t): dict(
                percent_of_earth_area=round(100.0 * area[t] / area_total, 4),
                percent_of_land_area=round(100.0 * area[t] / area_land_total, 4),
                antarctica_pct_of_earth=round(100.0 * area_reg[t]["antarctica"] / area_total, 4),
                greenland_pct_of_earth=round(100.0 * area_reg[t]["greenland"] / area_total, 4),
                other_pct_of_earth=round(100.0 * area_reg[t]["other"] / area_total, 4),
            ) for t in THRESHOLDS},
        chosen_threshold_m=CHOSEN,
        threshold_rationale=THRESHOLD_RATIONALE,
        bytes_read=nbytes, elapsed_s=round(el, 1),
        throughput_MB_s=round(nbytes / 2 ** 20 / max(el, 1e-9), 1),
    )
    return np.load(out60, mmap_mode="r"), thick_stats, out60


# ------------------------------------------------------- ice-free land, 1/240

def build_ice_free(ice60, force=False):
    out = os.path.join(DEM_DIR, "earth_ice_free_land_1_240deg.npy")
    land_p = os.path.join(DEM_DIR, "earth_land_mask_1_240deg.npy")
    if C.is_complete(out, (H, W), "bool") and not force:
        print("  ice-free land mask already present, reusing")
    else:
        print(f"  upsampling the ice mask {UPSAMPLE}x NEAREST (it is a mask -- "
              f"never interpolated) and ANDing with NOT ice")
        land = np.load(land_p, mmap_mode="r")
        mm, part = open_memmap_part(out, (H, W), np.bool_)
        band = band_rows_for_width(ICE_W, 1, budget=128 * 2 ** 20)
        for r0 in range(0, ICE_H, band):
            r1 = min(ICE_H, r0 + band)
            ic = np.asarray(ice60[r0:r1])
            up = np.repeat(np.repeat(ic, UPSAMPLE, axis=0), UPSAMPLE, axis=1)
            lm = np.asarray(land[r0 * UPSAMPLE:r1 * UPSAMPLE])
            mm[r0 * UPSAMPLE:r1 * UPSAMPLE] = lm & ~up
            del ic, up, lm
            if (r0 // band) % 8 == 0:
                mm.flush()
        mm.flush()
        del mm
        finish_part(part, out)
        say_peak("ice-free land")

    m = np.load(out, mmap_mode="r")
    land = np.load(land_p, mmap_mode="r")
    lat = row_lat(H)
    cosw = np.cos(np.radians(lat))
    band = band_rows_for_width(W, 1, budget=256 * 2 ** 20)
    a_ifl = a_land = a_tot = 0.0
    n_ifl = 0
    for r0 in range(0, H, band):
        r1 = min(H, r0 + band)
        b = np.asarray(m[r0:r1])
        l = np.asarray(land[r0:r1])
        wr = cosw[r0:r1]
        n_ifl += int(b.sum())
        a_ifl += float((b.sum(axis=1) * wr).sum())
        a_land += float((l.sum(axis=1) * wr).sum())
        a_tot += float(W * wr.sum())
        del b, l
    return out, dict(
        shape=[H, W], dtype="bool", cells=n_ifl,
        percent_of_earth_by_cell=round(100.0 * n_ifl / (H * W), 4),
        percent_of_earth_by_area=round(100.0 * a_ifl / a_tot, 4),
        land_percent_of_earth_by_area=round(100.0 * a_land / a_tot, 4),
        ice_removed_pp_of_earth_area=round(100.0 * (a_land - a_ifl) / a_tot, 4),
        ice_as_percent_of_land_area=round(100.0 * (a_land - a_ifl) / a_land, 4),
    )


# ------------------------------------------- SCAR ADD cross-check (no shapely)

def gpkg_vertices(path, max_features=None, stride=1):
    """Polygon vertices from a GeoPackage, parsed directly.

    No vector library is installed (no geopandas, fiona, pyogrio or shapely), so
    the GeoPackage is read as what it is -- a SQLite database -- and the geometry
    blobs are unpacked by hand.

    GPKG blob = 'GP' magic | version | flags | srs_id(int32) | optional envelope
                | standard WKB
    The envelope length is encoded in flag bits 1..3, and the byte order in
    bit 0. The WKB that follows is an ordinary MultiPolygon.

    Returns (xs, ys, n_features, n_rings) in the layer's own CRS.
    """
    db = sqlite3.connect(path)
    cur = db.cursor()
    tbl = cur.execute(
        "SELECT table_name FROM gpkg_contents WHERE data_type='features'").fetchone()[0]
    gcol = cur.execute(
        "SELECT column_name FROM gpkg_geometry_columns WHERE table_name=?",
        (tbl,)).fetchone()[0]
    q = f'SELECT "{gcol}" FROM "{tbl}"'
    if max_features:
        q += f" LIMIT {int(max_features)}"
    ENV_LEN = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    xs, ys = [], []
    nfeat = nring = 0
    for (blob,) in cur.execute(q):
        if not blob or blob[:2] != b"GP":
            continue
        flags = blob[3]
        env = ENV_LEN.get((flags >> 1) & 0x07, 0)
        off = 8 + env
        wkb = blob[off:]
        bo = "<" if wkb[0] == 1 else ">"
        gtype = struct.unpack_from(bo + "I", wkb, 1)[0] & 0xFF
        p = 5
        polys = 1
        if gtype == 6:                                  # MultiPolygon
            polys = struct.unpack_from(bo + "I", wkb, p)[0]
            p += 4
        for _ in range(polys):
            if gtype == 6:
                p += 1                                   # per-polygon byte order
                p += 4                                   # per-polygon type (3)
            nrings = struct.unpack_from(bo + "I", wkb, p)[0]
            p += 4
            for _r in range(nrings):
                npts = struct.unpack_from(bo + "I", wkb, p)[0]
                p += 4
                if npts:
                    pts = np.frombuffer(wkb, dtype=bo + "f8", count=npts * 2, offset=p)
                    pts = pts.reshape(npts, 2)[::stride]
                    xs.append(pts[:, 0].copy())
                    ys.append(pts[:, 1].copy())
                p += npts * 16
                nring += 1
        nfeat += 1
    db.close()
    if not xs:
        return np.array([]), np.array([]), nfeat, nring
    return np.concatenate(xs), np.concatenate(ys), nfeat, nring


def scar_crosscheck(ice_free_path, land_path, stride=37):
    """Do SCAR exposed-rock outcrops fall inside ice_free_land?

    They are exposed Antarctic ROCK, so they should. Disagreement is
    informative either way, and the expected direction is known in advance:
    the ice mask is derived at 1/60 degree, about 1.85 km, while many outcrops
    are a few hundred metres across. A small outcrop surrounded by ice sits in a
    1.85 km cell that is mostly ice, so surface-minus-bed exceeds the threshold
    and the cell is called ice. SMALL OUTCROPS ARE THEREFORE EXPECTED TO BE
    MISSED, and the agreement rate measures the resolution limit rather than
    correctness.
    """
    from rasterio.warp import transform as warp_transform
    if not os.path.exists(SCAR):
        return dict(available=False,
                    reason="no SCAR ADD rock outcrop data on disk")
    t0 = time.perf_counter()
    x, y, nfeat, nring = gpkg_vertices(SCAR, stride=stride)
    if x.size == 0:
        return dict(available=False, reason="no geometries parsed")
    lon, lat = warp_transform("EPSG:3031", "EPSG:4326", x, y)
    lon = np.asarray(lon)
    lat = np.asarray(lat)
    keep = np.isfinite(lon) & np.isfinite(lat)
    lon, lat = lon[keep], lat[keep]

    ifl = np.load(ice_free_path, mmap_mode="r")
    land = np.load(land_path, mmap_mode="r")
    cell = 180.0 / H
    r = np.clip(((90.0 - lat) / cell).astype(np.int64), 0, H - 1)
    c = np.clip(((lon + 180.0) / (360.0 / W)).astype(np.int64), 0, W - 1)
    # sample row by row so the memmap is touched in order
    inside_ifl = np.zeros(r.size, dtype=bool)
    on_land = np.zeros(r.size, dtype=bool)
    order = np.argsort(r)
    for i in order:
        inside_ifl[i] = bool(ifl[r[i], c[i]])
        on_land[i] = bool(land[r[i], c[i]])
    n = int(r.size)
    return dict(
        available=True, source=os.path.relpath(SCAR, ROOT).replace("\\", "/"),
        crs_in="EPSG:3031", reprojected_to="EPSG:4326",
        n_features=nfeat, n_rings=nring, vertex_stride=stride,
        n_vertices_tested=n,
        pct_inside_ice_free_land=round(100.0 * int(inside_ifl.sum()) / n, 3),
        pct_on_land_mask=round(100.0 * int(on_land.sum()) / n, 3),
        pct_on_land_but_called_ice=round(
            100.0 * int((on_land & ~inside_ifl).sum()) / n, 3),
        pct_off_land_mask=round(100.0 * int((~on_land).sum()) / n, 3),
        elapsed_s=round(time.perf_counter() - t0, 1),
        interpretation=(
            "outcrops are exposed rock, so a high percentage inside "
            "ice_free_land is confirmation. The ice mask is built at 1/60 deg "
            "(~1.85 km) while many outcrops are a few hundred metres across, so "
            "small ones sit in cells that are mostly ice and are expected to be "
            "classified ice. The agreement rate therefore measures the "
            "resolution limit of the ice mask, not whether the mask is correct. "
            "Vertices are tested rather than filled polygons, because no "
            "geometry library is installed -- a weaker test, and stated as such."),
    )


# ----------------------------------------------------------------- the picture

def save_png(ice_free_path, land_path, ice60_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    f = 20                                   # 1/240 -> 1/12 deg, viewable
    oh, ow = H // f, W // f
    ifl = np.load(ice_free_path, mmap_mode="r")
    land = np.load(land_path, mmap_mode="r")
    cls = np.zeros((oh, ow), dtype=np.uint8)  # 0 ocean, 1 ice, 2 ice-free land
    for i in range(oh):
        lb = np.asarray(land[i * f:(i + 1) * f])
        ib = np.asarray(ifl[i * f:(i + 1) * f])
        lmaj = lb.reshape(f, ow, f).mean(axis=(0, 2)) > 0.5
        imaj = ib.reshape(f, ow, f).mean(axis=(0, 2)) > 0.5
        cls[i] = np.where(imaj, 2, np.where(lmaj, 1, 0))
    cmap = ListedColormap(["#0b2a4a", "#dfe9f3", "#6b8f3a"])
    fig, ax = plt.subplots(figsize=(16, 8))
    ax.imshow(cls, extent=(-180, 180, -90, 90), cmap=cmap, vmin=0, vmax=2,
              interpolation="nearest")
    ax.set_title("Earth reference population: ice-free land (green). "
                 "Ice sheets (pale) are EXCLUDED.\n"
                 "ice = ETOPO 60s surface - bed > 20 m; land = WorldClim 30s "
                 "valid-data footprint", fontsize=10)
    ax.set_xlabel("longitude"); ax.set_ylabel("latitude")
    ax.grid(alpha=0.25, linewidth=0.4)
    import matplotlib.patches as mp
    ax.legend(handles=[mp.Patch(color="#6b8f3a", label="ice-free land (reference population)"),
                       mp.Patch(color="#dfe9f3", label="land but ice-covered (excluded)"),
                       mp.Patch(color="#0b2a4a", label="not land")],
              loc="lower left", fontsize=8, framealpha=0.9)
    out = os.path.join(DEM_DIR, "earth_ice_free_land.png")
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return out


def main():
    print("=" * 78)
    print("PHASE 1b -- ICE MASK AND ICE-FREE LAND")
    print("=" * 78)
    print(f"\nfree disk {C.free_gib(ROOT):.1f} GiB   floor {DISK_FLOOR_GIB}")
    C.require_disk(DISK_FLOOR_GIB, ROOT)
    t0 = time.perf_counter()

    for p in (SURF, BED):
        if not os.path.exists(p):
            raise SystemExit(f"STOP: missing {p}")

    ice60, th, ice60_path = build_ice()
    if th:
        print(f"\n  --- thickness, both gates ---")
        print(f"    valid cells {th['percent_valid']}%   "
              f"negative(<-1 m) {th['negative_thickness_cells']:,}")
        print(f"    thickness p50 {th['thickness_p50']:.2f} m  "
              f"p99 {th['thickness_p99']:.1f} m  max {th['thickness_max']:.1f} m")
        print(f"\n    ICE AREA vs THRESHOLD (the sensitivity check)")
        print(f"      {'thresh':>8s} {'% Earth':>9s} {'% land':>8s} "
              f"{'Antarctica':>11s} {'Greenland':>10s} {'other':>8s}")
        for t in THRESHOLDS:
            a = th["area_fraction_by_threshold"][str(t)]
            print(f"      {t:7.0f}m {a['percent_of_earth_area']:9.4f} "
                  f"{a['percent_of_land_area']:8.3f} "
                  f"{a['antarctica_pct_of_earth']:11.4f} "
                  f"{a['greenland_pct_of_earth']:10.4f} "
                  f"{a['other_pct_of_earth']:8.4f}")
        lo = th["area_fraction_by_threshold"]["5.0"]["percent_of_earth_area"]
        hi = th["area_fraction_by_threshold"]["50.0"]["percent_of_earth_area"]
        print(f"    spread 5 m -> 50 m: {abs(lo-hi):.4f} pp of Earth's area "
              f"({100*abs(lo-hi)/max(lo,1e-9):.1f}% relative) -- "
              f"{'INSENSITIVE, choice is safe' if abs(lo-hi)/max(lo,1e-9) < 0.15 else 'SENSITIVE, revisit'}")

    land_p = os.path.join(DEM_DIR, "earth_land_mask_1_240deg.npy")
    ifl_path, ifl = build_ice_free(ice60)
    print(f"\n  --- ice-free land, both gates ---")
    print(f"    shape {ifl['shape']}  cells {ifl['cells']:,}")
    print(f"    land            {ifl['land_percent_of_earth_by_area']:.4f}% of Earth by area")
    print(f"    ICE-FREE LAND   {ifl['percent_of_earth_by_area']:.4f}% of Earth by area")
    print(f"    ice removed     {ifl['ice_removed_pp_of_earth_area']:.4f} pp "
          f"= {ifl['ice_as_percent_of_land_area']:.2f}% of land area")
    exp_lo, exp_hi = 24.0, 28.0
    ok = exp_lo <= ifl["percent_of_earth_by_area"] <= exp_hi
    print(f"    expectation ~26% (land 28.86% minus ~10% of land as ice) -> "
          f"{'PASS' if ok else 'OUT OF RANGE, investigate'}")

    sc = scar_crosscheck(ifl_path, land_p)
    print(f"\n  --- SCAR ADD rock-outcrop cross-check ---")
    if not sc.get("available"):
        print(f"    NOT AVAILABLE: {sc.get('reason')}")
    else:
        print(f"    {sc['n_features']:,} features, {sc['n_rings']:,} rings, "
              f"{sc['n_vertices_tested']:,} vertices tested (stride {sc['vertex_stride']})")
        print(f"    inside ice_free_land      {sc['pct_inside_ice_free_land']}%")
        print(f"    on the land mask at all   {sc['pct_on_land_mask']}%")
        print(f"    on land but called ice    {sc['pct_on_land_but_called_ice']}%")
        print(f"    off the land mask         {sc['pct_off_land_mask']}%")

    png = save_png(ifl_path, land_p, ice60_path)
    print(f"\n  wrote {os.path.relpath(png, ROOT)}")

    el = time.perf_counter() - t0
    C.manifest_write("earth_ice_free_land", dict(
        phase="1b", body="earth", variable="ice_free_land",
        units="boolean (True = ice-free land)",
        file=os.path.relpath(ifl_path, ROOT).replace("\\", "/"),
        png=os.path.relpath(png, ROOT).replace("\\", "/"),
        source_files=[os.path.relpath(SURF, ROOT), os.path.relpath(BED, ROOT),
                      "cube/dem/earth_land_mask_1_240deg.npy"],
        all_sources_resolve=all(os.path.exists(p) for p in (SURF, BED, land_p)),
        definition=("ice_free_land = land_mask AND NOT ice, where "
                    "ice = (ETOPO 60s surface - ETOPO 60s bed) > 20 m. This is the "
                    "step-3 Earth reference population: the land mask alone would "
                    "include the Antarctic and Greenland ice sheets, so every Earth "
                    "percentile would be computed over a population that is about a "
                    "tenth ice."),
        native_resolution="1/60 deg (10800x21600) for the ice term",
        working_resolution="1/240 deg (43200x86400)",
        resampling=("ice mask upsampled 1/60 -> 1/240 by EXACT 4x NEAREST "
                    "replication; it is a mask and is never interpolated"),
        threshold_m=CHOSEN, threshold_rationale=THRESHOLD_RATIONALE,
        nodata_rule=("a cell is ice only where BOTH surface and bed are valid; "
                     "where either is nodata the cell is not called ice"),
        thickness=th, ice_free=ifl, scar_crosscheck=sc,
        slope_convention=SLOPE_CONVENTION, window_convention=WINDOW_CONVENTION,
        convention_warning=CONVENTION_WARNING,
        tpi_sign_convention=C.TPI_SIGN_NOTE,
        validation_policy=("BOTH GATES: plausibility of values AND sufficiency of "
                           "coverage. Phase 1 showed the Mars scale gate passing on "
                           "a DEM that was 99.7 percent nodata."),
        peak_rss_gib=peak_rss_gib(), elapsed_s=round(el, 1),
        build_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))

    pk = peak_rss_gib()
    print(f"\n{'='*78}")
    print(f"PHASE 1b elapsed {el/60:.1f} min   peak RAM "
          f"{'unknown' if pk is None else f'{pk:.2f} GiB'} (cap {PEAK_CAP_GIB})")
    print(f"free disk {C.free_gib(ROOT):.1f} GiB")
    print("Continuing to Phase 2 (Moon) as instructed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
