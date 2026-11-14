"""
Every area the engine has been run on, and where on Earth each run points.

    python build/figure_tested_areas.py

  docs/figures/tested_areas.png

Top row: the targets (nine Artemis III regions at the Moon's south pole; two custom test
circles on the Moon; the six Mars zones, filled when their runs are finished).
Bottom: Earth, with the best-matching cell of every finished run and the Atacama control patch.

Reads only finished results: runs/*_summary.json, runs/_tests, runs/custom_*. It computes no score.
Colours: Moon aqua, Mars orange, as in the other figures; the ranking system is the marker shape.
"""
import glob
import io
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

HP = os.path.join(C.ROOT, "cube", "healpix")
OUT = os.path.join(C.ROOT, "docs", "figures")
COL = {"moon": "#1baf7a", "mars": "#eb6834"}
INK, INK2, GRID, SURF, LAND = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb", "#dcdad4"
NS = {"earth": 1024, "moon": 256, "mars": 512}
jl = lambda *p: json.load(io.open(os.path.join(C.ROOT, *p), encoding="utf-8"))


def sample(body, layer, lon, lat):
    from astropy import units as u
    from astropy_healpix import HEALPix
    hp = HEALPix(nside=NS[body], order="nested")
    v = np.load(os.path.join(HP, f"{body}_{layer}_nside{NS[body]}.npy"), mmap_mode="r")
    return np.asarray(v[np.asarray(hp.lonlat_to_healpix(lon.ravel() * u.deg, lat.ravel() * u.deg))]).reshape(lon.shape)


def relief(body, w=900, h=450):
    lon, lat = np.meshgrid((np.arange(w) + 0.5) / w * 360 - 180, 90 - (np.arange(h) + 0.5) / h * 180)
    r = np.log10(np.clip(sample(body, "roughness_21km", lon, lat), 1, None))
    lo, hi = np.nanpercentile(r, [2, 98])
    return np.clip((r - lo) / (hi - lo), 0, 1)


def frame(ax, title, sub=None):
    ax.set_facecolor(SURF)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(title, loc="left", fontsize=10.5, color=INK, fontweight="bold", pad=14 if sub else 6)
    if sub:
        ax.text(0, 1.012, sub, transform=ax.transAxes, fontsize=8.2, color=INK2, va="bottom")


def main():
    tm = jl("contract", "targets_moon.json")["targets"]
    tx = jl("contract", "targets_mars.json")["targets"]
    rows = jl("runs", "moon_summary.json") + (jl("runs", "mars_summary.json") if os.path.exists(os.path.join(C.ROOT, "runs", "mars_summary.json")) else [])
    for r in rows:
        r["body"] = "moon" if r["out_dir"].split("/")[1].startswith("moon") else "mars"
    custom = []
    for d in sorted(glob.glob(os.path.join(C.ROOT, "runs", "_tests", "*"))) + sorted(glob.glob(os.path.join(C.ROOT, "runs", "custom_*"))):
        f = os.path.join(d, "output.json")
        if os.path.exists(f):
            o = json.load(io.open(f, encoding="utf-8"))
            custom.append(dict(body=o["run"]["target"]["body"], system=o["run"]["ranking"]["system"], name=o["run"]["target"]["name"],
                               sel=o["run"]["target"]["selection"], best_site=dict(lat=o["sites"][0]["lat"], lon=o["sites"][0]["lon"])))
    done_mars = {}
    for r in rows:
        if r["body"] == "mars":
            done_mars[r["target"]] = done_mars.get(r["target"], 0) + 1
    fx = jl("contract", "control_fixtures.json")["controls"]["positive_atacama"]

    fig = plt.figure(figsize=(13.2, 10.2), facecolor=SURF)
    gs = fig.add_gridspec(2, 3, height_ratios=[1.0, 1.55], width_ratios=[0.78, 1.3, 1.3], hspace=0.2, wspace=0.07,
                          left=0.03, right=0.985, top=0.885, bottom=0.03)

    # ---- A. the Moon's south pole, within 6.5 degrees: the nine Artemis III regions
    ax = fig.add_subplot(gs[0, 0])
    R, cap = 1737.4, 6.5
    ext = 2 * R * np.tan(np.radians(cap) / 2)
    x = np.linspace(-ext, ext, 520)
    X, Y = np.meshgrid(x, x[::-1])
    rr = np.hypot(X, Y)
    lat = 2 * np.degrees(np.arctan(rr / (2 * R))) - 90
    lon = np.degrees(np.arctan2(X, Y))
    bg = np.log10(np.clip(sample("moon", "roughness_21km", lon, lat), 1, None))
    ax.imshow(np.where(rr <= ext, bg, np.nan), cmap="Greys", extent=[-ext, ext, -ext, ext], vmin=np.nanpercentile(bg, 2), vmax=np.nanpercentile(bg, 99.5), alpha=0.55)
    order = sorted(range(len(tm)), key=lambda i: tm[i]["name"])
    for n, i in enumerate(order):
        v = np.array(tm[i]["geometry"]["vertices_lonlat"])
        rho = 2 * R * np.tan(np.radians(90 + v[:, 1]) / 2)
        px, py = rho * np.sin(np.radians(v[:, 0])), rho * np.cos(np.radians(v[:, 0]))
        ax.fill(px, py, facecolor=COL["moon"], edgecolor="#0f7d56", alpha=0.75, linewidth=1.0)
        ax.text(px.mean(), py.mean(), str(n + 1), ha="center", va="center", fontsize=7.5, color=INK, fontweight="bold")
    ax.plot([0], [0], marker="+", color=INK, markersize=8)
    ax.text(0, -ext * 0.07, "south pole", ha="center", va="top", fontsize=7.5, color=INK2)
    ax.set_xlim(-ext, ext); ax.set_ylim(-ext, ext); ax.set_aspect("equal")
    frame(ax, "Moon: nine Artemis III regions", "south pole, to 83.5°S · 18 runs finished")
    key = "   ".join(f"{n + 1} {tm[i]['name']}" for n, i in enumerate(order))
    words, lines, cur = key.split("   "), [], ""
    for wd in words:
        if len(cur) + len(wd) > 44:
            lines.append(cur); cur = wd
        else:
            cur = (cur + "   " + wd) if cur else wd
    lines.append(cur)
    ax.text(0, -0.02, "\n".join(lines), transform=ax.transAxes, fontsize=7.4, color=INK2, va="top", linespacing=1.35)

    # ---- B. the whole Moon: the custom test targets
    ax = fig.add_subplot(gs[0, 1])
    ax.imshow(relief("moon"), cmap="Greys", extent=[-180, 180, -90, 90], alpha=0.5, aspect="auto")
    seen = set()
    for c in custom:
        if c["body"] != "moon" or c["sel"]["method"] != "circle":
            continue
        p = c["sel"]["params"]
        k = (p["lat"], p["lon"])
        if k in seen:
            continue
        seen.add(k)
        ax.plot([p["lon"]], [p["lat"]], marker="o", markersize=11, markerfacecolor="none", markeredgecolor=COL["moon"], markeredgewidth=2.2)
        nm = "Tycho, 43 km circle" if "Tycho" in c["name"] else "near Copernicus, 14 km circle"
        ax.annotate(nm, (p["lon"], p["lat"]), xytext=(11, 0), textcoords="offset points", fontsize=8.5, color=INK, va="center", fontweight="bold")
    ax.plot([0], [-83], marker="s", markersize=9, markerfacecolor=COL["moon"], markeredgecolor="#0f7d56")
    ax.annotate("the nine Artemis regions (left panel)", (0, -83), xytext=(10, 2), textcoords="offset points", fontsize=8.2, color=INK, va="center")
    ax.set_xlim(-180, 180); ax.set_ylim(-90, 90)
    frame(ax, "Moon: custom test targets", "drawn by hand to test circles and the API · 4 runs finished")

    # ---- C. Mars: the six zones
    ax = fig.add_subplot(gs[0, 2])
    ax.imshow(relief("mars"), cmap="Greys", extent=[-180, 180, -90, 90], alpha=0.5, aspect="auto")
    off = {"Jezero crater": (-11, 9, "right"), "Gale crater": (-11, 10, "right"), "Meridiani Planum, Endeavour": (11, -12, "left"),
           "Gusev crater": (-11, -11, "right"), "Erebus Montes, Arcadia": (11, 9, "left"), "Deuteronilus Mensae": (11, 9, "left")}
    for t in tx:
        n = done_mars.get(t["name"], 0)
        total = 4 if t.get("second_construction") else 2
        full = n >= total
        ax.plot([t["center_lon"]], [t["center_lat"]], marker="o", markersize=11, markerfacecolor=COL["mars"] if n else "none",
                markeredgecolor="#b44a1d", markeredgewidth=2.0, alpha=1.0 if full else 0.9)
        dx, dy, ha = off[t["name"]]
        ax.annotate(f"{t['name'].split(',')[0]}  {n}/{total}", (t["center_lon"], t["center_lat"]), xytext=(dx, dy), textcoords="offset points",
                    fontsize=8.5, color=INK, ha=ha, va="center", fontweight="bold" if n else "normal")
    ax.set_xlim(-180, 180); ax.set_ylim(-90, 90)
    nm = sum(done_mars.values())
    frame(ax, "Mars: six NASA Exploration Zones", f"100 km discs · {nm} of 24 runs finished · filled = has results")

    # ---- D. Earth: where every finished run points
    ax = fig.add_subplot(gs[1, :])
    w, h = 1800, 900
    lon, lat = np.meshgrid((np.arange(w) + 0.5) / w * 360 - 180, 90 - (np.arange(h) + 0.5) / h * 180)
    land = sample("earth", "koppen_class", lon, lat) > 0
    ax.imshow(np.where(land, 1.0, np.nan), cmap=matplotlib.colors.ListedColormap([LAND]), extent=[-180, 180, -90, 90], aspect="auto")
    pts = [dict(body=r["body"], system=r["system"], lat=r["best_site"]["lat"], lon=r["best_site"]["lon"]) for r in rows]
    pts += [dict(body=c["body"], system=c["system"], lat=c["best_site"]["lat"], lon=c["best_site"]["lon"]) for c in custom]
    for body in ("moon", "mars"):
        for system, mk, fill in (("all_variables", "o", True), ("earth_reachable_only", "s", False)):
            q = [p for p in pts if p["body"] == body and p["system"] == system]
            ax.scatter([p["lon"] for p in q], [p["lat"] for p in q], marker=mk, s=74, linewidths=1.9,
                       facecolors=COL[body] if fill else "none", edgecolors=COL[body] if not fill else SURF, zorder=4 if fill else 5, alpha=0.95)
    ax.scatter([fx["centre_lon"]], [fx["centre_lat"]], marker="*", s=230, color=INK, edgecolors=SURF, linewidths=1.0, zorder=6)
    labels = [(-69.0, -20.5, "Atacama – Altiplano – Puna", (-22, 30, "right")), (-155.5, 19.5, "Mauna Loa, Hawaii", (12, -14, "left")),
              (126.2, -6.0, "eastern Indonesia", (12, -18, "left")), (115.4, -8.2, "Bali", (-10, -16, "right")),
              (-24.4, 15.0, "Cape Verde", (10, 12, "left")), (-73.4, 18.4, "Haiti", (12, 10, "left")),
              (56.9, 23.4, "northern Oman", (12, 8, "left")), (37.2, 10.7, "Ethiopian highlands", (12, -12, "left")),
              (104.9, 51.6, "south of Lake Baikal", (12, 8, "left")), (16.3, 28.7, "central Libya", (10, 10, "left")),
              (81.0, 36.0, "northern Tibet", (10, 12, "left")), (147.8, -6.5, "New Guinea", (10, 10, "left")),
              (fx["centre_lon"], fx["centre_lat"], "the control patch (Atacama, Yungay)", (26, -30, "left"))]
    have = np.array([[p["lon"], p["lat"]] for p in pts])
    for lo, la, txt, (dx, dy, ha) in labels:
        if txt.startswith("the control") or np.min(np.hypot(have[:, 0] - lo, have[:, 1] - la)) < 4.0:
            ax.annotate(txt, (lo, la), xytext=(dx, dy), textcoords="offset points", fontsize=8.6, color=INK, ha=ha, va="center",
                        arrowprops=dict(arrowstyle="-", color=INK2, linewidth=0.7, shrinkA=0, shrinkB=5))
    ax.set_xlim(-180, 180); ax.set_ylim(-60, 84)
    n_all = sum(1 for p in pts if p["system"] == "all_variables"); n_re = len(pts) - n_all
    frame(ax, "Earth: the best-matching cell of every finished run",
          f"{len(pts)} runs. One mark per run: the single best cell, not the whole best 1%. Marks on top of each other are runs that point at the same ground.")
    hd = [Line2D([0], [0], marker="o", linestyle="", markersize=8.5, markerfacecolor=COL["moon"], markeredgecolor=SURF, label="Moon target, all variables rank"),
          Line2D([0], [0], marker="s", linestyle="", markersize=8, markerfacecolor="none", markeredgecolor=COL["moon"], markeredgewidth=1.9, label="Moon target, only what Earth can match"),
          Line2D([0], [0], marker="o", linestyle="", markersize=8.5, markerfacecolor=COL["mars"], markeredgecolor=SURF, label="Mars target, all variables rank"),
          Line2D([0], [0], marker="s", linestyle="", markersize=8, markerfacecolor="none", markeredgecolor=COL["mars"], markeredgewidth=1.9, label="Mars target, only what Earth can match"),
          Line2D([0], [0], marker="*", linestyle="", markersize=13, markerfacecolor=INK, markeredgecolor=SURF, label="the Atacama control patch")]
    lg = ax.legend(handles=hd, loc="lower left", bbox_to_anchor=(0.008, 0.015), frameon=True, fontsize=8.6, labelcolor=INK, borderpad=0.8, handletextpad=0.5)
    lg.get_frame().set_facecolor(SURF); lg.get_frame().set_edgecolor(GRID)

    fig.suptitle("Every area the engine has been run on, and where on Earth each run points", x=0.03, y=0.972, ha="left", fontsize=15, color=INK, fontweight="bold")
    fig.text(0.03, 0.935, f"{len(pts)} finished runs on 14 November 2026: {sum(1 for p in pts if p['body'] == 'moon')} lunar, {sum(1 for p in pts if p['body'] == 'mars')} martian. "
             "Every target is run under both ranking systems. Grey shading on the Moon and Mars is roughness at 21 km.", fontsize=9.5, color=INK2)
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "tested_areas.png")
    fig.savefig(p, dpi=150, facecolor=SURF)
    plt.close(fig)
    print("wrote", p, f"({len(pts)} runs: {n_all} all_variables, {n_re} earth_reachable_only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
