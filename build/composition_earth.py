"""
EARTH COMPOSITION, REBUILT -- B31.

    python build/composition_earth.py [--v1-check] [--test]

WHAT IT DOES
    earth_SiO2 and earth_FeO are not measured. They are a lookup from a rock
    CLASS to a typical weight percent. This script applies that lookup, from
    two class maps:

      GLiM    earth_lithology_l3 (Hartmann & Moosdorf 2012), whole planet,
              through sources/glim_composition_lookup_v2.csv
      GeoMAP  earth_geomap_lithcode (Cox et al. 2023), Antarctica and South
              Georgia, through sources/geomap_composition_lookup.csv

RULE, stated before running
    Where GeoMAP names a rock class in a pixel, GeoMAP is used. Everywhere
    else GLiM is used. GeoMAP is the dedicated 1:250,000 compilation of
    Antarctic outcrop; GLiM's Antarctica comes from a continental-scale map.
    One pixel takes one source, never a blend.

    GLiM rule is unchanged from B19: the 6-character subclass row if the
    table has one, else the 2-character level-1 row; wb, ig, nd carry no
    composition.

    --v1-check applies the ORIGINAL lookup (sources/glim_composition_lookup.csv)
    with no GeoMAP and compares against a snapshot of the layers as they were
    before this rebuild. The original builder script is not on disk; this is
    the proof that the re-implementation is exact. The snapshot is a COPY in
    cube/_work, so this script never reads a path it writes.

GATES, stated before running
    range   SiO2 in [0, 100] wt%, FeO_T in [0, 40] wt%
    ties    distinct_levels and largest_tie_fraction over the reference
            population, reported, compared with B19 (66 / 71 levels, 0.1167)
    source  every finite value has a source code 1..3, every NaN has 0

OUTPUT (cube/healpix, Nside 1024 nested)
    earth_SiO2, earth_FeO                float32 wt%
    earth_composition_source             uint8   0 none, 1 GLiM subclass row,
                                                 2 GLiM level-1 row, 3 GeoMAP
    earth_composition_support            float32 winning class share of the
                                                 vote that supplied the class
"""

import argparse
import csv
import io
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

HP = os.path.join(C.ROOT, "cube", "healpix")
SRC = os.path.join(C.ROOT, "sources")
LOOK_V1 = os.path.join(SRC, "glim_composition_lookup.csv")
LOOK_V2 = os.path.join(SRC, "glim_composition_lookup_v2.csv")
LOOK_GM = os.path.join(SRC, "geomap_composition_lookup.csv")
SNAP = os.path.join(C.ROOT, "cube", "_work", "composition_before_B31")
NSIDE = 1024
NO_COMP = ("wb", "ig", "nd")
GATE = {"SiO2": (0.0, 100.0), "FeO": (0.0, 40.0)}


def read_lookup(path):
    out = {}
    with io.open(path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            s, f = r["SiO2_wt_pct"].strip(), r["FeO_wt_pct"].strip()
            out[r["code"].strip()] = (float(s) if s else np.nan,
                                      float(f) if f else np.nan)
    return out


def glim_arrays(lookup):
    """per-class SiO2, FeO and source code, indexed by the l3 class id."""
    vocab = json.load(io.open(os.path.join(HP, "lithology_summary.json"),
                              encoding="utf-8"))["vocab"]
    K = max(int(k) for k in vocab) + 1
    si = np.full(K, np.nan)
    fe = np.full(K, np.nan)
    src = np.zeros(K, dtype=np.uint8)
    for k, code in vocab.items():
        k = int(k)
        if code[:2] in NO_COMP or code == "NULL":
            continue
        if code in lookup and np.isfinite(lookup[code][0]):
            si[k], fe[k] = lookup[code]
            src[k] = 1
        elif code[:2] in lookup and np.isfinite(lookup[code[:2]][0]):
            si[k], fe[k] = lookup[code[:2]]
            src[k] = 2
    return si, fe, src


def apply_glim(lookup):
    l3 = np.load(os.path.join(HP, f"earth_lithology_l3_nside{NSIDE}.npy"))
    si_c, fe_c, src_c = glim_arrays(lookup)
    ok = l3 != 65535
    si = np.full(l3.size, np.nan, dtype=np.float32)
    fe = np.full(l3.size, np.nan, dtype=np.float32)
    src = np.zeros(l3.size, dtype=np.uint8)
    si[ok] = si_c[l3[ok]]
    fe[ok] = fe_c[l3[ok]]
    src[ok] = src_c[l3[ok]]
    return si, fe, src


def ties(v, ref):
    x = v[ref & np.isfinite(v)]
    u, c = np.unique(x, return_counts=True)
    return int(u.size), float(c.max() / x.size), int(x.size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v1-check", action="store_true")
    ap.add_argument("--test", action="store_true", help="compute, write nothing")
    a = ap.parse_args()
    t0 = time.perf_counter()
    print("=" * 78)
    print("B31 -- EARTH COMPOSITION REBUILT (GLiM + GeoMAP)")
    print("=" * 78)

    if a.v1_check:
        si, fe, _ = apply_glim(read_lookup(LOOK_V1))
        bad = 0
        for nm, arr in (("SiO2", si), ("FeO", fe)):
            old = np.load(os.path.join(SNAP, f"earth_{nm}_nside{NSIDE}.npy"))
            same_nan = bool(np.array_equal(np.isfinite(old), np.isfinite(arr)))
            f = np.isfinite(old) & np.isfinite(arr)
            md = float(np.max(np.abs(old[f] - arr[f]))) if f.any() else 0.0
            print(f"v1 check {nm}: NaN pattern identical {same_nan}, "
                  f"max |diff| {md:g}, finite {int(f.sum()):,}")
            bad += (not same_nan) or md > 0
        print("V1 RE-IMPLEMENTATION", "EXACT" if not bad else "DIFFERS")
        return 1 if bad else 0

    look = read_lookup(LOOK_V2)
    gm = read_lookup(LOOK_GM)
    si, fe, src = apply_glim(look)
    n_glim = int(np.isfinite(si).sum())

    lc = np.load(os.path.join(HP, f"earth_geomap_lithcode_nside{NSIDE}.npy"))
    used = np.zeros(lc.size, dtype=bool)
    per_code = {}
    for code in np.unique(lc[lc > 0]):
        ch = chr(int(code))
        if ch not in gm or not np.isfinite(gm[ch][0]):
            raise SystemExit(f"GeoMAP LITHCODE '{ch}' has no lookup row")
        m = lc == code
        si[m], fe[m] = gm[ch]
        src[m] = 3
        used |= m
        per_code[ch] = int(m.sum())
    print(f"GLiM gives {n_glim:,} pixels; GeoMAP overrides or fills "
          f"{int(used.sum()):,}; finite now {int(np.isfinite(si).sum()):,}")

    sup_g = np.load(os.path.join(HP, f"earth_lithology_support_nside{NSIDE}.npy"))
    sup_m = np.load(os.path.join(HP, f"earth_geomap_support_nside{NSIDE}.npy"))
    sup = np.where(src == 3, sup_m, sup_g).astype(np.float32)
    sup[src == 0] = np.nan

    ref = np.load(os.path.join(HP, f"earth_reference_mask_nside{NSIDE}.npy")) > 0.5
    lat = C.healpix_lat(NSIDE)
    res = {}
    ok_all = True
    for nm, arr in (("SiO2", si), ("FeO", fe)):
        lo, hi = GATE[nm]
        f = np.isfinite(arr)
        out = int(np.sum((arr[f] < lo) | (arr[f] > hi)))
        nlev, tie, nref = ties(arr, ref)
        src_ok = bool(np.all((src > 0) == f))
        ok_all &= (out == 0) and src_ok
        q = np.percentile(arr[ref & f], [1, 50, 99])
        res[nm] = dict(n_valid=int(f.sum()), outside_gate=out,
                       distinct_levels=nlev, largest_tie_fraction=round(tie, 4),
                       reference_valid=nref, reference_total=int(ref.sum()),
                       p1=float(q[0]), p50=float(q[1]), p99=float(q[2]),
                       source_agrees=src_ok)
        print(f"{nm}: valid {int(f.sum()):,}  outside gate {out}  levels "
              f"{nlev}  largest tie {tie:.4f}  reference valid {nref:,} of "
              f"{int(ref.sum()):,}  p1/50/99 {q.round(2).tolist()}")
    S = lat < -53.0
    res["south_of_53S"] = dict(
        reference_pixels=int((S & ref).sum()),
        reference_with_composition=int((S & ref & np.isfinite(si)).sum()),
        reference_from_geomap=int((S & ref & (src == 3)).sum()),
        reference_from_glim=int((S & ref & ((src == 1) | (src == 2))).sum()),
        geomap_pixels_all=int((src == 3).sum()),
        geomap_pixels_by_lithcode=per_code)
    res["source_counts"] = {n: int((src == i).sum()) for i, n in enumerate(
        ("none", "glim_subclass_row", "glim_level1_row", "geomap"))}
    print(json.dumps(res["south_of_53S"], indent=1))
    print(json.dumps(res["source_counts"]))

    if os.path.isdir(SNAP):
        for nm, arr in (("SiO2", si), ("FeO", fe)):
            old = np.load(os.path.join(SNAP, f"earth_{nm}_nside{NSIDE}.npy"))
            both = np.isfinite(old) & np.isfinite(arr)
            ch = both & (old != arr)
            res[nm]["vs_before"] = dict(
                newly_finite=int((~np.isfinite(old) & np.isfinite(arr)).sum()),
                newly_nan=int((np.isfinite(old) & ~np.isfinite(arr)).sum()),
                changed=int(ch.sum()),
                changed_in_reference=int((ch & ref).sum()),
                changed_north_of_53S=int((ch & ~S).sum()),
                median_abs_change=(float(np.median(np.abs(arr[ch] - old[ch])))
                                   if ch.any() else 0.0))
            print(f"{nm} against the snapshot: {res[nm]['vs_before']}")

    if not ok_all:
        print("A GATE FAILED -- nothing written")
        return 1
    if a.test:
        print("TEST MODE -- nothing written")
        return 0

    man = json.load(io.open(C.MANIFEST, encoding="utf-8"))["layers"]
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for nm, arr in (("SiO2", si), ("FeO", fe)):
        key = f"earth_{nm}"
        C.atomic_save(os.path.join(HP, f"{key}_nside{NSIDE}.npy"), arr)
        e = dict(man.get(key, {}))
        e.update(
            phase="3b", body="earth", variable=nm, units="wt%", nside=NSIDE,
            order="nested", file=f"cube/healpix/{key}_nside{NSIDE}.npy",
            dtype="float32", built_by="build/composition_earth.py",
            built_utc=now,
            support_file=f"cube/healpix/earth_composition_support_nside{NSIDE}.npy",
            source_code_file=f"cube/healpix/earth_composition_source_nside{NSIDE}.npy",
            source=("class-to-wt% lookup. GLiM classes (earth_lithology_l3, "
                    "Hartmann & Moosdorf 2012, doi:10.1029/2012GC004370) "
                    "through sources/glim_composition_lookup_v2.csv; south of "
                    "53 S, where SCAR GeoMAP (Cox et al. 2023, "
                    "doi:10.1594/PANGAEA.951482) names a rock class, GeoMAP "
                    "through sources/geomap_composition_lookup.csv. Values "
                    "checked against Gard, Hasterok & Halpin (2019), "
                    "doi:10.5281/zenodo.3359791; see cube/gard_verification.json."),
            source_rule=("one pixel, one source: GeoMAP where it names a "
                         "class, GLiM elsewhere; never a blend"),
            support_note=("the winning class share of the vote that supplied "
                          "the class (GLiM or GeoMAP); NOT an independent "
                          "measurement of this oxide."),
            validation=dict(
                n_valid=res[nm]["n_valid"],
                range_gate_stated_in_advance=list(GATE[nm]),
                pixels_outside_stated_gate=0, range_gate_pass=True,
                distinct_levels=res[nm]["distinct_levels"],
                largest_tie_fraction=res[nm]["largest_tie_fraction"],
                reference_valid=res[nm]["reference_valid"],
                p1=res[nm]["p1"], p50=res[nm]["p50"], p99=res[nm]["p99"]),
            b31=res["south_of_53S"])
        C.manifest_write(key, e)
        print("wrote", key)
    for key, arr, units, role in (
            ("earth_composition_source", src,
             "0 none, 1 GLiM subclass row, 2 GLiM level-1 row, 3 GeoMAP",
             "diagnostic: which class map supplied the composition"),
            ("earth_composition_support", sup,
             "winning class share of the vote that supplied the class (0..1)",
             "support of earth_SiO2 and earth_FeO")):
        C.atomic_save(os.path.join(HP, f"{key}_nside{NSIDE}.npy"), arr)
        valid = np.isfinite(arr) if arr.dtype.kind == "f" else (arr > 0)
        C.manifest_write(key, dict(
            file=f"cube/healpix/{key}_nside{NSIDE}.npy", nside=NSIDE,
            order="nested", dtype=str(arr.dtype), n_pixels=int(arr.size),
            phase="3g", body="earth", variable=key.replace("earth_", ""),
            units=units, role=role, matching_eligible=False,
            nodata=(None if arr.dtype.kind == "f" else 0),
            built_by="build/composition_earth.py", built_utc=now,
            validation=dict(n_valid=int(valid.sum()))))
        print("wrote", key)
    with io.open(os.path.join(HP, "composition_earth_summary.json"), "w",
                 encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    print(f"done in {time.perf_counter()-t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
