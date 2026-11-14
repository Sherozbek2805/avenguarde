"""First contact: load the Moon pairing, score Haworth, print the essentials. No files written."""
import sys
import time

import numpy as np

sys.path.insert(0, __file__.rsplit("smoke.py", 1)[0])
import analog_engine as AE

t0 = time.perf_counter()
P = AE.Pairing("moon")
print(f"loaded in {P.load_seconds:.1f} s: {P.n:,} Earth cells, {len(P.names)} variables, body pixels {P.Bd.shape[1]:,}")
for system in ("earth_reachable_only", "all_variables"):
    rk, parent = P.ranking("Haworth", "all_dimensions", system)
    c = P.cal(rk["ranking_set"])
    VT, n_used = P.body_vectors(c, P.targets["Haworth"]["healpix_pixels"])
    t1 = time.perf_counter()
    maps = P.di_maps(rk["ranking_set"], VT)
    di = maps["combined"]
    print(f"\n{system}: set {rk['ranking_set']} ({len(c['dims'])} variables), target cells {n_used}, distinct {VT.shape[0]}, "
          f"own spread {AE.mean_pairwise(VT) / c['d_bar']:.2f}")
    print(f"  maps in {time.perf_counter() - t1:.1f} s (first call also whitens Earth); DI min {di.min():.3f}, median {np.median(di):.3f}, max {di.max():.1f}; NaN {int(np.isnan(di).sum())}")
    j = int(np.argmin(di))
    print("  best cell group DI:", {g: round(float(maps[g][j]), 3) for g in maps})
print(f"\ntotal {time.perf_counter() - t0:.1f} s")
