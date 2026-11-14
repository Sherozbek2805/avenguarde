"""
Two figures for the pooled scale (B33), used by build/spec_rev10.py.

    python build/figure_pooled_scale.py

  docs/figures/atlas/pooled_overlap.png    Earth and the target body on ONE
        physical axis, per variable. This is the "overlap figure" step 3 of
        the spec asks for. Where the two shapes share ground, a physical
        match exists; where they do not touch, none does.
  docs/figures/atlas/pooled_position.png   the pooled scale itself: physical
        value -> position 0..1, with each body's median marked.

Description only. Reads the cube and cube/phase4/pooled_scale_<body>.npz.
Colours: Earth blue, Mars orange, Moon aqua, checked for colour-blind
separation; identity is also carried by direct labels, never colour alone.
"""

import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

HP = os.path.join(C.ROOT, "cube", "healpix")
P4 = os.path.join(C.ROOT, "cube", "phase4")
OUT = os.path.join(C.ROOT, "docs", "figures", "atlas")
NS = {"earth": 1024, "moon": 256, "mars": 512}
COL = {"earth": "#2a78d6", "mars": "#eb6834", "moon": "#1baf7a"}
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
VARS = [("roughness_21km", "Roughness at 21 km (m)", True),
        ("SiO2", "Silica, SiO2 (wt%)", False),
        ("temp_level", "Temperature level (K)", False)]


def style(ax):
    ax.set_facecolor(SURF)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(axis="x", colors=INK2, labelsize=8, length=3, color=GRID)
    ax.tick_params(axis="y", left=False, labelleft=False)


def earth_vals(d):
    ref = np.load(os.path.join(P4, "ref_pixels.npy"))[np.load(os.path.join(P4, "complete_mask.npy"))]
    return np.load(os.path.join(HP, f"earth_{d}_nside1024.npy"))[ref].astype(np.float64)


def body_vals(body, d):
    v = np.load(os.path.join(HP, f"{body}_{d}_nside{NS[body]}.npy")).astype(np.float64)
    return v[np.isfinite(v)]


def overlap():
    fig, axes = plt.subplots(2, 3, figsize=(11, 5.6), facecolor=SURF)
    for r, body in enumerate(("moon", "mars")):
        for c, (d, label, log) in enumerate(VARS):
            ax = axes[r, c]
            style(ax)
            e, b = earth_vals(d), body_vals(body, d)
            if log:
                e, b = np.log10(e[e > 0]), np.log10(b[b > 0])
            lo = min(np.percentile(e, 0.5), np.percentile(b, 0.5))
            hi = max(np.percentile(e, 99.5), np.percentile(b, 99.5))
            bins = np.linspace(lo, hi, 70)
            peaks = {}
            for name, v in (("earth", e), (body, b)):
                h, edges = np.histogram(v, bins=bins, density=True)
                mid = 0.5 * (edges[1:] + edges[:-1])
                ax.fill_between(mid, h, step="mid", color=COL[name], alpha=0.16, linewidth=0)
                ax.step(mid, h, where="mid", color=COL[name], linewidth=2)
                peaks[name] = (mid[np.argmax(h)], h.max())
            top = max(p[1] for p in peaks.values())
            ax.set_ylim(0, top * 1.28)
            for name, (x, y) in peaks.items():
                ax.annotate(name.capitalize(), (x, y), xytext=(0, 6), textcoords="offset points",
                            ha="center", va="bottom", fontsize=9, color=INK, fontweight="bold")
            if log:
                ticks = [t for t in (0, 1, 2, 3) if lo <= t <= hi]
                ax.set_xticks(ticks)
                ax.set_xticklabels([f"{10**t:g}" for t in ticks])
            ax.set_xlabel(label, fontsize=9, color=INK2)
            if c == 0:
                ax.text(-0.02, 0.5, f"Earth and {body.capitalize()}", transform=ax.transAxes, rotation=90,
                        ha="right", va="center", fontsize=10, color=INK, fontweight="bold")
    fig.suptitle("Where Earth and the target body share ground, and where they do not",
                 x=0.012, ha="left", fontsize=13, color=INK, fontweight="bold")
    fig.text(0.012, 0.925, "Share of cells at each physical value, both bodies on one axis. Height is relative within a panel.",
             fontsize=9, color=INK2)
    handles = [plt.Line2D([0], [0], color=COL[k], linewidth=2, label=k.capitalize()) for k in ("earth", "moon", "mars")]
    fig.legend(handles=handles, loc="upper right", bbox_to_anchor=(0.995, 0.995), ncol=3, frameon=False,
               fontsize=9, labelcolor=INK2)
    fig.subplots_adjust(left=0.05, right=0.985, top=0.86, bottom=0.10, hspace=0.50, wspace=0.10)
    p = os.path.join(OUT, "pooled_overlap.png")
    fig.savefig(p, dpi=150, facecolor=SURF)
    plt.close(fig)
    return p


def position():
    knots = np.load(os.path.join(P4, "pooled_scale_moon.npz"))
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.5), facecolor=SURF)
    for c, (d, label, log) in enumerate(VARS):
        ax = axes[c]
        ax.set_facecolor(SURF)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(GRID)
        ax.tick_params(colors=INK2, labelsize=8, length=3, color=GRID)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        x, p = knots[d + "__x"], knots[d + "__p"]
        e, b = earth_vals(d), body_vals("moon", d)
        ok = (p > 0.003) & (p < 0.997)
        xx = np.log10(x[ok]) if log else x[ok]
        ax.plot(xx, p[ok], color=INK2, linewidth=2)
        # label placement per panel, set by eye so no label is clipped or sits on the curve
        place = {"roughness_21km": {"earth": (10, -14, "left"), "moon": (-10, 12, "right")},
                 "SiO2": {"earth": (10, -14, "left"), "moon": (10, 2, "left")},
                 "temp_level": {"earth": (-10, 12, "right"), "moon": (-10, 12, "right")}}[d]
        for name, v, dy in (("earth", e, -14), ("moon", b, 10)):
            m = float(np.median(v))
            pm = float(np.interp(m, x, p))
            xm = np.log10(m) if log else m
            ax.plot([xm], [pm], marker="o", markersize=9, color=COL[name], markeredgecolor=SURF, markeredgewidth=2, zorder=3)
            txt = f"{name.capitalize()} median\n{m:,.0f}" + (" m" if log else (" K" if d == "temp_level" else "%")) + f" → {pm:.2f}"
            dx, dy2, ha = place[name]
            ax.annotate(txt, (xm, pm), xytext=(dx, dy2), textcoords="offset points",
                        ha=ha, va="center", fontsize=8.5, color=INK)
        if log:
            ticks = [t for t in (0, 1, 2, 3) if xx.min() <= t <= xx.max()]
            ax.set_xticks(ticks)
            ax.set_xticklabels([f"{10**t:g}" for t in ticks])
        ax.set_ylim(0, 1)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
        if c:
            ax.tick_params(axis="y", labelleft=False)
        else:
            ax.set_ylabel("Position on the pooled scale", fontsize=9, color=INK2)
        ax.set_xlabel(label, fontsize=9, color=INK2)
    fig.suptitle("The pooled scale: one curve turns a physical value into a position, for both bodies",
                 x=0.012, ha="left", fontsize=13, color=INK, fontweight="bold")
    fig.text(0.012, 0.885, "Earth and Moon. The same value lands at the same position whichever body it is on. Dots mark each body's median cell.",
             fontsize=9, color=INK2)
    fig.subplots_adjust(left=0.065, right=0.985, top=0.80, bottom=0.16, wspace=0.08)
    pth = os.path.join(OUT, "pooled_position.png")
    fig.savefig(pth, dpi=150, facecolor=SURF)
    plt.close(fig)
    return pth


if __name__ == "__main__":
    print("wrote", overlap())
    if "--overlap-only" not in sys.argv:
        # B38, 11 Nov 2026: the rank curve no longer exists (min-max scale; build/figure_minmax_scale.py).
        raise SystemExit("pooled_position.png is the rank scale of B33 and is not rebuilt; the overlap figure was written")
