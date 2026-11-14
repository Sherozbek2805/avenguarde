"""
Figures for the deck and the video -- AND a visual gate.

    python build/figures.py

Rendered from the DEMs this project built, not from any colorized source
image, so what a viewer sees is the data the engine actually consumes.

WHY THESE ARE A GATE, NOT DECORATION
    Phase 1 shipped a Mars DEM that was 99.68 percent nodata and the range
    gate passed it: the few thousand surviving cells had entirely plausible
    elevations. One glance at a hillshade would have shown it instantly.
    A statistic can pass on broken data; a picture of the whole globe cannot
    hide a hole in it.

WHAT A HILLSHADE HERE IS AND IS NOT
    The DEM is block-mean downsampled FIRST, then shaded. That is not the
    same product as shading at native resolution and then downsampling: this
    one shows relief at the displayed scale and suppresses everything finer.
    For a 4000 px global figure that is what you want, but it means these
    images must NOT be used to judge small-scale roughness.

    Vertical exaggeration is unavoidable and is stated. At 4320 px wide an
    Earth cell spans about 9.3 km, so true-scale relief would be invisible.
    The z-factor is recorded in the sidecar for every figure.
"""

import io
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C
from phase1_dems import DEM_DIR, GRIDS, peak_rss_gib, say_peak

ROOT = C.ROOT
FIG_DIR = os.path.join(ROOT, "docs", "figures")

SUN_AZIMUTH_DEG = 315.0          # from the north-west, the cartographic default
SUN_ALTITUDE_DEG = 45.0

# Integer downsample factors, chosen so the output lands near 4000 px wide
# without resampling artefacts. A non-integer factor would need interpolation
# and would blur the very discontinuities these figures exist to reveal.
PLAN = {
    "moon":  dict(file="moon_dem_1_64deg.npy",   factor=6,  z=12.0),
    "mars":  dict(file="mars_dem_1_128deg.npy",  factor=12, z=10.0),
    "earth": dict(file="earth_dem_1_240deg.npy", factor=20, z=14.0),
}


def downsample_mean(path, factor, band_rows=512):
    """Block-mean a memmapped DEM, NaN-aware, in bands."""
    a = np.load(path, mmap_mode="r")
    h, w = a.shape
    oh, ow = h // factor, w // factor
    out = np.full((oh, ow), np.nan, dtype=np.float32)
    step = max(1, band_rows // factor)
    for i0 in range(0, oh, step):
        i1 = min(oh, i0 + step)
        blk = np.asarray(a[i0 * factor:i1 * factor, :ow * factor],
                         dtype=np.float32)
        blk = blk.reshape(i1 - i0, factor, ow, factor)
        with np.errstate(invalid="ignore"):
            out[i0:i1] = np.nanmean(blk, axis=(1, 3))
        del blk
    return out, (h, w)


def hillshade(z, cell_m, az_deg, alt_deg, zf):
    """Standard hillshade. Longitude WRAPS, latitude CLIPS -- the same rule
    as everywhere else in this project, so the antimeridian shows no seam and
    the poles invent no neighbours."""
    zz = np.where(np.isfinite(z), z, np.nan) * zf
    # north-south: edge-replicate (clip)
    up = np.vstack([zz[:1], zz[:-1]])
    dn = np.vstack([zz[1:], zz[-1:]])
    # east-west: roll (wrap)
    lf = np.roll(zz, 1, axis=1)
    rt = np.roll(zz, -1, axis=1)
    with np.errstate(invalid="ignore"):
        dzdx = (rt - lf) / (2.0 * cell_m)
        dzdy = (dn - up) / (2.0 * cell_m)
        slope = np.arctan(np.hypot(dzdx, dzdy))
        aspect = np.arctan2(dzdy, -dzdx)
        zen = np.radians(90.0 - alt_deg)
        azm = np.radians(360.0 - az_deg + 90.0)
        hs = (np.cos(zen) * np.cos(slope) +
              np.sin(zen) * np.sin(slope) * np.cos(azm - aspect))
    hs = np.clip(hs, 0.0, 1.0)
    return hs


def to_png(path, rgb):
    from PIL import Image
    Image.fromarray(rgb, mode="RGB").save(path, optimize=True)


def shade_rgb(hs, z):
    """Grey hillshade, slightly tinted by elevation so a flat-but-high plain
    is distinguishable from a flat-but-low one. Nodata is rendered MAGENTA,
    deliberately: a hole must be impossible to mistake for terrain."""
    g = (np.nan_to_num(hs, nan=0.0) * 255.0).astype(np.uint8)
    rgb = np.dstack([g, g, g])
    v = np.isfinite(z)
    if v.any():
        lo, hi = np.nanpercentile(z[v], [2, 98])
        if hi > lo:
            t = np.clip((z - lo) / (hi - lo), 0, 1)
            warm = (30.0 * t).astype(np.int16)
            cool = (30.0 * (1.0 - t)).astype(np.int16)
            rgb[..., 0] = np.clip(rgb[..., 0].astype(np.int16) + warm, 0, 255)
            rgb[..., 2] = np.clip(rgb[..., 2].astype(np.int16) + cool, 0, 255)
    rgb[~v] = (255, 0, 255)
    return rgb


def sidecar(path, **kw):
    kw["written_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    io.open(path, "w", encoding="utf-8").write(
        json.dumps(kw, indent=1, ensure_ascii=False))


def relief(body, report):
    pl = PLAN[body]
    src = os.path.join(DEM_DIR, pl["file"])
    f, zf = pl["factor"], pl["z"]
    t0 = time.perf_counter()
    z, native = downsample_mean(src, f)
    oh, ow = z.shape
    cell_m = (180.0 / native[0]) * (np.pi * C.BODY_RADIUS_M[body] / 180.0) * f
    hs = hillshade(z, cell_m, SUN_AZIMUTH_DEG, SUN_ALTITUDE_DEG, zf)
    rgb = shade_rgb(hs, z)
    name = (f"{body}_shaded_relief_{ow}px_az{int(SUN_AZIMUTH_DEG)}"
            f"_alt{int(SUN_ALTITUDE_DEG)}_z{zf:g}.png")
    out = os.path.join(FIG_DIR, name)
    to_png(out, rgb)
    nodata = float(100.0 * (~np.isfinite(z)).sum() / z.size)
    sidecar(out.replace(".png", ".json"),
            figure=name, body=body,
            source=os.path.relpath(src, ROOT).replace("\\", "/"),
            native_shape=list(native), rendered_shape=[oh, ow],
            downsample_factor=f,
            downsample_method="NaN-aware block mean, then shade",
            displayed_cell_km=round(cell_m / 1000.0, 4),
            sun_azimuth_deg=SUN_AZIMUTH_DEG,
            sun_altitude_deg=SUN_ALTITUDE_DEG,
            vertical_exaggeration=zf,
            nodata_percent_at_display_scale=round(nodata, 6),
            nodata_colour="magenta (255, 0, 255)",
            edge_rule="longitude wraps, latitude clips",
            caveat=("Shaded AFTER downsampling, so relief finer than the "
                    "displayed cell is suppressed. Do not judge small-scale "
                    "roughness from this image."),
            purpose="deck/video figure AND visual validation gate")
    el = time.perf_counter() - t0
    print(f"  {body:6s} {ow} x {oh} px   displayed cell "
          f"{cell_m/1000:7.3f} km   z x{zf:g}   nodata {nodata:.6f}%   "
          f"{el:5.1f} s")
    print(f"         -> docs/figures/{name}")
    report[body] = dict(file=name, nodata_percent=round(nodata, 6),
                        shape=[oh, ow], displayed_cell_km=round(cell_m/1e3, 4),
                        hs_mean=round(float(np.nanmean(hs)), 4),
                        z_p2=round(float(np.nanpercentile(z, 2)), 1),
                        z_p98=round(float(np.nanpercentile(z, 98)), 1))
    del z, hs, rgb
    return report


def ice_free_figure(report):
    """Three classes, so a human can SEE that Antarctica and Greenland are out."""
    f = 20
    land_p = os.path.join(DEM_DIR, "earth_land_mask_1_240deg.npy")
    ifl_p = os.path.join(DEM_DIR, "earth_ice_free_land_1_240deg.npy")
    land = np.load(land_p, mmap_mode="r")
    ifl = np.load(ifl_p, mmap_mode="r")
    h, w = land.shape
    oh, ow = h // f, w // f
    # majority vote within each block, not a mean: these are categories
    cls = np.zeros((oh, ow), dtype=np.uint8)      # 0 ocean 1 ice 2 ice-free
    for i in range(oh):
        lb = np.asarray(land[i * f:(i + 1) * f, :ow * f]).reshape(f, ow, f)
        ib = np.asarray(ifl[i * f:(i + 1) * f, :ow * f]).reshape(f, ow, f)
        lf = (lb > 0).mean(axis=(0, 2))
        iff = (ib > 0).mean(axis=(0, 2))
        row = np.zeros(ow, dtype=np.uint8)
        row[lf >= 0.5] = 1
        row[iff >= 0.5] = 2
        cls[i] = row
    pal = np.array([[12, 28, 58],        # ocean, deep blue
                    [236, 240, 248],     # ice, near-white
                    [122, 158, 92]],     # ice-free land, green
                   dtype=np.uint8)
    rgb = pal[cls]
    # a latitude graticule every 30 deg so the eye can place Antarctica
    for latd in (-60, -30, 0, 30, 60):
        r = int(round((90.0 - latd) / 180.0 * oh))
        if 0 <= r < oh:
            rgb[r, ::6] = (255, 90, 0)
    name = f"earth_ice_free_land_mask_{ow}px.png"
    out = os.path.join(FIG_DIR, name)
    to_png(out, rgb)
    tot = cls.size
    frac = {k: round(100.0 * float((cls == v).sum()) / tot, 4)
            for k, v in (("ocean", 0), ("ice", 1), ("ice_free_land", 2))}
    sidecar(out.replace(".png", ".json"),
            figure=name,
            sources=[os.path.relpath(land_p, ROOT).replace("\\", "/"),
                     os.path.relpath(ifl_p, ROOT).replace("\\", "/")],
            rendered_shape=[oh, ow], downsample_factor=f,
            downsample_method=("per-block majority vote (>= 0.5 of the block), "
                               "NOT a mean -- these are categories, and a mean "
                               "would invent a half-ice cell"),
            colours=dict(ocean="rgb(12,28,58)", ice="rgb(236,240,248)",
                         ice_free_land="rgb(122,158,92)",
                         graticule="rgb(255,90,0) dashed, every 30 deg of latitude"),
            pixel_share_percent_of_plate_carree=frac,
            warning=("Plate carree: these pixel shares are NOT area shares. "
                     "Antarctica is grossly exaggerated here. The area-weighted "
                     "figures are in the phase 1b manifest entry: ice-free land "
                     "is 26.1558% of Earth's AREA."),
            purpose=("show that Antarctica and Greenland are excluded from the "
                     "Earth reference population"))
    print(f"  ice mask {ow} x {oh} px   plate-carree pixel share "
          f"ocean {frac['ocean']}%  ice {frac['ice']}%  "
          f"ice-free land {frac['ice_free_land']}%")
    print(f"         -> docs/figures/{name}")
    report["ice_free_mask"] = dict(file=name, pixel_share_percent=frac,
                                   shape=[oh, ow])
    return report


def main():
    os.makedirs(FIG_DIR, exist_ok=True)
    print("=" * 78)
    print("FIGURES -- rendered from the DEMs this project built")
    print(f"sun azimuth {SUN_AZIMUTH_DEG} deg, altitude {SUN_ALTITUDE_DEG} deg")
    print("=" * 78)
    rep = {}
    for b in ("moon", "mars", "earth"):
        relief(b, rep)
        say_peak(f"{b} figure")
    ice_free_figure(rep)
    sidecar(os.path.join(FIG_DIR, "_figures_summary.json"),
            sun_azimuth_deg=SUN_AZIMUTH_DEG,
            sun_altitude_deg=SUN_ALTITUDE_DEG, figures=rep,
            peak_rss_gib=peak_rss_gib())
    print("=" * 78)
    pk = peak_rss_gib()
    print(f"peak RAM {'unknown' if pk is None else f'{pk:.2f} GiB'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


# ---------------------------------------------------------------------------
# POLAR FIGURE -- added because the global figures CANNOT validate the poles.
#
# Plate carree stretches the last rows across the whole image width, so the
# polar caps appear as horizontal streaking in every global figure above. That
# is a projection artefact, not a data defect, but it means the global figures
# are blind exactly where the lunar targets sit: 85 to 89.9 degrees south.
# A south polar stereographic rendering is the only way to look at them.

POLAR_RADIUS_DEG = 5.0           # 85 to 90 degrees
POLAR_PX = 2400


def polar_south(body, zf, report):
    pl = PLAN[body]
    src = os.path.join(DEM_DIR, pl["file"])
    a = np.load(src, mmap_mode="r")
    h, w = a.shape
    r0 = int(np.floor((90.0 - (-90.0 + POLAR_RADIUS_DEG)) / 180.0 * h)) - 2
    sub = np.array(a[max(0, r0):], dtype=np.float32)  # copy: band-limited below
    sub_lat0 = 90.0 - (max(0, r0) + 0.5) * (180.0 / h)

    n = POLAR_PX
    g = (np.arange(n) + 0.5) / n * 2.0 - 1.0
    X, Y = np.meshgrid(g * POLAR_RADIUS_DEG, g * POLAR_RADIUS_DEG)
    rr = np.hypot(X, Y)
    lat = rr - 90.0                                 # degrees, negative
    lon = np.degrees(np.arctan2(X, Y))
    inside = rr <= POLAR_RADIUS_DEG

    # BAND-LIMIT EACH SOURCE ROW ALONG LONGITUDE BEFORE SAMPLING.
    # A plate carree row at 89 degrees has cells about 8 m wide east-west
    # against 474 m north-south. Sampling that anisotropy with nearest
    # neighbour onto an isotropic polar grid produces heavy moire. Averaging
    # each row over round(1/cos(lat)) columns first makes the row roughly
    # isotropic, so the polar sampling is smooth. This affects the FIGURE
    # only; no layer is built from it.
    for i in range(sub.shape[0]):
        la_i = sub_lat0 - i * (180.0 / h)
        k = int(round(1.0 / max(np.cos(np.radians(la_i)), 1e-12)))
        if k < 2:
            continue
        k = min(k, w)
        row = sub[i].astype(np.float64)
        ext = np.concatenate([row[-k:], row, row[:k]])      # longitude wraps
        cs = np.concatenate([[0.0], np.cumsum(ext)])
        half = k // 2
        lo = k - half
        sub[i] = ((cs[lo + k:lo + k + w] - cs[lo:lo + w]) / k).astype(np.float32)

    # BILINEAR, not nearest. The output cell is ~126 m against a 474 m source
    # row, so nearest neighbour lays down annuli of constant elevation and the
    # hillshade differentiates every annulus boundary into a hard ring. Those
    # rings are a resampling artefact and would read as real terrain.
    rf = (sub_lat0 - lat) / (180.0 / h)
    cf = (lon + 180.0) / (360.0 / w) - 0.5
    r0i = np.floor(rf).astype(np.int64); fy = (rf - r0i).astype(np.float32)
    c0i = np.floor(cf).astype(np.int64); fx = (cf - c0i).astype(np.float32)
    nr = sub.shape[0]
    r0c = np.clip(r0i, 0, nr - 1); r1c = np.clip(r0i + 1, 0, nr - 1)
    c0c = c0i % w; c1c = (c0i + 1) % w                    # longitude wraps
    z = ((1 - fy) * ((1 - fx) * sub[r0c, c0c] + fx * sub[r0c, c1c]) +
         fy * ((1 - fx) * sub[r1c, c0c] + fx * sub[r1c, c1c]))
    z = np.where(inside, z, np.nan)
    del sub, rf, cf, r0i, c0i, r0c, r1c, c0c, c1c, fx, fy

    cell_m = (POLAR_RADIUS_DEG / (n / 2.0)) * (np.pi *
                                               C.BODY_RADIUS_M[body] / 180.0)
    hs = hillshade(z, cell_m, SUN_AZIMUTH_DEG, SUN_ALTITUDE_DEG, zf)
    rgb = shade_rgb(hs, z)
    rgb[~inside] = (0, 0, 0)
    # 1-degree colatitude rings, so 85 / 86 / 87 / 88 / 89 are readable
    for d in (1, 2, 3, 4, 5):
        ring = np.abs(rr - d) < (POLAR_RADIUS_DEG / n)
        rgb[ring] = (255, 140, 0)

    name = (f"{body}_south_polar_{int(90-POLAR_RADIUS_DEG)}S_to_90S_{n}px"
            f"_az{int(SUN_AZIMUTH_DEG)}_alt{int(SUN_ALTITUDE_DEG)}_z{zf:g}.png")
    out = os.path.join(FIG_DIR, name)
    to_png(out, rgb)
    nod = float(100.0 * np.isnan(z[inside]).sum() / max(int(inside.sum()), 1))
    sidecar(out.replace(".png", ".json"),
            figure=name, body=body,
            source=os.path.relpath(src, ROOT).replace("\\", "/"),
            projection="south polar stereographic (azimuthal, pole at centre)",
            extent=f"{90-POLAR_RADIUS_DEG:.0f}S to 90S",
            rendered_shape=[n, n], displayed_cell_km=round(cell_m / 1000.0, 4),
            resampling=("bilinear. Each source row is first band-limited along longitude over "
                        "round(1/cos(lat)) columns to make it roughly "
                        "isotropic, then nearest neighbour onto the polar "
                        "grid. Without the band-limiting step a plate carree "
                        "row near the pole is ~8 m wide east-west against "
                        "474 m north-south and the polar resampling moires "
                        "badly. FIGURE ONLY -- no layer is built this way."),
            limiting_resolution_km=round((180.0 / h) *
                                         (np.pi * C.BODY_RADIUS_M[body] /
                                          1000.0 / 180.0), 4),
            sun_azimuth_deg=SUN_AZIMUTH_DEG, sun_altitude_deg=SUN_ALTITUDE_DEG,
            vertical_exaggeration=zf,
            nodata_percent_inside_disc=round(nod, 6),
            nodata_colour="magenta (255, 0, 255); outside the disc is black",
            graticule="1-degree colatitude rings in orange: 89S, 88S, 87S, 86S, 85S",
            why=("The global plate carree figures stretch the polar rows across "
                 "the full image width and cannot be used to inspect them. The "
                 "lunar targets are at 85 to 89.9 degrees south, so the region "
                 "these figures cannot show is the one that matters most."),
            purpose="visual validation of the polar region AND a deck figure")
    print(f"  {body:6s} south polar {n} x {n} px   cell "
          f"{cell_m/1000:6.3f} km   nodata inside disc {nod:.6f}%")
    print(f"         -> docs/figures/{name}")
    report[f"{body}_south_polar"] = dict(file=name, nodata_percent=round(nod, 6),
                                         displayed_cell_km=round(cell_m/1e3, 4))
    return report
