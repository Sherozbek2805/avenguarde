"""
PHASE 1 -- the three common DEMs plus the Earth land mask. Then STOP.

Exact angular grids, verified from headers before use:
    Earth  1/240 deg   43,200 x 86,400   463.3 m at the equator   NO RESAMPLING
    Moon   1/64  deg   11,520 x 23,040   473.8 m   exact 4x block average, x0.5
    Mars   1/128 deg   23,040 x 46,080   463.1 m   area-weighted, factor 2.315408

MEMORY DISCIPLINE
    Earth at 1/240 deg is 3.73 Gpx = 14.9 GB as float32. It is NEVER held in
    RAM. Every full-size array is an np.memmap; every pass is banded. Peak
    allocation is capped and printed after each stage. The host is a thin laptop
    on a spinning disk -- swapping locks it for minutes.

TWO BASELINE CONVENTIONS, BOTH CORRECT, RECORDED IN EVERY ENTRY
    slope    centre-to-centre   2h*c       7 km requested -> 7.58 km achieved
    windows  full footprint    (2h+1)*c   21 km requested -> 20.85 km achieved
    A slope is a height difference ACROSS a distance; a window statistic covers
    an AREA. They are not meant to match. Do not "fix" one to agree with the
    other.

    python build/phase1_dems.py --body earth|moon|mars|mask|all
"""

import argparse
import glob
import io
import json
import os
import re
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

ROOT = C.ROOT
DEM_DIR = os.path.join(ROOT, "cube", "dem")
DISK_FLOOR_GIB = 60.0
PEAK_CAP_GIB = 4.0
BAND_ROWS = 2000                 # legacy default; prefer band_rows_for_width()
BAND_BYTES_BUDGET = 512 * 2 ** 20   # 512 MB per band of working float32


def band_rows_for_width(width, bytes_per_cell=4, budget=BAND_BYTES_BUDGET,
                        multiple_of=1):
    """Rows per band chosen by BYTES, not by a fixed row count.

    A fixed row count is safe on a 23,040-wide Moon row and four times too large
    on an 86,400-wide Earth row. Sizing by bytes makes one code path correct on
    every body, which is the point of the common working grid.
    """
    rows = max(multiple_of, int(budget // (width * bytes_per_cell)))
    if multiple_of > 1:
        rows = max(multiple_of, (rows // multiple_of) * multiple_of)
    return rows

GRIDS = {
    "earth": dict(ppd=240, shape=(43200, 86400), m_at_eq=463.3),
    "moon":  dict(ppd=64,  shape=(11520, 23040), m_at_eq=473.8),
    "mars":  dict(ppd=128, shape=(23040, 46080), m_at_eq=463.1),
}

SLOPE_CONVENTION = (
    "slope uses CENTRE-TO-CENTRE spacing, 2*h*cell: a slope is a height "
    "difference ACROSS a distance, so only the two endpoints and their "
    "separation enter. 7 km requested -> 7.58 km achieved at 463 m.")
WINDOW_CONVENTION = (
    "window statistics use the FULL FOOTPRINT, (2*h+1)*cell: a window statistic "
    "covers an AREA, so the centre cell counts. 21 km requested -> 20.85 km "
    "achieved at 463 m.")
CONVENTION_WARNING = (
    "These two conventions differ BY DESIGN and must not be reconciled. A later "
    "reader who 'fixes' one to match the other will silently change every "
    "terrain variable.")

# Published global extremes, for the scale gate. Same logic as Phase 0: a
# missing or wrong scale factor shows up as a range that is physically
# impossible, which a single landmark cannot detect.
PUBLISHED_RANGE = {
    "earth": dict(min_m=-10900.0, max_m=8850.0, tol=0.20,
                  source="ETOPO 2022 global relief: Challenger Deep ~-10,900 m, "
                         "Everest ~8,850 m; surface (ice) variant"),
    "moon":  dict(min_m=-9130.0, max_m=10780.0, tol=0.15,
                  source="USGS Luna map sheet from LOLA; extremes approximate"),
    "mars":  dict(min_m=-8200.0, max_m=21250.0, tol=0.20,
                  source="MOLA: Hellas floor ~-8,200 m, Olympus Mons ~21,250 m"),
}

_PEAK = {"fn": None}


def peak_rss_gib():
    """Peak working set of this process. Explicit ctypes signatures are
    required: GetCurrentProcess's default restype truncates the 64-bit
    pseudo-handle, GetProcessMemoryInfo then fails and returns 0, which is
    indistinguishable from 'used no memory'."""
    if _PEAK["fn"] is None:
        try:
            import ctypes
            from ctypes import wintypes

            class _PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t),
                            ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]

            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            ps = ctypes.WinDLL("psapi", use_last_error=True)
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            k32.GetCurrentProcess.argtypes = []
            ps.GetProcessMemoryInfo.restype = wintypes.BOOL
            ps.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE,
                                                ctypes.POINTER(_PMC), wintypes.DWORD]

            def probe():
                pmc = _PMC()
                pmc.cb = ctypes.sizeof(_PMC)
                if ps.GetProcessMemoryInfo(k32.GetCurrentProcess(),
                                           ctypes.byref(pmc), pmc.cb):
                    return pmc.PeakWorkingSetSize / 2 ** 30
                return None
            _PEAK["fn"] = probe if probe() else (lambda: None)
        except Exception:
            _PEAK["fn"] = lambda: None
    return _PEAK["fn"]()


def say_peak(stage):
    p = peak_rss_gib()
    flag = ""
    if p is not None and p > PEAK_CAP_GIB:
        flag = f"   !! OVER THE {PEAK_CAP_GIB} GiB CAP"
    print(f"    peak RAM after {stage}: "
          f"{'unknown' if p is None else f'{p:.2f} GiB'}{flag}", flush=True)
    return p


def open_memmap_part(path, shape, dtype):
    """A full-size array as a disk-backed .npy, written to <name>.part."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    part = path + ".part"
    return np.lib.format.open_memmap(part, mode="w+", dtype=dtype, shape=shape), part


def finish_part(part, path):
    os.replace(part, path)
    return path


# --------------------------------------------------------------- band validation

def validate_dem_banded(path, body, bytes_read, elapsed, extra=None):
    """Stream the DEM and compute shape, nodata, percentiles and polar validity
    without ever holding it in RAM."""
    a = np.load(path, mmap_mode="r")
    h, w = a.shape
    cell = 180.0 / h
    lat_rows = 90.0 - (np.arange(h) + 0.5) * cell

    band = band_rows_for_width(w, 4)
    n_valid = 0
    n_nodata = 0
    lo, hi = np.inf, -np.inf
    # reservoir for percentiles: every 97th row, subsampled along it. Cheap, and
    # 97 is coprime with every band size used so the sample is not aligned to
    # band boundaries.
    samp = []
    bands = {"abs_lat_gt_60": 0, "abs_lat_gt_80": 0, "abs_lat_gt_85": 0,
             "lat_85S_to_90S": 0}
    band_tot = dict.fromkeys(bands, 0)

    for r0 in range(0, h, band):
        r1 = min(h, r0 + band)
        blk = np.asarray(a[r0:r1])
        v = np.isfinite(blk)
        n_valid += int(v.sum())
        n_nodata += int(v.size - v.sum())
        if v.any():
            lo = min(lo, float(blk[v].min()))
            hi = max(hi, float(blk[v].max()))
        la = lat_rows[r0:r1]
        for name, m in (("abs_lat_gt_60", np.abs(la) > 60),
                        ("abs_lat_gt_80", np.abs(la) > 80),
                        ("abs_lat_gt_85", np.abs(la) > 85),
                        ("lat_85S_to_90S", la <= -85.0)):
            if m.any():
                sub = v[m]
                bands[name] += int(sub.sum())
                band_tot[name] += int(sub.size)
        for rr in range(r0, r1, 97):
            row = blk[rr - r0, ::211]
            row = row[np.isfinite(row)]
            if row.size:
                samp.append(row.astype(np.float32, copy=True))
        del blk, v

    s = np.concatenate(samp) if samp else np.array([], dtype=np.float32)
    q = np.percentile(s.astype(np.float64), [1, 50, 99]) if s.size else [None] * 3
    pct = {"global": round(100.0 * n_valid / (h * w), 4)}
    for k in bands:
        pct[k] = round(100.0 * bands[k] / band_tot[k], 4) if band_tot[k] else None

    pr = PUBLISHED_RANGE[body]
    near_lo = abs(lo - pr["min_m"]) <= abs(pr["min_m"]) * pr["tol"]
    near_hi = abs(hi - pr["max_m"]) <= abs(pr["max_m"]) * pr["tol"]
    inside = lo >= pr["min_m"] * (1 + pr["tol"]) and hi <= pr["max_m"] * (1 + pr["tol"])
    scale_ok = bool(inside and near_lo and near_hi)

    out = dict(
        file=os.path.relpath(path, ROOT).replace("\\", "/"),
        shape=[h, w], dtype=str(a.dtype),
        bytes_on_disk=os.path.getsize(path),
        n_valid=n_valid, n_nodata=n_nodata, percent_valid=pct,
        min_m=lo, p1_m=q[0], p50_m=q[1], p99_m=q[2], max_m=hi,
        percentile_sample_n=int(s.size),
        scale_gate=dict(published=pr, measured=[lo, hi], inside=bool(inside),
                        near_low=bool(near_lo), near_high=bool(near_hi),
                        passed=scale_ok,
                        doubled_would_be=[lo * 2, hi * 2],
                        why=("a wrong or missing band scale shows as a physically "
                             "impossible range; a single landmark cannot detect it")),
        bytes_read=bytes_read, elapsed_s=round(elapsed, 1),
        throughput_MB_s=round(bytes_read / 2 ** 20 / max(elapsed, 1e-9), 1),
        peak_rss_gib=peak_rss_gib(),
    )
    if extra:
        out.update(extra)
    return out, scale_ok


def print_validation(v, label):
    print(f"\n  --- {label} validation ---")
    print(f"    shape {v['shape']}  dtype {v['dtype']}  "
          f"{v['bytes_on_disk']/2**30:.2f} GiB on disk")
    print(f"    nodata cells {v['n_nodata']:,}   valid {v['percent_valid']['global']}%")
    print(f"    min {v['min_m']:.1f}  p1 {v['p1_m']:.1f}  p50 {v['p50_m']:.1f}  "
          f"p99 {v['p99_m']:.1f}  max {v['max_m']:.1f}  (m)")
    g = v["scale_gate"]
    print(f"    SCALE GATE: measured [{g['measured'][0]:.0f}, {g['measured'][1]:.0f}] "
          f"vs published [{g['published']['min_m']:.0f}, {g['published']['max_m']:.0f}] "
          f"-> {'PASS' if g['passed'] else 'FAIL'}")
    print(f"    polar validity: >60 {v['percent_valid']['abs_lat_gt_60']}%  "
          f">80 {v['percent_valid']['abs_lat_gt_80']}%  "
          f">85 {v['percent_valid']['abs_lat_gt_85']}%  "
          f"85-90S {v['percent_valid']['lat_85S_to_90S']}%")
    print(f"    read {v['bytes_read']/2**20:.0f} MB in {v['elapsed_s']}s "
          f"= {v['throughput_MB_s']} MB/s   peak RAM "
          f"{v['peak_rss_gib']:.2f} GiB" if v["peak_rss_gib"] else "")


def manifest_dem(body, v, method, source_files, native, extra):
    C.manifest_write(f"dem_{body}", dict(
        phase="1", body=body, variable="elevation", units="m",
        file=v["file"],
        source_files=[os.path.relpath(p, ROOT).replace("\\", "/") for p in source_files],
        source_absolute=source_files[:4],
        all_sources_resolve=all(os.path.exists(p) for p in source_files),
        n_source_files=len(source_files),
        native_resolution=native,
        working_resolution=f"1/{GRIDS[body]['ppd']} deg = {GRIDS[body]['m_at_eq']} m "
                           f"at the equator ({v['shape'][0]}x{v['shape'][1]})",
        target_nside=C.NSIDE[body],
        method=method,
        slope_convention=SLOPE_CONVENTION,
        window_convention=WINDOW_CONVENTION,
        convention_warning=CONVENTION_WARNING,
        tpi_sign_convention=C.TPI_SIGN_NOTE,
        nodata_rule=extra.get("nodata_rule"),
        clip_range_applied=None,
        scale_offset_applied=extra.get("scale_offset_applied"),
        shape=v["shape"], dtype=v["dtype"],
        n_nodata=v["n_nodata"], percent_valid=v["percent_valid"],
        stats=dict(min=v["min_m"], p1=v["p1_m"], p50=v["p50_m"],
                   p99=v["p99_m"], max=v["max_m"]),
        scale_gate=v["scale_gate"],
        bytes_read=v["bytes_read"], elapsed_s=v["elapsed_s"],
        throughput_MB_s=v["throughput_MB_s"], peak_rss_gib=v["peak_rss_gib"],
        build_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **{k: val for k, val in extra.items()
           if k not in ("nodata_rule", "scale_offset_applied")}))


# ============================================================ EARTH (mosaic)

TILE_RE = re.compile(r"_15s_([NS])(\d{2})([EW])(\d{3})_surface\.tif$", re.I)


def tile_nw(name):
    """North-west corner of an ETOPO 15s tile, from its filename.

    Verified against the header: ETOPO_..._N00E000_surface.tif has
    bounds(left=0, bottom=-15, right=15, top=0), so the name encodes
    top-latitude and left-longitude.
    """
    m = TILE_RE.search(name)
    if not m:
        return None
    ns, la, ew, lo = m.group(1).upper(), int(m.group(2)), m.group(3).upper(), int(m.group(4))
    top = la if ns == "N" else -la
    left = lo if ew == "E" else -lo
    return top, left


def build_earth(force=False):
    import rasterio
    ppd = GRIDS["earth"]["ppd"]
    H, W = GRIDS["earth"]["shape"]
    out_path = os.path.join(DEM_DIR, "earth_dem_1_240deg.npy")
    tiles = sorted(glob.glob(os.path.join(ROOT, "sources", "etopo_surface",
                                          "*15s*surface*.tif")))
    if C.is_complete(out_path, (H, W), "float32") and not force:
        print("  earth DEM already complete, reusing")
        v, ok = validate_dem_banded(out_path, "earth", 0, 1e-9)
        return v, ok, tiles

    print(f"  mosaicking {len(tiles)} tiles into {H} x {W} float32 "
          f"({H*W*4/2**30:.1f} GiB, memmapped -- never in RAM)")
    arr, part = open_memmap_part(out_path, (H, W), np.float32)
    t0 = time.perf_counter()
    nbytes = 0
    placed = 0
    for i, p in enumerate(tiles, 1):
        nw = tile_nw(os.path.basename(p))
        if nw is None:
            print(f"    !! cannot parse tile name: {p}")
            continue
        top, left = nw
        r0 = int(round((90.0 - top) * ppd))
        c0 = int(round((left + 180.0) * ppd))
        with rasterio.open(p) as s:
            blk = s.read(1)
            nd = s.nodata
        nbytes += blk.nbytes
        blk = blk.astype(np.float32)
        if nd is not None:
            blk[blk == nd] = np.nan
        arr[r0:r0 + blk.shape[0], c0:c0 + blk.shape[1]] = blk
        placed += 1
        if i % 48 == 0:
            el = time.perf_counter() - t0
            print(f"    {i}/{len(tiles)} tiles  {el/60:.1f} min  "
                  f"{nbytes/2**20/el:.0f} MB/s", flush=True)
        del blk
    arr.flush()
    del arr
    finish_part(part, out_path)
    el = time.perf_counter() - t0
    print(f"    placed {placed} tiles in {el/60:.1f} min")
    say_peak("earth mosaic")
    v, ok = validate_dem_banded(out_path, "earth", nbytes, el,
                                extra=dict(tiles_placed=placed))
    return v, ok, tiles


def seam_check(path, n_boundaries=6):
    """Is slope systematically higher across tile boundaries?

    A mosaic that is one row or column out produces a step at every seam, which
    shows as an elevated gradient exactly on the boundary columns and nowhere
    else. Compare the mean |dz| ON the seams against the mean just beside them.
    """
    ppd = GRIDS["earth"]["ppd"]
    a = np.load(path, mmap_mode="r")
    H, W = a.shape
    seam_cols = [int(round((lon + 180.0) * ppd)) for lon in range(-165, 180, 15)]
    rows = np.linspace(int(0.25 * H), int(0.75 * H), n_boundaries).astype(int)
    on, off = [], []
    for r in rows:
        band = np.asarray(a[r:r + 1, :]).ravel()
        d = np.abs(np.diff(band))
        good = np.isfinite(d)
        for c in seam_cols:
            if 2 < c < W - 3:
                if good[c - 1]:
                    on.append(d[c - 1])
                for k in (c - 3, c + 2):
                    if 0 <= k < d.size and good[k]:
                        off.append(d[k])
    on = np.array(on, dtype=np.float64)
    off = np.array(off, dtype=np.float64)
    res = dict(n_seam_samples=int(on.size), n_offseam_samples=int(off.size),
               mean_abs_dz_on_seam_m=float(on.mean()) if on.size else None,
               mean_abs_dz_off_seam_m=float(off.mean()) if off.size else None)
    if on.size and off.size and off.mean() > 0:
        res["ratio_on_over_off"] = float(on.mean() / off.mean())
        res["verdict"] = ("no seam artefact" if res["ratio_on_over_off"] < 3.0
                          else "SEAM ARTEFACT -- mosaic placement is suspect")
    return res


# ============================================================= MOON (exact 4x)

def build_moon(force=False):
    import rasterio
    H, W = GRIDS["moon"]["shape"]
    src = os.path.join(ROOT, "Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif")
    out_path = os.path.join(DEM_DIR, "moon_dem_1_64deg.npy")
    if C.is_complete(out_path, (H, W), "float32") and not force:
        print("  moon DEM already complete, reusing")
        v, ok = validate_dem_banded(out_path, "moon", 0, 1e-9)
        return v, ok, [src]

    with rasterio.open(src) as s:
        sh, sw = s.height, s.width
        sc, of, nd = s.scales[0], s.offsets[0], s.nodata
        f = sw // W
        assert sh // f == H and sh % f == 0 and sw % f == 0, "not an exact integer factor"
        print(f"  exact {f}x block average {sh}x{sw} -> {H}x{W}; "
              f"applying band scale {sc} (half-metres -> metres)")
        arr, part = open_memmap_part(out_path, (H, W), np.float32)
        t0 = time.perf_counter()
        nbytes = 0
        rows_per_band = band_rows_for_width(sw, 4, multiple_of=f)
        print(f"    band = {rows_per_band} source rows "
              f"({rows_per_band*sw*4/2**20:.0f} MB of float32)")
        for bi, r0 in enumerate(range(0, sh, rows_per_band)):
            r1 = min(sh, r0 + rows_per_band)
            blk = s.read(1, window=((r0, r1), (0, sw)))
            nbytes += blk.nbytes
            # float32, not float64: the float64 rule is for summed-area tables
            # that accumulate billions of values, not a mean over f*f=16 cells
            b = blk.astype(np.float32)
            good = np.ones(b.shape, dtype=np.float32) if nd is None else \
                (blk != nd).astype(np.float32)
            if nd is not None:
                b *= good                    # zero the nodata so it adds nothing
            b *= sc
            if of:
                b += of * good
            nb = (r1 - r0) // f
            # masked mean WITHOUT nanmean's internal copy
            ssum = b.reshape(nb, f, W, f).sum(axis=(1, 3), dtype=np.float32)
            cnt = good.reshape(nb, f, W, f).sum(axis=(1, 3), dtype=np.float32)
            with np.errstate(invalid="ignore", divide="ignore"):
                arr[r0 // f:r0 // f + nb] = np.where(cnt > 0, ssum / np.maximum(cnt, 1),
                                                     np.nan).astype(np.float32)
            del blk, b, good, ssum, cnt
            if bi % 8 == 0:
                arr.flush()                  # let dirty pages leave the working set
                el = time.perf_counter() - t0
                print(f"    {r1}/{sh} source rows  {el/60:.1f} min  "
                      f"{nbytes/2**20/max(el,1e-9):.0f} MB/s", flush=True)
    arr.flush()
    del arr
    finish_part(part, out_path)
    el = time.perf_counter() - t0
    say_peak("moon downsample")
    v, ok = validate_dem_banded(out_path, "moon", nbytes, el, extra=dict(
        downsample_factor=f, exact_integer_factor=True,
        scale_offset_applied=dict(scale=sc, offset=of,
                                  why="GeoTIFF band scale: stored int16 are HALF METRES"),
        nodata_rule=f"source nodata {nd} -> NaN BEFORE scaling; "
                    f"area average skips NaN; NaN only where no valid source pixel"))
    return v, ok, [src]


# ====================================================== MARS (area-weighted)

def axis_operator(n_src, src_origin, src_px, n_out, out_origin, out_px):
    """Sparse area-overlap operator mapping n_src cells onto n_out cells.

    Exact fractional overlap, so a non-integer factor needs no interpolation and
    invents no values. Entry (i, j) is the overlap LENGTH in degrees between
    output cell i and source cell j.

    Works for ASCENDING or DESCENDING axes. The candidate index range is found
    by mapping both target edges through the actual step and bracketing, so the
    sign of src_px is irrelevant. An earlier version derived the index from the
    bottom of the source range, which is index 0 only for an ascending axis; on
    the descending ROW axis it mirrored the lookup and left 0.3 percent of Mars
    valid. See test_axis_operator().
    """
    from scipy import sparse
    rows, cols, vals = [], [], []
    for i in range(n_out):
        a = out_origin + i * out_px
        b = out_origin + (i + 1) * out_px
        lo, hi = (a, b) if a <= b else (b, a)
        # map both edges to fractional source index, whatever the sign of src_px
        ja = (lo - src_origin) / src_px
        jb = (hi - src_origin) / src_px
        j0 = int(np.floor(min(ja, jb))) - 1
        j1 = int(np.ceil(max(ja, jb))) + 1
        for j in range(max(j0, 0), min(j1, n_src)):
            sa = src_origin + j * src_px
            sb = src_origin + (j + 1) * src_px
            slo, shi = (sa, sb) if sa <= sb else (sb, sa)
            ov = min(hi, shi) - max(lo, slo)
            if ov > 0:
                rows.append(i)
                cols.append(j)
                vals.append(ov)
    return sparse.csr_matrix((vals, (rows, cols)), shape=(n_out, n_src))


def test_axis_operator(verbose=True):
    """Self-test. Both axis directions must behave identically.

    This is the regression guard for the bug that left Mars 0.3 percent valid.
    """
    import numpy as _np
    fails = []

    asc = axis_operator(10, -180.0, 1.0, 5, -180.0, 2.0)
    desc = axis_operator(10, 90.0, -1.0, 5, 90.0, -2.0)
    for name, M in (("ascending", asc), ("descending", desc)):
        nnz = _np.diff(M.indptr)
        if not (nnz == 2).all():
            fails.append(f"{name}: nnz per output row {nnz.tolist()}, expected all 2")
        rowsum = _np.asarray(M.sum(axis=1)).ravel()
        if not _np.allclose(rowsum, 2.0):
            fails.append(f"{name}: row sums {rowsum.tolist()}, expected all 2.0 deg")
    # every source cell must be fully accounted for exactly once
    for name, M in (("ascending", asc), ("descending", desc)):
        colsum = _np.asarray(M.sum(axis=0)).ravel()
        if not _np.allclose(colsum, 1.0):
            fails.append(f"{name}: col sums {colsum.tolist()}, expected all 1.0 deg")
    # a non-integer factor must still conserve total length
    frac = axis_operator(7, 0.0, 1.0, 3, 0.0, 7.0 / 3.0)
    tot = float(frac.sum())
    if abs(tot - 7.0) > 1e-9:
        fails.append(f"fractional: total overlap {tot}, expected 7.0")

    if verbose:
        print("    axis_operator self-test: " +
              ("PASS" if not fails else "FAIL"))
        for f in fails:
            print("      " + f)
    return fails


def build_mars(force=False):
    import rasterio
    H, W = GRIDS["mars"]["shape"]
    src = os.path.join(ROOT, "sources", "tier1_terrain",
                       "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif")
    out_path = os.path.join(DEM_DIR, "mars_dem_1_128deg.npy")
    if C.is_complete(out_path, (H, W), "float32") and not force:
        print("  mars DEM already complete, reusing")
        v, ok = validate_dem_banded(out_path, "mars", 0, 1e-9)
        return v, ok, [src]

    with rasterio.open(src) as s:
        sh, sw = s.height, s.width
        spx = s.transform.a
        s_left, s_top = s.transform.c, s.transform.f
        nd, sc, of = s.nodata, s.scales[0], s.offsets[0]
        out_px = 1.0 / GRIDS["mars"]["ppd"]
        factor = (sw / 360.0) / GRIDS["mars"]["ppd"]
        print(f"  area-weighted {sh}x{sw} -> {H}x{W}, factor {factor:.6f} "
              f"(non-integer, exact fractional overlap)")
        print(f"  source lon extent {s_left} .. {s_left + sw * spx}")
        print(f"  0.46 px short of global in lon, 0.23 px in lat: the easternmost "
              f"target column and southernmost row are PARTIALLY covered and are "
              f"averaged over the fraction that exists")

        if test_axis_operator():
            raise RuntimeError("axis_operator self-test FAILED; refusing to resample")
        print("  building the sparse column operator once ...")
        Cop = axis_operator(sw, s_left, spx, W, -180.0, out_px)
        print(f"    column operator {Cop.shape}, {Cop.nnz:,} non-zeros")
        say_peak("column operator")

        arr, part = open_memmap_part(out_path, (H, W), np.float32)
        t0 = time.perf_counter()
        nbytes = 0
        # Budget on the SOURCE bytes actually held, not the output rows. Each
        # output row pulls `factor` source rows, and TWO full-width float32
        # arrays are live at once (values and validity weights). Sizing by
        # output rows against the source width overshot by about 2*factor.
        per_out_row = 2 * factor * sw * 4
        out_band = max(32, int((512 * 2 ** 20) // per_out_row))
        for o0 in range(0, H, out_band):
            o1 = min(H, o0 + out_band)
            lat_hi = 90.0 - o0 * out_px
            lat_lo = 90.0 - o1 * out_px
            j0 = max(0, int(np.floor((s_top - lat_hi) / abs(spx))) - 2)
            j1 = min(sh, int(np.ceil((s_top - lat_lo) / abs(spx))) + 2)
            Rop = axis_operator(j1 - j0, s_top - j0 * abs(spx), -abs(spx),
                                o1 - o0, 90.0 - o0 * out_px, -out_px)
            blk = s.read(1, window=((j0, j1), (0, sw)))
            nbytes += blk.nbytes
            b = blk.astype(np.float32)
            valid = np.ones(b.shape, dtype=np.float32)
            if nd is not None:
                bad = blk == nd
                b[bad] = 0.0
                valid[bad] = 0.0
            b *= sc
            if of:
                b += of * valid
            # columns first (sparse @ dense), then rows: keeps the peak small
            num = (Cop @ b.T).T
            den = (Cop @ valid.T).T
            num = Rop @ num
            den = Rop @ den
            with np.errstate(invalid="ignore", divide="ignore"):
                res = np.where(den > 0, num / np.maximum(den, 1e-30), np.nan)
            arr[o0:o1] = res.astype(np.float32)
            del blk, b, valid, num, den, res, Rop
            el = time.perf_counter() - t0
            print(f"    {o1}/{H} output rows  {el/60:.1f} min  "
                  f"{nbytes/2**20/max(el,1e-9):.0f} MB/s", flush=True)
    arr.flush()
    del arr
    finish_part(part, out_path)
    el = time.perf_counter() - t0
    say_peak("mars resample")
    v, ok = validate_dem_banded(out_path, "mars", nbytes, el, extra=dict(
        downsample_factor=round(factor, 6),
        exact_integer_factor=False,
        resampling="exact fractional area overlap in both axes, no interpolation",
        source_extent_note=("source is 359.99845 deg wide and 179.99922 tall, "
                            "0.46 px short in lon and 0.23 px in lat; the "
                            "easternmost target column and southernmost row are "
                            "averaged over the fraction that exists"),
        scale_offset_applied=dict(scale=sc, offset=of, why="GeoTIFF band scale"),
        nodata_rule=(f"source nodata {nd} excluded from the weighted mean; output "
                     f"NaN only where no valid source pixel overlaps")))
    return v, ok, [src]


# ================================================== EARTH LAND MASK (WorldClim)

def build_land_mask(force=False):
    """The land mask is the WorldClim valid-data FOOTPRINT, not an ETOPO land test.

    v1 defines it as the "WorldClim 2.1 10' tmin/tmax valid-data footprint (valid
    in all 12 months of both)". ETOPO carries valid data over the ocean too, so
    an ETOPO footprint would not be a land mask at all. At 30 arc-sec that
    footprint differs from the 10-arcmin one, which is why it is rebuilt here.

    The 24 members are decompressed ONCE and the per-cell valid-month count is
    PERSISTED, so Phase 3 reuses it instead of repeating the pass.
    """
    import rasterio
    H, W = GRIDS["earth"]["shape"]
    SH, SW = 21600, 43200
    out_path = os.path.join(DEM_DIR, "earth_land_mask_1_240deg.npy")
    nvalid_path = os.path.join(DEM_DIR, "_earth_wc30s_valid_months.npy")
    zips = {v: os.path.join(ROOT, "sources", "tier2_thermal", f"wc2.1_30s_{v}.zip")
            for v in ("tmin", "tmax")}
    srcs = list(zips.values())
    nbytes, el = 0, 1e-9

    if C.is_complete(out_path, (H, W), "bool") and not force:
        print("  land mask already complete, reusing")
    else:
        if C.is_complete(nvalid_path, (SH, SW), "uint8") and not force:
            print("  reusing the persisted valid-month count")
        else:
            print(f"  counting valid months across 24 WorldClim 30s members "
                  f"({SH}x{SW}); one sequential pass per member")
            nvm, nvpart = open_memmap_part(nvalid_path, (SH, SW), np.uint8)
            nvm[:] = 0
            t0 = time.perf_counter()
            for var in ("tmin", "tmax"):
                for m in range(1, 13):
                    member = f"zip://{zips[var]}!wc2.1_30s_{var}_{m:02d}.tif"
                    with rasterio.open(member) as s:
                        if (s.height, s.width) != (SH, SW):
                            raise RuntimeError(f"{member}: shape {s.height}x{s.width} "
                                               f"!= {SH}x{SW}")
                        nd = s.nodata
                        for r0 in range(0, SH, BAND_ROWS):
                            r1 = min(SH, r0 + BAND_ROWS)
                            blk = s.read(1, window=((r0, r1), (0, SW)))
                            nbytes += blk.nbytes
                            good = np.isfinite(blk) & (blk > -1e30)
                            if nd is not None:
                                good &= blk != nd
                            nvm[r0:r1] += good.astype(np.uint8)
                            del blk, good
                    el = time.perf_counter() - t0
                    print(f"    {var}_{m:02d}  {el/60:.1f} min  "
                          f"{nbytes/2**20/max(el,1e-9):.0f} MB/s", flush=True)
            nvm.flush()
            del nvm
            finish_part(nvpart, nvalid_path)
            el = time.perf_counter() - t0
            say_peak("worldclim valid-month count")

        nv = np.load(nvalid_path, mmap_mode="r")
        print("  land = valid in ALL 24 members, nearest-upsampled 2x "
              "from 1/120 to 1/240 deg")
        mm, mpart = open_memmap_part(out_path, (H, W), np.bool_)
        for r0 in range(0, SH, BAND_ROWS):
            r1 = min(SH, r0 + BAND_ROWS)
            land = np.asarray(nv[r0:r1]) == 24
            mm[r0 * 2:r1 * 2] = np.repeat(np.repeat(land, 2, axis=0), 2, axis=1)
            del land
        mm.flush()
        del mm
        finish_part(mpart, out_path)
        say_peak("land mask upsample")

    mask = np.load(out_path, mmap_mode="r")
    cell = 180.0 / H
    lat = 90.0 - (np.arange(H) + 0.5) * cell
    cosw = np.cos(np.radians(lat))
    n_land = 0
    aw_land = aw_tot = 0.0
    for r0 in range(0, H, BAND_ROWS):
        r1 = min(H, r0 + BAND_ROWS)
        blk = np.asarray(mask[r0:r1])
        n_land += int(blk.sum())
        aw_land += float((blk.sum(axis=1) * cosw[r0:r1]).sum())
        aw_tot += float(W * cosw[r0:r1].sum())
        del blk
    cell_pct = 100.0 * n_land / (H * W)
    area_pct = 100.0 * aw_land / aw_tot
    OLD_CELL, OLD_AREA = 34.6373, 30.2364
    print(f"\n  --- land mask ---")
    print(f"    shape {list(mask.shape)}  dtype {mask.dtype}")
    print(f"    land cells {n_land:,} = {cell_pct:.4f}% BY CELL COUNT")
    print(f"    land area                = {area_pct:.4f}% BY AREA (cos-lat weighted)")
    print(f"    old 1/10-deg grid: {OLD_CELL}% by cell, {OLD_AREA}% by area")
    print(f"    CHANGE: {cell_pct - OLD_CELL:+.4f} pp by cell, "
          f"{area_pct - OLD_AREA:+.4f} pp by area")

    entry = dict(
        phase="1", body="earth", variable="land_mask",
        units="boolean (True = land)",
        file=os.path.relpath(out_path, ROOT).replace("\\", "/"),
        source_files=[os.path.relpath(p, ROOT).replace("\\", "/") for p in srcs],
        all_sources_resolve=all(os.path.exists(p) for p in srcs),
        definition=("the WorldClim 2.1 30 arc-second valid-data footprint: a cell "
                    "is land where ALL 24 members (12 months of tmin AND 12 of "
                    "tmax) carry valid data. NOT an ETOPO-derived land test -- "
                    "ETOPO has valid data over the ocean, so its footprint is not "
                    "a land mask."),
        native_resolution="30 arc-sec = 1/120 deg (21600x43200)",
        working_resolution="1/240 deg (43200x86400), nearest-upsampled 2x",
        resampling=("nearest neighbour for the 2x upsample: no invented values, "
                    "footprint unchanged (the recorded resampling_policy)"),
        nodata_rule="a member's nodata, non-finite, or value < -1e30 counts invalid",
        shape=list(mask.shape), dtype=str(mask.dtype),
        land_cells=n_land,
        land_percent_by_cell=round(cell_pct, 4),
        land_percent_by_area=round(area_pct, 4),
        previous_grid_percent_by_cell=OLD_CELL,
        previous_grid_percent_by_area=OLD_AREA,
        change_pp_by_cell=round(cell_pct - OLD_CELL, 4),
        change_pp_by_area=round(area_pct - OLD_AREA, 4),
        valid_month_count_cached=os.path.relpath(nvalid_path, ROOT).replace("\\", "/"),
        cache_note=("the per-cell valid-month count is persisted so Phase 3 reuses "
                    "it rather than decompressing the 24 members again"),
        bytes_read=nbytes, elapsed_s=round(el, 1),
        throughput_MB_s=round(nbytes / 2 ** 20 / max(el, 1e-9), 1) if nbytes else None,
        slope_convention=SLOPE_CONVENTION,
        window_convention=WINDOW_CONVENTION,
        convention_warning=CONVENTION_WARNING,
        peak_rss_gib=peak_rss_gib(),
        build_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    C.manifest_write("earth_land_mask", entry)
    return entry


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", default="all",
                    choices=["earth", "moon", "mars", "mask", "all"])
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)

    print("=" * 78)
    print("PHASE 1 -- THE THREE COMMON DEMs + EARTH LAND MASK")
    print("=" * 78)
    free = C.free_gib(ROOT)
    print(f"\nfree disk on {ROOT}: {free:.1f} GiB   floor {DISK_FLOOR_GIB} GiB")
    C.require_disk(DISK_FLOOR_GIB, ROOT)
    print("  disk check PASSED")
    os.makedirs(DEM_DIR, exist_ok=True)

    todo = ["earth", "moon", "mars", "mask"] if a.body == "all" else [a.body]
    t_all = time.perf_counter()
    summary = {}
    for body in todo:
        print(f"\n{'=' * 78}\n{body.upper()}\n{'=' * 78}")
        if body == "mask":
            summary["mask"] = build_land_mask(force=a.force)
            continue
        fn = {"earth": build_earth, "moon": build_moon, "mars": build_mars}[body]
        v, ok, srcs = fn(force=a.force)
        print_validation(v, body)
        extra = {k: v[k] for k in list(v) if k in (
            "tiles_placed", "downsample_factor", "exact_integer_factor",
            "resampling", "source_extent_note", "scale_offset_applied",
            "nodata_rule")}
        method = {
            "earth": ("mosaic of 288 ETOPO 2022 15 arc-second surface tiles "
                      "(3600x3600 each) placed on an exact 1/240 degree grid. NO "
                      "RESAMPLING: 15 arc-sec IS 1/240 degree, verified from the "
                      "tile headers to within 1e-12"),
            "moon": ("exact 4x block area-average of LOLA LDEM 118 m "
                     "(256 px/deg -> 64 px/deg), with the GeoTIFF band scale 0.5 "
                     "applied so stored half-metres become metres"),
            "mars": ("exact fractional area-overlap resampling of the HRSC/MOLA "
                     "200 m blend (296.372222 px/deg -> 128 px/deg, factor "
                     "2.315408); no interpolation"),
        }[body]
        native = {
            "earth": "15 arc-sec = 1/240 deg (288 tiles of 3600x3600)",
            "moon": "256 px/deg = 118.4506 m (46080x92160)",
            "mars": "296.372222 px/deg = 200 m (53347x106694)",
        }[body]
        manifest_dem(body, v, method, srcs, native, extra)
        summary[body] = dict(validation=v, scale_gate_passed=ok)
        if body == "earth":
            sc = seam_check(os.path.join(DEM_DIR, "earth_dem_1_240deg.npy"))
            print(f"\n  --- seam check across tile boundaries ---")
            for k, val in sc.items():
                print(f"    {k}: {val}")
            C.manifest_write("dem_earth_seam_check", sc)
            summary["earth"]["seam_check"] = sc
        if not ok:
            print(f"\n  !! {body} SCALE GATE FAILED -- stopping before the next body")
            break

    el = time.perf_counter() - t_all
    pk = peak_rss_gib()
    print(f"\n{'=' * 78}")
    print(f"PHASE 1 elapsed {el / 60:.1f} min   peak RAM "
          f"{'unknown' if pk is None else f'{pk:.2f} GiB'} (cap {PEAK_CAP_GIB})")
    print(f"free disk now {C.free_gib(ROOT):.1f} GiB")
    print("STOPPING. Do not begin Phase 2.")
    io.open(os.path.join(DEM_DIR, "phase1_summary.json"), "w",
            encoding="utf-8").write(json.dumps(summary, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
