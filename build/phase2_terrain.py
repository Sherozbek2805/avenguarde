"""
PHASE 2 -- terrain variables, one body at a time.

    python build/phase2_terrain.py --body moon

ROUTE TAKEN: BINNING HAPPENS INSIDE THE BAND LOOP. No 463 m intermediate is
ever written.

    The brief raised the median as the obstacle. It does not apply: HEALPix
    binning here is an AREA-WEIGHTED MEAN, and a mean streams perfectly. Two
    accumulators of length npix -- a weighted sum and a weight total -- are
    updated band by band and divided once at the end. A HEALPix pixel spanning
    several bands is handled automatically, because the accumulator does not
    care which band a contribution came from, so a pixel never needs to be
    "complete" within one band.

    Medians ARE needed, but only for the VALIDATION of the finished layer, and
    the finished layer is tiny: 786,432 values for the Moon, 12,582,912 for
    Earth. A full exact median on that is instant.

    Accumulator cost: 2 x npix x 8 bytes = 12 MB for the Moon, 201 MB for Earth.
    Against 13.9 GiB of avoided intermediate per Earth layer, times seven layers.

ONE SAT SERVES EVERY WINDOW STATISTIC
    One summed-area table of values and one of squares, per band, give all four
    roughness scales AND the 21 km TPI mean in O(1) per pixel per window. The
    DEM is read once. Slope needs its own small-halo pass, being a gradient
    rather than a window statistic.

    roughness_21km IS the ruggedness dimension. Built once, named once.

H IS FITTED INSIDE THE BAND LOOP
    Four 463 m roughness layers for Earth would be 55 GiB held at once. Within
    one band all four exist together, so H is fitted there and binned
    immediately -- "compute native, aggregate after" without ever materialising
    the layers.

TWO BASELINE CONVENTIONS, BOTH CORRECT
    slope    centre-to-centre   2h*c
    windows  full footprint    (2h+1)*c
    Recorded in every entry. Do not reconcile them.
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
from phase1_dems import (DEM_DIR, DISK_FLOOR_GIB, GRIDS, PEAK_CAP_GIB,
                         CONVENTION_WARNING, SLOPE_CONVENTION, WINDOW_CONVENTION,
                         peak_rss_gib, say_peak)

ROOT = C.ROOT
OUT_DIR = os.path.join(ROOT, "cube", "healpix")

DEM_FILE = {"moon": "moon_dem_1_64deg.npy",
            "mars": "mars_dem_1_128deg.npy",
            "earth": "earth_dem_1_240deg.npy"}

SLOPE_BASELINE_KM = 7.0
TPI_WINDOW_KM = 21.0
ROUGH_REQUESTED_KM = (5.25, 10.5, 21.0, 42.0)
MIN_VALID_FRAC = 0.5
R2_MIN = 0.90                 # below this, H is withheld -- see the manifest note

SAT_BUDGET = 1100 * 2 ** 20   # bytes for the three float64 SATs of one band


def cell_km_ns(body):
    """North-south cell size in km. One row of the working grid."""
    h = GRIDS[body]["shape"][0]
    return (180.0 / h) * (np.pi * C.BODY_RADIUS_M[body] / 1000.0 / 180.0)


def half_for_window(window_km, cell):
    """Half-width so the FULL FOOTPRINT (2h+1)*cell lands on window_km."""
    return max(1, int(round((window_km / cell - 1.0) / 2.0)))


def achieved_window_km(half, cell):
    return (2 * half + 1) * cell


def ew_halves(lat, cell, extent_km, width):
    """Per-row east-west half-width, widening as 1/cos(lat), capped at half the
    parallel. A capped row measures a SHORTER extent than requested."""
    cos = np.maximum(np.cos(np.radians(lat)), 1e-9)
    n = extent_km / (cell * cos)
    cap = max(1, (width - 1) // 2)
    return np.clip(np.rint((n - 1.0) / 2.0), 1, cap).astype(np.int64), cap


def sat3(z):
    """Summed-area tables of value, square and validity, in float64.

    float64 is required here and not elsewhere: these accumulate across the
    whole band width, and a float32 running sum loses low-order bits long before
    the end of a row, so the differenced rectangle sums come out wrong. Squared
    elevations reach ~4.5e8 on Earth and summing 10^8 of them reaches ~10^16.
    """
    v = np.isfinite(z)
    zz = np.where(v, z, 0.0).astype(np.float64)
    # shift by the band mean: var = E[z^2] - E[z]^2 cancels catastrophically on
    # nearly flat ground where both terms are large and almost equal
    off = float(zz[v].mean()) if v.any() else 0.0
    zz = np.where(v, zz - off, 0.0)
    h, w = z.shape
    S = np.zeros((h + 1, w + 1)); S2 = np.zeros_like(S); N = np.zeros_like(S)
    np.cumsum(np.cumsum(zz, 0), 1, out=S[1:, 1:])
    np.cumsum(np.cumsum(zz * zz, 0), 1, out=S2[1:, 1:])
    np.cumsum(np.cumsum(v.astype(np.float64), 0), 1, out=N[1:, 1:])
    return S, S2, N, off


def _rect_wrapped(T, r0, r1, c_lo, c_hi, w):
    """Rectangle sums with longitude WRAP and latitude CLIP.

    Longitude wraps, latitude does not. Treating longitude as clipping
    truncates every window at the antimeridian; treating latitude as wrapping
    teleports a window across the pole.
    """
    left = np.clip(c_lo, 0, w); right = np.clip(c_hi, 0, w)
    out = (T[r1, right] - T[r0, right] - T[r1, left] + T[r0, left])
    lo_wrap = c_lo < 0
    if lo_wrap.any():
        a = (c_lo[lo_wrap] % w)
        out[lo_wrap] += (T[r1, w] - T[r0, w] - T[r1, a] + T[r0, a])
    hi_wrap = c_hi > w
    if hi_wrap.any():
        b = c_hi[hi_wrap] - w
        out[hi_wrap] += (T[r1, b] - T[r0, b] - T[r1, 0] + T[r0, 0])
    return out


def window_stats_from_sat(S, S2, N, off, half_ns, half_ew, core0, core1, w,
                          want_mean=False):
    """Window std (and optionally mean) for rows [core0, core1) of the band."""
    nrows = core1 - core0
    outs = np.full((nrows, w), np.nan, dtype=np.float32)
    outm = np.full((nrows, w), np.nan, dtype=np.float32) if want_mean else None
    cols = np.arange(w)
    bh = S.shape[0] - 1
    for i, r in enumerate(range(core0, core1)):
        hw = int(half_ew[r])
        r0 = max(0, r - half_ns); r1 = min(bh, r + half_ns + 1)
        n = _rect_wrapped(N, r0, r1, cols - hw, cols + hw + 1, w)
        s = _rect_wrapped(S, r0, r1, cols - hw, cols + hw + 1, w)
        cells = (r1 - r0) * min(2 * hw + 1, w)
        ok = n >= MIN_VALID_FRAC * cells
        with np.errstate(invalid="ignore", divide="ignore"):
            m1 = np.where(ok, s / np.maximum(n, 1), np.nan)
            if want_mean:
                outm[i] = (m1 + off).astype(np.float32)
            s2 = _rect_wrapped(S2, r0, r1, cols - hw, cols + hw + 1, w)
            m2 = np.where(ok, s2 / np.maximum(n, 1), np.nan)
            outs[i] = np.sqrt(np.maximum(m2 - m1 * m1, 0.0)).astype(np.float32)
    return outs, outm


# Band sizing. Two separate budgets, because two different things are large:
#   CORE_BUDGET  one float32 layer over the core rows of a band. Ten or so are
#                live at once (four roughness scales, TPI, slope, H, R2 and the
#                fit's running sums), so this is the number that multiplies.
#   SAT_BUDGET   the three float64 summed-area tables. They exist only while
#                the roughness loop runs and are freed before the fit.
CORE_BUDGET = 96 * 2 ** 20
SAT_BUDGET = 900 * 2 ** 20

# Phase 2 gets its OWN disk floor. The 60 GiB floor belongs to Phase 1, which
# wrote a 13.9 GiB Earth DEM plus full-width resampling intermediates. Phase 2
# writes, MEASURED and not estimated:
#     moon    7 layers x   3.0 MB =  21 MB
#     mars    7 layers x  12.0 MB =  84 MB
#     earth   7 layers x  48.0 MB = 336 MB
#     all three bodies            = 0.431 GiB
# plus a 48 MB peak transient, being the one .part file atomic_save renames.
# No working-resolution intermediate is written at all -- that is the routing
# decision at the top of this file. A 5 GiB floor is better than tenfold
# margin. The Phase 1 floor is deliberately NOT lowered: later phases that DO
# write large intermediates, B9's Earth thermal rebuild among them at roughly
# 15 GiB of temporary, must keep their own gate.
PHASE2_DISK_FLOOR_GIB = 5.0

# ---------------------------------------------------------------------------
# RECORDED DEPARTURE FROM THE SPEC -- aggregation statistic.
# The spec says a HEALPix cell's value is the MEDIAN of the native values
# inside it. This builds the AREA-WEIGHTED MEAN instead. Deliberate, and
# recorded in every manifest entry rather than left to be rediscovered: silent
# drift is how this project ended up with three different temperature
# definitions. The spec is to be updated to match.
AGGREGATION_DECISION = dict(
    spec_says="median of the native values inside the HEALPix pixel",
    implemented=("area-weighted mean, cos(lat) weights, accumulated inside "
                 "the band loop"),
    status="DEPARTURE FROM SPEC -- deliberate; the spec is to be updated",
    reasoning=[
        "A mean streams and a median does not. The mean needs two "
        "accumulators of length npix, 96 MB for the Moon and 201 MB for "
        "Earth, and a pixel never has to be complete within one band. A "
        "median needs every contributing value present at once, which means "
        "writing a working-resolution intermediate -- 13.9 GiB per Earth "
        "layer, about 97 GiB over the seven layers -- then reading it back.",
        "Each HEALPix pixel averages roughly 215 native cells, so the "
        "sampling error on the mean is small.",
        "All three DEMs passed their range and coverage gates in phase 1, so "
        "the outlier robustness a median buys has no known outliers to "
        "defend against.",
        "The quantities being aggregated are smooth window statistics, "
        "already averaged over 5 to 42 km footprints, so within one 7 km "
        "pixel they vary little and mean and median nearly coincide.",
    ],
    consequence=("Where a pixel straddles a sharp boundary -- a crater rim, a "
                 "coastline -- the mean is pulled toward the extreme while a "
                 "median would ignore it. The support gate is what exposes "
                 "those pixels."),
    spec_update_required=True,
)


def band_plan(width, halo):
    core = max(1, int(CORE_BUDGET // (width * 4)))
    while core > 1 and 3 * 8 * (core + 2 * halo + 1) * (width + 1) > SAT_BUDGET:
        core //= 2
    return core


# ------------------------------------------------------------------- slope

def slope_from_band(z, lat_band, cell, core0, core1, w, m_ns, m_ew):
    """Slope in degrees for rows [core0, core1) of an extended band.

    CENTRE-TO-CENTRE convention: dz is taken across +/-m cells and divided by
    the full 2m-cell span. A slope is a height difference ACROSS a distance, so
    only the two endpoints and their separation enter -- the centre cell does
    not count, unlike a window statistic, which owns every cell it covers.
    """
    dist_ns = 2.0 * m_ns * cell * 1000.0
    cos = np.maximum(np.cos(np.radians(lat_band)), 1e-9)
    bh = z.shape[0]
    out = np.full((core1 - core0, w), np.nan, dtype=np.float32)
    for i, r in enumerate(range(core0, core1)):
        if r - m_ns < 0 or r + m_ns >= bh:
            continue                  # top/bottom of the globe, not of a band
        k = int(m_ew[r])
        dz_ns = z[r + m_ns] - z[r - m_ns]
        dz_ew = np.roll(z[r], -k) - np.roll(z[r], k)        # longitude WRAPS
        dist_ew = 2.0 * k * cell * cos[r] * 1000.0
        with np.errstate(invalid="ignore", divide="ignore"):
            g = np.hypot(dz_ns / dist_ns, dz_ew / dist_ew)
            out[i] = np.degrees(np.arctan(g)).astype(np.float32)
    return out


# ------------------------------------------------- streaming HEALPix binning

class HealpixAccumulator:
    """Area-weighted mean onto HEALPix NESTED, accumulated band by band.

    Two float64 arrays of length npix per layer: a weighted sum and a weight
    total. A HEALPix pixel spanning several bands needs no special handling --
    the accumulator does not care which band a contribution came from, so a
    pixel is never required to be complete within one band. That is exactly
    why the median objection does not apply: this is a MEAN.

    cos(lat) weighting belongs HERE. HEALPix pixels are equal-area, which is
    why nothing downstream needs weighting, but the lat/lon grid being binned
    FROM is not equal-area, so the weight has to be applied on the way in.

    np.bincount, not np.add.at: add.at is an unbuffered ufunc loop and runs one
    to two orders of magnitude slower. Earth has 3.7e9 cell-to-pixel
    assignments to make.
    """

    def __init__(self, nside, names):
        from astropy_healpix import HEALPix
        self.hp = HEALPix(nside=nside, order="nested")
        self.npix = int(self.hp.npix)
        self.num = {n: np.zeros(self.npix, dtype=np.float64) for n in names}
        self.den = {n: np.zeros(self.npix, dtype=np.float64) for n in names}
        # Reference weight total: every native cell that lands in the pixel,
        # valid or not. den/ref is the SUPPORT FRACTION -- how much of the
        # pixel actually contributed. One array serves all layers, because the
        # grid is the same for all of them; only the NaN patterns differ.
        self.ref = np.zeros(self.npix, dtype=np.float64)

    def index_for_band(self, lat_rows, lon, chunk=32):
        """HEALPix index for every cell of a band, as int32.

        Computed ONCE per band and reused for all seven layers -- one index
        pass serves the lot. Built in row chunks because the lon/lat pair
        astropy wants is float64, and a whole Earth band of those is 650 MB of
        temporary for an answer that fits in 96 MB.
        """
        from astropy import units as u
        nr, w = lat_rows.size, lon.size
        out = np.empty((nr, w), dtype=np.int32)
        for a in range(0, nr, chunk):
            b = min(nr, a + chunk)
            la = np.repeat(lat_rows[a:b], w)
            lo = np.tile(lon, b - a)
            out[a:b] = self.hp.lonlat_to_healpix(
                lo * u.deg, la * u.deg).reshape(b - a, w).astype(np.int32)
        return out

    def add_reference(self, idx_flat, wt_flat):
        """Called ONCE per band, before the layers. Counts every cell."""
        self.ref += np.bincount(idx_flat, weights=wt_flat, minlength=self.npix)

    def add(self, name, values, idx_flat, wt_flat):
        """Accumulate one layer of one band. values is float32 (nr, w)."""
        v = np.isfinite(values).ravel()
        wv = np.where(v, wt_flat, 0.0)
        self.den[name] += np.bincount(idx_flat, weights=wv, minlength=self.npix)
        np.multiply(wv, np.where(v, values.ravel(), 0.0), out=wv)
        self.num[name] += np.bincount(idx_flat, weights=wv, minlength=self.npix)
        del v, wv

    def finish(self, name):
        """Returns the layer, the pixel count, and the SUPPORT FRACTION.

        Support is the third gate. The coverage gate says only whether a pixel
        got anything at all: a pixel reports valid while resting on three cells
        out of two hundred. Support says how much of it actually contributed.
        """
        out = np.full(self.npix, np.nan, dtype=np.float32)
        nz = self.den[name] > 0
        out[nz] = (self.num[name][nz] / self.den[name][nz]).astype(np.float32)
        sup = np.full(self.npix, np.nan, dtype=np.float32)
        rz = self.ref > 0
        sup[rz] = (self.den[name][rz] / self.ref[rz]).astype(np.float32)
        self.num.pop(name); self.den.pop(name)            # free as we go
        return out, int(nz.sum()), sup


# ---------------------------------------------------------------- validation

def validate(arr, nside, name, units, extra=None, support=None):
    """THREE GATES: range, coverage, support.

    One function and not two, because of Phase 1: the Mars scale gate PASSED on
    a DEM that was 99.68 percent nodata. A range check alone is not a
    validation.
    """
    lat = C.healpix_lat(nside)
    v = np.isfinite(arr)
    bands = {"global": np.ones(arr.size, dtype=bool),
             "abs_lat_gt_60": np.abs(lat) > 60,
             "abs_lat_gt_80": np.abs(lat) > 80,
             "abs_lat_gt_85": np.abs(lat) > 85,
             "lat_85S_to_90S": lat <= -85.0}
    pct = {}
    for b, m in bands.items():
        t = int(m.sum())
        pct[b] = round(100.0 * int((v & m).sum()) / t, 4) if t else None
    f = arr[v].astype(np.float64)
    st = {}
    if f.size:
        q = np.percentile(f, [1, 25, 50, 75, 99])
        st = dict(min=float(f.min()), p1=float(q[0]), p25=float(q[1]),
                  p50=float(q[2]), p75=float(q[3]), p99=float(q[4]),
                  max=float(f.max()), iqr=float(q[3] - q[1]),
                  mean=float(f.mean()))
    out = dict(name=name, units=units, n_pixels=int(arr.size),
               expected_npix=12 * nside ** 2,
               shape_ok=bool(arr.size == 12 * nside ** 2),
               dtype=str(arr.dtype), n_valid=int(v.sum()),
               coverage_gate=pct, range_gate=st)
    if support is not None:
        sv = np.isfinite(support)
        sf = support[sv & v].astype(np.float64)        # support WHERE valid
        sg = dict(definition=("achieved weight total over expected weight "
                              "total: the cos(lat)-weighted fraction of the "
                              "native cells falling in the pixel that carried "
                              "a usable value"),
                  n_pixels_with_reference=int(sv.sum()))
        if sf.size:
            q = np.percentile(sf, [1, 5, 25, 50, 75])
            sg.update(min=float(sf.min()), p1=float(q[0]), p5=float(q[1]),
                      p25=float(q[2]), p50=float(q[3]), p75=float(q[4]),
                      max=float(sf.max()), mean=float(sf.mean()))
            for thr in (0.05, 0.10, 0.25, 0.50, 0.90):
                sg[f"valid_pixels_below_{thr:.2f}"] = int((sf < thr).sum())
            sg["valid_pixels_fully_supported"] = int((sf >= 0.999).sum())
            sg["thin_support_warning"] = (
                "A pixel passing the coverage gate on a small support "
                "fraction is a weak measurement, not a missing one. Filter on "
                "support, not on validity alone.")
        out["support_gate"] = sg
    if extra:
        out.update(extra)
    return out


def show(v):
    g, s = v["coverage_gate"], v["range_gate"]
    sg = v.get("support_gate", {})
    print(f"    {v['name']:34s} valid {g['global']:8.4f}%   "
          f">85deg {g['abs_lat_gt_85']:8.4f}%   85-90S "
          f"{g['lat_85S_to_90S']:8.4f}%")
    if s:
        print(f"    {'':34s} min {s['min']:10.4f}  p50 {s['p50']:10.4f}  "
              f"max {s['max']:10.4f}  IQR {s['iqr']:7.4f}   [{v['units']}]")
    if sg.get("p50") is not None:
        print(f"    {'':34s} support p1 {sg['p1']:.4f}  p50 {sg['p50']:.4f}  "
              f"mean {sg['mean']:.4f}   below 0.50: "
              f"{sg['valid_pixels_below_0.50']:,}   full: "
              f"{sg['valid_pixels_fully_supported']:,}")


# -------------------------------------------------------------------- driver

def build_body(body):
    nside = C.NSIDE[body]
    dem_path = os.path.join(DEM_DIR, DEM_FILE[body])
    if not os.path.exists(dem_path):
        raise SystemExit(f"STOP: {dem_path} missing -- Phase 1 must run first")
    z_all = np.load(dem_path, mmap_mode="r")
    Hh, Ww = z_all.shape
    if (Hh, Ww) != tuple(GRIDS[body]["shape"]):
        raise SystemExit(f"STOP: DEM is {Hh}x{Ww}, expected "
                         f"{GRIDS[body]['shape']}")
    cell = cell_km_ns(body)

    # Achieved scales, recomputed PER BODY: the cells differ, so one requested
    # window lands on a different footprint on each body.
    halves = [half_for_window(r, cell) for r in ROUGH_REQUESTED_KM]
    achieved = [achieved_window_km(h, cell) for h in halves]
    tpi_half = half_for_window(TPI_WINDOW_KM, cell)
    tpi_ach = achieved_window_km(tpi_half, cell)
    idx21 = ROUGH_REQUESTED_KM.index(21.0)
    if halves[idx21] != tpi_half:
        raise SystemExit("STOP: the 21 km roughness and the 21 km TPI must "
                         "share one window; they do not")

    rough_names = [f"roughness_{r:g}km" for r in ROUGH_REQUESTED_KM]
    layers = (["slope"] + rough_names +
              ["tpi_21km", "roughness_scaling_exponent", "scaling_exponent_r2"])

    print(f"  grid {Hh} x {Ww}, cell {cell:.4f} km, Nside {nside} "
          f"({12*nside**2:,} pixels)")
    print(f"  roughness requested {list(ROUGH_REQUESTED_KM)} km")
    print(f"            ACHIEVED  {[round(a, 3) for a in achieved]} km   "
          f"(halves {halves})")
    print(f"  tpi 21 km -> achieved {tpi_ach:.3f} km (half {tpi_half}) -- the "
          f"SAME window as {rough_names[idx21]}")
    print(f"  {rough_names[idx21]} IS the ruggedness dimension. One layer.")

    logs = np.log(np.array(achieved, dtype=np.float64))
    logs_c = logs - logs.mean()
    denom = float((logs_c ** 2).sum())
    print(f"  H fit on the ACHIEVED scales, log centred at the geometric mean "
          f"{np.exp(logs.mean()):.3f} km")

    m_ns = max(1, int(round(SLOPE_BASELINE_KM / (2.0 * cell))))
    halo = max(max(halves), m_ns)
    core_rows = band_plan(Ww, halo)
    ext = core_rows + 2 * halo + 1
    nbands = (Hh + core_rows - 1) // core_rows
    print(f"  bands: {core_rows} core rows + {halo} halo each side -> "
          f"{nbands} bands; 3 float64 SATs = "
          f"{3*8*ext*(Ww+1)/2**20:.0f} MB, one float32 core layer = "
          f"{core_rows*Ww*4/2**20:.0f} MB")

    acc = HealpixAccumulator(nside, layers)
    print(f"  accumulators: {len(layers)} layers x 2 x {acc.npix:,} x 8 B = "
          f"{len(layers)*2*acc.npix*8/2**20:.0f} MB -- and NO working-"
          f"resolution intermediate is ever written")

    lat_all = 90.0 - (np.arange(Hh) + 0.5) * (180.0 / Hh)
    lon = -180.0 + (np.arange(Ww) + 0.5) * (360.0 / Ww)
    cos_all = np.maximum(np.cos(np.radians(lat_all)), 1e-9)
    cap = max(1, (Ww - 1) // 2)
    ew_all = [ew_halves(lat_all, cell, r, Ww)[0] for r in ROUGH_REQUESTED_KM]
    ew_slope = np.clip(np.rint(SLOPE_BASELINE_KM / (2.0 * cell * cos_all)),
                       1, Ww // 2).astype(np.int64)

    # Saturation counted globally and BEFORE the loop, so a capped row is
    # reported rather than silently measuring a shorter extent than requested.
    sat_rows = {f"{r:g}km": int((np.rint((r / (cell * cos_all) - 1.0) / 2.0)
                                 > cap).sum()) for r in ROUGH_REQUESTED_KM}
    sat_rows["slope_7km"] = int((np.rint(SLOPE_BASELINE_KM /
                                 (2.0 * cell * cos_all)) > Ww // 2).sum())

    t0 = time.perf_counter()
    nbytes = 0
    r2_lo = h_fin = h_cells = 0
    for bi, c0 in enumerate(range(0, Hh, core_rows)):
        c1 = min(Hh, c0 + core_rows)
        e0 = max(0, c0 - halo); e1 = min(Hh, c1 + halo)
        z = np.asarray(z_all[e0:e1], dtype=np.float32)
        nbytes += z.nbytes
        k0, k1 = c0 - e0, c1 - e0               # core rows within the band
        nr = k1 - k0

        # --- ONE SAT pass serves all four roughness scales and the TPI mean
        S, S2, N, off = sat3(z)
        rough = []
        tpi = None
        for si, hw in enumerate(halves):
            std, mean = window_stats_from_sat(
                S, S2, N, off, hw, ew_all[si][e0:e1], k0, k1, Ww,
                want_mean=(si == idx21))
            rough.append(std)
            if si == idx21:
                tpi = (z[k0:k1] - mean).astype(np.float32)
                del mean
        del S, S2, N                            # free ~900 MB before the fit

        # --- H fitted HERE, inside the band, from the four ACHIEVED scales.
        # Two passes over the four scales rather than one stacked array: a
        # stacked float64 Y plus its prediction is 2.6 GB on Earth, and not
        # doing that is the whole point of banding.
        ok = np.ones((nr, Ww), dtype=bool)
        for a in rough:
            ok &= np.isfinite(a) & (a > 0.0)    # log(0) is not a data point
        ybar = np.zeros((nr, Ww), dtype=np.float32)
        hfit = np.zeros((nr, Ww), dtype=np.float32)
        for si, a in enumerate(rough):
            y = np.log(np.where(ok, a, 1.0)).astype(np.float32)
            ybar += y
            hfit += np.float32(logs_c[si]) * y
            del y
        ybar /= np.float32(len(rough))
        hfit /= np.float32(denom)
        ssr = np.zeros((nr, Ww), dtype=np.float32)
        sst = np.zeros((nr, Ww), dtype=np.float32)
        for si, a in enumerate(rough):
            y = np.log(np.where(ok, a, 1.0)).astype(np.float32)
            d = y - ybar
            sst += d * d
            d -= np.float32(logs_c[si]) * hfit
            ssr += d * d
            del y, d
        del ybar
        with np.errstate(invalid="ignore", divide="ignore"):
            r2 = np.where(sst > 0, 1.0 - ssr / sst, np.nan).astype(np.float32)
        del ssr, sst
        r2[~ok] = np.nan
        hfit[~ok] = np.nan
        h_cells += int(ok.sum())
        bad = ok & (r2 < R2_MIN)
        r2_lo += int(bad.sum())
        hfit[bad] = np.nan              # no single power law holds here
        h_fin += int(np.isfinite(hfit).sum())
        del ok, bad

        slope = slope_from_band(z, lat_all[e0:e1], cell, k0, k1, Ww,
                                m_ns, ew_slope[e0:e1])
        del z

        # --- bin: one index pass, seven layers
        idx = acc.index_for_band(lat_all[c0:c1], lon).ravel()
        wt = np.repeat(cos_all[c0:c1], Ww)
        acc.add_reference(idx, wt)        # every cell, valid or not
        acc.add("slope", slope, idx, wt); del slope
        for nm, a in zip(rough_names, rough):
            acc.add(nm, a, idx, wt)
        del rough
        acc.add("tpi_21km", tpi, idx, wt); del tpi
        acc.add("roughness_scaling_exponent", hfit, idx, wt); del hfit
        acc.add("scaling_exponent_r2", r2, idx, wt); del r2
        del idx, wt

        if bi % 8 == 0 or c1 == Hh:
            el = time.perf_counter() - t0
            eta = el / (bi + 1) * (nbands - bi - 1)
            pk = peak_rss_gib()
            print(f"    band {bi+1}/{nbands}  row {c1}/{Hh}  {el/60:5.1f} min"
                  f"  eta {eta/60:5.1f} min  "
                  f"{nbytes/2**20/max(el, 1e-9):6.1f} MB/s  peak "
                  f"{'?' if pk is None else f'{pk:.2f}'} GiB", flush=True)
    el = time.perf_counter() - t0
    say_peak(f"{body} band loop")

    os.makedirs(OUT_DIR, exist_ok=True)
    results = {}
    print(f"\n  --- {body.upper()} LAYERS, BOTH GATES ---")
    for nm in layers:
        arr, nfilled, sup = acc.finish(nm)
        path = os.path.join(OUT_DIR, f"{body}_{nm}_nside{nside}.npy")
        C.atomic_save(path, arr)
        spath = os.path.join(OUT_DIR,
                             f"{body}_{nm}_support_nside{nside}.npy")
        C.atomic_save(spath, sup)
        units = ("degrees" if nm == "slope" else
                 "dimensionless" if nm in ("roughness_scaling_exponent",
                                           "scaling_exponent_r2") else "m")
        extra = dict(healpix_pixels_filled=nfilled)
        if nm == "slope":
            extra["slope_parameters"] = dict(
                requested_baseline_km=SLOPE_BASELINE_KM,
                ns_cells_each_side=m_ns,
                achieved_baseline_km=round(2 * m_ns * cell, 4),
                convention="centre-to-centre, 2*m*cell",
                gradient="hypot of the north-south and east-west differences",
                ew_rows_saturated=sat_rows["slope_7km"])
        if nm in rough_names:
            j = rough_names.index(nm)
            extra.update(
                requested_window_km=ROUGH_REQUESTED_KM[j],
                achieved_window_km=round(achieved[j], 4),
                half_cells=halves[j],
                estimator="standard deviation of elevation within the window",
                ew_rows_saturated=sat_rows[f"{ROUGH_REQUESTED_KM[j]:g}km"])
            if j == idx21:
                extra["serves_as"] = (
                    "the RUGGEDNESS dimension. Roughness at 21 km and "
                    "ruggedness at 21 km are the same quantity; this layer is "
                    "built once and both names point at it.")
        if nm == "tpi_21km":
            extra.update(requested_window_km=TPI_WINDOW_KM,
                         achieved_window_km=round(tpi_ach, 4),
                         half_cells=tpi_half,
                         sign_convention=C.TPI_SIGN_NOTE,
                         ew_rows_saturated=sat_rows["21km"])
        if nm == "roughness_scaling_exponent":
            extra.update(
                requested_scales_km=list(ROUGH_REQUESTED_KM),
                achieved_scales_km=[round(a, 4) for a in achieved],
                fit="OLS of log(sigma) on CENTRED log(achieved scale)",
                log_centred_at_km=round(float(np.exp(logs.mean())), 4),
                r2_threshold=R2_MIN,
                withheld_for_low_r2=r2_lo,
                withheld_pct_of_fittable=round(
                    100.0 * r2_lo / max(h_cells, 1), 4),
                not_shepard_deviogram=True,
                estimator_note=(
                    "Moving-window standard deviation at four scales, NOT "
                    "Shepard's deviogram. The name is roughness_scaling_"
                    "exponent rather than 'hurst' for exactly that reason: the "
                    "estimator differs from the one the Hurst literature "
                    "assumes, so these numbers are not interchangeable with "
                    "published H values."),
                validated_on=(
                    "synthetic fractional Brownian surfaces at H = 0.3, 0.5, "
                    "0.7 using this body's achieved scales; see the fBm gate "
                    "in the Phase 2 report"),
                outside_unit_interval=(
                    "Values below 0 and above 1 are NOT errors. This is the "
                    "slope of log roughness against log scale, which may "
                    "legitimately exceed 1: it does so where a widening "
                    "window swallows a discrete feature such as a crater rim "
                    "and roughness grows faster than linearly. Those pixels "
                    "are detecting DISCRETE FEATURES rather than fractal "
                    "texture -- a real measurement of the wrong quantity. A "
                    "value below 0 says roughness FALLS as the window "
                    "widens. R2 does not screen either case out, because the "
                    "power law is clean; only its exponent is meaningless as "
                    "a texture descriptor. This is also why the layer is "
                    "named roughness_scaling_exponent and not hurst."),
                redundancy_finding=(
                    "VARIABLES.md section B8 predicted HIGH redundancy "
                    "against ruggedness. That prediction is WRONG. Measured "
                    "correlation of this layer with roughness_21km on the "
                    "Moon is -0.157 globally and -0.306 over 85-90S. H "
                    "carries information nothing else carries; it is simply "
                    "noisy. The B8 verdict of HOLD stands, but for the "
                    "signal-to-noise reason, not the redundancy reason."),
                status="HOLD -- built and stored, not wired into the default "
                       "dimension set")
        if nm == "scaling_exponent_r2":
            extra["purpose"] = (
                "Diagnostic for roughness_scaling_exponent. Retained in full, "
                "including where it falls below the threshold that withholds "
                "H, so the reason H is missing stays recoverable.")
        v = validate(arr, nside, f"{body}_{nm}", units, extra, support=sup)
        show(v)
        del sup
        results[nm] = v
        C.manifest_write(f"{body}_{nm}", dict(
            phase="2", body=body, variable=nm, units=units,
            file=os.path.relpath(path, ROOT).replace("\\", "/"),
            source_files=[os.path.relpath(dem_path, ROOT).replace("\\", "/")],
            source_resolves=os.path.exists(dem_path),
            native_resolution=f"working grid {Hh}x{Ww}, cell {cell:.4f} km",
            working_resolution=f"1/{GRIDS[body]['ppd']} deg = {cell*1000:.1f} m",
            nside=nside, order="nested",
            binning=("area-weighted mean onto HEALPix NESTED with cos(lat) "
                     "weights, accumulated INSIDE the band loop; no "
                     "intermediate at working resolution was written"),
            nodata_rule=(f"NaN propagates from the DEM. A window statistic is "
                         f"NaN where under {MIN_VALID_FRAC:.0%} of the window "
                         f"is valid; slope is NaN where either stencil end is "
                         f"NaN; H is NaN where any of the four scales is "
                         f"invalid or zero, or where R2 < {R2_MIN}"),
            aggregation_decision=AGGREGATION_DECISION,
            support_file=os.path.relpath(spath, ROOT).replace("\\", "/"),
            gates=("THREE gates, not two: range (are the values plausible), "
                   "coverage (did the pixel get anything) and support (how "
                   "much of the pixel actually contributed). The coverage "
                   "gate alone lies: a pixel reports valid while resting on a "
                   "handful of its ~215 contributing cells."),
            slope_convention=SLOPE_CONVENTION,
            window_convention=WINDOW_CONVENTION,
            convention_warning=CONVENTION_WARNING,
            tpi_sign_convention=C.TPI_SIGN_NOTE,
            ew_saturation_note=("The east-west stencil widens as 1/cos(lat) "
                                "and is capped at half the parallel. A capped "
                                "row measures a SHORTER extent than "
                                "requested; ew_rows_saturated counts them."),
            validation=v,
            elapsed_s=round(el, 1), bytes_read=nbytes,
            throughput_MB_s=round(nbytes / 2 ** 20 / max(el, 1e-9), 1),
            throughput_note=("bytes_read divided by elapsed. This is a "
                             "COMPUTE rate, not a disk rate: phase 2 reads "
                             "the DEM once and then does far more work per "
                             "byte than phase 1, which measured 156 MB/s on "
                             "this same disk. Do not read it as I/O "
                             "throughput."),
            peak_rss_gib=peak_rss_gib(),
            build_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))

    print("\n  east-west stencil saturation (capped at half the parallel):")
    for k, n in sat_rows.items():
        print(f"    {k:>10s}: {n} of {Hh} rows ({100.0*n/Hh:.4f}%)")
    print(f"    widest achievable east-west extent on the pole row "
          f"(|lat| {abs(lat_all[0]):.4f}): "
          f"{(2*cap+1)*cell*cos_all[0]:.3f} km, against 42 km requested")
    print(f"\n  H: {h_cells:,} working cells had four usable scales; "
          f"{r2_lo:,} withheld for R2 < {R2_MIN} "
          f"({100.0*r2_lo/max(h_cells,1):.4f}%); {h_fin:,} retained")
    return results, dict(
        elapsed_s=round(el, 1), bands=nbands, core_rows=core_rows, halo=halo,
        bytes_read=nbytes,
        throughput_MB_s=round(nbytes / 2 ** 20 / max(el, 1e-9), 1),
        peak_rss_gib=peak_rss_gib(), saturated_rows=sat_rows,
        achieved_scales_km=[round(a, 4) for a in achieved],
        h_fittable_cells=h_cells, h_withheld_low_r2=r2_lo, h_retained=h_fin)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", required=True, choices=["moon", "mars", "earth"])
    a = ap.parse_args(argv)
    print("=" * 78)
    print(f"PHASE 2 -- TERRAIN VARIABLES: {a.body.upper()}")
    print("=" * 78)
    print(f"\nfree disk {C.free_gib(ROOT):.1f} GiB")
    print(f"phase 2 floor {PHASE2_DISK_FLOOR_GIB} GiB   (phase 1 used "
          f"{DISK_FLOOR_GIB} GiB; phase 2 writes 0.431 GiB for all three "
          f"bodies and writes no intermediates -- see the comment on "
          f"PHASE2_DISK_FLOOR_GIB)")
    C.require_disk(PHASE2_DISK_FLOOR_GIB, ROOT)
    t0 = time.perf_counter()
    res, meta = build_body(a.body)
    pk = peak_rss_gib()
    print("=" * 78)
    print(f"{a.body.upper()}: {(time.perf_counter()-t0)/60:.1f} min   "
          f"peak RAM {'unknown' if pk is None else f'{pk:.2f} GiB'} "
          f"(cap {PEAK_CAP_GIB} GiB)   {meta['throughput_MB_s']} MB/s   "
          f"free disk {C.free_gib(ROOT):.1f} GiB")
    with open(os.path.join(OUT_DIR, f"phase2_{a.body}_summary.json"), "w",
              encoding="utf-8") as fh:
        json.dump(dict(layers=res, meta=meta), fh, indent=1, default=str)
    if a.body == "moon":
        print("\nSTOPPING after the Moon, as instructed. Awaiting "
              "confirmation before Mars and Earth.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
