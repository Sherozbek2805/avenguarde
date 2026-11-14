"""
MARS ELEVATION on HEALPix -- an input layer for the temperature table lookup.

    python build/mars_elevation_healpix.py

Area-weighted mean of the 1/128 deg working DEM (MOLA-HRSC blend, phase 1)
onto Nside 512, by the same HealpixAccumulator as every other layer. It is
NOT a ranking dimension (B8f: elevation ranked within each body is out); it
sets the surface pressure in the thermal model: P = 546 Pa * exp(-z / H).
Recorded with role 'input: pressure for the thermal model'.
"""

import io
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C
from phase1_dems import DEM_DIR, peak_rss_gib
from phase2_terrain import DEM_FILE, HealpixAccumulator, show, validate

BODY, NSIDE = "mars", C.NSIDE["mars"]
OUT = os.path.join(C.ROOT, "cube", "healpix")


def main():
    z = np.load(os.path.join(DEM_DIR, DEM_FILE[BODY]), mmap_mode="r")
    H, W = z.shape
    lat = 90.0 - (np.arange(H) + 0.5) * (180.0 / H)
    lon = -180.0 + (np.arange(W) + 0.5) * (360.0 / W)
    cos = np.maximum(np.cos(np.radians(lat)), 1e-9)
    acc = HealpixAccumulator(NSIDE, ["elevation"])
    t0 = time.perf_counter()
    step = 256
    for r0 in range(0, H, step):
        r1 = min(H, r0 + step)
        idx = acc.index_for_band(lat[r0:r1], lon).ravel()
        wt = np.repeat(cos[r0:r1], W)
        acc.add_reference(idx, wt)
        acc.add("elevation", np.asarray(z[r0:r1], dtype=np.float32), idx, wt)
        if (r0 // step) % 20 == 0:
            print(f"    rows {r1}/{H}  {(time.perf_counter()-t0)/60:.1f} min", flush=True)
    arr, nfilled, sup = acc.finish("elevation")
    path = os.path.join(OUT, f"{BODY}_elevation_nside{NSIDE}.npy")
    C.atomic_save(path, arr)
    v = np.isfinite(arr)
    const = np.all(sup[v] == sup[v][0])
    vres = validate(arr, NSIDE, f"{BODY}_elevation", "m", dict(healpix_pixels_filled=nfilled), support=sup)
    show(vres)
    entry = dict(
        phase="1", body=BODY, variable="elevation", units="m (MOLA areoid)",
        role="input: surface pressure for the thermal model; never ranks (B8f)",
        nside=NSIDE, order="nested", file=os.path.relpath(path, C.ROOT).replace(os.sep, "/"),
        source_files=[os.path.relpath(os.path.join(DEM_DIR, DEM_FILE[BODY]), C.ROOT).replace(os.sep, "/")],
        source_resolves=True, matching_eligible=False,
        binning="area-weighted mean onto HEALPix NESTED with cos(lat) weights",
        validation=vres, peak_rss_gib=peak_rss_gib(),
        build_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    if const:
        entry.update(support_constant=float(sup[v][0]), support_valid_pixels=int(v.sum()),
                     support_file_removed="constant on every valid pixel; value recorded")
    else:
        spath = os.path.join(OUT, f"{BODY}_elevation_support_nside{NSIDE}.npy")
        C.atomic_save(spath, sup)
        entry["support_file"] = os.path.relpath(spath, C.ROOT).replace(os.sep, "/")
    C.manifest_write(f"{BODY}_elevation", entry)
    print(f"wrote {path} in {(time.perf_counter()-t0)/60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
