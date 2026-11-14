"""
THE CUBE ATLAS -- every ranking layer as a map, every pairing as graphs, one PDF.

    python build/atlas.py [--quick]

Writes docs/figures/atlas/*.png (reused by the spec revision) and
docs/CUBE_ATLAS_2026-11-09.pdf, one page per figure with a caption that says
what is shown, from which file, with which stretch. Nothing here changes a
number in the cube; it reads the manifest and the arrays as they are.

Rendering rules (the same as the project's other figures):
  - maps are HEALPix -> plate carree 2880 x 1440 by pixel lookup, no smoothing
  - Earth ranking layers are shown over the REFERENCE POPULATION only, because
    that is what ranks; everything else is dark grey
  - colour stretch is p2..p98 of the shown population unless the layer has a
    physical range (SVF 0..1, albedo, composition); roughness is log10
  - absent / masked = dark grey, never a colour that could pass for a value
  - south-polar insets for the Moon and Mars, 85-90 S, polar stereographic
"""

import argparse
import io
import json
import os
import sys
import time

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C
from figures_h import to_platecarree, to_south_polar

ROOT = C.ROOT
HP = os.path.join(ROOT, "cube", "healpix")
OUT_DIR = os.path.join(ROOT, "docs", "figures", "atlas")
PDF = os.path.join(ROOT, "docs", "CUBE_ATLAS_2026-11-09.pdf")
DARK = "#2b2b2b"
PC_W, PC_H = 2880, 1440
POLAR_PX, POLAR_RAD = 1200, 5.0

LAYERS = {   # name: (label, units, stretch, cmap)
    "slope": ("Slope, 7 km baseline", "degrees", "p98", "magma"),
    "roughness_5.25km": ("Roughness, 5.25 km window", "m (log10)", "log", "viridis"),
    "roughness_10.5km": ("Roughness, 10.5 km window", "m (log10)", "log", "viridis"),
    "roughness_21km": ("Roughness, 21 km window", "m (log10)", "log", "viridis"),
    "roughness_42km": ("Roughness, 42 km window", "m (log10)", "log", "viridis"),
    "tpi_21km": ("Topographic position index, 21 km", "m", "sym", "RdBu_r"),
    "tpi_7km": ("Topographic position index, 7 km", "m", "sym", "RdBu_r"),
    "svf_30km": ("Sky view factor, 30 km radius", "dimensionless", (0.6, 1.0), "cividis"),
    "temp_level": ("Temperature level", "K", "p2p98", "inferno"),
    "temp_range_diurnal": ("Diurnal temperature range", "K", "p2p98", "plasma"),
    "temp_range_seasonal": ("Seasonal temperature range", "K", "p2p98", "plasma"),
    "thermal_inertia": ("Thermal inertia", "tiu (Mars) / K^-1 apparent (Earth)", "log", "YlGnBu_r"),
    "SiO2": ("Silica, SiO2", "wt%", (35, 70), "coolwarm"),
    "FeO": ("Iron oxide, FeO_T", "wt%", (0, 30), "copper_r"),
    "albedo": ("Bolometric albedo", "dimensionless", (0.06, 0.32), "gray"),
}
BODY_ORDER = (("earth", 1024), ("moon", 256), ("mars", 512))


def load(body, nside, name):
    p = os.path.join(HP, f"{body}_{name}_nside{nside}.npy")
    return np.load(p) if os.path.exists(p) else None


def earth_ref():
    m = np.load(os.path.join(HP, "earth_reference_mask_nside1024.npy"))
    return np.isfinite(m) & (m > 0.5)


def stretch(vals, spec):
    f = vals[np.isfinite(vals)]
    if isinstance(spec, tuple):
        return spec[0], spec[1], False
    if spec == "log":
        f = f[f > 0]
        return np.percentile(f, 2), np.percentile(f, 98), True
    if spec == "sym":
        a = np.percentile(np.abs(f), 98)
        return -a, a, False
    if spec == "p98":
        return 0.0, np.percentile(f, 98), False
    return np.percentile(f, 2), np.percentile(f, 98), False


def draw_map(arr2d, title, caption, cmap, vmin, vmax, log, units, path, polar=None, fs=(13, 7.6)):
    fig = plt.figure(figsize=fs, dpi=150)
    if polar is None:
        ax = fig.add_axes([0.03, 0.12, 0.84, 0.80])
    else:
        ax = fig.add_axes([0.03, 0.12, 0.62, 0.80])
        axp = fig.add_axes([0.665, 0.30, 0.22, 0.44])
    cm = plt.get_cmap(cmap).copy(); cm.set_bad(DARK)
    shown = np.log10(np.where(arr2d > 0, arr2d, np.nan)) if log else arr2d
    lo, hi = (np.log10(max(vmin, 1e-6)), np.log10(hi_ := max(vmax, 1e-6))) if log else (vmin, vmax)
    im = ax.imshow(np.ma.masked_invalid(shown), cmap=cm, vmin=lo, vmax=hi, interpolation="nearest",
                   extent=[-180, 180, -90, 90], aspect="auto")
    ax.set_xticks(range(-180, 181, 60)); ax.set_yticks(range(-90, 91, 30))
    ax.tick_params(labelsize=7); ax.grid(color="white", alpha=0.15, linewidth=0.4)
    ax.set_title(title, fontsize=13, loc="left", pad=8)
    if polar is not None:
        parr, inside, rr = polar
        ps = np.log10(np.where(parr > 0, parr, np.nan)) if log else parr
        axp.imshow(np.ma.masked_invalid(ps), cmap=cm, vmin=lo, vmax=hi, interpolation="nearest")
        axp.contour(rr, levels=[1, 2, 3, 4, 5], colors="white", linewidths=0.4, alpha=0.5)
        axp.set_xticks([]); axp.set_yticks([]); axp.set_title("85–90°S, polar stereographic", fontsize=8)
    cax = fig.add_axes([0.90, 0.20, 0.015, 0.62])
    cb = fig.colorbar(im, cax=cax); cb.ax.tick_params(labelsize=7)
    cb.set_label(("log10 " if log else "") + units, fontsize=8)
    fig.text(0.03, 0.04, caption, fontsize=8, color="#333333", wrap=True)
    fig.savefig(path, facecolor="white"); plt.close(fig)


def map_pages(pdf, quick):
    ref = earth_ref()
    made = []
    for body, nside in BODY_ORDER:
        names = list(LAYERS) if not quick else ["slope", "temp_level"]
        for nm in names:
            a = load(body, nside, nm)
            if a is None:
                continue
            shown = a.copy()
            pop = "reference population (ice-free, water-free land)" if body == "earth" else "all pixels"
            if body == "earth":
                shown[~ref] = np.nan
            label, units, spec, cmap = LAYERS[nm]
            vmin, vmax, log = stretch(shown, spec)
            pc = to_platecarree(shown, nside, PC_W, PC_H)
            polar = None
            if body in ("moon", "mars"):
                pa, inside, rr = to_south_polar(shown, nside, POLAR_PX, POLAR_RAD)
                polar = (pa, inside, rr)
            v = np.isfinite(shown)
            ent = json.load(io.open(C.MANIFEST, encoding="utf-8"))["layers"].get(f"{body}_{nm}", {})
            modelled = " MODELLED, not measured." if ent.get("modelled") else ""
            cap = (f"{body}_{nm}_nside{nside}.npy  ·  {pop}: {100*v.mean():.1f}% of pixels valid  ·  "
                   f"stretch {'log10 ' if log else ''}{vmin:.3g}..{vmax:.3g} {units.split(' (')[0]}  ·  "
                   f"absent/masked = dark grey.{modelled}"
                   + (" Orbit-track striping north of 60 deg comes from the TES thermal-inertia input and is real in the source." if body == "mars" and nm.startswith("temp") else ""))
            path = os.path.join(OUT_DIR, f"map_{body}_{nm.replace('.', 'p')}.png")
            draw_map(pc, f"{body.capitalize()} — {label}", cap, cmap, vmin, vmax, log, units, path, polar)
            pdf.savefig(plt.figure(figsize=(13, 7.6)) if False else _img_fig(path)); plt.close("all")
            made.append(path)
            print(f"  map {body:5s} {nm:22s} valid {100*v.mean():6.2f}%", flush=True)
    return made


def _img_fig(path):
    """A PDF page that is exactly the PNG."""
    from PIL import Image
    im = Image.open(path)
    w, h = im.size
    fig = plt.figure(figsize=(w / 150, h / 150), dpi=150)
    ax = fig.add_axes([0, 0, 1, 1]); ax.imshow(im); ax.axis("off")
    return fig


def text_page(pdf, title, lines, fs=(13, 7.6)):
    fig = plt.figure(figsize=fs, dpi=150)
    fig.text(0.06, 0.90, title, fontsize=18, weight="bold")
    y = 0.84
    for ln in lines:
        fig.text(0.06, y, ln, fontsize=10.5, family="monospace" if ln.startswith("  ") else None)
        y -= 0.036
    pdf.savefig(fig); plt.close(fig)


def coverage_pages(pdf):
    man = json.load(io.open(C.MANIFEST, encoding="utf-8"))["layers"]
    ref = earth_ref()
    for body, nside in BODY_ORDER:
        names = [k.replace(body + "_", "", 1) for k, e in man.items()
                 if e.get("body") == body and e.get("phase") in ("2", "2c", "3", "3b", "3d", "3e", "3f")
                 and not e.get("role") and e.get("matching_eligible") is not False
                 and "HOLD" not in str(e.get("validation", {}).get("status", "")) and not k.endswith("_r2")]
        cnt = np.zeros(12 * nside ** 2, dtype=np.int16)
        for nm in names:
            a = load(body, nside, nm)
            cnt += np.isfinite(a)
        shown = cnt.astype(np.float32)
        if body == "earth":
            shown[~ref] = np.nan
        pc = to_platecarree(shown, nside, PC_W, PC_H)
        path = os.path.join(OUT_DIR, f"coverage_{body}.png")
        hist = np.bincount(cnt[np.isfinite(shown)], minlength=len(names) + 1)
        cap = (f"Number of ranking layers with a value, per pixel, of {len(names)} on {body}.  "
               f"Pixels with all {len(names)}: {100*hist[len(names)]/max(hist.sum(),1):.1f}%; "
               + "; ".join(f"{k}: {100*hist[k]/max(hist.sum(),1):.1f}%" for k in range(len(names)-1, max(len(names)-4, -1), -1)))
        draw_map(pc, f"{body.capitalize()} — dimensions available per pixel", cap, "viridis", 0, len(names), False, "layers", path,
                 to_south_polar(shown, nside, POLAR_PX, POLAR_RAD) if body != "earth" else None)
        pdf.savefig(_img_fig(path)); plt.close("all")
        print(f"  coverage {body}: all {len(names)} on {100*hist[len(names)]/max(hist.sum(),1):.1f}%")


def rank_pct(v):
    n = v.size; o = np.argsort(v, kind="stable"); sv = v[o]
    new = np.ones(n, bool); new[1:] = sv[1:] != sv[:-1]
    gid = np.cumsum(new) - 1; st = np.flatnonzero(new); en = np.append(st[1:], n)
    r = np.empty(n); r[o] = ((st + en - 1) / 2.0)[gid]; return (r + 0.5) / n


def heatmap(pdf, R, names, title, caption, path):
    n = len(names)
    fig, ax = plt.subplots(figsize=(11, 10.5), dpi=150)
    im = ax.imshow(R, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(n)); ax.set_yticks(range(n))
    ax.set_xticklabels(names, rotation=45, ha="right", fontsize=8); ax.set_yticklabels(names, fontsize=8)
    for i in range(n):
        for j in range(n):
            ax.text(j, i, f"{R[i, j]:+.2f}", ha="center", va="center", fontsize=6,
                    color="white" if abs(R[i, j]) > 0.6 else "black")
    ax.set_title(title, fontsize=11, loc="left")
    fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02).set_label("Spearman rank correlation", fontsize=8)
    fig.subplots_adjust(bottom=0.22, top=0.94, left=0.22, right=0.92)
    fig.text(0.02, 0.02, caption, fontsize=8, color="#333333", wrap=True)
    fig.savefig(path, facecolor="white"); pdf.savefig(fig); plt.close(fig)


def correlation_pages(pdf):
    dc = json.load(io.open(os.path.join(ROOT, "cube", "phase4", "dimension_check.json"), encoding="utf-8"))
    names = dc["candidates"]; R = np.array([[dc["correlation"][a][b] for b in names] for a in names])
    heatmap(pdf, R, names, "Earth reference population — rank correlation of the 14 candidates",
            f"cube/phase4/dimension_check.json, {dc['complete_cases']:,} complete pixels. SVF vs roughness −0.97 and apparent TI vs diurnal range −0.96 are the two decided redundancies.",
            os.path.join(OUT_DIR, "corr_earth.png"))
    ev = {}
    for body, nside, dims in (("moon", 256, ["slope", "roughness_5.25km", "roughness_10.5km", "roughness_21km", "roughness_42km", "tpi_21km", "tpi_7km", "svf_30km", "temp_level", "temp_range_diurnal", "SiO2", "FeO"]),
                              ("mars", 512, ["slope", "roughness_5.25km", "roughness_10.5km", "roughness_21km", "roughness_42km", "tpi_21km", "tpi_7km", "svf_30km", "temp_level", "temp_range_diurnal", "temp_range_seasonal", "thermal_inertia", "SiO2", "FeO"])):
        arrs = {d: load(body, nside, d) for d in dims}
        v = np.all([np.isfinite(arrs[d]) for d in dims], axis=0)
        P = np.vstack([rank_pct(arrs[d][v]) for d in dims]); R = np.corrcoef(P)
        heatmap(pdf, R, dims, f"{body.capitalize()} — rank correlation of its {len(dims)} ranking layers",
                f"All {body} pixels with every layer present: {int(v.sum()):,}. Computed for this atlas; Mars thermal layers are modelled.",
                os.path.join(OUT_DIR, f"corr_{body}.png"))
        ev[body] = np.linalg.eigvalsh(R)
    # eigenvalue spectra
    fig, ax = plt.subplots(figsize=(13, 6), dpi=150)
    for tag, key in (("Earth–Moon (12)", "earth_moon"), ("Earth–Mars (14)", "earth_mars")):
        e = dc["pairings"][key]["with_additions"]["eigenvalues"]
        ax.plot(range(1, len(e) + 1), e, marker="o", label=f"{tag}: λ_min {min(e):.4f}, {sum(x < 0.1 for x in e)} below the floor")
    ax.axhline(0.1, color="red", linestyle="--", linewidth=1, label="whitening floor 0.10")
    ax.set_yscale("log"); ax.set_xlabel("eigenvalue rank (ascending)"); ax.set_ylabel("eigenvalue of the rank-correlation matrix")
    ax.set_title("Eigenvalue spectra on Earth's reference population — what the whitening floors", loc="left", fontsize=13)
    ax.legend(fontsize=9); ax.grid(alpha=0.3)
    fig.text(0.06, 0.01, "Floored directions are the roughness family plus SVF–roughness and apparent-TI–diurnal-range; together under 0.7% of the variance.", fontsize=8)
    p = os.path.join(OUT_DIR, "eigenvalues.png"); fig.savefig(p, facecolor="white", bbox_inches="tight"); pdf.savefig(fig); plt.close(fig)


def distribution_pages(pdf):
    ref = earth_ref()
    dims = ["slope", "roughness_5.25km", "roughness_21km", "roughness_42km", "tpi_21km", "tpi_7km", "svf_30km",
            "temp_level", "temp_range_diurnal", "temp_range_seasonal", "thermal_inertia", "SiO2", "FeO"]
    fig, axes = plt.subplots(4, 4, figsize=(13, 10), dpi=150); axes = axes.ravel()
    cols = {"earth": "#1f77b4", "moon": "#7f7f7f", "mars": "#d62728"}
    for ax, nm in zip(axes, dims):
        label, units, spec, _ = LAYERS[nm]
        for body, nside in BODY_ORDER:
            a = load(body, nside, nm)
            if a is None: continue
            v = a[ref] if body == "earth" else a
            v = v[np.isfinite(v)]
            if nm == "thermal_inertia" and body == "earth":
                continue       # K^-1 apparent, a different quantity; shown in its own panel below
            if spec == "log":
                v = v[v > 0]; v = np.log10(v)
            lo, hi = np.percentile(v, [0.5, 99.5])
            ax.hist(v, bins=80, range=(lo, hi), density=True, histtype="step", linewidth=1.3, color=cols[body], label=body)
        ax.set_title(label, fontsize=9); ax.set_xlabel(("log10 " if spec == "log" else "") + units.split(" (")[0], fontsize=7)
        ax.tick_params(labelsize=6); ax.set_yticks([])
        ax.legend(fontsize=6, frameon=False)
    ax = axes[len(dims)]
    a = load("earth", 1024, "thermal_inertia"); v = a[ref]; v = v[np.isfinite(v)]
    ax.hist(np.log10(v), bins=80, range=np.percentile(np.log10(v), [0.5, 99.5]), density=True, histtype="step", color=cols["earth"], linewidth=1.3)
    ax.set_title("Earth apparent thermal inertia", fontsize=9); ax.set_xlabel("log10 K^-1", fontsize=7); ax.set_yticks([]); ax.tick_params(labelsize=6)
    for ax in axes[len(dims) + 1:]: ax.axis("off")
    fig.suptitle("Distributions of every ranking variable, in native units, per body (Earth: reference population). Different scales per body are expected; the rank transform removes them.", fontsize=9, y=0.995)
    fig.tight_layout()
    p = os.path.join(OUT_DIR, "distributions.png"); fig.savefig(p, facecolor="white"); pdf.savefig(fig); plt.close(fig)


def model_pages(pdf):
    # KRC validation
    val = json.load(io.open(os.path.join(ROOT, "cube", "phase4", "mars_thermal_1d_validation.json"), encoding="utf-8"))
    fig, ax = plt.subplots(figsize=(13, 7.6), dpi=150)
    x = np.array([c["tk_krc"] for c in val["cases"]]); y = np.array([c["tk_model"] for c in val["cases"]])
    ax.scatter(x, y, s=40, color="#d62728", zorder=3)
    for c in val["cases"]:
        ax.annotate(c["name"][:14], (c["tk_krc"], c["tk_model"]), fontsize=6, xytext=(4, 3), textcoords="offset points")
    lim = [140, 320]; ax.plot(lim, lim, "k--", linewidth=0.8); ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("KRC surface kinetic temperature (K), Mone.prt reference"); ax.set_ylabel("NumPy port (K)")
    ax.set_title(f"Validation of the Mars thermal model against KRC's own one-point reference: median |ΔT| {val['median_abs_dT']:.2f} K, mean {val['mean_dT']:+.2f} K", loc="left", fontsize=12)
    ax.grid(alpha=0.3)
    p = os.path.join(OUT_DIR, "krc_validation.png"); fig.savefig(p, facecolor="white", bbox_inches="tight"); pdf.savefig(fig); plt.close(fig)
    # diurnal curves from the table
    tb = np.load(os.path.join(ROOT, "cube", "mars_temp_table.npz"))
    ti_ax, alb_ax, elev_ax, lat_ax, tau_ax, lt = tb["ti"], tb["albedo"], tb["elev_km"], tb["lat"], tb["tau"], tb["local_time"]
    i_ls = 0; i_a = int(np.argmin(np.abs(alb_ax - 0.25))); i_e = int(np.argmin(np.abs(elev_ax - (-1)))); i_l = int(np.argmin(np.abs(lat_ax - 0))); i_t = int(np.argmin(np.abs(tau_ax - 0.3)))
    fig, ax = plt.subplots(figsize=(13, 6.5), dpi=150)
    for ti in (30, 80, 200, 500, 1200):
        i_ti = int(np.argmin(np.abs(ti_ax - ti)))
        ax.plot(lt, tb["ts"][i_ls, i_ti, i_a, i_e, i_l, i_t], marker="o", label=f"TI {ti_ax[i_ti]:.0f} tiu")
    ax.set_xlabel("local time (h)"); ax.set_ylabel("surface temperature (K)"); ax.legend(fontsize=9); ax.grid(alpha=0.3)
    ax.set_title("What thermal inertia does to the day: model curves at the equator, Ls 0, albedo 0.25, −1 km, dust 0.3", loc="left", fontsize=12)
    fig.text(0.06, 0.01, "cube/mars_temp_table.npz. Low inertia (dust) swings ~130 K; high inertia (rock) ~60 K. This is the physics behind the Mars diurnal-range layer.", fontsize=8)
    p = os.path.join(OUT_DIR, "diurnal_curves.png"); fig.savefig(p, facecolor="white", bbox_inches="tight"); pdf.savefig(fig); plt.close(fig)
    # MCD comparison bars
    s = json.load(io.open(os.path.join(HP, "phase3f_mars_summary.json"), encoding="utf-8"))["mcd_comparison"]
    fig, ax = plt.subplots(figsize=(13, 5.5), dpi=150)
    names = list(s); x = np.arange(len(names)); w = 0.25
    ax.bar(x - w, [s[n]["mean_diff_K"] for n in names], w, label="mean difference (model − MCD), K")
    ax.bar(x, [s[n]["median_abs_diff_K"] for n in names], w, label="median |difference|, K")
    ax.bar(x + w, [s[n]["p95_abs_diff_K"] for n in names], w, label="p95 |difference|, K")
    for i, n in enumerate(names):
        ax.text(i, max(s[n]["p95_abs_diff_K"], 0) + 0.5, f"r = {s[n]['pearson_r']:.3f}", ha="center", fontsize=9)
    ax.set_xticks(x); ax.set_xticklabels(names); ax.axhline(0, color="k", linewidth=0.6); ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.3)
    ax.set_title(f"Modelled Mars temperatures against the Mars Climate Database at its own 5.6 × 3.75° grid ({s[names[0]]['gcm_cells']} cells)", loc="left", fontsize=12)
    p = os.path.join(OUT_DIR, "mcd_comparison.png"); fig.savefig(p, facecolor="white", bbox_inches="tight"); pdf.savefig(fig); plt.close(fig)
    # dust climatology
    import phase3f_mars_temperature as P
    tau, dlat, dlon, files = P.dust_tau_ref(np.arange(0, 360, 30.0))
    fig, ax = plt.subplots(figsize=(13, 6), dpi=150)
    zonal = tau.mean(axis=2)
    im = ax.imshow(zonal.T, aspect="auto", origin="lower", extent=[-15, 345, dlat.min(), dlat.max()], cmap="YlOrBr")
    ax.set_xlabel("Ls (deg)"); ax.set_ylabel("latitude"); ax.set_xticks(range(0, 360, 30))
    fig.colorbar(im, ax=ax, fraction=0.03).set_label("visible dust opacity at 546 Pa (zonal mean)", fontsize=8)
    ax.set_title("Dust opacity forcing of the thermal model: Montabone et al. climatology, MY29–MY32 mean, per 30° of Ls", loc="left", fontsize=12)
    p = os.path.join(OUT_DIR, "dust_climatology.png"); fig.savefig(p, facecolor="white", bbox_inches="tight"); pdf.savefig(fig); plt.close(fig)


def composition_page(pdf):
    s = json.load(io.open(os.path.join(HP, "mars_composition_summary.json"), encoding="utf-8"))
    em = s["endmembers"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6), dpi=150)
    names = list(em)
    si = [em[n]["SiO2"] for n in names]; fe = [em[n]["FeO"] for n in names]
    lo = [em[n].get("alt_SiO2", (em[n]["SiO2"],) * 2)[0] for n in names]; hi = [em[n].get("alt_SiO2", (em[n]["SiO2"],) * 2)[1] for n in names]
    ax1.barh(names, si, color="#4c72b0"); ax1.errorbar(si, range(len(names)), xerr=[np.array(si) - np.array(lo), np.array(hi) - np.array(si)], fmt="none", ecolor="k", capsize=3)
    ax1.set_xlabel("SiO2 wt%"); ax1.set_title("End-member silica with the assumed alternatives", fontsize=10)
    lo = [em[n].get("alt_FeO", (em[n]["FeO"],) * 2)[0] for n in names]; hi = [em[n].get("alt_FeO", (em[n]["FeO"],) * 2)[1] for n in names]
    ax2.barh(names, fe, color="#c44e52"); ax2.errorbar(fe, range(len(names)), xerr=[np.array(fe) - np.array(lo), np.array(hi) - np.array(fe)], fmt="none", ecolor="k", capsize=3)
    ax2.set_xlabel("FeO_T wt%"); ax2.set_title("End-member iron with the assumed alternatives", fontsize=10)
    for ax in (ax1, ax2): ax.tick_params(labelsize=8); ax.grid(axis="x", alpha=0.3)
    sens = {k: s["layers"][k]["sensitivity"] for k in ("SiO2", "FeO")}
    fig.suptitle(f"Mars composition end-member table (TES mineral maps → oxides). Rank order survives the alternatives for SiO2 (ρ {sens['SiO2']['spearman_base_vs_low']:.2f}–{sens['SiO2']['spearman_base_vs_high']:.2f}) and only partly for FeO (ρ {sens['FeO']['spearman_base_vs_high']:.2f}–{sens['FeO']['spearman_base_vs_low']:.2f}).", fontsize=9)
    fig.tight_layout()
    p = os.path.join(OUT_DIR, "composition_endmembers.png"); fig.savefig(p, facecolor="white"); pdf.savefig(fig); plt.close(fig)


def provenance_page(pdf):
    enc = json.load(io.open(os.path.join(ROOT, "cube", "provenance_encoding.json"), encoding="utf-8"))["layers"]
    names = sorted(enc); keys = ["BINNED", "COPIED_FROM_COARSER", "NO_VALID_SOURCE", "ABSENT"]
    cols = ["#2ca02c", "#ff7f0e", "#7f7f7f", "#000000"]
    fig, ax = plt.subplots(figsize=(13, 12), dpi=150)
    left = np.zeros(len(names))
    for k, c in zip(keys, cols):
        vals = np.array([enc[n]["counts"][k] / sum(enc[n]["counts"].values()) for n in names])
        ax.barh(names, vals, left=left, color=c, label=k); left += vals
    ax.set_xlim(0, 1); ax.set_xlabel("share of pixels"); ax.tick_params(labelsize=7); ax.legend(fontsize=8, loc="lower right")
    ax.set_title("Provenance of every pixel of every layer: binned from finer data, copied from coarser, covered but empty, or absent", loc="left", fontsize=12)
    fig.tight_layout()
    p = os.path.join(OUT_DIR, "provenance.png"); fig.savefig(p, facecolor="white"); pdf.savefig(fig); plt.close(fig)


def dimension_table_page(pdf):
    man = json.load(io.open(C.MANIFEST, encoding="utf-8"))["layers"]
    rows = ["slope", "roughness_5.25km", "roughness_10.5km", "roughness_21km", "roughness_42km", "tpi_21km", "tpi_7km", "svf_30km",
            "temp_level", "temp_range_diurnal", "temp_range_seasonal", "thermal_inertia", "SiO2", "FeO"]
    fig, ax = plt.subplots(figsize=(13, 7.6), dpi=150); ax.axis("off")
    cell = []
    for r in rows:
        line = [r]
        for body, nside in BODY_ORDER:
            e = man.get(f"{body}_{r}")
            if e is None: line.append("—"); continue
            arr = load(body, nside, r)
            cov = 100.0 * float(np.isfinite(arr).mean()) if arr is not None else None
            tag = "modelled" if e.get("modelled") else ("weak" if "weak_dimension_mars" in e or "weak_dimension_moon" in e else "")
            line.append(f"✓ {cov:.1f}%{(' ' + tag) if tag else ''}" if cov is not None else "✓")
        line.append("✓" if man.get(f"moon_{r}") and man.get(f"earth_{r}") else "")
        line.append("✓" if man.get(f"mars_{r}") and man.get(f"earth_{r}") else "")
        cell.append(line)
    tbl = ax.table(cellText=cell, colLabels=["variable", "Earth (coverage)", "Moon", "Mars", "Earth–Moon", "Earth–Mars"], loc="center", cellLoc="left")
    tbl.auto_set_font_size(False); tbl.set_fontsize(8); tbl.scale(1, 1.5)
    em = sum(1 for l in cell if l[4]); emx = sum(1 for l in cell if l[5])
    ax.set_title(f"The ranking dimensions as built, 9 Nov 2026: Earth–Moon {em}, Earth–Mars {emx}. Coverage = share of the body's pixels with a value (Earth: whole sphere, land ≈ 30%).", loc="left", fontsize=11)
    p = os.path.join(OUT_DIR, "dimension_table.png"); fig.savefig(p, facecolor="white", bbox_inches="tight"); pdf.savefig(fig); plt.close(fig)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--quick", action="store_true"); a = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)
    t0 = time.perf_counter()
    state = io.open(os.path.join(ROOT, "CUBE_STATE.md"), encoding="utf-8").read().splitlines()
    with PdfPages(PDF) as pdf:
        text_page(pdf, "Terrestrial Analog Finder — the cube, in pictures", [
            "NASA Space Apps Challenge 2026 · generated by build/atlas.py on " + time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
            "", "What this is: one map per ranking layer per body, then the graphs that justify the layers.",
            "HEALPix NESTED, Nside 1024 Earth / 256 Moon / 512 Mars; pixel sides 6.37 / 6.95 / 6.79 km.",
            "Earth maps show the reference population only (ice-free, water-free land), because that is what ranks.",
            "Absent or masked pixels are dark grey. Mars temperature layers are MODELLED, not measured (VARIABLES.md B28).",
            "", "Contents: 1 dimension table · 2 coverage maps · 3 layer maps (Earth, Moon, Mars) · 4 distributions",
            "5 rank-correlation matrices and eigenvalue spectra · 6 the Mars thermal model and its checks",
            "7 Mars composition end-member table · 8 provenance of every layer", "",
        ] + [l for l in state if l.startswith("| **Earth-") or l.startswith("| earth |") or l.startswith("| moon |") or l.startswith("| mars |")])
        dimension_table_page(pdf); print("  dimension table")
        coverage_pages(pdf)
        map_pages(pdf, a.quick)
        distribution_pages(pdf); print("  distributions")
        correlation_pages(pdf); print("  correlations")
        model_pages(pdf); print("  model pages")
        composition_page(pdf); print("  composition")
        provenance_page(pdf); print("  provenance")
    print(f"wrote {PDF} ({os.path.getsize(PDF)/2**20:.1f} MB) in {(time.perf_counter()-t0)/60:.1f} min; PNGs in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
