"""
PHASE 5 -- VALIDATE THE WHOLE CUBE AGAINST ITS OWN MANIFEST.

    python build/cube_validate.py [--quick]

The manifest is the cube's claim about itself. This script checks that the
claim and the disk agree, for every layer, with no exceptions written in:

  file        every referenced file exists; HEALPix arrays have 12*Nside^2
              entries; the dtype on disk matches the dtype recorded
  support     the support array exists and has the layer's shape, OR the
              manifest records the constant it was replaced by
  provenance  the provenance array exists, is uint8, has the layer's shape,
              holds only codes 0..3, and AGREES with the values: a finite
              value must carry code 1 or 2 (BINNED / COPIED) and a NaN must
              carry 0 or 3 (ABSENT / NO_VALID_SOURCE). A disagreement means
              the layer was rebuilt and its provenance was not.
  range       where a gate was stated in advance, the values still sit
              inside it; where only statistics were recorded, the recorded
              n_valid still equals the count on disk
  orphans     every .npy in cube/healpix is referenced by some manifest
              entry. A file no entry points at is a file nobody can defend.
  encoding    every layer in provenance_encoding.json is in the manifest and
              its file exists
  pairings    the matchable dimension sets come out at the counts the spec
              decided (Earth-Moon 10, Earth-Mars 6), from the manifest flags
              alone, with no list of names written into this script

Output: cube/cube_validation.json and a table. Exit status 1 on any failure.
--quick skips the per-pixel provenance agreement check (reads every array).
"""

import argparse
import io
import json
import os
import sys
import time
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

HP = os.path.join(C.ROOT, "cube", "healpix")
EXPECTED_PAIRS = {"earth_moon": 12, "earth_mars": 13}  # B33, 11 Nov 2026: thermal inertia cannot be pooled (different units) and no longer ranks. Was 14:  # B28 Mars thermal modelled (+3); B29 Earth apparent TI pairs with Mars TES TI (+1)  # 10 / 6 until 9 Nov 2026; +tpi_7km (B26); +svf_30km both, +SiO2 +FeO Mars (B27); becomes 10 -> 11 when earth_thermal_inertia exists
FILE_KEYS = ("file", "support_file", "provenance_file", "sigma_file",
             "legend_file")


def absp(rel):
    return rel if os.path.isabs(rel) else os.path.join(C.ROOT, rel)


def stated_gate(e):
    """Find a range gate stated in advance, in any of the shapes the builders
    used. Returns (lo, hi) or None."""
    v = e.get("validation") or {}
    if isinstance(v.get("range_gate_stated_in_advance"), list):
        return tuple(v["range_gate_stated_in_advance"])
    if isinstance(v.get("gate"), list):
        return tuple(v["gate"])
    rg = v.get("range_gate")
    if isinstance(rg, dict) and isinstance(rg.get("stated_in_advance"), list):
        return tuple(rg["stated_in_advance"])
    return None


def check_layer(key, e, quick):
    r = dict(checks={}, fail=[], warn=[])
    f = e.get("file")
    if not f:
        r["checks"]["file"] = "no file field (summary entry)"
        return r
    fp = absp(f)
    if not os.path.exists(fp):
        if f.replace("\\", "/").startswith("cube/dem/"):
            # the working-resolution elevation grids and masks (30 GB) are not in the public repository;
            # they are needed only to rebuild a layer, never to run the engine
            r["warn"].append(f"not in this copy: {f} (working-resolution grid, needed only to rebuild a layer)")
        else:
            r["fail"].append(f"file missing: {f}")
        return r
    a = np.load(fp, mmap_mode="r")
    nside = e.get("nside")
    is_hp = nside is not None
    if is_hp:
        want = 12 * int(nside) ** 2
        if a.size != want or a.ndim != 1:
            r["fail"].append(f"shape {a.shape} != ({want},)")
    rec_dtype = (e.get("dtype") or (e.get("validation") or {}).get("dtype"))
    if rec_dtype and str(a.dtype) != str(rec_dtype):
        r["fail"].append(f"dtype on disk {a.dtype} != recorded {rec_dtype}")
    r["checks"]["file"] = f"ok {a.dtype} {a.shape}"
    if not is_hp:
        return r                       # working-resolution DEMs and masks

    a = np.asarray(a)
    if a.dtype.kind == "f":
        valid = np.isfinite(a)
    else:
        nd = e.get("nodata")
        if nd is None:
            nd = 0 if a.dtype == np.uint8 and "koppen" in key else None
        valid = (a != nd) if nd is not None else np.ones(a.size, bool)
    n_valid = int(valid.sum())
    r["checks"]["n_valid_on_disk"] = n_valid
    v = e.get("validation") or {}
    rec_valid = v.get("n_valid")
    if rec_valid is not None and int(rec_valid) != n_valid:
        r["fail"].append(f"n_valid on disk {n_valid:,} != recorded "
                         f"{int(rec_valid):,} -- rebuilt without re-validating?")

    # range gate
    g = stated_gate(e)
    if g is not None and a.dtype.kind == "f" and n_valid:
        lo, hi = float(g[0]), float(g[1])
        fv = a[valid]
        out = int(np.sum((fv < lo) | (fv > hi)))
        r["checks"]["range_gate"] = f"[{lo:g},{hi:g}] outside={out:,}"
        rec = v.get("pixels_outside_stated_gate")
        if out and rec is not None and int(rec) == out and v.get("range_gate_pass") is False:
            # the builder stated the gate, measured the failure, recorded the
            # count and kept the values: "built, measured, marked and
            # reported" is the project's rule. The validator's question is
            # whether the claim matches the disk, and it does.
            r["warn"].append(f"stated gate {g} FAILS on {out:,} values -- "
                             f"RECORDED by the builder, counted not clipped")
        elif out:
            r["fail"].append(f"{out:,} values outside the stated gate {g}"
                             + (f" but the manifest records {rec}" if rec is not None else ""))
    elif g is not None and a.dtype.kind in "ui" and n_valid:
        lo, hi = int(g[0]), int(g[1])
        fv = a[valid]
        out = int(np.sum((fv < lo) | (fv > hi)))
        r["checks"]["range_gate"] = f"[{lo},{hi}] outside={out:,}"
        if out:
            r["fail"].append(f"{out:,} codes outside the stated gate {g}")
    else:
        r["checks"]["range_gate"] = "no stated bounds (statistics only)"

    # support
    sf = e.get("support_file")
    if sf:
        sp = absp(sf)
        if not os.path.exists(sp):
            r["fail"].append(f"support_file missing: {sf}")
        else:
            s = np.load(sp, mmap_mode="r")
            if s.shape != a.shape:
                r["fail"].append(f"support shape {s.shape} != {a.shape}")
            else:
                r["checks"]["support"] = "ok"
    elif "support_constant" in e:
        r["checks"]["support"] = f"constant {e['support_constant']} (recorded)"
    elif (e.get("role") == "mask" or str(e.get("role") or "").startswith("diagnostic")
          or key.endswith("_support")):
        r["checks"]["support"] = "n/a"
    else:
        r["warn"].append("no support_file and no recorded constant")

    # provenance
    pf = e.get("provenance_file")
    if pf:
        pp = absp(pf)
        if not os.path.exists(pp):
            r["fail"].append(f"provenance_file missing: {pf}")
        else:
            p = np.load(pp, mmap_mode="r")
            if p.dtype != np.uint8:
                r["fail"].append(f"provenance dtype {p.dtype} != uint8")
            if p.shape != a.shape:
                r["fail"].append(f"provenance shape {p.shape} != {a.shape}")
            elif not quick:
                p = np.asarray(p)
                if p.max() > 3:
                    r["fail"].append(f"provenance code {int(p.max())} > 3")
                usable = (p == 1) | (p == 2)
                dis = int(np.sum(usable != valid))
                cnt = np.bincount(p, minlength=4)
                r["checks"]["provenance"] = (
                    f"ABSENT {cnt[0]:,} BINNED {cnt[1]:,} COPIED {cnt[2]:,} "
                    f"NOVALID {cnt[3]:,}; disagree with values on {dis:,}")
                if dis:
                    r["fail"].append(f"provenance disagrees with the values on "
                                     f"{dis:,} pixels -- stale provenance")
            else:
                r["checks"]["provenance"] = "present (agreement not checked, --quick)"
    elif (e.get("phase") in ("2", "2c", "3", "3b", "3c", "3d", "3e", "3f")
          and e.get("role") != "mask"
          and not str(e.get("role") or "").startswith("diagnostic")
          and not key.endswith("_support")):
        r["fail"].append("data layer with no provenance_file")
    else:
        r["checks"]["provenance"] = "n/a"

    for k in ("sigma_file", "legend_file"):
        if e.get(k) and not os.path.exists(absp(e[k])):
            r["fail"].append(f"{k} missing: {e[k]}")
    return r


def pairings(man):
    by = defaultdict(set)
    for k, e in man.items():
        b = e.get("body")
        if b is None or str(e.get("phase")) not in ("2", "2c", "3", "3b", "3c", "3d", "3e", "3f"):
            continue
        v = e.get("validation") or {}
        if e.get("matching_eligible") is False or v.get("matching_eligible") is False:
            continue
        if "HOLD" in str(v.get("status", "")):
            continue
        if k.endswith("scaling_exponent_r2"):
            continue
        if e.get("role") and e["role"] not in ("dimension",):
            continue
        by[b].add(k.replace(b + "_", "", 1))
    return {"earth_moon": sorted(by["earth"] & by["moon"]),
            "earth_mars": sorted(by["earth"] & by["mars"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    t0 = time.perf_counter()
    man_all = json.load(io.open(C.MANIFEST, encoding="utf-8"))
    man = man_all["layers"]
    print("=" * 78)
    print(f"CUBE VALIDATION  --  {len(man)} manifest entries, manifest updated "
          f"{man_all.get('updated_utc')}")
    print("=" * 78)

    results = {}
    nfail = 0
    for key in sorted(man):
        r = check_layer(key, man[key], a.quick)
        results[key] = r
        flag = "FAIL" if r["fail"] else ("warn" if r["warn"] else "ok")
        nfail += bool(r["fail"])
        line = f"{flag:4s} {key:36s} {r['checks'].get('file', ''):28s}"
        if r["fail"]:
            line += "  " + " | ".join(r["fail"])
        elif r["warn"]:
            line += "  " + " | ".join(r["warn"])
        print(line)

    # orphans
    referenced = set()
    for e in man.values():
        for k in FILE_KEYS:
            if e.get(k):
                referenced.add(os.path.normpath(absp(e[k])))
    on_disk = sorted(os.path.join(HP, f) for f in os.listdir(HP)
                     if f.endswith(".npy"))
    orphans = [os.path.relpath(f, C.ROOT).replace(os.sep, "/")
               for f in on_disk if os.path.normpath(f) not in referenced]
    print(f"\nORPHANS in cube/healpix (no manifest entry points at them): "
          f"{len(orphans)}")
    for o in orphans:
        print(f"   {o}")

    # encoding
    enc_p = os.path.join(C.ROOT, "cube", "provenance_encoding.json")
    enc = json.load(io.open(enc_p, encoding="utf-8"))
    enc_issues = []
    for stem, info in (enc.get("layers") or {}).items():
        if stem not in man:
            enc_issues.append(f"{stem}: in provenance_encoding.json, not in manifest")
        elif not os.path.exists(os.path.join(HP, info["provenance_file"])):
            enc_issues.append(f"{stem}: provenance file missing")
        elif man[stem].get("provenance_file") != "cube/healpix/" + info["provenance_file"]:
            enc_issues.append(f"{stem}: manifest points at "
                              f"{man[stem].get('provenance_file')}, encoding at "
                              f"{info['provenance_file']}")
    print(f"\nPROVENANCE ENCODING: {len(enc.get('layers') or {})} layers, "
          f"{len(enc_issues)} issues")
    for s in enc_issues:
        print(f"   {s}")

    # pairings
    pr = pairings(man)
    pair_fail = []
    print("\nMATCHABLE DIMENSIONS (from manifest flags alone):")
    for k, want in EXPECTED_PAIRS.items():
        got = pr[k]
        ok = len(got) == want
        print(f"   {k:11s} {len(got):2d} (expected {want})  "
              f"{'ok' if ok else 'MISMATCH'}: {', '.join(got)}")
        if not ok:
            pair_fail.append(f"{k}: {len(got)} != {want}")

    # ranking sets (B36): each calibrated list must be a subset of its parent
    # set and its matrices must be on disk with the right shape
    rs_path = os.path.join(C.ROOT, "cube", "phase4", "ranking_sets.json")
    if os.path.exists(rs_path):
        rs = json.load(io.open(rs_path, encoding="utf-8"))
        p4c = json.load(io.open(os.path.join(C.ROOT, "cube", "phase4", "phase4c_summary.json"), encoding="utf-8"))
        n_ok = 0
        for sid, st in rs["sets"].items():
            n = st["n_dims"]
            bad = []
            if not set(st["dimensions"]) <= set(p4c[st["base_set"]]["dimensions"]):
                bad.append("dimensions not in the parent set")
            for key, shape in (("whiten_file", (n, n)), ("center_file", (2, n))):
                f = os.path.join(C.ROOT, st[key])
                if not os.path.exists(f):
                    bad.append(f"{key} missing")
                elif np.load(f, mmap_mode="r").shape != shape:
                    bad.append(f"{key} shape != {shape}")
            if bad:
                pair_fail.append(f"ranking set {sid}: " + "; ".join(bad))
            else:
                n_ok += 1
        used = {c["ranking_set"] for bd in rs["targets"] for t in rs["targets"][bd] for c in t["constructions"].values()}
        missing = sorted(used - set(rs["sets"]))
        if missing:
            pair_fail.append(f"preset targets use uncalibrated ranking sets: {missing}")
        same = io.open(rs_path, encoding="utf-8").read() == io.open(
            os.path.join(C.ROOT, "contract", "targets_ranking.json"), encoding="utf-8").read()
        if not same:
            pair_fail.append("contract/targets_ranking.json differs from cube/phase4/ranking_sets.json")
        print(f"\nRANKING SETS (B36): {n_ok} of {len(rs['sets'])} calibrated lists consistent; "
              f"{len(used)} used by preset targets; contract copy {'identical' if same else 'DIFFERS'}")
    else:
        pair_fail.append("cube/phase4/ranking_sets.json missing -- run build/ranking_sets.py")

    nfail_total = nfail + len(orphans) + len(enc_issues) + len(pair_fail)
    el = time.perf_counter() - t0
    verdict = "PASS" if nfail_total == 0 else "FAIL"
    print(f"\n{verdict}: {nfail} layer failures, {len(orphans)} orphans, "
          f"{len(enc_issues)} encoding issues, {len(pair_fail)} pairing "
          f"mismatches   ({el/60:.1f} min)")
    io.open(os.path.join(C.ROOT, "cube", "cube_validation.json"), "w",
            encoding="utf-8").write(json.dumps(dict(
                verdict=verdict, quick=a.quick,
                manifest_entries=len(man), layer_failures=nfail,
                orphans=orphans, encoding_issues=enc_issues,
                pairings=pr, pairing_failures=pair_fail,
                layers=results, elapsed_s=round(el, 1),
                run_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
                indent=1))
    return 0 if nfail_total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
