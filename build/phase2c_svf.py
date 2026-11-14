"""
PHASE 2c -- SKY VIEW FACTOR, one body at a time. DECIDED by Sherozbek, 9 Nov 2026.

    python build/phase2c_svf.py --body moon|mars|earth [--test]

THE QUANTITY (VARIABLES.md B2, Zaksek, Ostir & Pokrajac 2011, Remote Sensing 3:398)
    SVF = 1 - (1/n) * sum_i sin(gamma_i)
    gamma_i = horizon elevation angle in azimuth i, floored at 0 (terrain that
    falls away does not add sky above the horizontal), n = 16 azimuths at
    22.5 degree spacing, search radius 30 km. SVF = 1 is a flat plain with a
    free horizon; SVF -> 0 is the floor of a deep, steep-walled pit. The
    Zaksek form, not the cosine-weighted Dozier & Frew form: the dimension
    being added is OPENNESS, and the thermal dimensions already carry the
    radiative information.

WHERE IT IS COMPUTED -- at about 1 km, on two grids, one kernel
    The working DEM (463 m; 474 m Moon) is block-averaged 2x2 to 0.93 km
    (0.95 km Moon), the "1 km" B2 specifies: a rim 10 km away is not better
    resolved by 118 m sampling, and the 30 km radius is then 32 cells.
    Sub-kilometre terrain is invisible to this SVF. It measures BASIN-SCALE
    openness. Said here so nobody reads a 118 m DEM into a 118 m-faithful SVF.

    |lat| <= 80   plate carree band loop. The east-west column step of every
                  ray is scaled by 1/cos(lat) at the band centre, so the 16
                  azimuths stay 22.5 degrees apart physically. Longitude wraps.
    |lat| >  80   POLAR STEREOGRAPHIC caps, both poles, every body. A horizon
                  sweep along a lat/lon row at 89 S follows a curved,
                  converging path and its azimuths are not the azimuths it
                  claims (B2, Appendix H): that is wrong, not imprecise, and
                  85-89.9 S is the lunar target band. The cap is reprojected
                  from the 463 m DEM with an area-averaging resampler onto a
                  square 0.93 km grid, the SAME kernel runs with cos = 1 and
                  no wrap, and the result is binned to HEALPix weighted by the
                  true cell area (1/k^2, k the stereographic scale factor).
    The two passes meet at 80 degrees: each HEALPix pixel takes its value
    from whichever pass covers its cells, both where it straddles.

THE HORIZON KERNEL
    For azimuth theta and step k = 1..K: row shift dr = -round(k cos theta),
    column shift dc = round(k sin theta / cos lat_band); the horizon tangent is
    max_k (z[r+dr, c+dc] - z[r, c]) / d_k with d_k the true horizontal distance
    of that shift. Angles are compared, never elevations -- a near low ridge
    hides a far high one. A NaN neighbour is NO obstruction (np.fmax); a NaN
    cell is NaN. Every DEM here is 100% valid, so this matters only at the
    cap edges.

EARTH: THE SEA IS A SURFACE
    ETOPO carries bathymetry. A coastal site looks at the sea surface, not
    the seafloor, so every cell outside the land mask is set to 0 m before
    the sweep. Inland water keeps its DEM value. Recorded.

GATES, STATED BEFORE THE RUN
    range     0 <= SVF <= 1 (a sum of sines of angles in [0, 90] cannot leave it)
    coverage  every pixel of every body; the DEMs are complete
    support   fraction of the pixel's weight that carried a value
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
from phase1_dems import DEM_DIR, GRIDS, PEAK_CAP_GIB, peak_rss_gib, say_peak
from phase2_terrain import (DEM_FILE, OUT_DIR, PHASE2_DISK_FLOOR_GIB, ROOT,
                            HealpixAccumulator, cell_km_ns, show, validate)

NAME = "svf_30km"
N_AZ = 16
RADIUS_KM = 30.0
POLAR_LAT = 80.0          # the caps start here
CAP_EDGE_LAT = 77.5       # the cap is reprojected out to here for a 30 km halo
DOWN = 2                  # 2x2 block mean of the working DEM
CORE_ROWS = 256           # rows of the 2x grid per band
LAND_MASK = os.path.join(DEM_DIR, "earth_land_mask_1_240deg.npy")
DECISION = ("Added 9 Nov 2026 on Sherozbek's decision: the Mars-Earth set was "
            "six elevation-derived variables and he asked for sky view factor "
            "on all three bodies as the form/openness dimension B2 specified. "
            "Built by build/phase2c_svf.py; measurements in VARIABLES.md B27.")


# ------------------------------------------------------------------ kernel

def steps_for_azimuth(theta_deg, K, cos_band):
    """Unique (dr, dc, k) steps along one azimuth, 1 <= k <= K cells."""
    th = np.radians(theta_deg)
    out, last = [], None
    for k in range(1, K + 1):
        dr = -int(round(k * np.cos(th)))
        dc = int(round(k * np.sin(th) / cos_band))
        if (dr, dc) == (0, 0) or (dr, dc) == last:
            continue
        last = (dr, dc)
        out.append((dr, dc, k))
    return out


def svf_kernel(z, core0, core1, cell_km, K, cos_rows, cos_band, wrap):
    """SVF for rows [core0, core1) of z. z carries >= K halo rows each side.

    cos_rows: cos(lat) per row of z (east-west metres per column); all 1.0 on
    the stereographic grid. cos_band: the scalar used for the column step.
    wrap: longitude wraps on the lat/lon grid; the stereographic cap is padded
    with NaN instead, so a ray leaving the cap sees no obstruction.
    """
    h, w = z.shape
    z0 = z[core0:core1]
    nr = core1 - core0
    sin_sum = np.zeros((nr, w), dtype=np.float32)
    cos_core = cos_rows[core0:core1].astype(np.float32)
    for i in range(N_AZ):
        tanmax = np.zeros((nr, w), dtype=np.float32)
        for dr, dc, k in steps_for_azimuth(i * 360.0 / N_AZ, K, cos_band):
            r0, r1 = core0 + dr, core1 + dr
            if r0 < 0 or r1 > h:
                continue                 # only at the very poles of the grid
            zs = z[r0:r1]
            if dc:
                zs = np.roll(zs, -dc, axis=1)
            d_km = cell_km * np.hypot(dr, dc * cos_core)       # per row
            inv = (1.0 / (1000.0 * d_km)).astype(np.float32)
            tan = (zs - z0) * inv[:, None]
            np.fmax(tanmax, tan, out=tanmax)
        # sin(atan(t)) = t / sqrt(1 + t^2); tanmax >= 0 by the floor
        sin_sum += tanmax / np.sqrt(1.0 + tanmax * tanmax)
    svf = 1.0 - sin_sum / np.float32(N_AZ)
    svf[~np.isfinite(z0)] = np.nan
    return svf.astype(np.float32)


def block_mean2(a):
    """2x2 block mean, NaN-aware, of a (2m, 2n) float32 array."""
    h, w = a.shape
    b = a.reshape(h // 2, 2, w // 2, 2)
    with np.errstate(invalid="ignore"):
        return np.nanmean(b, axis=(1, 3)).astype(np.float32)


# ------------------------------------------------------------------- driver

def load_rows(z_all, land, r0, r1):
    """463 m rows [r0, r1), ocean set to the sea surface on Earth."""
    # np.array, not np.asarray: a float32 memmap opened read-only comes back
    # as a read-only VIEW from asarray, and the sea-surface assignment below
    # then fails. Moon and Mars never assign, which is why only Earth broke.
    z = np.array(z_all[r0:r1], dtype=np.float32, copy=True)
    if land is not None:
        z[~np.asarray(land[r0:r1])] = 0.0
    return z


def latlon_pass(body, z_all, land, acc, cell2, K, test):
    Hh, Ww = z_all.shape
    H2, W2 = Hh // DOWN, Ww // DOWN
    lat2 = 90.0 - (np.arange(H2) + 0.5) * (180.0 / H2)
    lon2 = -180.0 + (np.arange(W2) + 0.5) * (360.0 / W2)
    cos2 = np.maximum(np.cos(np.radians(lat2)), 1e-9)
    rows_in = np.abs(lat2) <= POLAR_LAT
    first, last = int(np.argmax(rows_in)), int(H2 - np.argmax(rows_in[::-1]))
    bands = list(range(first, last, CORE_ROWS))
    if test:
        bands = [bands[len(bands) // 2], bands[-1]]
    print(f"  lat/lon pass: rows {first}..{last} of the {H2}x{W2} 2x grid, "
          f"{len(bands)} bands of {CORE_ROWS}, K = {K} cells = "
          f"{K*cell2:.2f} km")
    t0 = time.perf_counter()
    max_dc = 0
    for bi, c0 in enumerate(bands):
        c1 = min(last, c0 + CORE_ROWS)
        e0, e1 = max(0, c0 - K), min(H2, c1 + K)
        z = block_mean2(load_rows(z_all, land, DOWN * e0, DOWN * e1))
        k0, k1 = c0 - e0, c1 - e0
        cos_band = float(np.cos(np.radians(lat2[(c0 + c1) // 2])))
        max_dc = max(max_dc, int(round(K / cos_band)))
        svf = svf_kernel(z, k0, k1, cell2, K, cos2[e0:e1], cos_band, wrap=True)
        del z
        idx = acc.index_for_band(lat2[c0:c1], lon2).ravel()
        wt = np.repeat(cos2[c0:c1], W2)
        acc.add_reference(idx, wt)
        acc.add(NAME, svf, idx, wt)
        if test:
            f = svf[np.isfinite(svf)]
            print(f"    TEST band lat {lat2[c0]:+.1f}..{lat2[c1-1]:+.1f}: "
                  f"min {f.min():.4f} p1 {np.percentile(f,1):.4f} p50 "
                  f"{np.median(f):.4f} max {f.max():.4f}")
        del svf, idx, wt
        if bi % 5 == 0 or bi == len(bands) - 1:
            el = time.perf_counter() - t0
            eta = el / (bi + 1) * (len(bands) - bi - 1)
            pk = peak_rss_gib()
            print(f"    band {bi+1}/{len(bands)}  lat {lat2[c0]:+.1f}  "
                  f"{el/60:5.1f} min  eta {eta/60:5.1f} min  peak "
                  f"{'?' if pk is None else f'{pk:.2f}'} GiB", flush=True)
    return dict(bands=len(bands), core_rows=CORE_ROWS, halo_rows=K,
                max_column_step=max_dc,
                elapsed_s=round(time.perf_counter() - t0, 1))


def polar_pass(body, z_all, land, acc, cell2, K, south, test):
    from rasterio.crs import CRS
    from rasterio.transform import from_origin
    from rasterio.warp import Resampling, reproject
    from rasterio.warp import transform as rtransform
    R = C.BODY_RADIUS_M[body]
    Hh, Ww = z_all.shape
    ppd = Hh / 180.0
    src_crs = CRS.from_proj4(f"+proj=longlat +R={R:.1f} +no_defs")
    dst_crs = CRS.from_proj4(f"+proj=stere +lat_0={-90 if south else 90} "
                             f"+lon_0=0 +R={R:.1f} +units=m +no_defs")
    nrows = int(round((90.0 - CAP_EDGE_LAT) * ppd))
    if south:
        r0, r1 = Hh - nrows, Hh
        top_lat = -CAP_EDGE_LAT
    else:
        r0, r1 = 0, nrows
        top_lat = 90.0
    z = load_rows(z_all, land, r0, r1)
    src_tr = from_origin(-180.0, top_lat, 1.0 / ppd, 1.0 / ppd)
    px = cell2 * 1000.0
    half = 2.0 * R * np.tan(np.radians(90.0 - CAP_EDGE_LAT) / 2.0) * 1.02
    n = int(np.ceil(2 * half / px))
    n += n % 2
    dst_tr = from_origin(-n / 2 * px, n / 2 * px, px, px)
    dst = np.full((n, n), np.nan, dtype=np.float32)
    t0 = time.perf_counter()
    reproject(z, dst, src_transform=src_tr, src_crs=src_crs,
              dst_transform=dst_tr, dst_crs=dst_crs,
              resampling=Resampling.average, src_nodata=np.nan,
              dst_nodata=np.nan, num_threads=4)
    del z
    t_rep = time.perf_counter() - t0
    # pad K NaN on every side: a ray leaving the cap sees no obstruction
    zp = np.full((n + 2 * K, n + 2 * K), np.nan, dtype=np.float32)
    zp[K:K + n, K:K + n] = dst
    ones = np.ones(n + 2 * K, dtype=np.float32)
    svf = svf_kernel(zp, K, K + n, cell2, K, ones, 1.0, wrap=False)[:, K:K + n]
    del zp
    t_svf = time.perf_counter() - t0 - t_rep
    xs = (np.arange(n) + 0.5) * px - n / 2 * px
    ys = n / 2 * px - (np.arange(n) + 0.5) * px
    X, Y = np.meshgrid(xs, ys)
    lons, lats = rtransform(dst_crs, src_crs, X.ravel(), Y.ravel())
    lons = np.asarray(lons); lats = np.asarray(lats)
    inside = (np.abs(lats) > POLAR_LAT) & np.isfinite(dst.ravel())
    kscale = 2.0 / (1.0 + np.sin(np.radians(np.abs(lats[inside]))))
    wt = (1.0 / kscale ** 2).astype(np.float64)
    from astropy import units as u
    idx = acc.hp.lonlat_to_healpix(lons[inside] * u.deg,
                                   lats[inside] * u.deg).astype(np.int32)
    vals = svf.ravel()[inside].astype(np.float32)
    acc.add_reference(idx, wt)
    acc.add(NAME, vals.reshape(1, -1), idx, wt)
    f = vals[np.isfinite(vals)]
    pole = "S" if south else "N"
    print(f"  polar cap {pole}: {n}x{n} cells at {cell2:.3f} km, reproject "
          f"{t_rep:.1f} s, kernel {t_svf:.1f} s, {int(inside.sum()):,} cells "
          f"inside |lat| > {POLAR_LAT:g}; SVF min {f.min():.4f} p1 "
          f"{np.percentile(f, 1):.4f} p50 {np.median(f):.4f} max {f.max():.4f}")
    return dict(pole=pole, grid=[n, n], cell_km=round(cell2, 4),
                cells_binned=int(inside.sum()),
                scale_factor_range=[float(kscale.min()), float(kscale.max())],
                reproject_s=round(t_rep, 1), kernel_s=round(t_svf, 1),
                src_rows=[r0, r1], resampling="average (area-weighted)",
                dst_crs=dst_crs.to_proj4())


def build_body(body, test):
    nside = C.NSIDE[body]
    dem_path = os.path.join(DEM_DIR, DEM_FILE[body])
    z_all = np.load(dem_path, mmap_mode="r")
    Hh, Ww = z_all.shape
    if (Hh, Ww) != tuple(GRIDS[body]["shape"]):
        raise SystemExit(f"STOP: DEM is {Hh}x{Ww}, expected {GRIDS[body]['shape']}")
    land = None
    if body == "earth":
        land = np.load(LAND_MASK, mmap_mode="r")
        if land.shape != z_all.shape:
            raise SystemExit("STOP: land mask shape differs from the DEM")
    cell = cell_km_ns(body)
    cell2 = DOWN * cell
    K = int(round(RADIUS_KM / cell2))
    print(f"  grid {Hh} x {Ww} at {cell:.4f} km -> 2x2 block mean {cell2:.4f} km")
    print(f"  {N_AZ} azimuths, radius {RADIUS_KM:g} km -> K = {K} cells = "
          f"{K*cell2:.3f} km achieved")
    if land is not None:
        print("  Earth: cells outside the land mask set to 0 m (sea surface)")
    acc = HealpixAccumulator(nside, [NAME])
    t0 = time.perf_counter()
    ll = latlon_pass(body, z_all, land, acc, cell2, K, test)
    say_peak(f"{body} svf lat/lon pass")
    caps = [polar_pass(body, z_all, land, acc, cell2, K, True, test)]
    if not test:
        caps.append(polar_pass(body, z_all, land, acc, cell2, K, False, test))
    say_peak(f"{body} svf polar caps")
    el = time.perf_counter() - t0

    arr, nfilled, sup = acc.finish(NAME)
    v = np.isfinite(arr)
    out_of = int(np.sum(v & ((arr < 0.0) | (arr > 1.0))))
    print(f"  RANGE GATE [0, 1]: {out_of:,} outside  "
          f"{'PASS' if out_of == 0 else 'FAIL'}")
    if test:
        f = arr[v]
        print(f"  TEST: {int(v.sum()):,} pixels filled; SVF min {f.min():.4f} "
              f"p50 {np.median(f):.4f} max {f.max():.4f}; nothing written")
        return None

    path = os.path.join(OUT_DIR, f"{body}_{NAME}_nside{nside}.npy")
    C.atomic_save(path, arr)
    sv = sup[v]
    const = sv.size > 0 and np.all(sv == sv[0])
    sup_entry = {}
    if const:
        sup_entry = dict(
            support_constant=float(sv[0]), support_valid_pixels=int(v.sum()),
            support_file_removed=(
                f"support was CONSTANT at {float(sv[0]):g} on every valid "
                f"pixel and carried no information, so no array was written "
                f"and the value is recorded here (8 Nov cleanup rule)."))
        print(f"  support constant {float(sv[0]):g} on all valid pixels -- recorded")
    else:
        spath = os.path.join(OUT_DIR, f"{body}_{NAME}_support_nside{nside}.npy")
        C.atomic_save(spath, sup)
        sup_entry = dict(support_file=os.path.relpath(spath, ROOT).replace(os.sep, "/"))
        print(f"  support varies: min {sv.min():.4f} p50 {np.median(sv):.4f} -- written")

    extra = dict(healpix_pixels_filled=nfilled,
                 range_gate_stated_in_advance=[0.0, 1.0],
                 pixels_outside_stated_gate=out_of,
                 range_gate_pass=bool(out_of == 0),
                 azimuths=N_AZ, radius_km_requested=RADIUS_KM,
                 radius_cells=K, radius_km_achieved=round(K * cell2, 4),
                 computed_at_km=round(cell2, 4),
                 latlon_pass=ll, polar_caps=caps)
    vres = validate(arr, nside, f"{body}_{NAME}", "dimensionless", extra,
                    support=sup)
    show(vres)
    rel = lambda p: os.path.relpath(p, ROOT).replace(os.sep, "/")
    srcs = [rel(dem_path)] + ([rel(LAND_MASK)] if land is not None else [])
    C.manifest_write(f"{body}_{NAME}", dict(
        phase="2c", body=body, variable=NAME, units="dimensionless, 0..1",
        file=rel(path), source_files=srcs, source_resolves=True,
        nside=nside, order="nested",
        formula=("SVF = 1 - (1/16) * sum_i sin(max(gamma_i, 0)); gamma_i = "
                 "horizon elevation angle in azimuth i over a 30 km search "
                 "radius. Zaksek, Ostir & Pokrajac (2011) Remote Sensing "
                 "3(2):398-415; horizon after Dozier, Bruno & Downey (1981). "
                 "NOT the cosine-weighted Dozier & Frew (1990) form -- this "
                 "layer is OPENNESS, the thermal layers carry radiation."),
        native_resolution=f"working grid {Hh}x{Ww}, cell {cell:.4f} km",
        computed_on=(f"2x2 block mean of the working DEM = {cell2:.4f} km "
                     f"(B2: 'compute at 1 km'). Sub-kilometre terrain is "
                     f"invisible to this SVF; it measures basin-scale openness."),
        polar_method=(f"|lat| <= {POLAR_LAT:g}: plate carree band loop, "
                      f"column step scaled by 1/cos(lat) at the band centre "
                      f"so azimuths stay 22.5 deg apart, longitude wraps. "
                      f"|lat| > {POLAR_LAT:g}: polar stereographic caps on "
                      f"both poles (rasterio reproject, area-averaging "
                      f"resampler, {cell2:.3f} km square cells), the SAME "
                      f"kernel with cos = 1 and NaN padding, binned to HEALPix "
                      f"with true-area weights 1/k^2. A lat/lon sweep at the "
                      f"pole is wrong, not imprecise (B2, Appendix H)."),
        horizon_rule=("angles compared, never elevations; a NaN neighbour is "
                      "no obstruction (np.fmax); a NaN cell is NaN; horizon "
                      "angle floored at 0"),
        earth_sea_rule=("Earth only: cells outside earth_land_mask set to 0 m "
                        "(the sea surface) before the sweep, because ETOPO "
                        "carries bathymetry and a coast looks at the sea, not "
                        "the seafloor. Inland water keeps its DEM value."
                        if land is not None else None),
        approximations=[
            "cos(lat) for the column step is taken at the band centre; a "
            f"{CORE_ROWS}-row band spans {CORE_ROWS*180.0/(Hh//DOWN):.2f} deg "
            "of latitude, so the azimuth error is under 2 deg at 80 deg lat",
            "the 16 ray directions are rounded to whole cells per step, so "
            "the sampled azimuth wobbles by up to atan(0.5/k) at step k",
            "the two passes share HEALPix pixels only where a pixel straddles "
            "80 deg; there each pass contributes the cells on its side"],
        binning=("area-weighted mean onto HEALPix NESTED: cos(lat) weights on "
                 "the lat/lon pass, 1/k^2 stereographic-area weights on the "
                 "caps, accumulated in one HealpixAccumulator"),
        gates=("THREE: range (0..1, stated in advance), coverage, support."),
        decision=DECISION,
        validation=vres, elapsed_s=round(el, 1), peak_rss_gib=peak_rss_gib(),
        build_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **sup_entry))
    io.open(os.path.join(OUT_DIR, f"phase2c_{body}_summary.json"), "w",
            encoding="utf-8").write(json.dumps(vres, indent=1, default=str))
    return vres


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", required=True, choices=["moon", "mars", "earth"])
    ap.add_argument("--test", action="store_true",
                    help="two lat/lon bands and the south cap; write nothing")
    a = ap.parse_args(argv)
    print("=" * 78)
    print(f"PHASE 2c -- SKY VIEW FACTOR: {a.body.upper()}")
    print("=" * 78)
    print("RANGE GATE, stated BEFORE the run: 0 <= SVF <= 1")
    C.require_disk(PHASE2_DISK_FLOOR_GIB, ROOT)
    t0 = time.perf_counter()
    build_body(a.body, a.test)
    pk = peak_rss_gib()
    print(f"\n{a.body.upper()}: {(time.perf_counter()-t0)/60:.1f} min   peak RAM "
          f"{'?' if pk is None else f'{pk:.2f}'} GiB (cap {PEAK_CAP_GIB})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
