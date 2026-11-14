"""
PHASE 3f -- MARS SURFACE TEMPERATURE AT PIXEL SCALE, MODELLED. (VARIABLES.md B28)

    python build/phase3f_mars_temperature.py [--test]

WHAT THIS REPLACES
    The three Mars thermal layers from the Mars Climate Database (355 km model
    grid, 3,072 distinct values, matching_eligible false). Same names, same
    definitions, same stated range gates -- ONE convention. The MCD arrays are
    overwritten; their validation numbers are kept in the new manifest entry
    under superseded_mcd_layer, and the MCD is used as the coarse-scale check.

HOW
    Every pixel's temperature is read from cube/mars_temp_table.npz, the
    lookup table produced by the NumPy port of KRC's one-point mode
    (build/mars_thermal_1d.py, validated against KRC's own reference set to a
    median 1.4 K), by multilinear interpolation over
        log thermal inertia   mars_thermal_inertia      (TES, 2.96 km, measured)
        albedo                mars_albedo               (TES, 7.4 km, built here)
        elevation             mars_elevation            (MOLA-HRSC, pressure)
        latitude              the pixel centre
        dust opacity          Montabone v2 kriged climatology, 3 deg, four
                              storm-free years MY29-MY32, per 30-deg Ls bin,
                              converted IR-absorption-at-610-Pa -> visible at
                              the model's 546 Pa reference
    for 12 seasons (Ls 0..330) and 12 local times (0..22 h). Then:
        temp_level            mean over Ls of the model's daily mean
        temp_range_diurnal    mean over Ls of (max - min over the 12 local times)
                              -- the SAME definition the MCD layer carried,
                              12 samples, so the cross-body contract holds
        temp_range_seasonal   max - min over Ls of the daily mean

STATUS WORDS, on every entry
    Surface temperature fields are MODELLED, not measured. Computed with a
    one-dimensional surface heat-balance model (a NumPy port of KRC's
    one-point mode, Kieffer 2013) driven by TES thermal inertia (Putzig &
    Mellon 2007), TES albedo, MOLA-derived pressure, latitude and a
    climatological dust opacity. No spacecraft measured a gridded
    surface-temperature climatology at this resolution. Expected error is a
    few kelvin in the mean and larger in the diurnal range and near the
    seasonal CO2 caps. Agreement with the MCD was checked only at the GCM
    scale; the MCD's high-resolution mode does not adjust surface temperature.

GATES, STATED BEFORE THE RUN (the MCD layers' own gates, unchanged)
    temp_level 120..310 K, temp_range_diurnal 0..200 K, temp_range_seasonal
    0..150 K; coverage; support (the thermal-inertia support, the finest
    input); table-edge clipping counts; non-converged-case flag (RMS > 0.5 K).
"""

import argparse
import glob
import io
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C
from phase1_dems import peak_rss_gib, say_peak
from phase2_terrain import show, validate
from phase3_thermal import GATES, bin_grid, sample_grid

BODY, NSIDE = "mars", C.NSIDE["mars"]
HP = os.path.join(C.ROOT, "cube", "healpix")
TABLE = os.path.join(C.ROOT, "cube", "mars_temp_table.npz")
TABLE_META = os.path.join(C.ROOT, "cube", "mars_temp_table.json")
ALB_IMG = os.path.join(C.ROOT, "sources", "tes_albedo", "global_albedo_8ppd.img")
DUST_DIR = os.path.join(C.ROOT, "sources", "dust_climatology")
VIS_IR_RATIO = 2.6          # visible extinction / 9.3 um absorption, ASSUMED (see note)
P_REF_MODEL, P_REF_DUST = 546.0, 610.0
RMS_FLAG = 0.5
STATUS = ("MODELLED, NOT MEASURED. Computed with a one-dimensional surface "
          "heat-balance model (NumPy port of KRC one-point mode, Kieffer 2013, "
          "validated against KRC's reference set to a median 1.4 K) driven by TES "
          "thermal inertia (Putzig & Mellon 2007), TES albedo (Christensen 2001), "
          "MOLA-derived surface pressure, latitude and the Montabone et al. (2015) "
          "dust climatology (MY29-MY32). No spacecraft measured a gridded "
          "surface-temperature climatology at this resolution. Expected error: a "
          "few kelvin in the mean, larger in the diurnal range and near the "
          "seasonal CO2 caps. Agreement with the Mars Climate Database was checked "
          "only at its 5.6 x 3.75 deg grid; the MCD high-resolution mode does not "
          "adjust surface temperature.")


def pixel_lonlat():
    from astropy import units as u
    from astropy_healpix import HEALPix
    hp = HEALPix(nside=NSIDE, order="nested")
    lon, lat = hp.healpix_to_lonlat(np.arange(hp.npix))
    lon = lon.to_value(u.deg); lat = lat.to_value(u.deg)
    return np.where(lon > 180.0, lon - 360.0, lon), lat


def build_albedo():
    """TES 8 ppd bolometric albedo onto HEALPix, bin then fill (7.4 km ~ pixel)."""
    a = np.fromfile(ALB_IMG, dtype="<f4").reshape(1440, 2880).astype(np.float64)
    lat = 90.0 - (np.arange(1440) + 0.5) / 8.0
    lon = -180.0 + (np.arange(2880) + 0.5) / 8.0
    acc = bin_grid({"a": a}, lat, lon, NSIDE, {"a": a})
    filled, _ = sample_grid({"a": a}, lat, lon, NSIDE)
    arr, nfilled, sup = acc.finish("a")
    gap = ~np.isfinite(arr) & np.isfinite(filled["a"])
    arr[gap] = filled["a"][gap]; sup[gap] = 0.0
    return arr, sup, int(gap.sum()), dict(
        source_min=float(a.min()), source_max=float(a.max()),
        source_cells_at_floor_0_06=int((a <= 0.0600001).sum()),
        source_cells_at_ceiling_0_32=int((a >= 0.3199).sum()))


def dust_tau_ref(ls_bins):
    """Visible dust opacity at the model's 546 Pa reference per Ls bin, on the
    climatology's 3-degree grid, averaged over the years on disk."""
    from scipy.io import netcdf_file
    files = sorted(glob.glob(os.path.join(DUST_DIR, "dustscenario_MY*_v2-0.nc")))
    if not files:
        raise SystemExit("STOP: no dust climatology files in sources/dust_climatology")
    acc = None; cnt = None
    for f in files:
        nc = netcdf_file(f, "r", mmap=False)
        ls = nc.variables["Ls"][:].astype(float)
        cd = nc.variables["cdod610"][:].astype(float)             # (time, lat, lon)
        lat = nc.variables["latitude"][:].astype(float)
        lon = nc.variables["longitude"][:].astype(float)
        if acc is None:
            acc = np.zeros((len(ls_bins),) + cd.shape[1:]); cnt = np.zeros(len(ls_bins))
        for i, l0 in enumerate(ls_bins):
            d = np.abs(((ls - l0) + 180.0) % 360.0 - 180.0)
            sel = d <= 15.0
            good = np.isfinite(cd[sel]).all(axis=(1, 2))
            if sel.any():
                acc[i] += np.nanmean(cd[sel], axis=0) * sel.sum(); cnt[i] += sel.sum()
        nc.close()
    cdod = acc / np.maximum(cnt, 1)[:, None, None]
    tau_ref = VIS_IR_RATIO * cdod * (P_REF_MODEL / P_REF_DUST)
    if lat[0] > lat[-1]:                      # the files run north to south; interpolators need ascending axes
        lat = lat[::-1].copy(); tau_ref = tau_ref[:, ::-1, :].copy()
    return tau_ref, lat, lon, [os.path.relpath(f, C.ROOT).replace(os.sep, "/") for f in files]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="measure, write nothing")
    a = ap.parse_args()
    print("=" * 78)
    print("PHASE 3f -- MARS SURFACE TEMPERATURE, MODELLED AT PIXEL SCALE")
    print("=" * 78)
    for k, (lo, hi) in GATES["mars"].items():
        print(f"  RANGE GATE stated in advance: {k:22s} {lo:6.1f} .. {hi:6.1f} K  (the MCD layer's gate)")
    if not os.path.exists(TABLE):
        raise SystemExit(f"STOP: {TABLE} not built yet (build/mars_temp_table.py)")
    C.require_disk(2.0, C.ROOT)
    t0 = time.perf_counter()
    from scipy.interpolate import RegularGridInterpolator as RGI

    tb = np.load(TABLE)
    meta = json.load(io.open(TABLE_META, encoding="utf-8"))
    ls_ax, ti_ax, alb_ax, elev_ax, lat_ax, tau_ax, lt_ax = (tb[k] for k in
        ("ls", "ti", "albedo", "elev_km", "lat", "tau", "local_time"))
    print(f"  table: Ls {ls_ax.size} TI {ti_ax.size} A {alb_ax.size} elev {elev_ax.size} "
          f"lat {lat_ax.size} tau {tau_ax.size} LT {lt_ax.size}; built {meta['built_utc']}")

    # ---- inputs on the pixel grid
    lon_px, lat_px = pixel_lonlat()
    ti = np.load(os.path.join(HP, f"mars_thermal_inertia_nside{NSIDE}.npy"))
    ti_sup = np.load(os.path.join(HP, f"mars_thermal_inertia_support_nside{NSIDE}.npy"))
    elev = np.load(os.path.join(HP, f"mars_elevation_nside{NSIDE}.npy")) / 1000.0
    alb, alb_sup, alb_copied, alb_src = build_albedo()
    print(f"  albedo: {int(np.isfinite(alb).sum()):,} pixels, {alb_copied:,} copied; source "
          f"floor 0.06 on {alb_src['source_cells_at_floor_0_06']:,} cells, ceiling 0.32 on "
          f"{alb_src['source_cells_at_ceiling_0_32']:,}")
    tau_map, dlat, dlon, dust_files = dust_tau_ref(ls_ax)
    print(f"  dust: {len(dust_files)} years, tau_vis(546 Pa) per Ls: zonal p50 "
          f"{np.median(tau_map, axis=(1, 2)).round(2).tolist()}")
    # dust per pixel per Ls: bilinear on the 3-deg grid (lon periodic)
    dlon_ext = np.concatenate([dlon, [dlon[0] + 360.0]])
    lon_q = np.where(lon_px < dlon[0], lon_px + 360.0, lon_px)
    tau_px = np.empty((ls_ax.size, lon_px.size), dtype=np.float32)
    for i in range(ls_ax.size):
        grid = np.concatenate([tau_map[i], tau_map[i][:, :1]], axis=1)
        f = RGI((dlat, dlon_ext), grid, bounds_error=False, fill_value=None)
        tau_px[i] = f(np.column_stack([np.clip(lat_px, dlat.min(), dlat.max()), lon_q]))

    valid = np.isfinite(ti) & np.isfinite(alb) & np.isfinite(elev)
    idx = np.where(valid)[0]
    print(f"  pixels with all inputs: {idx.size:,} of {ti.size:,} ({100*valid.mean():.3f}%)")
    # clip to the table, counting
    lti = np.log(np.clip(ti[idx], ti_ax[0], ti_ax[-1]))
    n_ti_clip = int(np.sum((ti[idx] < ti_ax[0]) | (ti[idx] > ti_ax[-1])))
    alb_q = alb[idx]                                   # extrapolated below 0.10 (floor 0.06)
    n_alb_below = int(np.sum(alb_q < alb_ax[0]))
    elev_q = np.clip(elev[idx], elev_ax[0], elev_ax[-1])
    n_elev_clip = int(np.sum((elev[idx] < elev_ax[0]) | (elev[idx] > elev_ax[-1])))
    lat_q = np.clip(lat_px[idx], lat_ax[0], lat_ax[-1])
    n_lat_clip = int(np.sum(np.abs(lat_px[idx]) > lat_ax[-1]))

    # ---- interpolate per Ls
    axes = (np.log(ti_ax), alb_ax, elev_ax, lat_ax, tau_ax)
    daily_mean = np.full((ls_ax.size, idx.size), np.nan, dtype=np.float32)
    diurnal = np.full_like(daily_mean, np.nan)
    frost = np.zeros_like(daily_mean)
    rms = np.zeros_like(daily_mean)
    n_tau_clip = 0
    CH = 400_000
    for i in range(ls_ax.size):
        tq = tau_px[i, idx]
        n_tau_clip += int(np.sum((tq < tau_ax[0]) | (tq > tau_ax[-1])))
        tq = np.clip(tq, tau_ax[0], tau_ax[-1])
        f_ts = RGI(axes, tb["ts"][i], bounds_error=False, fill_value=None)
        f_mean = RGI(axes, tb["ts_mean"][i], bounds_error=False, fill_value=None)
        f_frost = RGI(axes, tb["frost"][i], bounds_error=False, fill_value=None)
        f_rms = RGI(axes, tb["rms_last_sol"][i], bounds_error=False, fill_value=None)
        for c0 in range(0, idx.size, CH):
            c1 = min(idx.size, c0 + CH)
            pts = np.column_stack([lti[c0:c1], alb_q[c0:c1], elev_q[c0:c1], lat_q[c0:c1], tq[c0:c1]])
            ts = f_ts(pts)                                            # (n, 12 LT)
            diurnal[i, c0:c1] = ts.max(axis=1) - ts.min(axis=1)
            daily_mean[i, c0:c1] = f_mean(pts)
            frost[i, c0:c1] = f_frost(pts)
            rms[i, c0:c1] = f_rms(pts)
        print(f"    Ls {ls_ax[i]:5.1f}: daily mean p50 {np.median(daily_mean[i]):.1f} K, "
              f"diurnal p50 {np.median(diurnal[i]):.1f} K, frost on "
              f"{int((frost[i] > 0).sum()):,} px   {(time.perf_counter()-t0)/60:.1f} min", flush=True)
    say_peak("interpolation")

    out = {}
    npix = ti.size
    for nm in ("temp_level", "temp_range_diurnal", "temp_range_seasonal"):
        arr = np.full(npix, np.nan, dtype=np.float32)
        if nm == "temp_level":
            arr[idx] = daily_mean.mean(axis=0)
        elif nm == "temp_range_diurnal":
            arr[idx] = diurnal.mean(axis=0)
        else:
            arr[idx] = daily_mean.max(axis=0) - daily_mean.min(axis=0)
        out[nm] = arr
    frost_seasons = np.full(npix, np.nan, dtype=np.float32); frost_seasons[idx] = (frost > 0).sum(axis=0)
    rms_max = np.full(npix, np.nan, dtype=np.float32); rms_max[idx] = rms.max(axis=0)
    n_nonconv = int((rms_max[idx] > RMS_FLAG).sum())

    # ---- coarse-scale check against the MCD layers being replaced
    cmp = {}
    gcm_lon = np.floor((lon_px + 180.0) / 5.625).astype(int)
    gcm_lat = np.floor((90.0 - lat_px) / 3.75).astype(int)
    cell = gcm_lat * 64 + gcm_lon
    for nm in out:
        old_p = os.path.join(HP, f"mars_{nm}_nside{NSIDE}.npy")
        if not os.path.exists(old_p):
            continue
        old = np.load(old_p)
        both = np.isfinite(old) & np.isfinite(out[nm])
        cnt = np.bincount(cell[both], minlength=64 * 49)
        m_new = np.bincount(cell[both], weights=out[nm][both], minlength=64 * 49) / np.maximum(cnt, 1)
        m_old = np.bincount(cell[both], weights=old[both], minlength=64 * 49) / np.maximum(cnt, 1)
        ok = cnt > 50
        d = m_new[ok] - m_old[ok]
        cmp[nm] = dict(gcm_cells=int(ok.sum()), mean_diff_K=float(d.mean()),
                       median_abs_diff_K=float(np.median(np.abs(d))),
                       p95_abs_diff_K=float(np.percentile(np.abs(d), 95)),
                       pearson_r=float(np.corrcoef(m_new[ok], m_old[ok])[0, 1]),
                       mcd_p50=float(np.median(m_old[ok])), model_p50=float(np.median(m_new[ok])))
        print(f"  MCD check {nm:20s}: {ok.sum()} GCM cells, mean diff {d.mean():+.2f} K, "
              f"median |diff| {np.median(np.abs(d)):.2f}, p95 {np.percentile(np.abs(d), 95):.2f}, "
              f"r {cmp[nm]['pearson_r']:.4f}")

    for nm, arr in out.items():
        lo, hi = GATES["mars"][nm]
        v = np.isfinite(arr)
        out_of = int(np.sum(v & ((arr < lo) | (arr > hi))))
        f = arr[v]
        print(f"  {nm:20s} valid {100*v.mean():.3f}%  p1 {np.percentile(f,1):.1f} p50 {np.median(f):.1f} "
              f"p99 {np.percentile(f,99):.1f} K  gate [{lo:g},{hi:g}]: "
              f"{'PASS' if out_of == 0 else f'FAIL {out_of:,} outside'}")
    print(f"  clipped to table edges: TI {n_ti_clip:,}, elev {n_elev_clip:,}, lat {n_lat_clip:,}, "
          f"tau {n_tau_clip:,} (per Ls, summed); albedo below 0.10 (extrapolated) {n_alb_below:,}; "
          f"non-converged (RMS > {RMS_FLAG} K in some season) {n_nonconv:,}")
    if a.test:
        print("\nTEST -- nothing written")
        return 0

    man = json.load(io.open(C.MANIFEST, encoding="utf-8"))["layers"]
    rel = lambda p: os.path.relpath(p, C.ROOT).replace(os.sep, "/")
    # albedo layer
    ap_ = os.path.join(HP, f"mars_albedo_nside{NSIDE}.npy")
    aps = os.path.join(HP, f"mars_albedo_support_nside{NSIDE}.npy")
    C.atomic_save(ap_, alb.astype(np.float32)); C.atomic_save(aps, alb_sup)
    va = validate(alb.astype(np.float32), NSIDE, "mars_albedo", "dimensionless",
                  dict(pixels_copied_not_binned=alb_copied, **alb_src), support=alb_sup)
    C.manifest_write("mars_albedo", dict(
        phase="3f", body=BODY, variable="albedo", units="bolometric albedo, dimensionless",
        role="input: albedo for the thermal model; characterization (not a ranking dimension by decision of 9 Nov 2026)",
        nside=NSIDE, order="nested", file=rel(ap_), support_file=rel(aps),
        source_files=["sources/tes_albedo/global_albedo_8ppd.img", "sources/tes_albedo/global_albedo_8ppd.lbl"],
        source="MGS TES bolometric albedo, 8 ppd (7.41 km), PC_REAL, Christensen et al. (2001) JGR 106:23823; PDS mgs-m-tes-special-v1",
        source_note=("the product is clipped by its producers to 0.06..0.32: 131,653 source cells sit "
                     "at the floor and 126,665 at the ceiling. No nodata value; all cells finite."),
        binning="bin then fill: 7.41 km source against a 6.79 km pixel, so some pixels receive no cell centre and take a nearest copy (support 0.0)",
        matching_eligible=False, validation=va,
        build_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
    # thermal layers, replacing the MCD ones
    for nm, arr in out.items():
        key = f"mars_{nm}"
        old_entry = man.get(key, {})
        path = os.path.join(HP, f"{key}_nside{NSIDE}.npy")
        spath = os.path.join(HP, f"{key}_support_nside{NSIDE}.npy")
        sup = np.where(np.isfinite(arr), ti_sup, np.nan).astype(np.float32)
        C.atomic_save(path, arr); C.atomic_save(spath, sup)
        lo, hi = GATES["mars"][nm]
        v = np.isfinite(arr)
        out_of = int(np.sum(v & ((arr < lo) | (arr > hi))))
        uq, cq = np.unique(arr[v], return_counts=True)
        extra = dict(healpix_pixels_filled=int(v.sum()), units="K",
                     range_gate_stated_in_advance=[lo, hi],
                     pixels_outside_stated_gate=out_of, range_gate_pass=bool(out_of == 0),
                     distinct_levels=int(uq.size), largest_tie_fraction=float(cq.max() / cq.sum()),
                     table_edge_clipping=dict(ti=n_ti_clip, elev=n_elev_clip, lat=n_lat_clip,
                                              tau_per_ls_summed=n_tau_clip, albedo_extrapolated_below_0_10=n_alb_below),
                     non_converged_pixels=n_nonconv, non_converged_rule=f"table RMS > {RMS_FLAG} K in any season",
                     frost_seasons_p50=float(np.nanmedian(frost_seasons)),
                     mcd_comparison=cmp.get(nm))
        vres = validate(arr, NSIDE, key, "K", extra, support=sup)
        show(vres)
        sup_old = {k: old_entry.get("validation", {}).get(k) for k in ("coverage_gate", "range_gate", "distinct_levels", "largest_tie_fraction", "pct_copied")}
        C.manifest_write(key, dict(
            phase="3f", body=BODY, variable=nm, units="K", nside=NSIDE, order="nested",
            file=rel(path), support_file=rel(spath),
            source_files=[f"cube/healpix/mars_thermal_inertia_nside{NSIDE}.npy", rel(ap_),
                          f"cube/healpix/mars_elevation_nside{NSIDE}.npy", rel(TABLE)] + dust_files,
            source_resolves=True, status=STATUS, modelled=True,
            model=dict(code="build/mars_thermal_1d.py + build/mars_temp_table.py",
                       validation="cube/phase4/mars_thermal_1d_validation.json",
                       table=rel(TABLE), table_meta=rel(TABLE_META),
                       dust_conversion=(f"tau_vis(546 Pa) = {VIS_IR_RATIO} x cdod610 x 546/610. The "
                                        f"visible-to-9.3-um-absorption ratio {VIS_IR_RATIO} is ASSUMED "
                                        f"(literature range about 2.0-2.6); a 25% change in tau moves "
                                        f"the daily mean by 1-2 K"),
                       definitions=dict(temp_level="mean over 12 Ls of the model's daily mean",
                                        temp_range_diurnal="mean over Ls of max minus min over 12 local times (0..22 h) -- unchanged from the MCD layer",
                                        temp_range_seasonal="max minus min over Ls of the daily mean")),
            matching_eligible=True,
            matching_eligible_reason=("Pixel-scale by construction: thermal inertia (2.96 km) and "
                                      "albedo (7.4 km) vary pixel to pixel, so a candidate patch is no "
                                      "longer thermally constant. The value is MODELLED; see status."),
            superseded_mcd_layer=dict(
                what="the Mars Climate Database layer of the same name, overwritten 9 Nov 2026",
                reason="355 km GCM grid, 3,072 distinct values, matching_eligible false (B17a); one convention on disk",
                old_validation=sup_old, old_build_utc=old_entry.get("build_utc"),
                coarse_scale_agreement=cmp.get(nm)),
            gates="range (stated, the MCD layer's), coverage, support (thermal-inertia support), table clipping, convergence",
            validation=vres, peak_rss_gib=peak_rss_gib(),
            build_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
    C.atomic_save(os.path.join(HP, f"mars_temp_frost_seasons_nside{NSIDE}.npy"), frost_seasons)
    C.atomic_save(os.path.join(HP, f"mars_temp_model_rms_nside{NSIDE}.npy"), rms_max)
    for key, arr, desc in (("mars_temp_frost_seasons", frost_seasons, "number of the 12 Ls bins in which the model holds CO2 frost on the surface"),
                           ("mars_temp_model_rms", rms_max, f"largest last-sol RMS change over the 12 seasons; > {RMS_FLAG} K = not converged")):
        v = np.isfinite(arr)
        C.manifest_write(key, dict(
            phase="3f", body=BODY, variable=key.replace("mars_", ""), role="diagnostic of the modelled thermal layers",
            units="count" if "frost" in key else "K", nside=NSIDE, order="nested",
            file=f"cube/healpix/{key}_nside{NSIDE}.npy", description=desc, matching_eligible=False,
            validation=dict(n_valid=int(v.sum()), p50=float(np.nanmedian(arr)), max=float(np.nanmax(arr))),
            build_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
    io.open(os.path.join(HP, "phase3f_mars_summary.json"), "w", encoding="utf-8").write(
        json.dumps(dict(mcd_comparison=cmp, clipping=dict(ti=n_ti_clip, elev=n_elev_clip, lat=n_lat_clip, tau=n_tau_clip,
                        albedo_below=n_alb_below), non_converged=n_nonconv), indent=1))
    print(f"\nwrote mars_temp_level, mars_temp_range_diurnal, mars_temp_range_seasonal (modelled), "
          f"mars_albedo, two diagnostics   {(time.perf_counter()-t0)/60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
