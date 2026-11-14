"""
Shared machinery for building the variable cube. STEP 1 ONLY.

Nothing in here computes a distance, a target, a null or a ranking. If a later
edit adds one, it belongs in a different file.

Conventions, all settled before this was written:
  HEALPix NESTED, Nside 1024 Earth / 256 Moon / 512 Mars
  common terrain working grid 463 m on every body
  slope baseline 7 km, ruggedness and TPI 21 km
  all temperatures in KELVIN
  TPI < 0 means INSIDE A BOWL
  float32 on disk, float64 for any accumulator
"""

import io
import json
import os
import shutil
import time

import numpy as np

ROOT = os.environ.get("ANALOG_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # was fixed to one drive until 14 Nov 2026
OUT_DIR = os.path.join(ROOT, "cube")
WORK_DIR = os.path.join(ROOT, "cube", "_work")
MANIFEST = os.path.join(OUT_DIR, "cube_manifest.json")

# Body radii, metres. Taken from the source CRS where the raster declares one
# (LOLA's SPHEROID says 1737400), not from a table.
BODY_RADIUS_M = {"earth": 6371000.0, "moon": 1737400.0, "mars": 3396200.0}
NSIDE = {"earth": 1024, "moon": 256, "mars": 512}

TPI_SIGN_NOTE = ("TPI = z - mean(z within the window). TPI < 0 means the cell is "
                 "LOWER than its surroundings, i.e. INSIDE A BOWL (crater floor, "
                 "basin, valley). TPI > 0 means a rim, ridge or peak.")


# --------------------------------------------------------------------- plumbing

def free_gib(path):
    return shutil.disk_usage(path).free / 2 ** 30


def require_disk(gib, path=ROOT):
    have = free_gib(path)
    if have < gib:
        raise RuntimeError(f"REFUSING TO START: {have:.1f} GiB free on {path}, "
                           f"{gib} GiB required")
    return have


def atomic_save(path, arr):
    """Write to <name>.part, rename only when whole. A crashed run then leaves
    either a complete file or a .part, never a truncated .npy that a resume
    would trust."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    part = path + ".part"
    np.save(part, arr, allow_pickle=False)
    # np.save appends .npy if the name lacks it; guard both spellings
    produced = part if os.path.exists(part) else part + ".npy"
    os.replace(produced, path)
    return path


def is_complete(path, expect_shape=None, expect_dtype=None):
    """Resume test. A file counts as done only if it loads and matches."""
    if not os.path.exists(path):
        return False
    try:
        a = np.load(path, mmap_mode="r")
    except Exception:
        return False
    if expect_shape is not None and tuple(a.shape) != tuple(expect_shape):
        return False
    if expect_dtype is not None and a.dtype != np.dtype(expect_dtype):
        return False
    return True


class Clock:
    def __init__(self, total_stages):
        self.t0 = time.perf_counter()
        self.total = total_stages
        self.done = 0

    def stage(self, label):
        self.done += 1
        el = time.perf_counter() - self.t0
        rate = el / max(self.done - 1, 1) if self.done > 1 else el
        rem = rate * (self.total - self.done)
        print(f"  [{self.done}/{self.total}] {label}   elapsed {el/60:.1f} min, "
              f"est remaining {rem/60:.1f} min", flush=True)


# ------------------------------------------------------------------ DEM reading

def dem_grid_geometry(height, width):
    """Cell-centre latitudes and longitudes of a global equirectangular grid.

    row 0 is the TOP (+90), col 0 the WEST edge (-180). Returns (lat, lon,
    cell_deg) where lat has one entry per row and lon one per column.
    """
    cell_lat = 180.0 / height
    cell_lon = 360.0 / width
    lat = 90.0 - (np.arange(height) + 0.5) * cell_lat
    lon = -180.0 + (np.arange(width) + 0.5) * cell_lon
    return lat, lon, (cell_lat, cell_lon)


def block_mean_downsample(src_path, factor, band=1, scale=None, offset=None,
                          nodata=None, progress_every=400):
    """Stream a raster and area-average it down by an integer factor.

    Reads `factor` rows at a time, so peak memory is one band and not the
    raster. Returns (array float32 with NaN for nodata, n_valid_source,
    n_nodata_source, applied_scale, applied_offset).

    scale/offset default to the GeoTIFF band values. rasterio does NOT apply
    them on read -- LOLA stores half-metres with scales=(0.5,), so skipping this
    doubles every lunar elevation.
    """
    import rasterio
    with rasterio.open(src_path) as s:
        h, w = s.height, s.width
        if h % factor or w % factor:
            raise ValueError(f"{src_path}: shape {h}x{w} is not divisible by {factor}")
        sc = s.scales[band - 1] if scale is None else scale
        of = s.offsets[band - 1] if offset is None else offset
        nd = s.nodata if nodata is None else nodata
        oh, ow = h // factor, w // factor
        out = np.empty((oh, ow), dtype=np.float32)
        n_valid = n_nodata = 0
        for i in range(oh):
            blk = s.read(band, window=((i * factor, (i + 1) * factor), (0, w)))
            blk = blk.astype(np.float64)
            if nd is not None:
                bad = blk == nd
                n_nodata += int(bad.sum())
                blk[bad] = np.nan
            blk = blk * sc + of
            # (factor, w) -> (factor, ow, factor) -> nanmean over both block axes
            blk = blk.reshape(factor, ow, factor)
            with np.errstate(invalid="ignore"):
                row = np.nanmean(blk, axis=(0, 2))
            n_valid += int(np.isfinite(row).sum())
            out[i] = row.astype(np.float32)
            if progress_every and (i + 1) % progress_every == 0:
                print(f"      downsample {i+1}/{oh} rows", flush=True)
    return out, n_valid, n_nodata, sc, of


# ------------------------------------------------------- summed-area machinery

def _sat(a):
    """Summed-area table of a, and of its validity mask, in float64.

    float64 is not optional. Earth at 463 m accumulates 3.7e9 values; a float32
    running sum loses the low-order bits long before the end of a row and the
    differenced rectangle sums come out visibly wrong.
    """
    v = np.isfinite(a)
    z = np.where(v, a, 0.0).astype(np.float64)
    S = np.zeros((a.shape[0] + 1, a.shape[1] + 1), dtype=np.float64)
    N = np.zeros_like(S)
    np.cumsum(np.cumsum(z, axis=0), axis=1, out=S[1:, 1:])
    np.cumsum(np.cumsum(v.astype(np.float64), axis=0), axis=1, out=N[1:, 1:])
    return S, N


def _rect(S, r0, r1, c0, c1):
    """Inclusive-exclusive rectangle sum from a summed-area table."""
    return S[r1, c1] - S[r0, c1] - S[r1, c0] + S[r0, c0]


def window_stat_varying_ew(a, half_ns, half_ew_per_row, want="std",
                           min_valid_frac=0.5, shift_mean=True):
    """Windowed std or mean with an EW half-width that varies by row.

    The EW half-width widens as 1/cos(lat) to hold a constant physical extent,
    so the window is a different number of cells on every row and a separable
    filter will not do it. A summed-area table makes each row O(width)
    regardless of how wide its window is.

    shift_mean subtracts a global mean before accumulating. var = E[z^2] - E[z]^2
    is catastrophically cancelling on nearly flat ground (mare interior, ocean
    floor, playa) where both terms are large and nearly equal; shifting removes
    almost all of it for free.
    """
    h, w = a.shape
    off = 0.0
    if shift_mean:
        finite = a[np.isfinite(a)]
        off = float(finite.mean()) if finite.size else 0.0
    b = a - off
    S, N = _sat(b)
    S2, _ = _sat(b * b)
    out = np.full((h, w), np.nan, dtype=np.float32)

    cols = np.arange(w)
    for r in range(h):
        hw = int(half_ew_per_row[r])
        if hw < 1:
            continue
        r0 = max(0, r - half_ns)
        r1 = min(h, r + half_ns + 1)
        # longitude WRAPS, so a window crossing the antimeridian is the union of
        # two rectangles. Latitude CLIPS. Getting these the wrong way round
        # either truncates at the dateline or teleports across the pole.
        c0 = cols - hw
        c1 = cols + hw + 1
        left = np.clip(c0, 0, w)
        right = np.clip(c1, 0, w)
        n = _rect(N, r0, r1, left, right)
        s = _rect(S, r0, r1, left, right)
        s2 = _rect(S2, r0, r1, left, right)
        # wrapped remainder on the west side
        wrap_lo = c0 < 0
        if wrap_lo.any():
            lo = (c0[wrap_lo] % w)
            n[wrap_lo] += _rect(N, r0, r1, lo, w)
            s[wrap_lo] += _rect(S, r0, r1, lo, w)
            s2[wrap_lo] += _rect(S2, r0, r1, lo, w)
        # wrapped remainder on the east side
        wrap_hi = c1 > w
        if wrap_hi.any():
            hi = (c1[wrap_hi] - w)
            n[wrap_hi] += _rect(N, r0, r1, 0, hi)
            s[wrap_hi] += _rect(S, r0, r1, 0, hi)
            s2[wrap_hi] += _rect(S2, r0, r1, 0, hi)

        cells = (r1 - r0) * np.minimum(2 * hw + 1, w)
        ok = n >= min_valid_frac * cells
        with np.errstate(invalid="ignore", divide="ignore"):
            m1 = np.where(ok, s / np.maximum(n, 1), np.nan)
            if want == "mean":
                out[r] = (m1 + off).astype(np.float32)
            else:
                m2 = np.where(ok, s2 / np.maximum(n, 1), np.nan)
                var = np.maximum(m2 - m1 * m1, 0.0)
                out[r] = np.sqrt(var).astype(np.float32)
    return out


# ------------------------------------------------------------------- variables

def ew_half_width(lat_deg, cell_km_ns, extent_km, width, min_cells=1):
    """Half-width in CELLS per row so the east-west extent stays `extent_km`.

    The window spans 2*half+1 cells, so the half-width must be solved from
    (n_cells - 1) / 2 and NOT from n_cells / 2. Solving for the half and then
    adding the centre cell overshoots by one cell: measured at the smoke grid, a
    21 km window came out 24.64 km, 17 percent over.

    No cos-latitude clamp: the stencil widens toward the poles. Capped at half
    the parallel, because a window wider than the parallel wraps onto itself --
    in those rows the physical extent is SHORTER than requested, which
    `saturation_report` counts.
    """
    cos = np.maximum(np.cos(np.radians(lat_deg)), 1e-9)
    n_cells = extent_km / (cell_km_ns * cos)
    cells = np.rint((n_cells - 1.0) / 2.0)
    cap = max(1, (width - 1) // 2)
    return np.clip(cells, min_cells, cap).astype(np.int64)


def saturation_report(lat_deg, cell_km_ns, extent_km, width):
    """How many rows had their east-west stencil capped, and where.

    A capped row measures a SHORTER physical extent than asked for. Reporting it
    is the difference between a known limitation and a silent one.
    """
    cos = np.maximum(np.cos(np.radians(lat_deg)), 1e-9)
    want = np.rint((extent_km / (cell_km_ns * cos) - 1.0) / 2.0)
    cap = max(1, (width - 1) // 2)
    sat = want > cap
    out = dict(n_rows_saturated=int(sat.sum()), cap_half_cells=int(cap))
    if sat.any():
        out["saturated_lat_range"] = [float(lat_deg[sat].min()), float(lat_deg[sat].max())]
        # the extent actually achieved in the worst row
        worst = int(np.argmax(want))
        out["worst_row_lat"] = float(lat_deg[worst])
        out["worst_row_extent_km_achieved"] = float(
            (2 * cap + 1) * cell_km_ns * cos[worst])
        out["requested_extent_km"] = float(extent_km)
    return out


def slope_deg(z, lat_deg, cell_km_ns, baseline_km, width):
    """Slope in DEGREES over a constant physical baseline.

    slope = atan(hypot(dz_ns/dist_ns, dz_ew/dist_ew))

    A CENTRED difference: dz is taken across +/-m cells and divided by the full
    2m-cell span. v1 used an n-cell forward difference, which offsets the result
    half a baseline from the cell it is written to. v1's terrain layers are being
    rebuilt anyway (the baseline moved 11 km -> 7 km and the grid moved to
    HEALPix), so the centred form is adopted here rather than inherited.
    """
    h, w = z.shape
    m_ns = max(1, int(round(baseline_km / (2.0 * cell_km_ns))))
    dist_ns = 2.0 * m_ns * cell_km_ns * 1000.0

    dz_ns = np.full_like(z, np.nan)
    dz_ns[m_ns:h - m_ns] = z[2 * m_ns:] - z[:h - 2 * m_ns]

    cos = np.maximum(np.cos(np.radians(lat_deg)), 1e-9)
    m_ew = np.clip(np.rint(baseline_km / (2.0 * cell_km_ns * cos)), 1,
                   w // 2).astype(np.int64)
    dz_ew = np.full_like(z, np.nan)
    dist_ew = np.empty(h, dtype=np.float64)
    for r in range(h):
        k = int(m_ew[r])
        dz_ew[r] = np.roll(z[r], -k) - np.roll(z[r], k)      # longitude wraps
        dist_ew[r] = 2.0 * k * cell_km_ns * cos[r] * 1000.0

    with np.errstate(invalid="ignore", divide="ignore"):
        g = np.hypot(dz_ns / dist_ns, dz_ew / dist_ew[:, None])
        out = np.degrees(np.arctan(g)).astype(np.float32)
    # the east-west stencil saturates where half the parallel is shorter than
    # the baseline; count it rather than capping silently
    want_ew = np.rint(baseline_km / (2.0 * cell_km_ns * cos))
    sat = want_ew > (w // 2)
    return out, dict(ns_cells_each_side=m_ns,
                     ns_baseline_km=round(dist_ns / 1000.0, 4),
                     ns_baseline_km_requested=baseline_km,
                     ew_cells_each_side_equator=int(m_ew[h // 2]),
                     ew_cells_each_side_max=int(m_ew.max()),
                     form="centred difference over +/-m cells",
                     n_rows_ew_saturated=int(sat.sum()),
                     saturated_lat_range=([float(lat_deg[sat].min()),
                                           float(lat_deg[sat].max())]
                                          if sat.any() else None))


def ruggedness_m(z, lat_deg, cell_km_ns, window_km, width):
    half_ns = max(1, int(round((window_km / cell_km_ns - 1.0) / 2.0)))
    half_ew = ew_half_width(lat_deg, cell_km_ns, window_km, width, min_cells=1)
    out = window_stat_varying_ew(z, half_ns, half_ew, want="std")
    return out, dict(ns_half_cells=half_ns,
                     ns_window_km=round((2 * half_ns + 1) * cell_km_ns, 4),
                     ns_window_km_requested=window_km,
                     ew_half_cells_equator=int(half_ew[len(lat_deg) // 2]),
                     ew_half_cells_max=int(half_ew.max()),
                     min_valid_fraction=0.5,
                     saturation=saturation_report(lat_deg, cell_km_ns, window_km, width))


def tpi_m(z, lat_deg, cell_km_ns, window_km, width):
    half_ns = max(1, int(round((window_km / cell_km_ns - 1.0) / 2.0)))
    half_ew = ew_half_width(lat_deg, cell_km_ns, window_km, width, min_cells=1)
    mean = window_stat_varying_ew(z, half_ns, half_ew, want="mean")
    return (z - mean).astype(np.float32), dict(
        ns_half_cells=half_ns,
        ns_window_km=round((2 * half_ns + 1) * cell_km_ns, 4),
        ns_window_km_requested=window_km,
        ew_half_cells_equator=int(half_ew[len(lat_deg) // 2]),
        sign_convention=TPI_SIGN_NOTE,
        saturation=saturation_report(lat_deg, cell_km_ns, window_km, width))


# --------------------------------------------------------------- HEALPix binning

def bin_to_healpix(values, lat_deg, lon_deg, nside, cos_weight=True):
    """Area-average a global lat/lon field onto HEALPix NESTED.

    cos_weight: a lat/lon cell's area is proportional to cos(lat), so several
    cells falling in one HEALPix pixel must be weighted by it. HEALPix pixels are
    themselves equal-area -- that is why no area weighting is needed AFTER this
    step -- but the grid being binned FROM is not, so the weight belongs here.
    """
    from astropy import units as u
    from astropy_healpix import HEALPix

    hp = HEALPix(nside=nside, order="nested")
    npix = hp.npix
    h, w = values.shape
    acc = np.zeros(npix, dtype=np.float64)
    wsum = np.zeros(npix, dtype=np.float64)

    for r in range(h):
        row = values[r]
        good = np.isfinite(row)
        if not good.any():
            continue
        lonr = lon_deg[good]
        latr = np.full(lonr.shape, lat_deg[r])
        idx = hp.lonlat_to_healpix(lonr * u.deg, latr * u.deg)
        wt = (np.cos(np.radians(lat_deg[r])) if cos_weight else 1.0)
        np.add.at(acc, idx, row[good].astype(np.float64) * wt)
        np.add.at(wsum, idx, np.full(idx.shape, wt, dtype=np.float64))

    out = np.full(npix, np.nan, dtype=np.float32)
    nz = wsum > 0
    out[nz] = (acc[nz] / wsum[nz]).astype(np.float32)
    return out, dict(npix=int(npix), n_filled=int(nz.sum()),
                     cos_lat_weighted=bool(cos_weight))


def healpix_lat(nside):
    from astropy import units as u
    from astropy_healpix import HEALPix
    hp = HEALPix(nside=nside, order="nested")
    _, lat = hp.healpix_to_lonlat(np.arange(hp.npix))
    return lat.to_value(u.deg)


def validate_layer(arr, nside, name):
    """Shape, dtype, validity globally and in the three polar bands."""
    lat = healpix_lat(nside)
    v = np.isfinite(arr)
    bands = {"global": np.ones_like(v, bool),
             "abs_lat_gt_60": np.abs(lat) > 60,
             "abs_lat_gt_80": np.abs(lat) > 80,
             "abs_lat_gt_85": np.abs(lat) > 85,
             "lat_85S_to_90S": lat <= -85.0}
    pct = {}
    for b, m in bands.items():
        tot = int(m.sum())
        pct[b] = round(100.0 * int((v & m).sum()) / tot, 4) if tot else None
    f = arr[v].astype(np.float64)
    stats = {}
    if f.size:
        q = np.percentile(f, [1, 50, 99])
        stats = dict(min=float(f.min()), p1=float(q[0]), p50=float(q[1]),
                     p99=float(q[2]), max=float(f.max()))
    return dict(name=name, shape=list(arr.shape), expected_npix=12 * nside ** 2,
                shape_ok=bool(arr.size == 12 * nside ** 2),
                dtype=str(arr.dtype), n_valid=int(v.sum()),
                percent_valid=pct, stats=stats)


# ---------------------------------------------------------------- the manifest

def manifest_write(key, entry):
    """Append one layer's entry AS IT IS BUILT, never at the end."""
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    man = {}
    if os.path.exists(MANIFEST):
        try:
            man = json.load(io.open(MANIFEST, encoding="utf-8"))
        except ValueError:
            man = {}
    man.setdefault("layers", {})[key] = entry
    man["updated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    tmp = MANIFEST + ".part"
    io.open(tmp, "w", encoding="utf-8").write(json.dumps(man, indent=1, ensure_ascii=False))
    os.replace(tmp, MANIFEST)
    return MANIFEST
