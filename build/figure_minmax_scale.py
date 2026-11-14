"""
The min-max scale (B38), one figure for build/spec_rev10.py.

    python build/figure_minmax_scale.py

  docs/figures/atlas/minmax_position.png   three variables for Earth and the
        Moon, each on a STRAIGHT axis from the smallest to the largest value
        on either world. The top axis is the position 0..1; it is the same
        axis relabelled. Dots mark each world's median cell.

Description only. Reads the cube and cube/phase4/minmax_scale_summary.json.
Colours and label rules as in figure_pooled_scale.py.
"""

import io
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C
from figure_pooled_scale import earth_vals, body_vals, COL, INK, INK2, GRID, SURF, OUT

P4 = os.path.join(C.ROOT, "cube", "phase4")
VARS = [("roughness_21km", "Roughness at 21 km (m)", " m"),
        ("SiO2", "Silica, SiO2 (wt%)", "%"),
        ("temp_level", "Temperature level (K)", " K")]


def main():
    mm = json.load(io.open(os.path.join(P4, "minmax_scale_summary.json"), encoding="utf-8"))["pairings"]["moon"]["variables"]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.9), facecolor=SURF)
    for c, (d, label, unit) in enumerate(VARS):
        ax = axes[c]
        ax.set_facecolor(SURF)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.tick_params(axis="x", colors=INK2, labelsize=8, length=3, color=GRID)
        ax.tick_params(axis="y", left=False, labelleft=False)
        lo, hi = mm[d]["lo"], mm[d]["hi"]
        e, b = earth_vals(d), body_vals("moon", d)
        bins = np.linspace(lo, hi, 90)
        top = 0.0
        hs = {}
        for name, v in (("earth", e), ("moon", b)):
            h, edges = np.histogram(v, bins=bins, density=True)
            h = h / h.max()                       # height relative within a world
            mid = 0.5 * (edges[1:] + edges[:-1])
            ax.fill_between(mid, h, step="mid", color=COL[name], alpha=0.16, linewidth=0)
            ax.step(mid, h, where="mid", color=COL[name], linewidth=2)
            hs[name] = (mid, h)
            top = max(top, h.max())
        ax.set_xlim(lo, hi)
        ax.set_ylim(0, 1.75)
        # medians, labelled on two fixed rows above the shapes so nothing overlaps
        for name, v, row in (("earth", e, 1.52), ("moon", b, 1.24)):
            m = float(np.median(v))
            pos = (m - lo) / (hi - lo)
            ax.plot([m, m], [0, row - 0.06], color=COL[name], linewidth=1.2, linestyle=(0, (3, 3)))
            ax.plot([m], [row - 0.06], marker="o", markersize=8, color=COL[name], markeredgecolor=SURF, markeredgewidth=1.5, zorder=3)
            right = pos < 0.6
            ax.annotate(f"{name.capitalize()} median  {m:,.0f}{unit}  →  {pos:.2f}", (m, row - 0.06),
                        xytext=(9 if right else -9, 0), textcoords="offset points",
                        ha="left" if right else "right", va="center", fontsize=8.5, color=INK)
        ax.set_xlabel(label, fontsize=9, color=INK2)
        tx = ax.twiny()
        tx.set_xlim(0, 1)
        tx.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
        for s in ("top", "right", "left", "bottom"):
            tx.spines[s].set_visible(False)
        tx.tick_params(axis="x", colors=INK2, labelsize=8, length=3, color=GRID)
        if c == 0:
            tx.set_xlabel("Position on the min-max scale", fontsize=9, color=INK2, loc="left")
    fig.suptitle("The min-max scale: one straight axis from the smallest value to the largest, for both worlds",
                 x=0.012, ha="left", fontsize=13, color=INK, fontweight="bold")
    fig.text(0.012, 0.895, "Earth and Moon. Equal physical differences are equal distances on the scale. Shapes show where each world's cells lie; "
             "height is relative within a world.", fontsize=9, color=INK2)
    # no legend: each world is named on its own median label
    fig.subplots_adjust(left=0.025, right=0.975, top=0.74, bottom=0.14, wspace=0.16)
    pth = os.path.join(OUT, "minmax_position.png")
    fig.savefig(pth, dpi=150, facecolor=SURF)
    plt.close(fig)
    return pth


if __name__ == "__main__":
    print("wrote", main())
