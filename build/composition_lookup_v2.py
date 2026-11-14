"""
WRITE THE TWO COMPOSITION LOOKUP TABLES -- B31.

    python build/composition_lookup_v2.py

Reads   sources/glim_composition_lookup.csv   (v1, 98 rows, untouched)
        cube/gard_verification.json           (build/gard_verify.py)
Writes  sources/glim_composition_lookup_v2.csv
        sources/geomap_composition_lookup.csv

sources/ is WRITE-ONCE. If a target exists this script compares and refuses
to overwrite a file that differs.

GLiM v2 -- NO VALUE CHANGES
    Every v1 weight percent is carried over unchanged. What is added is the
    evidence: for each row with a matching class in Gard et al. (2019), the
    number of samples, the measured p25 / median / p75, and a verdict. The
    rule was fixed before the database was opened (see gard_verify.py):
    VERIFIED when the v1 value lies inside the interquartile range.

GeoMAP TABLE -- three kinds of row, stated before any layer is built
    SAME-AS-GLIM   the GeoMAP class is the same rock as a GLiM row, so it
                   takes that row's value. Two maps, one language.
    MEAN-OF-GLIM   the class is undifferentiated ("felsic to mafic"), so it
                   takes the mean of the GLiM rows it spans.
    GARD-MEDIAN    GLiM has no such rock (quartzite, metavolcanic), so the
                   value is the measured median.
    A SAME-AS-GLIM value must lie inside the Gard interquartile range where
    Gard has the class; the script checks this and stops if one does not.
"""

import csv
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

SRC = os.path.join(C.ROOT, "sources")
V1 = os.path.join(SRC, "glim_composition_lookup.csv")
V2 = os.path.join(SRC, "glim_composition_lookup_v2.csv")
GM = os.path.join(SRC, "geomap_composition_lookup.csv")
GARD = os.path.join(C.ROOT, "cube", "gard_verification.json")
GARD_CITE = ("Gard, Hasterok & Halpin (2019) Earth Syst. Sci. Data 11, "
             "1553-1566; data v1.1.0 doi:10.5281/zenodo.3359791")
COX = ("Cox et al. (2023) SCAR GeoMAP v.2022-08, doi:10.1594/PANGAEA.951482; "
       "class meanings from its LITHCODE vocabulary")

# LITHCODE -> (meaning, kind, GLiM rows or None, Gard class or None)
GEOMAP = [
    ("c", "cover sediments: till, moraine, colluvium", "SAME-AS-GLIM", ["sumxgl"], None),
    ("s", "mudstone, siltstone, sandstone, conglomerate", "SAME-AS-GLIM", ["ssmx__"], "ss"),
    ("l", "limestone", "SAME-AS-GLIM", ["sc"], "sc"),
    ("j", "volcanogenic sediments", "SAME-AS-GLIM", ["sspy__"], None),
    ("w", "mixed sediments and volcanics", "SAME-AS-GLIM", ["ssmxvr"], None),
    ("f", "felsic volcanic", "SAME-AS-GLIM", ["va"], "va"),
    ("a", "intermediate volcanic", "SAME-AS-GLIM", ["vi"], "vi"),
    ("b", "mafic to ultramafic volcanic", "SAME-AS-GLIM", ["vb"], "vb"),
    ("v", "felsic to mafic volcanic, undifferentiated", "MEAN-OF-GLIM", ["va", "vi", "vb"], None),
    ("g", "felsic intrusive", "SAME-AS-GLIM", ["pa"], "ant:felsic_intrusive"),
    ("h", "intermediate intrusive", "SAME-AS-GLIM", ["pi"], "pi"),
    ("d", "mafic intrusive", "SAME-AS-GLIM", ["pb"], "ant:mafic_intrusive"),
    ("i", "mixed intrusive, undifferentiated", "MEAN-OF-GLIM", ["pa", "pi", "pb"], None),
    ("u", "mafic to ultramafic intrusive", "MEAN-OF-GLIM+GARD", ["pb"], "gm:u"),
    ("n", "metamorphics: gneiss, migmatite", "SAME-AS-GLIM", ["mt"], "gm:n"),
    ("x", "metamorphic complexes", "SAME-AS-GLIM", ["mt"], "mt"),
    ("z", "tectonic rocks: mylonite, breccia", "SAME-AS-GLIM", ["mt"], "mt"),
    ("o", "hornfels", "SAME-AS-GLIM", ["mt"], "gm:o"),
    ("p", "low to medium grade metamorphic: slate, phyllite, schist", "SAME-AS-GLIM", ["mt"], "gm:p"),
    ("y", "metamorphosed siliciclastic rock", "SAME-AS-GLIM", ["ssmxmt"], "gm:y"),
    ("m", "metacarbonate: marble", "SAME-AS-GLIM", ["sc"], "gm:m"),
    ("e", "metamorphosed mafic to ultramafic intrusive", "SAME-AS-GLIM", ["pb"], "gm:e"),
    ("r", "metamorphosed felsic to intermediate intrusive", "MEAN-OF-GLIM", ["pa", "pi"], None),
    ("q", "quartzite", "GARD-MEDIAN", None, "gm:q"),
    ("t", "metavolcanic", "GARD-MEDIAN", None, "gm:t"),
]


def write_once(path, text):
    if os.path.exists(path):
        old = io.open(path, encoding="utf-8", newline="").read()
        if old == text:
            print(f"unchanged, already on disk: {path}")
            return
        raise SystemExit(f"REFUSED: {path} exists and differs. sources/ is "
                         f"write-once; choose a new version name.")
    tmp = path + ".part"
    io.open(tmp, "w", encoding="utf-8", newline="").write(text)
    os.replace(tmp, path)
    print(f"wrote {path}")


def to_csv(header, rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def main():
    gard = json.load(io.open(GARD, encoding="utf-8"))["classes"]
    with io.open(V1, encoding="utf-8", newline="") as fh:
        v1 = list(csv.DictReader(fh))
    val = {r["code"]: (float(r["SiO2_wt_pct"]), float(r["FeO_wt_pct"]))
           for r in v1 if r["SiO2_wt_pct"].strip()}

    # ---------------------------------------------------------- GLiM v2
    hdr = list(v1[0].keys()) + [
        "gard_class", "gard_n_SiO2", "gard_SiO2_p25", "gard_SiO2_median",
        "gard_SiO2_p75", "gard_n_FeO", "gard_FeO_p25", "gard_FeO_median",
        "gard_FeO_p75", "verification"]
    rows, tally = [], {}
    for r in v1:
        code = r["code"]
        g = gard.get(code)
        extra = [""] * 9
        if not r["SiO2_wt_pct"].strip():
            ver = "NO-COMPOSITION"
        elif g is None:
            base = gard.get(code[:2], {})
            bv = (base.get("verdict_sio2"), base.get("verdict_feo_t"))
            ver = (f"MODEL-ROW: derived from level-1 base '{code[:2]}' "
                   f"(SiO2 {bv[0]}, FeO_T {bv[1]}); the endmembers and pull "
                   f"weights are this project's construction (B19)")
        else:
            s, f = g["sio2"], g["feo_t"]
            extra = [g["definition"], s.get("n", 0), s.get("p25", ""),
                     s.get("median", ""), s.get("p75", ""), f.get("n", 0),
                     f.get("p25", ""), f.get("median", ""), f.get("p75", "")]
            vs, vf = g.get("verdict_sio2"), g.get("verdict_feo_t")
            if vs == vf == "VERIFIED":
                ver = "VERIFIED-GARD-IQR: both oxides inside the measured interquartile range"
            elif "NO VERDICT" in (vs, vf):
                ver = ("NO-VERDICT: fewer than 200 samples of this rock in "
                       "the database; value kept")
            else:
                ver = (f"OUTSIDE-GARD-IQR (SiO2 {vs}, FeO_T {vf}): value "
                       f"KEPT, see VARIABLES.md B31 for why the matching "
                       f"class is a poor one")
        tally[ver.split(":")[0].split(" ")[0]] = tally.get(
            ver.split(":")[0].split(" ")[0], 0) + 1
        rows.append([r[k] for k in v1[0].keys()] + extra + [ver])
    write_once(V2, to_csv(hdr, rows))
    print("GLiM v2 rows by verification:", tally)

    # ---------------------------------------------------------- GeoMAP
    hdr = ["code", "rock_type", "SiO2_wt_pct", "FeO_wt_pct", "basis",
           "glim_rows", "gard_class", "gard_n_SiO2", "gard_SiO2_p25",
           "gard_SiO2_median", "gard_SiO2_p75", "gard_n_FeO", "gard_FeO_p25",
           "gard_FeO_median", "gard_FeO_p75", "inside_gard_iqr", "source"]
    rows = []
    bad = []
    for code, meaning, kind, glim, gclass in GEOMAP:
        g = gard.get(gclass) if gclass else None
        if kind == "GARD-MEDIAN":
            si, fe = g["sio2"]["median"], g["feo_t"]["median"]
        elif kind == "MEAN-OF-GLIM+GARD":
            si = round((val[glim[0]][0] + g["sio2"]["median"]) / 2.0, 1)
            fe = round((val[glim[0]][1] + g["feo_t"]["median"]) / 2.0, 2)
        else:
            si = round(sum(val[c][0] for c in glim) / len(glim), 1)
            fe = round(sum(val[c][1] for c in glim) / len(glim), 2)
        inside = ""
        gx = [""] * 8
        if g:
            s, f = g["sio2"], g["feo_t"]
            gx = [s["n"], s["p25"], s["median"], s["p75"],
                  f["n"], f["p25"], f["median"], f["p75"]]
            if kind == "SAME-AS-GLIM":
                ok = (s["p25"] <= si <= s["p75"]) and (f["p25"] <= fe <= f["p75"])
                inside = "yes" if ok else "NO"
                if not ok:
                    bad.append((code, si, fe, s, f))
        rows.append([code, meaning, si, fe, kind,
                     "+".join(glim) if glim else "", gclass or ""] + gx
                    + [inside, COX + "; values: sources/glim_composition_lookup_v2.csv and "
                       + GARD_CITE])
        print(f"  {code}  {si:5.1f} {fe:6.2f}  {kind:18s} {meaning}")
    if bad:
        for b in bad:
            print("SAME-AS-GLIM value outside the Gard IQR:", b)
        raise SystemExit("stopped: a SAME-AS-GLIM row fails its own check")
    write_once(GM, to_csv(hdr, rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
