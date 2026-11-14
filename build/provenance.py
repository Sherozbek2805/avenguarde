"""
TASK 2 -- support == 0.0 means two different things. Fix it with an explicit
flag instead of an overloaded float.

    python build/provenance.py [--write]

THE BUG
    On the roughness_scaling_exponent layers, support exactly 0.0 means "the
    pixel has native cells but none carried a usable value" -- that is how the
    803 flat-water pixels were diagnosed, with support 0 against support NaN
    carrying the distinction.
    On the phase 3 thermal layers, support exactly 0.0 means "the value was
    COPIED from a coarser source because no native cell fell in this pixel".

    Same number, opposite meanings, and in one case the value is NaN while in
    the other it is a perfectly good temperature. Any downstream code that
    writes `support > 0` to mean usable silently drops every copied thermal
    pixel -- 99.91% of Mars, 71.12% of the Moon. That is the
    three-temperature-definitions pattern living inside the support field.

THE FIX
    A uint8 provenance code per pixel per layer, derived from the pair
    (value finite?, support), which disambiguates the two cases completely:

        value finite + support > 0   -> BINNED
        value finite + support == 0  -> COPIED_FROM_COARSER
        value NaN    + support == 0  -> NO_VALID_SOURCE
        value NaN    + support NaN   -> ABSENT

    Arrays identical across layers are written ONCE and shared, so the cost is
    a few files rather than one per layer.

    The encoding lives in ONE named place, cube/provenance_encoding.json, and
    every manifest entry points at it by name. Nobody has to infer it.
"""

import argparse
import hashlib
import io
import json
import os
import re
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

HEALPIX = os.path.join(C.ROOT, "cube", "healpix")
ENCODING_FILE = os.path.join(C.ROOT, "cube", "provenance_encoding.json")

ABSENT, BINNED, COPIED, NO_VALID = 0, 1, 2, 3

# Layers that are NOT data layers and carry no provenance of their own:
# masks, per-pixel uncertainties that share their parent's provenance, and
# diagnostic counts. Listed so a skip is a decision, not a surprise.
SKIP_STEMS = {
    "earth_reference_mask": "a mask (fraction of reference land), not a layer",
    "moon_SiO2_sigma": "uncertainty of moon_SiO2; shares its provenance file",
    "moon_FeO_sigma": "uncertainty of moon_FeO; shares its provenance file",
    "earth_geomap_rock_fraction": "a coverage fraction (exposed rock share of the pixel, GeoMAP), not a data layer",
}

# Layers whose support lives under another name. earth_SiO2 and earth_FeO are
# looked up THROUGH the lithology majority vote, so they inherit its support
# exactly; they are not independently measured.
# B31: south of 53 S the class can come from GeoMAP instead of GLiM, so the
# support is the winning share of WHICHEVER vote supplied the class. That
# combined array is written by build/composition_earth.py.
SUPPORT_ALIAS = {
    "earth_SiO2": "earth_composition_support_nside1024.npy",
    "earth_FeO": "earth_composition_support_nside1024.npy",
}
ENCODING = {
    "name": "cube_provenance_v1",
    "dtype": "uint8",
    "codes": {
        "0": {"name": "ABSENT",
              "meaning": ("No native source cell maps to this pixel and no "
                          "value was supplied. The layer value is NaN."),
              "value_is": "NaN", "support_is": "NaN"},
        "1": {"name": "BINNED",
              "meaning": ("The value is an area-weighted mean of the native "
                          "cells falling in this pixel. Support is the "
                          "cos(lat)-weighted fraction of those cells that "
                          "carried a usable value."),
              "value_is": "finite", "support_is": "greater than 0"},
        "2": {"name": "COPIED_FROM_COARSER",
              "meaning": ("No native cell fell in this pixel, so the value "
                          "was COPIED from the nearest source cell. The value "
                          "is usable but it is shared with neighbouring "
                          "pixels, so it adds no independent information. "
                          "Filter on distinct_levels and "
                          "largest_tie_fraction, not on support."),
              "value_is": "finite", "support_is": "exactly 0.0"},
        "3": {"name": "NO_VALID_SOURCE",
              "meaning": ("The source grid COVERS this pixel but supplied no "
                          "usable value. Two distinct situations share this "
                          "code and the stored arrays cannot separate them: "
                          "(a) the product reports nodata here BY DESIGN -- "
                          "MOD11C3 is land-only, so 8.5 million ocean pixels "
                          "are code 3 on every Earth thermal layer; and (b) "
                          "every contributing cell FAILED a quality test, as "
                          "with the 803 flat-water pixels that failed the "
                          "R-squared gate on scaling_exponent_r2. Check the "
                          "layer's own coverage note before reading code 3 "
                          "as failure. The value is NaN either way. It is "
                          "still NOT the same as ABSENT, where no source "
                          "cell reaches the pixel at all."),
              "value_is": "NaN", "support_is": "exactly 0.0"},
    },
    "why_this_exists": (
        "support == 0.0 previously meant NO_VALID_SOURCE on the scaling-"
        "exponent layers and COPIED_FROM_COARSER on the phase 3 thermal "
        "layers. Downstream code testing `support > 0` for usability would "
        "have silently dropped every copied thermal pixel, which is 99.91% of "
        "Mars and 71.12% of the Moon. Never infer usability from support "
        "alone; read this code."),
    "usable_for_statistics": [1, 2],
    "missing": [0, 3],
}


def derive(val, sup):
    p = np.full(val.shape, ABSENT, dtype=np.uint8)
    fv = np.isfinite(val)
    fs = np.isfinite(sup)
    p[fv & fs & (sup > 0)] = BINNED
    p[fv & fs & (sup <= 0)] = COPIED
    p[~fv & fs & (sup <= 0)] = NO_VALID
    # value finite but support missing entirely -> treat as copied, and say so
    p[fv & ~fs] = COPIED
    return p


def support_from_manifest(man, stem, val):
    """The cleanup of 8 Nov deleted support arrays that were CONSTANT on every
    valid pixel and recorded the constant in the manifest. Rebuild the array
    from that constant so provenance can still be derived -- 1.0 means every
    valid pixel is BINNED, and a NaN value under a covering source grid is
    NO_VALID_SOURCE (every DEM covers its whole sphere)."""
    e = man.get(stem)
    if not e or "support_constant" not in e:
        return None, None
    c = float(e["support_constant"])
    sup = np.where(np.isfinite(val), c, 0.0).astype(np.float32)
    return sup, c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    man_p = os.path.join(C.ROOT, "cube", "cube_manifest.json")
    man_layers = json.load(io.open(man_p, encoding="utf-8"))["layers"]

    files = sorted(f for f in os.listdir(HEALPIX)
                   if f.endswith(".npy") and "_support_" not in f
                   and "_provenance_" not in f)
    print("=" * 78)
    print("TASK 2 -- PROVENANCE CODES, replacing the overloaded support float")
    print("=" * 78)
    print(f"{'layer':44s} {'ABSENT':>10s} {'BINNED':>10s} {'COPIED':>10s} "
          f"{'NOVALID':>9s}")
    seen = {}
    report = {}
    for f in files:
        m = re.match(r"(.+)_nside(\d+)\.npy$", f)
        if not m:
            continue
        stem, ns = m.group(1), m.group(2)
        sup_f = f"{stem}_support_nside{ns}.npy"
        sp = os.path.join(HEALPIX, sup_f)
        val = np.load(os.path.join(HEALPIX, f))
        if val.dtype == np.uint8 or val.dtype == np.uint16:
            continue                       # categorical id layers
        if stem.endswith("_nsamples"):
            continue      # a diagnostic count, not a data layer
        if stem in SKIP_STEMS:
            print(f"  -- {stem}: skipped, {SKIP_STEMS[stem]}")
            continue
        own = f"{stem}_provenance_nside{ns}.npy"
        if os.path.exists(os.path.join(HEALPIX, own)):
            # written by its own builder (composition_moon, koppen); keep it
            p = np.load(os.path.join(HEALPIX, own))
            cnt = np.bincount(p, minlength=4)
            report[stem] = dict(nside=int(ns), provenance_file=own,
                                own_builder=True,
                                counts={ENCODING["codes"][str(i)]["name"]:
                                        int(cnt[i]) for i in range(4)})
            print(f"{stem:44s} {cnt[0]:>10,} {cnt[1]:>10,} {cnt[2]:>10,} "
                  f"{cnt[3]:>9,}   (own builder)")
            continue
        sup = None
        if not os.path.exists(sp):
            alias = SUPPORT_ALIAS.get(stem)
            sp = os.path.join(HEALPIX, alias) if alias else None
        if sp is None or not os.path.exists(sp):
            sup, const = support_from_manifest(man_layers, stem, val)
            if sup is None:
                print(f"  !! {stem}: NO support array, no alias and no "
                      f"recorded constant -- SKIPPED rather than guessing "
                      f"its provenance")
                continue
            print(f"  .. {stem}: support rebuilt from the manifest constant "
                  f"{const}")
        if sup is None:
            sup = np.load(sp)
        p = derive(val, sup)
        cnt = np.bincount(p, minlength=4)
        h = hashlib.sha1(p.tobytes()).hexdigest()[:12]
        if h in seen:
            target = seen[h]
        else:
            target = f"provenance_{h}_nside{ns}.npy"
            seen[h] = target
            if a.write:
                C.atomic_save(os.path.join(HEALPIX, target), p)
        report[stem] = dict(nside=int(ns), provenance_file=target,
                            counts={ENCODING["codes"][str(i)]["name"]:
                                    int(cnt[i]) for i in range(4)})
        print(f"{stem:44s} {cnt[0]:>10,} {cnt[1]:>10,} {cnt[2]:>10,} "
              f"{cnt[3]:>9,}")
        del val, sup, p
    print(f"\n{len(report)} layers -> {len(seen)} distinct provenance arrays "
          f"(shared where identical)")

    if a.write:
        enc = dict(ENCODING)
        enc["layers"] = report
        io.open(ENCODING_FILE, "w", encoding="utf-8").write(
            json.dumps(enc, indent=1, ensure_ascii=False))
        print(f"encoding -> {ENCODING_FILE}")
        man_p = os.path.join(C.ROOT, "cube", "cube_manifest.json")
        man = json.load(io.open(man_p, encoding="utf-8"))
        n = 0
        for k, e in man["layers"].items():
            key = k if k in report else None
            if key is None:
                continue
            e["provenance_file"] = ("cube/healpix/" +
                                    report[key]["provenance_file"])
            e["provenance_encoding"] = "cube/provenance_encoding.json"
            e["provenance_encoding_name"] = ENCODING["name"]
            e["support_warning"] = (
                "DO NOT test support against zero to decide usability. "
                "support == 0.0 means COPIED_FROM_COARSER on some layers and "
                "NO_VALID_SOURCE on others. Read provenance_file against "
                "cube/provenance_encoding.json instead.")
            n += 1
        tmp = man_p + ".part"
        io.open(tmp, "w", encoding="utf-8").write(
            json.dumps(man, indent=1, ensure_ascii=False))
        os.replace(tmp, man_p)
        print(f"manifest: {n} entries now carry provenance_file + the warning")
        # Orphans: a provenance_*.npy no layer points at any more. These
        # appear when a layer is REBUILT (Earth thermal, 9 Nov) and its NaN
        # pattern changes. Delete them and record it, the same way the 8 Nov
        # cleanup did -- one convention on disk, the numbers in a log.
        referenced = {v["provenance_file"] for v in report.values()}
        orphans = sorted(f for f in os.listdir(HEALPIX)
                         if f.startswith("provenance_") and f.endswith(".npy")
                         and f not in referenced)
        if orphans:
            log_p = os.path.join(C.ROOT, "cube", "cleanup_log.json")
            log = json.load(io.open(log_p, encoding="utf-8"))
            later = log.setdefault("later_removals", [])
            for f in orphans:
                fp = os.path.join(HEALPIX, f)
                b = os.path.getsize(fp)
                os.remove(fp)
                later.append(dict(
                    when=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    path="cube/healpix/" + f, bytes=b,
                    why=("orphaned provenance array: no manifest layer "
                         "references it after the layers it described were "
                         "rebuilt; superseded by the arrays written in this "
                         "run")))
                print(f"  removed orphan {f} ({b:,} bytes)")
            tmp = log_p + ".part"
            io.open(tmp, "w", encoding="utf-8").write(
                json.dumps(log, indent=1, ensure_ascii=False))
            os.replace(tmp, log_p)

    # ---- audit: who tests support against zero?
    print()
    print("AUDIT -- code that compares support (or a support-derived array) "
          "to zero")
    bd = os.path.join(C.ROOT, "build")
    pat = re.compile(r"(sup\w*|support)\s*(==|!=|>|>=|<|<=)\s*0|"
                     r"0\s*(==|!=|>|>=|<|<=)\s*(sup\w*|support)|"
                     r"\bden\w*\s*>\s*0")
    hits = 0
    for fn in sorted(os.listdir(bd)):
        if not fn.endswith(".py"):
            continue
        for i, line in enumerate(io.open(os.path.join(bd, fn),
                                         encoding="utf-8"), 1):
            if pat.search(line):
                print(f"  {fn}:{i}: {line.strip()[:96]}")
                hits += 1
    print(f"  {hits} site(s) found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
