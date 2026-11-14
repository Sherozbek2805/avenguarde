"""
TASK 2 -- map the roughness scaling exponent. This is a VISUAL GATE.

    python build/figures_h.py

The question it settles: the three medians land within 0.025 of each other
(Moon 0.776, Mars 0.778, Earth 0.753) on bodies with nothing geologically in
common. Either H is a genuine universal of planetary surfaces -- the fractal
landscape literature does cluster near 0.7-0.8 -- or the estimator is mostly
measuring its own window geometry and would return about 0.77 on anything.

A map separates those. If the pattern tracks geology, H is real and noisy. If
it looks like noise, or like a LATITUDE BAND, the estimator is looking at
itself.

Each map is rendered twice: as built, and with support < 0.50 masked, so it is
visible whether the pattern survives the filter.

A zonal profile accompanies each one. A latitude artefact is far easier to see
in a curve of H against latitude than in a map, because the eye forgives
gradual horizontal banding.
"""

import io
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C
from figures import FIG_DIR, sidecar

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BODIES = (("moon", 256), ("mars", 512), ("earth", 1024))
# ONE common colour range for all three bodies, deliberately: the question is
# whether they look alike, and a per-body stretch would hide the answer.
VMIN, VMAX = 0.30, 1.30
SUPPORT_CUT = 0.50
PC_W, PC_H = 2880, 1440
POLAR_PX, POLAR_RADIUS_DEG = 1600, 5.0


def hp_of(nside):
    from astropy_healpix import HEALPix
    return HEALPix(nside=nside, order="nested")


def to_platecarree(vals, nside, w=PC_W, h=PC_H):
    from astropy import units as u
    hp = hp_of(nside)
    lat = 90.0 - (np.arange(h) + 0.5) * (180.0 / h)
    lon = -180.0 + (np.arange(w) + 0.5) * (360.0 / w)
    out = np.empty((h, w), dtype=np.float32)
    for i in range(0, h, 64):
        j = min(h, i + 64)
        la = np.repeat(lat[i:j], w)
        lo = np.tile(lon, j - i)
        idx = hp.lonlat_to_healpix(lo * u.deg, la * u.deg)
        out[i:j] = vals[idx].reshape(j - i, w)
    return out


def to_south_polar(vals, nside, n=POLAR_PX, rad=POLAR_RADIUS_DEG):
    from astropy import units as u
    hp = hp_of(nside)
    g = (np.arange(n) + 0.5) / n * 2.0 - 1.0
    X, Y = np.meshgrid(g * rad, g * rad)
    rr = np.hypot(X, Y)
    inside = rr <= rad
    lat = rr - 90.0
    lon = np.degrees(np.arctan2(X, Y))
    idx = hp.lonlat_to_healpix(lon.ravel() * u.deg, lat.ravel() * u.deg)
    out = vals[idx].reshape(n, n).astype(np.float32)
    out[~inside] = np.nan
    return out, inside, rr


def save_map(arr, title, sub, path, polar_rings=None):
    fig_w = 13.0 if arr.shape[1] >= arr.shape[0] else 8.0
    fig_h = fig_w * arr.shape[0] / arr.shape[1] + 1.2
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=170)
    cmap = plt.get_cmap("turbo").copy()
    cmap.set_bad("#1a1a1a")                      # masked / absent, dark grey
    im = ax.imshow(np.ma.masked_invalid(arr), cmap=cmap, vmin=VMIN, vmax=VMAX,
                   interpolation="nearest")
    if polar_rings is not None:
        ax.contour(polar_rings, levels=[1, 2, 3, 4, 5], colors="white",
                   linewidths=0.4, alpha=0.5)
    ax.set_title(title, fontsize=12, pad=8)
    ax.text(0.5, -0.06, sub, transform=ax.transAxes, ha="center", va="top",
            fontsize=8.5, color="#444444")
    ax.set_xticks([]); ax.set_yticks([])
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.012,
                      extend="both")
    cb.set_label("roughness scaling exponent (dimensionless)", fontsize=8)
    cb.ax.tick_params(labelsize=7)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def zonal_profile(vals, nside, nbins=60):
    """Median H in equal-width latitude bins. A latitude artefact shows here
    far more clearly than on a map, because the eye forgives gradual bands."""
    lat = C.healpix_lat(nside)
    edges = np.linspace(-90, 90, nbins + 1)
    cen, med, cnt = [], [], []
    for a, b in zip(edges[:-1], edges[1:]):
        m = (lat >= a) & (lat < b) & np.isfinite(vals)
        cen.append((a + b) / 2.0)
        cnt.append(int(m.sum()))
        med.append(float(np.median(vals[m])) if m.sum() else np.nan)
    return np.array(cen), np.array(med), np.array(cnt)


def main():
    os.makedirs(FIG_DIR, exist_ok=True)
    D = os.path.join(C.ROOT, "cube", "healpix")
    rep = {}
    prof = {}
    print("=" * 78)
    print("H MAPS -- common colour range "
          f"[{VMIN}, {VMAX}] for all three bodies, on purpose")
    print("=" * 78)
    for b, ns in BODIES:
        h = np.load(os.path.join(D, f"{b}_roughness_scaling_exponent_nside{ns}.npy"))
        sup = np.load(os.path.join(
            D, f"{b}_roughness_scaling_exponent_support_nside{ns}.npy"))
        hm = h.copy()
        hm[~(np.isfinite(sup) & (sup >= SUPPORT_CUT))] = np.nan

        for tag, vals in (("", h), (f"_support{int(SUPPORT_CUT*100)}", hm)):
            pc = to_platecarree(vals, ns)
            note = ("all pixels as built" if not tag else
                    f"pixels with support < {SUPPORT_CUT:.2f} masked (dark grey)")
            nm = f"{b}_H_platecarree_{PC_W}px{tag}.png"
            save_map(pc, f"{b.capitalize()} — roughness scaling exponent",
                     f"plate carrée · Nside {ns} · {note} · "
                     f"colour range fixed [{VMIN}, {VMAX}] across all bodies",
                     os.path.join(FIG_DIR, nm))
            print(f"  {nm}")
            rep[nm] = dict(body=b, projection="plate carree", masked=bool(tag))
            del pc
            if b in ("moon", "mars"):
                po, inside, rr = to_south_polar(vals, ns)
                nm2 = f"{b}_H_southpolar_85S_to_90S_{POLAR_PX}px{tag}.png"
                save_map(po, f"{b.capitalize()} — roughness scaling exponent, "
                             f"85°S to 90°S",
                         f"south polar stereographic · white rings at 1° "
                         f"colatitude · {note}",
                         os.path.join(FIG_DIR, nm2), polar_rings=rr)
                print(f"  {nm2}")
                rep[nm2] = dict(body=b, projection="south polar stereographic",
                                masked=bool(tag))
                del po

        c, m, n = zonal_profile(h, ns)
        cm_, mm, nm_ = zonal_profile(hm, ns)
        prof[b] = dict(centres=c.tolist(), median_all=m.tolist(),
                       median_masked=mm.tolist(), counts=n.tolist())
        ok = np.isfinite(m)
        print(f"    zonal median H: min {np.nanmin(m):.4f} at "
              f"{c[ok][np.nanargmin(m[ok])]:+.1f} deg, max "
              f"{np.nanmax(m):.4f} at {c[ok][np.nanargmax(m[ok])]:+.1f} deg, "
              f"spread {np.nanmax(m)-np.nanmin(m):.4f}")
        del h, sup, hm

    # one combined zonal figure -- the latitude-artefact test, all bodies
    fig, ax = plt.subplots(figsize=(10, 5), dpi=170)
    for b, col in (("moon", "#bbbbbb"), ("mars", "#d1603d"),
                   ("earth", "#3d7dd1")):
        p = prof[b]
        ax.plot(p["centres"], p["median_all"], color=col, lw=1.8, label=b)
        ax.plot(p["centres"], p["median_masked"], color=col, lw=1.0, ls="--",
                alpha=0.8)
    ax.axhline(0.77, color="k", lw=0.7, ls=":", label="0.77")
    ax.set_xlabel("latitude (degrees)")
    ax.set_ylabel("median roughness scaling exponent")
    ax.set_title("Zonal median H — the latitude-artefact test\n"
                 "solid = all pixels, dashed = support ≥ 0.50", fontsize=11)
    ax.grid(alpha=0.25); ax.legend(fontsize=9)
    ax.set_xlim(-90, 90)
    p = os.path.join(FIG_DIR, "H_zonal_profiles.png")
    fig.savefig(p, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  H_zonal_profiles.png")

    sidecar(os.path.join(FIG_DIR, "_H_maps.json"),
            colour_range=[VMIN, VMAX],
            colour_range_note=("ONE range for all three bodies, deliberately: "
                               "the question is whether they look alike, and a "
                               "per-body stretch would hide the answer"),
            colormap="turbo", masked_colour="#1a1a1a",
            support_cut=SUPPORT_CUT, figures=rep, zonal_profiles=prof,
            purpose=("visual gate: does H track geology, or is it measuring "
                     "its own window geometry"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
