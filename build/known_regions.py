"""
THE KNOWN-REGION CHECK -- where do well-known analog regions sit in the finished rank maps?

    python build/known_regions.py

The engine is never given a list of analog sites. This script asks, after the fact, how much
of each well-known analog region falls inside Earth's best 1% and best 5% for every NASA
target, under the main ranking system (all_variables). By chance a region would have 1% of
its scored cells in the best 1%, and 5% in the best 5%.

Reads   runs/<body>_<target>__all_variables/rank_combined_nside1024.npy   (local; not in the repository)
Writes  runs/known_regions.json

The regions are ROUGH latitude / longitude boxes drawn around each site by hand. They are a
check of plausibility, not a validation set: all five are places experts already use, and
several are high, cold, dry ground, where temperature carries much of the score.

Written with AI assistance (Claude, Anthropic) under the team's direction; see AI_USE.md.
"""
import glob
import io
import json
import os
import sys
import time

import numpy as np
from astropy_healpix import HEALPix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

ROOT = C.ROOT
OUT = os.path.join(ROOT, "runs", "known_regions.json")

# name: (lat_min, lat_max, lon_min, lon_max), degrees, east positive
REGIONS = {
    "Atacama and Altiplano": (-27.0, -17.0, -71.0, -66.5),
    "Qaidam basin": (36.0, 39.2, 90.0, 96.5),
    "Hawaii, Big Island (Mauna Loa)": (18.9, 20.3, -156.1, -154.8),
    "Antarctic Dry Valleys": (-78.6, -76.9, 159.5, 164.5),
    "Iceland": (63.0, 66.6, -24.6, -13.4),
}


def main():
    t0 = time.perf_counter()
    hp = HEALPix(nside=1024, order="nested")
    lon, lat = hp.healpix_to_lonlat(np.arange(hp.npix))
    lat = lat.deg
    lon = ((lon.deg + 180.0) % 360.0) - 180.0
    idx = {k: np.flatnonzero((lat >= a) & (lat <= b) & (lon >= c) & (lon <= d)) for k, (a, b, c, d) in REGIONS.items()}
    out = dict(system="all_variables", chance=dict(best1_percent=1.0, best5_percent=5.0),
               regions={k: dict(lat_min=v[0], lat_max=v[1], lon_min=v[2], lon_max=v[3]) for k, v in REGIONS.items()},
               note="Rough boxes drawn by hand around each site. Shares are of the box's SCORED cells. Median over the runs of a body.",
               bodies={}, runs={})
    for body in ("moon", "mars"):
        runs = sorted(glob.glob(os.path.join(ROOT, "runs", body + "_*__all_variables")))
        per = {k: dict(best1=[], best5=[], median_rank=[]) for k in REGIONS}
        for run in runs:
            f = os.path.join(run, "rank_combined_nside1024.npy")
            if not os.path.exists(f):
                raise SystemExit(f"STOP: {f} missing -- run the engine for this target first")
            rk = np.load(f, mmap_mode="r")
            row = {}
            for k, ix in idx.items():
                v = np.asarray(rk[ix], dtype=float)
                v = v[np.isfinite(v)]
                b1, b5, md = 100 * float(np.mean(v <= 0.01)), 100 * float(np.mean(v <= 0.05)), 100 * float(np.median(v))
                per[k]["best1"].append(b1); per[k]["best5"].append(b5); per[k]["median_rank"].append(md)
                row[k] = dict(scored_cells=int(v.size), best1_percent=round(b1, 1), best5_percent=round(b5, 1), median_rank_percent=round(md, 1))
            out["runs"][os.path.basename(run)] = row
        out["bodies"][body] = dict(n_runs=len(runs), regions={
            k: dict(best1_percent_median=round(float(np.median(p["best1"])), 1), best1_percent_min=round(min(p["best1"]), 1), best1_percent_max=round(max(p["best1"]), 1),
                    best5_percent_median=round(float(np.median(p["best5"])), 1), median_rank_percent_median=round(float(np.median(p["median_rank"])), 1))
            for k, p in per.items()})
        print(body, len(runs), "runs")
        for k, r in out["bodies"][body]["regions"].items():
            print(f"   {k:32s} best 1%: {r['best1_percent_median']:5.1f}%  (min {r['best1_percent_min']}, max {r['best1_percent_max']})   best 5%: {r['best5_percent_median']:5.1f}%")
    out["built_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, indent=1))
    print(f"wrote {OUT} in {time.perf_counter() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
