"""
DECISION 3 -- lithology from the LiMW vector, and the water mask with it.

    python build/lithology.py [--bands N] [--test]

WHY THE VECTOR AND NOT THE 0.5-DEGREE RASTER
    Median polygon 3.01 km, finer than the 6.37 km HEALPix pixel. The raster
    is 55 km, 76x coarser by area, and yields only 13 distinct values over the
    whole planet. Measured, not assumed.

CATEGORICAL, SO MAJORITY VOTE -- the mean accumulator is WRONG here.
    Per (pixel, class) weights are accumulated, then the winning class is
    taken per pixel and the WINNING SHARE is reported as support, because a
    30% plurality and a 95% majority are not the same measurement.

    The count arrays are NOT materialised as 434 x npix, which would be 11 GB.
    Instead each band reduces to compact (pixel*K + class -> weight) pairs via
    np.unique, and the bands are merged. A HEALPix pixel holds only a handful
    of distinct lithologies, so the final table is ~25M pairs, not 5.5G cells.

NO INTERMEDIATE IS WRITTEN. The 1/240 degree rasterisation exists only inside
the band loop, exactly as in phase 2. Output is 12 MB, not 3.48 GiB.

THE WATER MASK IS REBUILT IN THE SAME PASS.
    wb polygons come from this same vector at 3 km rather than from the 55 km
    raster, so the provisional raster mask is deleted once this completes.
    ONE mask, ONE provenance, ONE filename -- three land masks on disk is how
    a project ends up with three definitions of the same thing.
"""

import argparse
import io
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C
from phase1_dems import DEM_DIR, peak_rss_gib, say_peak

GDB = os.path.join(C.ROOT, "LiMW_GIS 2015.gdb", "LiMW_GIS 2015.gdb")
LAYER = "GLiM_export"
SRC_CRS = "ESRI:54012"          # Eckert IV, equal area
OUT = os.path.join(C.ROOT, "cube", "healpix")
NSIDE = 1024
PPD = 240
H, W = 180 * PPD, 360 * PPD
EXCLUDE_XX = ("wb", "ig", "nd")


def flatten(coords, xs, ys, spans):
    """Walk a GeoJSON coordinate tree, appending x/y and recording structure."""
    if coords and isinstance(coords[0], (int, float)):
        xs.append(coords[0]); ys.append(coords[1])
        return 0
    n = len(coords)
    spans.append(n)
    for c in coords:
        flatten(c, xs, ys, spans)
    return n


def rebuild(coords, it):
    if coords and isinstance(coords[0], (int, float)):
        return next(it)
    return [rebuild(c, it) for c in coords]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bands", type=int, default=180)
    ap.add_argument("--test", action="store_true",
                    help="a few bands only, write nothing")
    ap.add_argument("--start", type=int, default=0,
                    help="first band index; polar bands are ocean")
    ap.add_argument("--ntest", type=int, default=3)
    a = ap.parse_args()

    import fiona
    import pyproj
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    from astropy_healpix import HEALPix
    from astropy import units as u

    print("=" * 78)
    print("DECISION 3 -- LITHOLOGY FROM THE LiMW VECTOR")
    print("=" * 78)
    C.require_disk(10.0, C.ROOT)

    # ---- class vocabulary, from the census of the whole layer
    t0 = time.perf_counter()
    with fiona.open(GDB, layer=LAYER) as src:
        n_feat = len(src)
        vocab = {}
        for f in src:
            L = (f["properties"].get("Litho") or "NULL").strip()
            if L not in vocab:
                vocab[L] = len(vocab)
    K = len(vocab)
    inv = {v: k for k, v in vocab.items()}
    print(f"{n_feat:,} features, {K} distinct Litho values "
          f"({time.perf_counter()-t0:.1f} s)")
    if K >= 1024:
        raise SystemExit("more classes than the key packing allows")

    hp = HEALPix(nside=NSIDE, order="nested")
    npix = int(hp.npix)
    fwd = pyproj.Transformer.from_crs("EPSG:4326", SRC_CRS, always_xy=True)
    inv_t = pyproj.Transformer.from_crs(SRC_CRS, "EPSG:4326", always_xy=True)

    lat_all = 90.0 - (np.arange(H) + 0.5) * (180.0 / H)
    lon_all = -180.0 + (np.arange(W) + 0.5) * (360.0 / W)

    ifl = np.load(os.path.join(DEM_DIR, "earth_ice_free_land_1_240deg.npy"),
                  mmap_mode="r")
    mask_out = None
    if not a.test:
        mp = os.path.join(DEM_DIR, "earth_land_reference_1_240deg.npy") + ".part"
        mask_out = np.lib.format.open_memmap(mp, mode="w+", dtype=np.uint8,
                                             shape=(H, W))

    rows_per_band = H // a.bands
    pairs = []
    wb_id = {i for L, i in vocab.items() if L[:2] == "wb"}
    t0 = time.perf_counter()
    n_poly_seen = 0
    blist = (range(a.bands) if not a.test
             else range(a.start, min(a.bands, a.start + a.ntest)))
    for b in blist:
        r0 = b * rows_per_band
        r1 = min(H, r0 + rows_per_band)
        lat_hi = 90.0 - r0 * (180.0 / H)
        lat_lo = 90.0 - r1 * (180.0 / H)
        # bbox in the SOURCE projection: Eckert IV is not cylindrical, so the
        # band's bounding box must be found by transforming its boundary, not
        # by transforming two corners.
        plon = np.linspace(-180, 180, 721)
        bx, by = [], []
        for la in (lat_lo, lat_hi, (lat_lo + lat_hi) / 2):
            x, y = fwd.transform(plon, np.full_like(plon, la))
            bx.append(x); by.append(y)
        bx = np.concatenate(bx); by = np.concatenate(by)
        bbox = (float(np.nanmin(bx)), float(np.nanmin(by)),
                float(np.nanmax(bx)), float(np.nanmax(by)))

        shapes = []
        wb_shapes = []
        with fiona.open(GDB, layer=LAYER) as src:
            for f in src.filter(bbox=bbox):
                g = f["geometry"]
                if g is None:
                    continue
                cid = vocab[(f["properties"].get("Litho") or "NULL").strip()]
                xs, ys, spans = [], [], []
                flatten(g["coordinates"], xs, ys, spans)
                if not xs:
                    continue
                lo, la = inv_t.transform(np.asarray(xs), np.asarray(ys))
                it = iter([(float(p), float(q)) for p, q in zip(lo, la)])
                geom = {"type": g["type"],
                        "coordinates": rebuild(g["coordinates"], it)}
                shapes.append((geom, cid + 1))        # 0 is "nothing"
                if cid in wb_id:
                    wb_shapes.append((geom, 1))
                n_poly_seen += 1

        tr = from_origin(-180.0, lat_hi, 1.0 / PPD, 1.0 / PPD)
        lith = rasterize(shapes, out_shape=(r1 - r0, W), transform=tr,
                         fill=0, dtype=np.int32) if shapes else \
            np.zeros((r1 - r0, W), dtype=np.int32)
        wbr = rasterize(wb_shapes, out_shape=(r1 - r0, W), transform=tr,
                        fill=0, dtype=np.uint8) if wb_shapes else \
            np.zeros((r1 - r0, W), dtype=np.uint8)

        if mask_out is not None:
            ib = np.asarray(ifl[r0:r1]) > 0
            mask_out[r0:r1] = (ib & (wbr == 0)).astype(np.uint8)
            del ib

        # ---- accumulate (pixel, class) weights, compactly
        good = lith > 0
        if good.any():
            la2 = np.repeat(lat_all[r0:r1], W).reshape(r1 - r0, W)
            lo2 = np.tile(lon_all, (r1 - r0, 1))
            idx = hp.lonlat_to_healpix(lo2[good] * u.deg,
                                       la2[good] * u.deg).astype(np.int64)
            cls = (lith[good] - 1).astype(np.int64)
            wt = np.cos(np.radians(la2[good]))
            key = idx * K + cls
            o = np.argsort(key, kind="stable")
            ks = key[o]
            ws = wt[o]
            uk, st = np.unique(ks, return_index=True)
            sums = np.add.reduceat(ws, st)
            pairs.append((uk, sums))
            del la2, lo2, idx, cls, wt, key, o, ks, ws
        del lith, wbr, good, shapes, wb_shapes

        if b % 10 == 0 or b == a.bands - 1:
            el = time.perf_counter() - t0
            done = b - (a.start if a.test else 0) + 1
            print(f"   band {done}/{a.bands}  lat {lat_lo:+6.1f}  "
                  f"{el/60:5.1f} min  eta "
                  f"{el/done*(a.bands-done)/60:5.1f} min  "
                  f"pairs {sum(p[0].size for p in pairs):,}", flush=True)
    say_peak("lithology band loop")

    if not pairs:
        print("NO POLYGONS IN THE BANDS PROCESSED -- polar bands are ocean; use --start to test over land.")
        return 0
    print(f"\nmerging {sum(p[0].size for p in pairs):,} partial pairs ...")
    allk = np.concatenate([p[0] for p in pairs])
    allw = np.concatenate([p[1] for p in pairs])
    del pairs
    o = np.argsort(allk, kind="stable")
    allk = allk[o]; allw = allw[o]
    uk, st = np.unique(allk, return_index=True)
    uw = np.add.reduceat(allw, st)
    del allk, allw, o
    print(f"  {uk.size:,} distinct (pixel, class) pairs")

    pix = (uk // K).astype(np.int64)
    cls = (uk % K).astype(np.int64)
    # Winning class per pixel. Pairs are sorted by key = pix*K + cls, so they
    # are already grouped by pixel. VECTORISED: a Python loop here would run
    # 12.6 million times and dominate the whole build.
    upix, pst = np.unique(pix, return_index=True)
    glen = np.diff(np.append(pst, uk.size))
    gmax = np.maximum.reduceat(uw, pst)
    gsum = np.add.reduceat(uw, pst)
    gid = np.repeat(np.arange(upix.size), glen)
    idxs = np.arange(uk.size)
    # first index attaining the group maximum, per group
    first = np.minimum.reduceat(np.where(uw == gmax[gid], idxs, uk.size), pst)
    win_c = np.full(npix, 65535, dtype=np.uint16)
    win_s = np.full(npix, np.nan, dtype=np.float32)
    win_c[upix] = cls[first].astype(np.uint16)
    with np.errstate(invalid="ignore", divide="ignore"):
        win_s[upix] = (gmax / np.where(gsum > 0, gsum, np.nan)).astype(np.float32)
    del gid, idxs, first, glen

    if a.test:
        print("TEST MODE -- nothing written")
        return 0

    mask_out.flush(); del mask_out
    final = os.path.join(DEM_DIR, "earth_land_reference_1_240deg.npy")
    os.replace(final + ".part", final)

    lvl1 = np.array([inv[c][:2] if c in inv else "??" for c in range(K)])
    l1vocab = sorted(set(lvl1))
    l1id = {t: i for i, t in enumerate(l1vocab)}
    l1_of_class = np.array([l1id[t] for t in lvl1], dtype=np.uint8)
    win_l1 = np.full(npix, 255, dtype=np.uint8)
    ok = win_c != 65535
    win_l1[ok] = l1_of_class[win_c[ok]]          # lookup, not a Python loop

    C.atomic_save(os.path.join(OUT, f"earth_lithology_l3_nside{NSIDE}.npy"),
                  win_c)
    C.atomic_save(os.path.join(OUT, f"earth_lithology_l1_nside{NSIDE}.npy"),
                  win_l1)
    C.atomic_save(os.path.join(OUT,
                               f"earth_lithology_support_nside{NSIDE}.npy"),
                  win_s)

    # ---- the FOURTH gate
    def tiestats(arr, valid):
        v = arr[valid]
        u2, c2 = np.unique(v, return_counts=True)
        return int(u2.size), float(c2.max() / c2.sum())

    excl_l1 = np.array([l1id[t] for t in EXCLUDE_XX if t in l1id],
                       dtype=np.uint8)
    land = ok & ~np.isin(win_l1, excl_l1)
    dl3, tf3 = tiestats(win_c, land)
    dl1, tf1 = tiestats(win_l1, land)
    print(f"\nFOURTH GATE (categorical)")
    print(f"  level-3: distinct_levels {dl3}, largest_tie_fraction {tf3:.4f}")
    print(f"  level-1: distinct_levels {dl1}, largest_tie_fraction {tf1:.4f}")
    print(f"  support (winning share): p1 {np.nanpercentile(win_s[land],1):.4f} "
          f"p25 {np.nanpercentile(win_s[land],25):.4f} "
          f"p50 {np.nanpercentile(win_s[land],50):.4f} "
          f"p75 {np.nanpercentile(win_s[land],75):.4f}")
    print(f"  pixels where the winner is a bare plurality (<0.50): "
          f"{int((win_s[land] < 0.5).sum()):,} of {int(land.sum()):,}")

    io.open(os.path.join(OUT, "lithology_summary.json"), "w",
            encoding="utf-8").write(json.dumps(dict(
                source="LiMW_GIS 2015.gdb / GLiM_export",
                features=n_feat, distinct_litho=K,
                aggregation="majority vote, cos(lat)-weighted",
                support_definition="winning class share of the pixel's weight",
                distinct_levels_l3=dl3, largest_tie_fraction_l3=tf3,
                distinct_levels_l1=dl1, largest_tie_fraction_l1=tf1,
                vocab={str(i): inv[i] for i in range(K)},
                l1vocab=l1vocab,
                elapsed_s=round(time.perf_counter() - t0, 1),
                peak_rss_gib=peak_rss_gib()), indent=1))
    print(f"\nwrote 3 HEALPix arrays and the land reference mask")
    return 0


if __name__ == "__main__":
    sys.exit(main())
