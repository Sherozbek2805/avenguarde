"""
MARS 1-D SURFACE THERMAL MODEL -- a NumPy port of KRC's one-point mode.

    python build/mars_thermal_1d.py --validate      # against sources/krc/doc/prt/Mone.prt
    python build/mars_thermal_1d.py --point Ls lat hour elev_km albedo TI tau [slope az]

WHY THIS EXISTS (VARIABLES.md B28)
    No measured gridded Mars surface-temperature map exists at pixel scale,
    and the Mars Climate Database's high-resolution mode does not touch
    surface temperature. The literature's route is a 1-D surface
    heat-balance model driven by thermal inertia, albedo, pressure and
    latitude (Kieffer 1977; Mellon 2000; Putzig & Mellon 2007; Kieffer
    2013). KRC is that model; it is public Fortran with no compiler on this
    machine yet. This is the same physics in NumPy, vectorised over CASES so
    that a lookup table of 10^4-10^5 (TI, albedo, pressure, latitude, dust,
    season) cells runs in minutes. Everything it produces is MODELLED, not
    measured, and is labelled so.

WHAT IT MIRRORS FROM KRC (Mone.inp defaults, Kieffer 2013 sections 2-3)
    soil        homogeneous, density 1600 kg m-3, specific heat 647 J kg-1 K-1,
                k = I^2 / (rho c); 21 layers, first 0.18 diurnal skin depths,
                ratio 1.2; insulating lower boundary (IIB = 0)
    time        explicit forward differences, 384 steps per sol; start at the
                equilibrium mean; after sol 3 all layers are reset to the mean
                surface temperature (KRC's "jump"), then run until the RMS
                change of the surface curve between sols is under DTMAX = 0.1 K
                or 15 sols -- the one-point mode has no seasonal memory
    sun         Keplerian orbit (a 1.52368 AU, e 0.0934, Ls of perihelion
                251 deg), obliquity 25.19 deg, solar constant 1368 W m-2,
                sol 88775 s; slope and down-slope azimuth as KRC's SLOPE/SLOAZI
    atmosphere  ONE grey layer. Solar: delta-Eddington two-stream
                (Joseph, Wiscombe & Weinman 1976; Toon et al. 1989 coefficients)
                with dust single-scattering albedo 0.90 and asymmetry 0.5,
                over a Lambert surface, visible opacity tau scaled by local
                pressure as KRC does. Infrared: dust opacity 0.25 tau plus a
                gas opacity 0.11 at 546 Pa scaling with pressure; layer
                emissivity 1 - exp(-1.66 tau_IR); the layer temperature obeys
                C_a dT_a/dt = absorbed solar + eps_a sigma Ts^4 - 2 eps_a sigma Ta^4
                with C_a = cp P / g (cp 735.9). This is KRC's architecture,
                not its code: KRC's atmosphere-temperature treatment has more
                terms (twilight, ice clouds, snowfall), none used here.
    pressure    P = 546 Pa * exp(-z / 10.26 km) (TATM 200 K, M 43.5); no
                seasonal pressure cycle in one-point mode
    frost       CO2 frost point from ln Pc = 27.9546 - 3182.48 / T (James et
                al. 1992) on the CO2 partial pressure (1 - 0.055) P; when the
                surface would fall below it the surface is held at the frost
                point and the energy deficit becomes frost mass (L = 589,944
                J kg-1); frost albedo 0.65, frost emissivity 0.95, frost
                sublimes when the balance turns positive

WHAT IT DOES NOT DO (recorded)
    temperature-dependent conductivity (KRC LKofT off in Mone.inp too),
    two-material columns, far-field radiation from slopes, twilight
    extension, ice clouds, atmospheric condensation, the seasonal pressure
    cycle, eclipses. Polar-cap-edge results are unreliable here exactly as
    KRC's documentation says they are for its one-point mode.

VALIDATION
    --validate runs KRC's own one-point reference set (Mone.prt, 22 cases:
    Viking landers, Arsia Mons, a polar cap point, spin-up tests) and reports
    the difference in surface kinetic temperature case by case. The target
    stated in advance: median |dT| under 3 K, no case over 8 K except the
    polar-cap test, which KRC itself flags as unreliable in this mode.
"""

import argparse
import io
import json
import os
import re
import sys
import time

import numpy as np

SIGMA = 5.670374419e-8
SOL_S = 88775.244                 # Mars solar day
SOLCON = 1368.0                   # KRC SOLCON, W m-2 at 1 AU
A_AU, ECC, LS_PERI, OBLIQ = 1.52368, 0.09340, 251.0, 25.19
RHO, CP_SOIL = 1600.0, 647.0      # KRC defaults DENSITY, SPEC_HEAT
EMIS_SOIL = 1.0
P0, Z_SCALE_KM = 546.0, 10.26     # KRC PTOTAL at 0 km; H = R*TATM/(M g)
FANON = 0.055                     # non-condensing mass fraction
CABR, TAURAT = 0.11, 0.25         # gas IR opacity at P0; dust IR/vis ratio
OMEGA_DUST, G_DUST = 0.90, 0.50   # DUSTA, ARC2
CP_ATM, GRAV = 735.9, 3.727
DIFFUSIVITY = 1.66
T_FROST_MIN = 146.0
L_FROST, A_FROST, E_FROST = 589944.0, 0.65, 0.95
SAT_A, SAT_B = 27.9546, 3182.48
N_LAYERS, FLAY, RLAY = 21, 0.18, 1.2
STEPS_PER_SOL = 384
SOLS_BEFORE_JUMP, MAX_SOLS, DTMAX = 3, 15, 0.1
NEWTON_ITERS = 4


# ------------------------------------------------------------------ geometry

def orbit(ls_deg):
    """Heliocentric distance (AU) and solar declination (rad) at Ls."""
    ls = np.radians(ls_deg)
    r = A_AU * (1.0 - ECC ** 2) / (1.0 + ECC * np.cos(ls - np.radians(LS_PERI)))
    dec = np.arcsin(np.sin(np.radians(OBLIQ)) * np.sin(ls))
    return r, dec


def cos_incidence(lat_rad, dec, hour_angle, slope_rad, az_rad):
    """cos of solar incidence on a flat surface (mu0) and on the slope.

    Hour angle 0 at local noon. Down-slope azimuth east of north, as KRC.
    """
    mu0 = np.sin(lat_rad) * np.sin(dec) + np.cos(lat_rad) * np.cos(dec) * np.cos(hour_angle)
    # solar azimuth east of north
    sin_az = -np.cos(dec) * np.sin(hour_angle)
    cos_az = (np.sin(dec) - np.sin(lat_rad) * mu0) / np.maximum(np.cos(lat_rad) * np.sqrt(np.maximum(1 - mu0 ** 2, 1e-12)), 1e-12)
    cos_az = np.clip(cos_az, -1, 1)
    sun_az = np.arctan2(sin_az, cos_az)
    sin_z = np.sqrt(np.maximum(1.0 - mu0 ** 2, 0.0))
    mu_s = np.cos(slope_rad) * mu0 + np.sin(slope_rad) * sin_z * np.cos(sun_az - az_rad)
    mu0 = np.maximum(mu0, 0.0)
    mu_s = np.where(mu0 > 0, np.maximum(mu_s, 0.0), 0.0)
    return mu0, mu_s


# --------------------------------------------------------- delta-Eddington

def delta_eddington(tau, omega, g, mu0, albedo):
    """Two-stream delta-Eddington for one homogeneous layer over a Lambert
    surface, unit incident flux normal to the beam. Returns the DOWNWARD flux
    at the surface (direct + diffuse, per unit mu0*F0 -> already includes mu0)
    and the flux absorbed in the layer, both per unit F0.
    Toon et al. (1989) Eddington coefficients; Joseph et al. (1976) scaling.
    """
    mu0 = np.maximum(mu0, 1e-6)
    f = g * g
    t = (1.0 - omega * f) * tau
    w = (1.0 - f) * omega / (1.0 - omega * f)
    gg = g / (1.0 + g)
    g1 = (7.0 - w * (4.0 + 3.0 * gg)) / 4.0
    g2 = -(1.0 - w * (4.0 - 3.0 * gg)) / 4.0
    g3 = (2.0 - 3.0 * gg * mu0) / 4.0
    g4 = 1.0 - g3
    lam = np.sqrt(np.maximum(g1 * g1 - g2 * g2, 1e-12))
    gam = g2 / (g1 + lam)
    denom = lam * lam - 1.0 / mu0 ** 2
    denom = np.where(np.abs(denom) < 1e-6, 1e-6, denom)
    cp0 = w * ((g1 - 1.0 / mu0) * g3 + g4 * g2) / denom          # C+ at tau=0 per F0
    cm0 = w * ((g1 + 1.0 / mu0) * g4 + g2 * g3) / denom          # C- at tau=0
    e_dir = np.exp(-t / mu0)
    cpt, cmt = cp0 * e_dir, cm0 * e_dir
    ep, em = np.exp(lam * t), np.exp(-lam * t)
    # F-(0) = 0 :            gam*k1 + k2 = -cm0
    # F+(t) = A (F-(t) + mu0 e_dir): k1 ep + gam k2 em + cpt = A (gam k1 ep + k2 em + cmt + mu0 e_dir)
    a11, a12, b1 = gam, 1.0, -cm0
    a21 = ep - albedo * gam * ep
    a22 = gam * em - albedo * em
    b2 = albedo * (cmt + mu0 * e_dir) - cpt
    det = a11 * a22 - a12 * a21
    det = np.where(np.abs(det) < 1e-12, 1e-12, det)
    k1 = (b1 * a22 - a12 * b2) / det
    k2 = (a11 * b2 - b1 * a21) / det
    f_down_dif = gam * k1 * ep + k2 * em + cmt
    f_up_top = k1 + gam * k2 + cp0
    down = np.maximum(f_down_dif, 0.0) + mu0 * e_dir
    absorbed_atm = mu0 - f_up_top - (1.0 - albedo) * down
    return down, np.maximum(absorbed_atm, 0.0)


# ------------------------------------------------------------------- model

def run_cases(ls, lat_deg, elev_km, albedo, inertia, tau_vis, slope_deg=0.0,
              az_deg=0.0, hours_out=None, verbose=False):
    """Run N independent one-point cases (all inputs arrays of length N or
    scalars). Returns a dict with the converged surface temperature curve at
    `hours_out` local times (default 24), daily mean/min/max, frost flag,
    sols run and the per-case RMS convergence."""
    ls, lat_deg, elev_km, albedo, inertia, tau_vis, slope_deg, az_deg = np.broadcast_arrays(
        *[np.atleast_1d(np.asarray(x, dtype=np.float64)) for x in
          (ls, lat_deg, elev_km, albedo, inertia, tau_vis, slope_deg, az_deg)])
    n = ls.size
    hours_out = np.arange(24.0) if hours_out is None else np.asarray(hours_out, float)

    r_au, dec = orbit(ls)
    s_toa = SOLCON / r_au ** 2                               # W m-2 at TOA, normal
    lat = np.radians(lat_deg); slope = np.radians(slope_deg); az = np.radians(az_deg)
    p = P0 * np.exp(-elev_km / Z_SCALE_KM)
    tau = tau_vis * p / P0                                   # KRC: opacity scales with P
    tau_ir = TAURAT * tau + CABR * p / P0
    eps_a = 1.0 - np.exp(-DIFFUSIVITY * tau_ir)
    c_atm = CP_ATM * p / GRAV
    t_frost = np.maximum(SAT_B / (SAT_A - np.log(np.maximum((1.0 - FANON) * p, 1e-3))), T_FROST_MIN)

    k = inertia ** 2 / (RHO * CP_SOIL)
    kappa = k / (RHO * CP_SOIL)
    skin = np.sqrt(kappa * SOL_S / np.pi)
    dz = np.empty((n, N_LAYERS))
    dz[:, 0] = FLAY * skin
    for i in range(1, N_LAYERS):
        dz[:, i] = dz[:, i - 1] * RLAY
    half = 0.5 * (dz[:, :-1] + dz[:, 1:])                    # centre-to-centre
    dt = SOL_S / STEPS_PER_SOL
    # stability check against the first layer
    if np.any(dt > 0.5 * dz[:, 0] ** 2 / kappa):
        raise RuntimeError("time step violates the explicit stability limit")

    # equilibrium start: radiative mean temperature of a perfect conductor
    hours = (np.arange(STEPS_PER_SOL) + 0.5) / STEPS_PER_SOL * 24.0
    ha = np.radians(15.0 * (hours[None, :] - 12.0))
    mu0_day, mus_day = cos_incidence(lat[:, None], dec[:, None], ha, slope[:, None], az[:, None])
    down_day, _ = delta_eddington(tau[:, None], OMEGA_DUST, G_DUST, mu0_day, albedo[:, None])
    # insolation on the slope: direct part redirected by mu_s/mu0, diffuse kept
    e_dir = np.exp(-(1.0 - OMEGA_DUST * G_DUST ** 2) * tau[:, None] / np.maximum(mu0_day, 1e-6))
    direct = np.where(mu0_day > 0, mus_day * e_dir, 0.0)
    diffuse = np.where(mu0_day > 0, down_day - mu0_day * e_dir, 0.0)
    q_sun_day = s_toa[:, None] * (direct + diffuse)          # W m-2 incident on the surface
    mean_abs = ((1.0 - albedo[:, None]) * q_sun_day).mean(axis=1)
    t_eq = (np.maximum(mean_abs, 1.0) / (EMIS_SOIL * SIGMA)) ** 0.25
    T = np.repeat(t_eq[:, None], N_LAYERS, axis=1)
    ts = t_eq.copy()
    ta = t_eq.copy() * 0.85
    frost = np.zeros(n)

    def surface_step(T1, dz1, q_abs, q_ir_down, ts_prev, frost):
        """Solve the surface quartic by Newton: absorbed + IR_down - eps sigma Ts^4 - k (Ts - T1)/(dz1/2) = 0."""
        eps = np.where(frost > 0, E_FROST, EMIS_SOIL)
        cond = k / (0.5 * dz1)
        x = ts_prev.copy()
        for _ in range(NEWTON_ITERS):
            f = q_abs + q_ir_down - eps * SIGMA * x ** 4 - cond * (x - T1)
            df = -4.0 * eps * SIGMA * x ** 3 - cond
            x = x - f / df
        # frost: hold at the frost point where the surface would be colder,
        # or where frost is present and the balance is still negative
        below = x < t_frost
        hold = below | (frost > 0)
        x_h = np.where(hold, t_frost, x)
        # energy not balanced at the held temperature -> frost mass change
        resid = q_abs + q_ir_down - eps * SIGMA * x_h ** 4 - cond * (x_h - T1)
        dfrost = np.where(hold, -resid * dt / L_FROST, 0.0)   # deficit -> frost grows
        frost_new = np.maximum(frost + dfrost, 0.0)
        # if frost just vanished this step, release the hold
        x_out = np.where(hold & (frost_new <= 0) & ~below, x, x_h)
        return x_out, frost_new, eps

    curve_prev = None
    sol_rms = np.full(n, np.inf)
    sols_done = 0
    for sol in range(MAX_SOLS):
        curve = np.empty((n, STEPS_PER_SOL))
        for j in range(STEPS_PER_SOL):
            alb_eff = np.where(frost > 0, A_FROST, albedo)
            q_abs = (1.0 - alb_eff) * q_sun_day[:, j]
            q_ir_down = eps_a * SIGMA * ta ** 4
            ts, frost, eps = surface_step(T[:, 0], dz[:, 0], q_abs, q_ir_down, ts, frost)
            # conduction: fluxes between layers, insulating bottom
            flux = k[:, None] * (T[:, :-1] - T[:, 1:]) / half          # positive downward
            top_flux = k * (ts - T[:, 0]) / (0.5 * dz[:, 0])
            dTdt = np.empty_like(T)
            dTdt[:, 0] = (top_flux - flux[:, 0]) / (RHO * CP_SOIL * dz[:, 0])
            dTdt[:, 1:-1] = (flux[:, :-1] - flux[:, 1:]) / (RHO * CP_SOIL * dz[:, 1:-1])
            dTdt[:, -1] = flux[:, -1] / (RHO * CP_SOIL * dz[:, -1])
            T += dt * dTdt
            # atmosphere layer
            _, abs_atm = delta_eddington(tau, OMEGA_DUST, G_DUST, mu0_day[:, j], albedo)
            q_atm = s_toa * abs_atm + eps_a * eps * SIGMA * ts ** 4 - 2.0 * eps_a * SIGMA * ta ** 4
            ta = ta + dt * q_atm / c_atm
            ta = np.maximum(ta, 120.0)
            curve[:, j] = ts
        sols_done = sol + 1
        if sol == SOLS_BEFORE_JUMP - 1:
            # KRC's jump: all layers to the mean surface temperature of the day
            tm = curve.mean(axis=1)
            T[:] = tm[:, None]
        if curve_prev is not None:
            sol_rms = np.sqrt(((curve - curve_prev) ** 2).mean(axis=1))
            if sol >= SOLS_BEFORE_JUMP + 2 and np.all(sol_rms < DTMAX):
                break
        curve_prev = curve.copy()
        if verbose:
            print(f"    sol {sol+1}: max RMS change {np.nanmax(sol_rms) if np.isfinite(sol_rms).any() else float('nan'):.3f} K")
    # sample at requested local times (linear on the periodic curve)
    idx = np.interp(hours_out, hours, np.arange(STEPS_PER_SOL))
    i0 = np.floor(idx).astype(int) % STEPS_PER_SOL
    i1 = (i0 + 1) % STEPS_PER_SOL
    wgt = idx - np.floor(idx)
    ts_out = curve[:, i0] * (1 - wgt) + curve[:, i1] * wgt
    return dict(hours=hours_out, ts=ts_out, ts_mean=curve.mean(axis=1),
                ts_min=curve.min(axis=1), ts_max=curve.max(axis=1),
                frost_kg_m2=frost, t_frost=t_frost, pressure_pa=p,
                sols=sols_done, rms_last=sol_rms, t_atm=ta)


# -------------------------------------------------------------- validation

def parse_mone_prt(path):
    rows = []
    for line in io.open(path, encoding="latin1"):
        m = re.match(r"\s*11\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*(.*)$", line)
        if m:
            v = [float(x) for x in m.groups()[:11]]
            rows.append(dict(ls=v[0], lat=v[1], hour=v[2], elev=v[3], alb=v[4], ti=v[5],
                             tau=v[6], slope=v[7], az=v[8], tk_krc=v[9], tb_krc=v[10],
                             name=m.group(12).strip()))
    return rows


def validate():
    here = os.path.dirname(os.path.abspath(__file__))
    prt = os.path.join(here, "..", "sources", "krc", "doc", "prt", "Mone.prt")
    rows = parse_mone_prt(prt)
    print(f"KRC one-point reference: {len(rows)} cases from {os.path.relpath(prt, os.path.join(here, '..'))}")
    print("TARGET, stated in advance: median |dT| < 3 K; no case > 8 K except the polar-cap test")
    t0 = time.perf_counter()
    out = run_cases([r["ls"] for r in rows], [r["lat"] for r in rows], [r["elev"] for r in rows],
                    [r["alb"] for r in rows], [r["ti"] for r in rows], [r["tau"] for r in rows],
                    [r["slope"] for r in rows], [r["az"] for r in rows],
                    hours_out=[r["hour"] for r in rows])
    # each case wants its own hour: pick the diagonal
    ts = np.array([out["ts"][i, i] for i in range(len(rows))])
    el = time.perf_counter() - t0
    print(f"{'case':20s} {'Ls':>6s} {'lat':>6s} {'hr':>5s} {'TI':>6s} {'tau':>4s} {'slp':>4s} "
          f"{'KRC':>7s} {'model':>7s} {'dT':>6s}")
    d = []
    for i, r in enumerate(rows):
        dT = ts[i] - r["tk_krc"]
        d.append(dT)
        print(f"{r['name'][:20]:20s} {r['ls']:6.1f} {r['lat']:6.1f} {r['hour']:5.2f} {r['ti']:6.1f} "
              f"{r['tau']:4.2f} {r['slope']:4.1f} {r['tk_krc']:7.2f} {ts[i]:7.2f} {dT:+6.2f}")
    d = np.array(d)
    polar = np.array(["Polar" in r["name"] for r in rows])
    print(f"\nmedian |dT| {np.median(np.abs(d)):.2f} K, mean dT {d.mean():+.2f} K, "
          f"max |dT| (non-polar) {np.abs(d[~polar]).max():.2f} K, polar case dT {d[polar][0]:+.2f} K; "
          f"{out['sols']} sols, {el:.1f} s")
    ok = np.median(np.abs(d)) < 3.0 and np.abs(d[~polar]).max() < 8.0
    print("VALIDATION", "PASS" if ok else "FAIL")
    res = dict(cases=[dict(**r, tk_model=float(ts[i]), dT=float(d[i])) for i, r in enumerate(rows)],
               median_abs_dT=float(np.median(np.abs(d))), mean_dT=float(d.mean()),
               max_abs_dT_nonpolar=float(np.abs(d[~polar]).max()), passed=bool(ok),
               sols=int(out["sols"]), elapsed_s=round(el, 1),
               target="median |dT| < 3 K, non-polar max < 8 K")
    p4 = os.path.join(here, "..", "cube", "phase4")
    os.makedirs(p4, exist_ok=True)
    io.open(os.path.join(p4, "mars_thermal_1d_validation.json"), "w", encoding="utf-8").write(
        json.dumps(res, indent=1))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--point", nargs="+", type=float,
                    help="Ls lat hour elev_km albedo TI tau [slope az]")
    a = ap.parse_args()
    if a.validate:
        return validate()
    if a.point:
        v = a.point + [0.0, 0.0][len(a.point) - 7:] if len(a.point) < 9 else a.point
        out = run_cases(v[0], v[1], v[3], v[4], v[5], v[6], v[7], v[8], hours_out=[v[2]], verbose=True)
        print(f"Ts at {v[2]:.2f} h = {out['ts'][0,0]:.2f} K; mean {out['ts_mean'][0]:.2f} "
              f"min {out['ts_min'][0]:.2f} max {out['ts_max'][0]:.2f}; P {out['pressure_pa'][0]:.0f} Pa; "
              f"frost point {out['t_frost'][0]:.1f} K; frost {out['frost_kg_m2'][0]:.2f} kg/m2; "
              f"T_atm {out['t_atm'][0]:.1f} K; {out['sols']} sols")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
