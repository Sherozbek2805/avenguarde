"""
MARS SURFACE-TEMPERATURE LOOKUP TABLE from the 1-D model (VARIABLES.md B28).

    python build/mars_temp_table.py [--quick]

The literature's method (Mellon 2000, Putzig & Mellon 2007, Fergason 2006):
run the thermal model over a grid of thermal inertia, albedo, pressure,
latitude, dust opacity and season, then read every pixel's temperature off
the table by interpolation. Inverted here: they went from measured T to TI,
we go from TI (theirs) to T.

AXES (stated so the interpolation limits are known):
    Ls         12 seasons, 0..330 step 30 (the MCD convention kept)
    TI         20 values, log-spaced 20..2500 tiu (Mars p1-p99 is 30..480;
               pixels outside are CLIPPED to the table edge and counted)
    albedo     7 values 0.10..0.40 step 0.05
    elevation  7 values -8, -4, -1, 2, 5, 10, 20 km -> pressure by one scale height
    latitude   30 values -87..87 step 6
    dust tau   4 values 0.15, 0.30, 0.60, 1.00 (visible, at the 546 Pa reference)
    local time 12 values 0..22 h step 2 (matches the MCD sampling, so the
               Mars diurnal-range definition 'max minus min over 12 local
               times' is unchanged)
Slope is NOT a table axis: flat surfaces. At 6.8 km the mean slope is a
few degrees; the slope effect on the daily mean is second order and is
recorded as an approximation, not hidden.

OUTPUT cube/mars_temp_table.npz: ts[Ls, TI, A, elev, lat, tau, LT] float32,
plus ts_mean, ts_min, ts_max, frost (kg m-2 at the end of the spin-up) and
the axes, and cube/mars_temp_table.json with the model constants and the
validation reference.
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
import mars_thermal_1d as M

OUT_NPZ = os.path.join(C.ROOT, "cube", "mars_temp_table.npz")
OUT_JSON = os.path.join(C.ROOT, "cube", "mars_temp_table.json")

LS = np.arange(0.0, 360.0, 30.0)
TI = np.geomspace(20.0, 2500.0, 20)
ALB = np.arange(0.10, 0.401, 0.05)
ELEV = np.array([-8.0, -4.0, -1.0, 2.0, 5.0, 10.0, 20.0])
LAT = np.arange(-87.0, 88.0, 6.0)
TAU = np.array([0.15, 0.30, 0.60, 1.00])
LT = np.arange(0.0, 24.0, 2.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="2 Ls, 1 tau: timing only")
    ap.add_argument("--extend-tau", type=float, default=None,
                    help="run ONE extra dust level for all Ls and merge it into the existing table")
    a = ap.parse_args()
    ls_ax, tau_ax = (LS[:2], TAU[1:2]) if a.quick else (LS, TAU)
    if a.extend_tau is not None:
        tau_ax = np.array([a.extend_tau])
    shape = (ls_ax.size, TI.size, ALB.size, ELEV.size, LAT.size, tau_ax.size)
    n_per = TI.size * ALB.size * ELEV.size * LAT.size
    print("=" * 78)
    print("MARS TEMPERATURE LOOKUP TABLE -- 1-D model, KRC one-point physics")
    print("=" * 78)
    print(f"  axes Ls {ls_ax.size} x TI {TI.size} x albedo {ALB.size} x elev {ELEV.size} "
          f"x lat {LAT.size} x tau {tau_ax.size} = {int(np.prod(shape)):,} cases, "
          f"{n_per:,} per (Ls, tau) chunk; {LT.size} local times")
    ts = np.full(shape + (LT.size,), np.nan, dtype=np.float32)
    tmean = np.full(shape, np.nan, dtype=np.float32)
    tmin = np.full(shape, np.nan, dtype=np.float32)
    tmax = np.full(shape, np.nan, dtype=np.float32)
    frost = np.full(shape, np.nan, dtype=np.float32)
    rms = np.full(shape, np.nan, dtype=np.float32)      # last-sol RMS change: convergence flag
    sols = np.zeros(shape[:1] + shape[5:6], dtype=np.int16)
    gTI, gA, gE, gL = np.meshgrid(TI, ALB, ELEV, LAT, indexing="ij")
    t0 = time.perf_counter()
    n_chunks = ls_ax.size * tau_ax.size
    k = 0
    for i, ls in enumerate(ls_ax):
        for j, tau in enumerate(tau_ax):
            tc = time.perf_counter()
            out = M.run_cases(ls, gL.ravel(), gE.ravel(), gA.ravel(), gTI.ravel(), tau,
                              hours_out=LT)
            sh = (TI.size, ALB.size, ELEV.size, LAT.size)
            ts[i, :, :, :, :, j, :] = out["ts"].reshape(sh + (LT.size,)).astype(np.float32)
            tmean[i, :, :, :, :, j] = out["ts_mean"].reshape(sh)
            tmin[i, :, :, :, :, j] = out["ts_min"].reshape(sh)
            tmax[i, :, :, :, :, j] = out["ts_max"].reshape(sh)
            frost[i, :, :, :, :, j] = out["frost_kg_m2"].reshape(sh)
            rms[i, :, :, :, :, j] = out["rms_last"].reshape(sh)
            nc = out["rms_last"] > 0.5
            fr = out["frost_kg_m2"] > 0
            sols[i, j] = out["sols"]
            k += 1
            el = time.perf_counter() - t0
            print(f"    Ls {ls:5.1f} tau {tau:.2f}: {out['sols']} sols, "
                  f"{time.perf_counter()-tc:5.1f} s; max RMS last sol "
                  f"{np.nanmax(out['rms_last']):.3f} K; frost on "
                  f"{int((out['frost_kg_m2'] > 0).sum()):,} cases; "
                  f"{el/60:5.1f} min, eta {el/k*(n_chunks-k)/60:5.1f} min", flush=True)
            print(f"       not converged (RMS > 0.5 K): {int(nc.sum()):,} cases, of which with frost "
                  f"{int((nc & fr).sum()):,}; non-frost RMS p99 {np.percentile(out['rms_last'][~fr], 99) if (~fr).any() else float('nan'):.3f} K", flush=True)
    if a.quick:
        print("QUICK run -- nothing written")
        return 0
    if a.extend_tau is not None:
        # merge the new dust level into the existing table, keeping tau ascending
        old = np.load(OUT_NPZ)
        order = np.argsort(np.concatenate([old["tau"], tau_ax]))
        def cat(name, new):
            return np.concatenate([old[name], new], axis=5)[:, :, :, :, :, order]
        ts, tmean, tmin, tmax = cat("ts", ts), cat("ts_mean", tmean), cat("ts_min", tmin), cat("ts_max", tmax)
        frost, rms = cat("frost", frost), cat("rms_last_sol", rms)
        sols = np.concatenate([old["sols"], sols], axis=1)[:, order]
        tau_ax = np.concatenate([old["tau"], tau_ax])[order]
        meta_old = json.load(io.open(OUT_JSON, encoding="utf-8"))
        print(f"  merged: tau axis now {tau_ax.tolist()}")
    np.savez_compressed(OUT_NPZ, ts=ts, ts_mean=tmean, ts_min=tmin, ts_max=tmax,
                        frost=frost, rms_last_sol=rms, sols=sols, ls=ls_ax, ti=TI, albedo=ALB, elev_km=ELEV,
                        lat=LAT, tau=tau_ax, local_time=LT)
    meta = dict(
        axes=dict(ls=ls_ax.tolist(), ti=TI.round(3).tolist(), albedo=ALB.round(3).tolist(),
                  elev_km=ELEV.tolist(), lat=LAT.tolist(), tau=tau_ax.tolist(),
                  local_time=LT.tolist()),
        model="build/mars_thermal_1d.py -- NumPy port of KRC one-point mode (Kieffer 2013)",
        model_constants=dict(rho=M.RHO, cp=M.CP_SOIL, emissivity=M.EMIS_SOIL, p0_pa=M.P0,
                             scale_height_km=M.Z_SCALE_KM, dust_ssa=M.OMEGA_DUST,
                             dust_g=M.G_DUST, taurat=M.TAURAT, cabr=M.CABR,
                             frost_albedo=M.A_FROST, frost_emis=M.E_FROST,
                             latent_heat=M.L_FROST, layers=M.N_LAYERS, flay=M.FLAY,
                             rlay=M.RLAY, steps_per_sol=M.STEPS_PER_SOL,
                             max_sols=M.MAX_SOLS, dtmax=M.DTMAX),
        validation="cube/phase4/mars_thermal_1d_validation.json (KRC Mone.prt, 23 cases)",
        approximations=[
            "flat surfaces: slope and aspect are not table axes",
            "one-layer grey atmosphere; dust opacity from a climatology, not the observed year",
            "no seasonal pressure cycle; no atmospheric condensation or ice clouds",
            "one-point mode: no seasonal memory, so the seasonal CO2 cap is not tracked and "
            "polar-cap-edge results are unreliable (as KRC documents for this mode)",
            "TI outside 20..2500 clipped to the table edge at interpolation time",
            "the model reads about 1 K colder than KRC on the reference set (mean -1.1 K)"],
        status="MODELLED, NOT MEASURED. Label every derived layer so.",
        built_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        elapsed_min=round((time.perf_counter() - t0) / 60, 1))
    if a.extend_tau is not None:
        meta["extended"] = (meta_old.get("extended", []) +
                            [dict(tau=float(a.extend_tau), built_utc=meta["built_utc"],
                                  reason="24% of (Ls, cell) dust values in the climatology lie below the original 0.15 floor")])
        meta["elapsed_min"] = meta_old.get("elapsed_min", 0) + meta["elapsed_min"]
    io.open(OUT_JSON, "w", encoding="utf-8").write(json.dumps(meta, indent=1))
    print(f"\nwrote {OUT_NPZ} ({os.path.getsize(OUT_NPZ)/2**20:.0f} MB) and {OUT_JSON} in "
          f"{meta['elapsed_min']} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
