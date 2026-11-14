"""
CHECK THE COMPOSITION LOOKUP AGAINST MEASURED ROCKS -- B31.

    python -I build/gard_verify.py

SOURCE
    Gard M., Hasterok D. & Halpin J.A. (2019) Global whole-rock geochemical
    database compilation, Earth Syst. Sci. Data 11, 1553-1566,
    doi:10.5194/essd-11-1553-2019. Data v1.1.0, doi:10.5281/zenodo.3359791,
    CC-BY-4.0. About one million analysed rock samples.

WHY
    B16 said it plainly: the lookup's weight percents were NOT read from the
    primary tables, because the publishers refused automated access. They
    carried the tag [UNVERIFIED-VALUE]. This is the check that was owed.

EVERYTHING BELOW WAS FIXED BEFORE THE DATA WAS OPENED

  IRON  FeO_T = feo_tot if given; else 0.8998 * fe2o3_tot if given; else
        feo + 0.8998 * fe2o3 when BOTH are given. A row with only one of
        feo / fe2o3 and no total is NOT used for iron: it would understate.

  CLEAN A value is used when 0 < SiO2 <= 100 and 0 <= FeO_T <= 100. The
        database stores some negatives; its authors treat them as invalid.

  CLASSES  rock_group / rock_origin are the database's own. rock_name is the
        sample collector's name, lower case. The six igneous classes follow
        the IUGS silica ranges that DEFINE the GLiM classes (Le Maitre 2002):
        basic 45-52, intermediate 52-63, acid > 63 wt% SiO2. For those six
        the SiO2 median is the middle of a defined range, so FeO_T is the
        independent check; the named-rock rows (basalt, granite ...) are the
        check that does not use silica at all.

  VERDICT  for a class with n >= 200: VERIFIED when the lookup value lies
        inside the measured interquartile range [p25, p75]; OUTSIDE
        otherwise. Fewer than 200 samples: NO VERDICT.

  ACTION  a VERIFIED value is KEPT unchanged. An OUTSIDE value is reported
        with the measured median beside it; replacing it is a method
        decision and is not taken by this script.
"""

import io
import json
import os
import re
import sys
import time
import zipfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

ZIP = os.path.join(C.ROOT, "sources", "gard2019", "complete.zip")
ZIP_MD5 = "9b97b54887ee7184c6650c845b4e92d4"
OUT = os.path.join(C.ROOT, "cube", "gard_verification.json")
N_MIN = 200
COLS = ["latitude", "longitude", "rock_name", "rock_type", "rock_group",
        "rock_origin", "rock_facies", "material", "sio2", "fe2o3",
        "fe2o3_tot", "feo", "feo_tot"]


def name_is(pattern):
    rx = re.compile(pattern)
    return lambda d: d["rock_name"].str.contains(rx, na=False)


def ign(origin, lo, hi):
    return lambda d: ((d["rock_group"] == "igneous") & (d["rock_origin"] == origin)
                      & (d["sio2"] > lo) & (d["sio2"] <= hi))


# code -> (description, selector, lookup SiO2, lookup FeO_T, which table)
CLASSES = [
    # ---- GLiM level-1 rows
    ("va", "acid volcanic: igneous, volcanic, SiO2 > 63", ign("volcanic", 63, 100)),
    ("vi", "intermediate volcanic: 52 < SiO2 <= 63", ign("volcanic", 52, 63)),
    ("vb", "basic volcanic: 45 < SiO2 <= 52", ign("volcanic", 45, 52)),
    ("pa", "acid plutonic: igneous, plutonic, SiO2 > 63", ign("plutonic", 63, 100)),
    ("pi", "intermediate plutonic: 52 < SiO2 <= 63", ign("plutonic", 52, 63)),
    ("pb", "basic plutonic: 45 < SiO2 <= 52", ign("plutonic", 45, 52)),
    ("py", "pyroclastics: name tuff, ignimbrite, pyroclastic, tephra, pumice, scoria",
     name_is(r"\b(tuff|ignimbrite|pyroclast\w*|tephra|pumice|scoria)\b")),
    ("ss", "siliciclastic sedimentary: sedimentary, clastic",
     lambda d: (d["rock_group"] == "sedimentary") & (d["rock_origin"] == "clastic")),
    ("sc", "carbonate sedimentary: name limestone, dolomite, dolostone, chalk",
     name_is(r"\b(limestone|dolomite|dolostone|chalk)\b")),
    ("sm", "mixed sedimentary: name marl or calcareous ...",
     name_is(r"\b(marl|marlstone|calcareous)\b")),
    ("ev", "evaporites: name evaporite, gypsum, anhydrite, halite",
     name_is(r"\b(evaporite|gypsum|anhydrite|halite)\b")),
    ("mt", "metamorphics: rock_group metamorphic",
     lambda d: d["rock_group"] == "metamorphic"),
    ("su", "unconsolidated: name sand, soil, loess, till, alluvium, sediment, mud, clay",
     name_is(r"^(sand|soil|loess|till|alluvium|sediment|mud|clay|silt|gravel)$")),
    # ---- GLiM subclass rows that name one rock
    ("ssss__", "coarse siliciclastic: name sandstone, arenite, arkose, wacke, conglomerate",
     name_is(r"\b(sandstone|arenite|\w*arenite|arkose|subarkose|greywacke|graywacke|wacke|conglomerate)\b")),
    ("sssh__", "fine siliciclastic: name shale, mudstone, siltstone, claystone, pelite, argillite",
     name_is(r"\b(shale|mudstone|siltstone|claystone|pelite|argillite)\b")),
    ("sula__", "laterite: name laterite, bauxite", name_is(r"\b(laterite|bauxite)\b")),
    ("sulo__", "loess: name loess", name_is(r"\bloess\b")),
    # ---- named igneous rocks: the check that does not use silica
    ("name:rhyolite", "name rhyolite", name_is(r"^rhyolite$")),
    ("name:dacite", "name dacite", name_is(r"^dacite$")),
    ("name:andesite", "name andesite", name_is(r"^andesite$")),
    ("name:basalt", "name basalt", name_is(r"^basalt$")),
    ("name:granite", "name granite", name_is(r"^granite$")),
    ("name:granodiorite", "name granodiorite", name_is(r"^granodiorite$")),
    ("name:diorite", "name diorite", name_is(r"^diorite$")),
    ("name:gabbro", "name gabbro", name_is(r"^gabbro$")),
    ("name:dolerite", "name dolerite or diabase", name_is(r"^(dolerite|diabase)$")),
    # ---- classes GeoMAP has and GLiM does not
    ("gm:q", "quartzite: name quartzite", name_is(r"\bquartzite\b")),
    ("gm:m", "metacarbonate: name marble", name_is(r"\bmarble\b")),
    ("gm:e", "mafic metamorphic: name amphibolite, metagabbro, metabasite, metabasalt, eclogite",
     name_is(r"\b(amphibolite|metagabbro|metabasite|metabasalt|eclogite)\b")),
    ("gm:u", "ultramafic: name peridotite, dunite, harzburgite, lherzolite, pyroxenite, serpentinite",
     name_is(r"\b(peridotite|dunite|harzburgite|lherzolite|pyroxenite|serpentinite)\b")),
    ("gm:t", "metavolcanic: rock_origin metavolcanic",
     lambda d: d["rock_origin"] == "metavolcanic"),
    ("gm:y", "metasedimentary: rock_origin metasedimentary",
     lambda d: d["rock_origin"] == "metasedimentary"),
    ("gm:p", "low to medium grade: name slate, phyllite, schist",
     name_is(r"\b(slate|phyllite|schist)\b")),
    ("gm:n", "gneiss and migmatite: name gneiss, orthogneiss, paragneiss, migmatite",
     name_is(r"\b(gneiss|orthogneiss|paragneiss|migmatite)\b")),
    ("gm:o", "hornfels: name hornfels", name_is(r"\bhornfels\b")),
    # ---- Antarctic samples only: does the global value hold there?
    ("ant:mafic_intrusive", "south of 60 S: plutonic with 45 < SiO2 <= 57, or name dolerite / gabbro",
     lambda d: (d["latitude"] < -60) & (
         ((d["rock_group"] == "igneous") & (d["rock_origin"] == "plutonic")
          & (d["sio2"] > 45) & (d["sio2"] <= 57))
         | d["rock_name"].str.contains(r"^(?:dolerite|diabase|gabbro)$", na=False))),
    ("ant:dolerite", "south of 60 S: name dolerite or diabase",
     lambda d: (d["latitude"] < -60) & d["rock_name"].str.contains(
         r"^(?:dolerite|diabase)$", na=False)),
    ("ant:felsic_intrusive", "south of 60 S: plutonic, SiO2 > 63",
     lambda d: (d["latitude"] < -60) & (d["rock_group"] == "igneous")
     & (d["rock_origin"] == "plutonic") & (d["sio2"] > 63)),
    ("ant:all", "south of 60 S: every sample", lambda d: d["latitude"] < -60),
]


def md5(path):
    import hashlib
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def stats(x):
    x = x[np.isfinite(x)]
    if x.size == 0:
        return dict(n=0)
    q = np.percentile(x, [25, 50, 75])
    return dict(n=int(x.size), p25=round(float(q[0]), 2),
                median=round(float(q[1]), 2), p75=round(float(q[2]), 2))


def main():
    import csv
    import pandas as pd
    t0 = time.perf_counter()
    print("=" * 78)
    print("B31 -- LOOKUP VALUES AGAINST GARD, HASTEROK & HALPIN (2019)")
    print("=" * 78)
    got = md5(ZIP)
    if got != ZIP_MD5:
        raise SystemExit(f"zip md5 {got} != Zenodo {ZIP_MD5}")
    with zipfile.ZipFile(ZIP) as z, z.open("complete.csv") as fh:
        # the file is not valid UTF-8 (Windows-1252 bytes in free-text
        # fields); latin-1 never fails and the columns used here are ASCII
        d = pd.read_csv(fh, usecols=COLS, low_memory=False, encoding="latin-1",
                        dtype={c: "string" for c in (
                            "rock_name", "rock_type", "rock_group",
                            "rock_origin", "rock_facies", "material")})
    print(f"{len(d):,} rows read ({time.perf_counter()-t0:.0f} s)")
    for c in ("sio2", "fe2o3", "fe2o3_tot", "feo", "feo_tot", "latitude"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    for c in ("rock_name", "rock_group", "rock_origin", "rock_facies"):
        d[c] = d[c].fillna("").str.strip().str.lower()

    pos = lambda s: s.where(s > 0)
    feo_t = pos(d["feo_tot"])
    feo_t = feo_t.fillna(0.8998 * pos(d["fe2o3_tot"]))
    both = pos(d["feo"]) + 0.8998 * pos(d["fe2o3"])
    feo_t = feo_t.fillna(both)
    d["feo_t"] = feo_t.where((feo_t >= 0) & (feo_t <= 100))
    d["sio2"] = d["sio2"].where((d["sio2"] > 0) & (d["sio2"] <= 100))
    n_si = int(d["sio2"].notna().sum())
    n_fe = int(d["feo_t"].notna().sum())
    print(f"usable SiO2 {n_si:,}; usable FeO_T {n_fe:,}")
    grp = d["rock_group"].value_counts().to_dict()
    print("rock_group:", {k or "(blank)": int(v) for k, v in grp.items()})

    look = {}
    with io.open(os.path.join(C.ROOT, "sources", "glim_composition_lookup.csv"),
                 encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["SiO2_wt_pct"].strip():
                look[r["code"].strip()] = (float(r["SiO2_wt_pct"]),
                                           float(r["FeO_wt_pct"]))

    out = dict(
        source="Gard, Hasterok & Halpin (2019) v1.1.0, doi:10.5281/zenodo.3359791, CC-BY-4.0",
        paper="Earth Syst. Sci. Data 11, 1553-1566, doi:10.5194/essd-11-1553-2019",
        zip_md5=ZIP_MD5, rows=int(len(d)), usable_sio2=n_si, usable_feo_t=n_fe,
        iron_rule="FeO_T = feo_tot, else 0.8998*fe2o3_tot, else feo + 0.8998*fe2o3 when both are given",
        verdict_rule=f"n >= {N_MIN}: VERIFIED when the lookup value lies inside [p25, p75]; else OUTSIDE",
        classes={})
    print(f"\n{'class':22s} {'n':>8s} {'SiO2 p25/med/p75':>22s} {'lookup':>7s} "
          f"{'':9s} {'n':>8s} {'FeO_T p25/med/p75':>22s} {'lookup':>7s}")
    for code, desc, sel in CLASSES:
        m = sel(d).fillna(False).to_numpy(dtype=bool)
        s_si = stats(d["sio2"].to_numpy()[m])
        s_fe = stats(d["feo_t"].to_numpy()[m])
        rec = dict(definition=desc, sio2=s_si, feo_t=s_fe)
        lv = look.get(code)
        line = f"{code:22s} {s_si['n']:>8,} "
        line += (f"{s_si['p25']:>6.1f}/{s_si['median']:>6.1f}/{s_si['p75']:>6.1f} "
                 if s_si["n"] else " " * 23)
        for nm, st, i in (("sio2", s_si, 0), ("feo_t", s_fe, 1)):
            v = None
            if lv is not None:
                rec[f"lookup_{nm}"] = lv[i]
                if st["n"] >= N_MIN:
                    v = "VERIFIED" if st["p25"] <= lv[i] <= st["p75"] else "OUTSIDE"
                else:
                    v = "NO VERDICT"
                rec[f"verdict_{nm}"] = v
            if i == 0:
                line += f"{(lv[0] if lv else float('nan')):>7.1f} {(v or ''):9s} "
                line += f"{s_fe['n']:>8,} "
                line += (f"{s_fe['p25']:>6.2f}/{s_fe['median']:>6.2f}/{s_fe['p75']:>6.2f} "
                         if s_fe["n"] else " " * 23)
            else:
                line += f"{(lv[1] if lv else float('nan')):>7.2f} {(v or '')}"
        out["classes"][code] = rec
        print(line)

    tmp = OUT + ".part"
    with io.open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    os.replace(tmp, OUT)
    print(f"\nwrote {OUT} ({time.perf_counter()-t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
