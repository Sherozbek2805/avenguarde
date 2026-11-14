"""
PHASE 0 -- smoke test. Proves the whole chain on something small, then STOPS.

    Moon only, ~2 km working grid, Nside 64, slope and ruggedness.
    read DEM -> downsample -> compute -> bin -> write -> manifest -> validate

Nothing here is a product. The point is to find a wrong transform, a wrong sign
or a wrong nodata rule in minutes rather than at hour eight of the real build.

    python build/phase0_smoke.py
"""

import io
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

ROOT = C.ROOT
LOLA = os.path.join(ROOT, "Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif")

# ---- smoke parameters, deliberately small
SMOKE_NSIDE = 64
DOWNSAMPLE = 16            # 118.4506 m * 16 = 1895.2 m ~ "2 km"
SLOPE_BASELINE_KM = 7.0
RUGGED_WINDOW_KM = 21.0
OUT = os.path.join(ROOT, "cube", "_smoke")

# DEM scale validation, against published figures rather than a guess.
#
# LOLA elevations are heights above/below the 1737.4 km lunar reference sphere.
# The commonly cited global range is about -9,130 m to +10,780 m (USGS Luna map
# sheet, which labels its own extremes approximate). Area-averaging to a coarser
# working grid can only pull the extremes INWARD, so the measured range must sit
# inside the published one and not far inside.
#
# This is the test that catches the half-metre trap: with the 0.5 band scale
# omitted the range would be about -18,100 to +21,400 m, double the known lunar
# relief and physically impossible. A single landmark cannot detect that; the
# range can.
LOLA_RANGE = dict(
    published_min_m=-9130.0, published_max_m=10780.0,
    source="USGS Luna map sheet based on LOLA; extremes labelled approximate",
    tolerance_frac=0.15,
    note="area-averaging pulls extremes inward, so measured must be inside "
         "published, within 15 percent",
)

# Kept as INFORMATIONAL only, not a pass/fail gate. Mons Huygens' famous
# ~5.5 km is RELIEF above the surrounding mare, not absolute elevation above the
# reference sphere -- conflating the two is what made the first version of this
# check fail.
LANDMARK = dict(name="Mons Huygens region", lat=19.92, lon=-2.93,
                informational_only=True,
                note="absolute elevation above the 1737.4 km sphere, NOT relief "
                     "above the surrounding mare; Imbrium's floor is well below "
                     "the sphere so the absolute value is much lower than the "
                     "quoted 5.5 km relief")


def main():
    t_start = time.perf_counter()
    print("=" * 78)
    print("PHASE 0 -- SMOKE TEST (Moon, ~2 km working grid, Nside 64)")
    print("=" * 78)

    have = C.free_gib(ROOT)
    print(f"\nfree disk on {ROOT}: {have:.1f} GiB")
    C.require_disk(40.0, ROOT)
    print("  disk check PASSED (>= 40 GiB)")

    os.makedirs(OUT, exist_ok=True)
    clock = C.Clock(6)
    report = {"phase": 0, "nside": SMOKE_NSIDE, "downsample": DOWNSAMPLE}

    # ---------------------------------------------------------------- 1. header
    import rasterio
    with rasterio.open(LOLA) as s:
        hdr = dict(shape=[s.height, s.width], dtype=str(s.dtypes[0]),
                   nodata=s.nodata, scales=list(s.scales),
                   offsets=list(s.offsets),
                   res_metres=[abs(s.transform.a), abs(s.transform.e)],
                   crs_is_projected=bool(s.crs and s.crs.is_projected),
                   block=list(s.block_shapes[0]))
    print(f"\nLOLA header, read not assumed:")
    for k, v in hdr.items():
        print(f"  {k:18s} {v}")
    if hdr["scales"] != [0.5]:
        print(f"  !! expected scales [0.5]; got {hdr['scales']}. STOPPING.")
        return 1
    print("  CONFIRMED: band scale is 0.5, so stored int16 values are HALF METRES.")
    print("  rasterio does not apply this on read; block_mean_downsample does.")
    report["lola_header"] = hdr
    clock.stage("read LOLA header")

    # ------------------------------------------------------------ 2. downsample
    dem_path = os.path.join(OUT, f"moon_dem_{DOWNSAMPLE}x.npy")
    oh, ow = hdr["shape"][0] // DOWNSAMPLE, hdr["shape"][1] // DOWNSAMPLE
    if C.is_complete(dem_path, (oh, ow), "float32"):
        print(f"\nworking DEM already present, reusing: {dem_path}")
        z = np.load(dem_path)
        dsinfo = {"reused": True}
    else:
        print(f"\ndownsampling {hdr['shape']} -> ({oh}, {ow}) by {DOWNSAMPLE}x "
              f"(area average, nodata skipped)")
        z, n_valid, n_nodata, sc, of = C.block_mean_downsample(
            LOLA, DOWNSAMPLE, scale=None, offset=None, progress_every=600)
        C.atomic_save(dem_path, z)
        dsinfo = dict(reused=False, applied_scale=sc, applied_offset=of,
                      source_nodata_cells=n_nodata, working_valid_cells=n_valid)
        print(f"  applied scale={sc} offset={of}; source nodata cells={n_nodata:,}")
    lat, lon, (cell_lat, cell_lon) = C.dem_grid_geometry(*z.shape)
    cell_km_ns = cell_lat * (np.pi * C.BODY_RADIUS_M["moon"] / 1000.0 / 180.0)
    print(f"  working grid {z.shape}, cell {cell_lat:.6f} deg = {cell_km_ns:.4f} km NS")
    report["working_grid"] = dict(shape=list(z.shape), cell_deg=cell_lat,
                                  cell_km_ns=round(cell_km_ns, 4), **dsinfo)
    clock.stage("downsample DEM")

    # ------------------------------------------------------- 3. DEM validation
    v = np.isfinite(z)
    f = z[v].astype(np.float64)
    q = np.percentile(f, [1, 50, 99])
    dem_stats = dict(shape=list(z.shape), dtype=str(z.dtype),
                     n_nodata=int((~v).sum()),
                     percent_valid=round(100.0 * v.sum() / v.size, 4),
                     min_m=float(f.min()), p1_m=float(q[0]), p50_m=float(q[1]),
                     p99_m=float(q[2]), max_m=float(f.max()))
    print(f"\nDEM validation:")
    for k, val in dem_stats.items():
        print(f"  {k:16s} {val}")
    # --- scale validation: global range against published LOLA extremes
    lo, hi = dem_stats["min_m"], dem_stats["max_m"]
    plo, phi = LOLA_RANGE["published_min_m"], LOLA_RANGE["published_max_m"]
    tol = LOLA_RANGE["tolerance_frac"]
    inside = (lo >= plo * (1 + tol)) and (hi <= phi * (1 + tol))
    near_lo = abs(lo - plo) <= abs(plo) * tol
    near_hi = abs(hi - phi) <= abs(phi) * tol
    scale_ok = bool(inside and near_lo and near_hi)
    print(f"\nDEM SCALE VALIDATION (the half-metre trap detector)")
    print(f"  measured  range : {lo:10.1f} .. {hi:10.1f} m")
    print(f"  published range : {plo:10.1f} .. {phi:10.1f} m  ({LOLA_RANGE['source']})")
    print(f"  inside published (+{int(tol*100)}% tol) : {inside}")
    print(f"  within {int(tol*100)}% of each extreme     : low={near_lo} high={near_hi}")
    print(f"  -> SCALE {'PASS' if scale_ok else 'FAIL'}")
    print(f"  if the 0.5 band scale had been skipped: {lo*2:.0f} .. {hi*2:.0f} m, "
          f"double the known lunar relief and impossible")

    # informational landmark, not a gate
    r = int((90.0 - LANDMARK["lat"]) / cell_lat)
    c = int((LANDMARK["lon"] + 180.0) / cell_lon)
    patch = z[max(0, r - 2):r + 3, max(0, c - 2):c + 3]
    pk = float(np.nanmax(patch)) / 1000.0
    print(f"\ninformational: {LANDMARK['name']} peak in a 5x5 patch = {pk:.3f} km")
    print(f"  {LANDMARK['note']}")

    report["scale_validation"] = dict(measured_min_m=lo, measured_max_m=hi,
                                      **LOLA_RANGE, inside=bool(inside),
                                      near_low=bool(near_lo), near_high=bool(near_hi),
                                      passed=scale_ok,
                                      doubled_would_be=[lo * 2, hi * 2])
    report["landmark_informational"] = dict(**LANDMARK, measured_km=round(pk, 3))
    if not scale_ok:
        print("\n  !! SCALE VALIDATION FAILED -- stopping before computing variables")
        io.open(os.path.join(OUT, "phase0_report.json"), "w",
                encoding="utf-8").write(json.dumps(report, indent=1, ensure_ascii=False))
        return 1
    report["dem"] = dem_stats
    clock.stage("validate DEM")

    # ------------------------------------------------------------- 4. variables
    results = {}
    for name, fn, kwargs, units in (
        ("slope", C.slope_deg,
         dict(baseline_km=SLOPE_BASELINE_KM), "degrees"),
        ("ruggedness", C.ruggedness_m,
         dict(window_km=RUGGED_WINDOW_KM), "m"),
    ):
        hp_path = os.path.join(OUT, f"moon_{name}_nside{SMOKE_NSIDE}.npy")
        if C.is_complete(hp_path, (12 * SMOKE_NSIDE ** 2,), "float32"):
            print(f"\n{name}: HEALPix layer already present, reusing")
            hpx = np.load(hp_path)
            meta = {"reused": True}
            binfo = {}
        else:
            print(f"\ncomputing {name} at the working grid ...")
            t0 = time.perf_counter()
            arr, meta = fn(z, lat, cell_km_ns, width=z.shape[1], **kwargs)
            print(f"  {name} computed in {time.perf_counter()-t0:.1f}s; "
                  f"meta={meta}")
            print(f"  binning to HEALPix NESTED Nside {SMOKE_NSIDE} ...")
            t0 = time.perf_counter()
            hpx, binfo = C.bin_to_healpix(arr, lat, lon, SMOKE_NSIDE)
            print(f"  binned in {time.perf_counter()-t0:.1f}s; {binfo}")
            C.atomic_save(hp_path, hpx)
            del arr
        val = C.validate_layer(hpx, SMOKE_NSIDE, f"moon_{name}")
        print(f"  validation: shape_ok={val['shape_ok']} "
              f"valid={val['percent_valid']['global']}% "
              f"polar85S={val['percent_valid']['lat_85S_to_90S']}%")
        print(f"              stats={ {k: round(x,3) for k,x in val['stats'].items()} }")
        results[name] = dict(validation=val, method_meta=meta, binning=binfo)

        C.manifest_write(f"smoke_moon_{name}", dict(
            phase="0-smoke", body="moon", variable=name, units=units,
            file=os.path.relpath(hp_path, ROOT).replace("\\", "/"),
            source_files=[os.path.relpath(LOLA, ROOT)],
            source_absolute=[LOLA],
            source_resolves=os.path.exists(LOLA),
            native_resolution=f"{hdr['res_metres'][0]:.4f} m ({hdr['shape'][0]}x{hdr['shape'][1]})",
            working_resolution=f"{cell_km_ns*1000:.1f} m ({z.shape[0]}x{z.shape[1]})",
            nside=SMOKE_NSIDE,
            method=("slope = atan(hypot(dz_ns/dist_ns, dz_ew/dist_ew)), centred "
                    "difference over +/-m cells, constant physical baseline, "
                    "east-west stencil widened as 1/cos(lat), no clamp"
                    if name == "slope" else
                    "NaN-aware standard deviation of elevation in a window of "
                    "constant physical extent; east-west half-width widened as "
                    "1/cos(lat); NaN where under half the window is valid"),
            baseline_or_window_km=(SLOPE_BASELINE_KM if name == "slope" else RUGGED_WINDOW_KM),
            method_parameters=meta,
            nodata_rule=("source nodata -32768 -> NaN before scaling; NaN "
                         "propagates; ruggedness additionally NaN where under "
                         "half the window is valid"),
            clip_range_applied=None,
            scale_offset_applied=dict(scale=hdr["scales"][0], offset=hdr["offsets"][0],
                                      why="GeoTIFF band scale: stored int16 are half-metres"),
            tpi_sign_convention=C.TPI_SIGN_NOTE,
            not_shepard_deviogram=True,
            percent_valid=val["percent_valid"],
            stats=val["stats"],
            healpix_binning=binfo,
            build_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            elapsed_s=round(time.perf_counter() - t_start, 1),
            smoke_only=True,
        ))
        clock.stage(f"{name} -> HEALPix -> manifest")

    # --------------------------------------------------- 5. delete intermediate
    size_gib = os.path.getsize(dem_path) / 2 ** 30
    os.remove(dem_path)
    print(f"\ndeleted the working DEM intermediate ({size_gib:.3f} GiB freed)")
    report["intermediate_deleted_gib"] = round(size_gib, 4)
    clock.stage("delete intermediate")

    report["variables"] = results
    report["total_elapsed_s"] = round(time.perf_counter() - t_start, 1)
    io.open(os.path.join(OUT, "phase0_report.json"), "w",
            encoding="utf-8").write(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"\ntotal elapsed {report['total_elapsed_s']}s")
    print(f"-> {os.path.join(OUT, 'phase0_report.json')}")
    print(f"-> {C.MANIFEST}")
    print("\nPHASE 0 COMPLETE. STOPPING for human confirmation before Phase 1.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
