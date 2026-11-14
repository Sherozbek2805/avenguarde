"""TARGET-ONLY DESCRIPTION (spec step 5: "report the target spread"). No Earth
cell is scored here. For each preset target, in its ranking set:
  spread      mean pairwise distance among the target's own cells / d_bar
  copy_all    what a PERFECT copy of one target cell would score under
              "mean distance to ALL target cells" (median and best over cells)
  copy_5      the same under "mean distance to the 5 nearest target cells"
A perfect copy of a piece of the target should score near 0. Random Earth
pairs score 1.0 by construction."""
import io
import json

import numpy as np

import os
ROOT = (os.environ.get("ANALOG_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).replace(chr(92), "/")
P4 = ROOT + "/cube/phase4/"
RS = json.load(io.open(P4 + "ranking_sets.json", encoding="utf-8"))
pool = json.load(io.open(P4 + "minmax_scale_summary.json", encoding="utf-8"))   # B38: min-max scale
out = []
print(f"{'target':30s} {'set':>4s} {'cells':>5s} {'spread':>7s} | copy scored on ALL: {'median':>6s} {'best':>6s} | on 5 nearest: {'median':>6s}")
for body in ("moon", "mars"):
    T = {t["name"]: t for t in json.load(io.open(ROOT + f"/contract/targets_{body}.json", encoding="utf-8"))["targets"]}
    Z = np.load(P4 + f"minmax_{body}.npy", mmap_mode="r")
    names = pool["pairings"][body]["names"]
    for t in RS["targets"][body]:
        for cn, c in t["constructions"].items():
            s = RS["sets"][c["ranking_set"]]
            W = np.load(ROOT + "/" + s["whiten_file"])
            mu, sd = np.load(ROOT + "/" + s["center_file"])
            pix = np.asarray(T[t["name"]]["healpix_pixels"])
            X = np.asarray(Z[[names.index(d) for d in s["dimensions"]]][:, pix]).T.astype(np.float64)
            X = X[np.isfinite(X).all(1)]
            V = np.unique(np.round(((X - mu) / sd) @ W, 6), axis=0)
            n = V.shape[0]
            D = np.sqrt(np.maximum(((V[:, None, :] - V[None, :, :]) ** 2).sum(-1), 0))
            spread = D[np.triu_indices(n, 1)].mean() / s["d_bar"]
            call = D.mean(1) / s["d_bar"]
            c5 = np.sort(D, axis=1)[:, :min(5, n)].mean(1) / s["d_bar"]
            tag = "" if (body == "moon" or cn == "without_composition") else " +comp"
            print(f"{(t['name'][:24] + tag):30s} {s['n_dims']:4d} {n:5d} {spread:7.2f} | {'':19s} {np.median(call):6.2f} {call.min():6.2f} | {'':13s} {np.median(c5):6.2f}")
            out.append(dict(target=t["name"], body=body, construction=cn, n_dims=s["n_dims"], distinct_cells=int(n), spread=round(float(spread), 3),
                            copy_all_median=round(float(np.median(call)), 3), copy_all_best=round(float(call.min()), 3), copy_5_median=round(float(np.median(c5)), 3)))
json.dump(out, io.open(ROOT + "/cube/phase4/target_spread_b36.json", "w", encoding="utf-8"), indent=1)
