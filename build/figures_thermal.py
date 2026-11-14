"""
PHASE 3.3 -- a map for every thermal layer.

    python build/figures_thermal.py

Plate carree for all three bodies, plus south polar stereographic for the Moon
and Mars. Absent pixels render DARK GREY so coverage edges are visible as
edges: if an edge that should be there is missing, something filled it in.
"""

import io
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C
from figures import FIG_DIR, sidecar
from figures_h import to_platecarree, to_south_polar

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

D = os.path.join(C.ROOT, "cube", "healpix")
LAYERS = {
    "moon": ("temp_level", "temp_range_diurnal"),
    "mars": ("temp_level", "temp_range_diurnal", "temp_range_seasonal"),
    "earth": ("temp_level", "temp_range_diurnal", "temp_range_seasonal"),
}
CMAP = {"temp_level": "inferno", "temp_range_diurnal": "viridis",
        "temp_range_seasonal": "magma"}


def draw(arr, title, sub, path, vmin, vmax, cmap, rings=None):
    fw = 13.0 if arr.shape[1] >= arr.shape[0] else 8.0
    fh = fw * arr.shape[0] / arr.shape[1] + 1.3
    fig, ax = plt.subplots(figsize=(fw, fh), dpi=170)
    cm = plt.get_cmap(cmap).copy()
    cm.set_bad("#2a2a2a")                 # ABSENT -- must read as an edge
    im = ax.imshow(np.ma.masked_invalid(arr), cmap=cm, vmin=vmin, vmax=vmax,
                   interpolation="nearest")
    if rings is not None:
        ax.contour(rings, levels=[1, 2, 3, 4, 5], colors="white",
                   linewidths=0.4, alpha=0.55)
    ax.set_title(title, fontsize=12, pad=8)
    ax.text(0.5, -0.06, sub, transform=ax.transAxes, ha="center", va="top",
            fontsize=8.5, color="#444444")
    ax.set_xticks([]); ax.set_yticks([])
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.012, extend="both")
    cb.set_label("kelvin", fontsize=8)
    cb.ax.tick_params(labelsize=7)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    os.makedirs(FIG_DIR, exist_ok=True)
    rep = {}
    for body, names in LAYERS.items():
        ns = C.NSIDE[body]
        for nm in names:
            p = os.path.join(D, f"{body}_{nm}_nside{ns}.npy")
            if not os.path.exists(p):
                print(f"  MISSING {p}")
                continue
            a = np.load(p)
            f = a[np.isfinite(a)]
            lo, hi = np.percentile(f, [1, 99])
            pc = to_platecarree(a, ns, 2880, 1440)
            valid = 100.0 * np.isfinite(a).mean()
            fn = f"{body}_{nm}_platecarree_2880px.png"
            draw(pc, f"{body.capitalize()} — {nm.replace('_',' ')}",
                 f"plate carrée · Nside {ns} · colour 1st–99th percentile "
                 f"[{lo:.1f}, {hi:.1f}] K · absent = dark grey · "
                 f"{valid:.2f}% of pixels have a value",
                 os.path.join(FIG_DIR, fn), lo, hi, CMAP[nm])
            print(f"  {fn}   valid {valid:.2f}%   [{lo:.1f}, {hi:.1f}] K")
            rep[fn] = dict(body=body, layer=nm, valid_pct=round(valid, 4),
                           vmin=float(lo), vmax=float(hi))
            del pc
            if body in ("moon", "mars"):
                po, inside, rr = to_south_polar(a, ns, 1600, 5.0)
                # The polar cap occupies a narrow slice of the global range,
                # so the global stretch flattens it to one colour. Give the
                # polar view its OWN stretch and say so on the figure.
                pf = po[np.isfinite(po)]
                plo, phi = np.percentile(pf, [1, 99])
                fn2 = f"{body}_{nm}_southpolar_85S_to_90S_1600px.png"
                draw(po, f"{body.capitalize()} — {nm.replace('_',' ')}, "
                         f"85°S to 90°S",
                     f"south polar stereographic · white rings at 1° "
                     f"colatitude · absent = dark grey · colour stretched to "
                     f"THIS REGION [{plo:.1f}, {phi:.1f}] K, not the global "
                     f"range [{lo:.1f}, {hi:.1f}] K",
                     os.path.join(FIG_DIR, fn2), plo, phi, CMAP[nm], rings=rr)
                print(f"  {fn2}")
                rep[fn2] = dict(body=body, layer=nm, projection="south polar")
                del po
            del a

    sidecar(os.path.join(FIG_DIR, "_thermal_maps.json"),
            figures=rep,
            absent_colour="#2a2a2a",
            colour_range="per-layer 1st to 99th percentile, stated on each figure",
            coverage_edges=dict(
                modis=("EXPECTED AND PRESENT. MOD11C3 is land only, so the "
                       "coastline is a hard edge in all three Earth figures "
                       "and 71% of the sphere is dark grey."),
                diviner=("EXPECTED AT 60 DEGREES AND CORRECTLY ABSENT. The "
                         "lunar thermal layers come from the Diviner GCP, "
                         "which is GLOBAL to +/-90 and 100% valid, so there "
                         "is no 60-degree edge to see. The +/-60 limit "
                         "belongs to the DGDR cylindrical regolith-"
                         "temperature product, which is an ANOMALY rather "
                         "than a temperature and was not used. Nothing "
                         "filled anything in -- a different product was "
                         "chosen, and that is why the edge is not there."),
                mars=("No edge: MCD is a global model, 100% valid, and "
                      "upsampled 1,024:1 from 3,072 cells.")),
            purpose="deck and video figures, and a visual gate on coverage")
    print(f"\n{len(rep)} figures -> docs/figures/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
