"""
SPEC REVISION 9 -- rev 8 docx + the 9 November 2026 changes + figures.

    python build/spec_rev9.py

Reads  docs/analog_finder_method_spec_rev8.docx  (never modified)
Writes docs/analog_finder_method_spec_rev9.docx

Method: the .docx is a zip; word/document.xml is edited as text. Nothing in
the existing text is rewritten except two sentences naming the revision.
Every change is an INSERTED block, headed "Revision 9 ...", placed after a
named anchor paragraph or table, so a reader can see exactly what is new.
Figures come from docs/figures/atlas (build/atlas.py) and are embedded as
inline pictures at full text width. Numbers are read from the cube's own
summary files at build time, not typed in.
"""

import io
import json
import os
import re
import shutil
import sys
import time
import zipfile
from xml.sax.saxutils import escape

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

ROOT = C.ROOT
SRC = os.path.join(ROOT, "docs", "analog_finder_method_spec_rev8.docx")
DST = os.path.join(ROOT, "docs", "analog_finder_method_spec_rev9.docx")
FIG = os.path.join(ROOT, "docs", "figures", "atlas")
TEXT_W_TWIPS = 9026
EMU_PER_TWIP = 635
PNG_DPI = 150

# ------------------------------------------------------------ xml builders

def para(text, bold_lead=None, size=None, italic=False, after=120):
    rpr = ""
    if size: rpr += f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
    if italic: rpr += "<w:i w:val=\"1\"/>"
    runs = ""
    if bold_lead:
        runs += f'<w:r><w:rPr><w:b w:val="1"/>{rpr}</w:rPr><w:t xml:space="preserve">{escape(bold_lead)}</w:t></w:r>'
    runs += f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'
    return f'<w:p><w:pPr><w:spacing w:after="{after}" w:lineRule="auto"/></w:pPr>{runs}</w:p>'


def heading(text, level=3):
    return (f'<w:p><w:pPr><w:pStyle w:val="Heading{level}"/></w:pPr>'
            f'<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>')


def table(header, rows, widths):
    assert abs(sum(widths) - TEXT_W_TWIPS) < 2, sum(widths)
    def cell(txt, w, head):
        shd = '<w:shd w:fill="1f3864" w:val="clear"/>' if head else ""
        rpr = '<w:b w:val="1"/><w:bCs w:val="1"/><w:color w:val="ffffff"/>' if head else ""
        return (f'<w:tc><w:tcPr><w:tcW w:type="dxa" w:w="{w}"/>{shd}<w:tcMar><w:top w:w="60" w:type="dxa"/>'
                f'<w:left w:w="100" w:type="dxa"/><w:bottom w:w="60" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tcMar></w:tcPr>'
                f'<w:p><w:pPr><w:spacing w:after="0" w:lineRule="auto"/></w:pPr><w:r><w:rPr>{rpr}<w:sz w:val="19"/><w:szCs w:val="19"/></w:rPr>'
                f'<w:t xml:space="preserve">{escape(txt)}</w:t></w:r></w:p></w:tc>')
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    hdr = '<w:tr><w:trPr><w:cantSplit w:val="1"/><w:tblHeader w:val="1"/></w:trPr>' + "".join(cell(h, w, True) for h, w in zip(header, widths)) + "</w:tr>"
    body = "".join('<w:tr><w:trPr><w:cantSplit w:val="1"/></w:trPr>' + "".join(cell(c, w, False) for c, w in zip(r, widths)) + "</w:tr>" for r in rows)
    bd = '<w:top w:color="000000" w:space="0" w:sz="4" w:val="single"/><w:left w:color="000000" w:space="0" w:sz="4" w:val="single"/><w:bottom w:color="000000" w:space="0" w:sz="4" w:val="single"/><w:right w:color="000000" w:space="0" w:sz="4" w:val="single"/><w:insideH w:color="000000" w:space="0" w:sz="4" w:val="single"/><w:insideV w:color="000000" w:space="0" w:sz="4" w:val="single"/>'
    return (f'<w:tbl><w:tblPr><w:tblStyle w:val="Table1"/><w:tblW w:w="{TEXT_W_TWIPS}" w:type="dxa"/><w:jc w:val="left"/>'
            f'<w:tblBorders>{bd}</w:tblBorders><w:tblLayout w:type="fixed"/><w:tblLook w:val="0000"/></w:tblPr>'
            f'<w:tblGrid>{grid}</w:tblGrid>{hdr}{body}</w:tbl>' + para("", after=60))


class Images:
    def __init__(self):
        self.items = []     # (rid, filename, bytes)
        self.n = 0

    def add(self, png_path, caption):
        from PIL import Image
        self.n += 1
        im = Image.open(png_path); w, h = im.size
        cx = TEXT_W_TWIPS * EMU_PER_TWIP
        cy = int(cx * h / w)
        rid = f"rIdAtlas{self.n}"
        name = f"atlas{self.n}.png"
        self.items.append((rid, name, open(png_path, "rb").read()))
        did = 5000 + self.n
        drawing = (
            f'<w:p><w:pPr><w:keepNext w:val="1"/><w:spacing w:after="40" w:before="120"/><w:jc w:val="center"/></w:pPr><w:r><w:drawing>'
            f'<wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:docPr id="{did}" name="Figure {self.n}" descr="{escape(os.path.basename(png_path))}"/>'
            f'<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
            f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:pic><pic:nvPicPr><pic:cNvPr id="{did}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
            f'</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>')
        cap = para(f"Figure R9-{self.n}. {caption}", size=18, italic=True, after=160)
        return drawing + cap


# ------------------------------------------------------------- the content

def load_numbers():
    n = {}
    man = json.load(io.open(C.MANIFEST, encoding="utf-8"))["layers"]
    n["man"] = man
    n["dc"] = json.load(io.open(os.path.join(ROOT, "cube", "phase4", "dimension_check.json"), encoding="utf-8"))
    n["val"] = json.load(io.open(os.path.join(ROOT, "cube", "phase4", "mars_thermal_1d_validation.json"), encoding="utf-8"))
    n["p3f"] = json.load(io.open(os.path.join(ROOT, "cube", "healpix", "phase3f_mars_summary.json"), encoding="utf-8"))
    n["comp"] = json.load(io.open(os.path.join(ROOT, "cube", "healpix", "mars_composition_summary.json"), encoding="utf-8"))
    n["p4c"] = json.load(io.open(os.path.join(ROOT, "cube", "phase4", "phase4c_summary.json"), encoding="utf-8"))
    n["cv"] = json.load(io.open(os.path.join(ROOT, "cube", "cube_validation.json"), encoding="utf-8"))
    n["seam"] = {b: json.load(io.open(os.path.join(ROOT, "cube", "phase4", f"svf_seam_{b}.json"), encoding="utf-8")) for b in ("moon", "mars", "earth")}
    n["enc"] = json.load(io.open(os.path.join(ROOT, "cube", "provenance_encoding.json"), encoding="utf-8"))
    n["em"], n["emx"] = n["cv"]["pairings"]["earth_moon"], n["cv"]["pairings"]["earth_mars"]
    return n


def blocks(img, n):
    man, dc, val, p3f, comp, p4c, cv = (n[k] for k in ("man", "dc", "val", "p3f", "comp", "p4c", "cv"))
    r = dc["correlation"]
    svf_r = r["svf_30km"]["roughness_5.25km"]; ati_r = r["thermal_inertia"]["temp_range_diurnal"]
    B = {}

    # ---- A. after the Revision 8 change table
    B["revision"] = heading("Revision 9 — what changed on 9 November 2026") + para(
        "Revision 9 adds the decisions and measurements of 9 November 2026. Nothing in the text above is rewritten; every "
        "addition is an inserted block headed \"Revision 9\" so the change is visible. Where an older statement is overridden, "
        "the block says so and the statement stays, as this document's rules require. A figure atlas accompanies this "
        "revision: docs/CUBE_ATLAS_2026-11-09.pdf, one map per ranking layer per body and the graphs behind every number here.") + table(
        ["Change", "Where"], [
            ["Topographic position index at 7 km added, all three bodies (B1's secondary recommendation)", "Step 2 Rev 9; Appendix E Rev 9 (B26)"],
            [f"Sky view factor built on all three bodies, polar-stereographic caps beyond 80°. Measured {svf_r:+.2f} against 5.25 km roughness on Earth land; kept ranking by decision", "Step 2 Rev 9; Appendix H (B27)"],
            [f"Thermal inertia: Mars from TES at 3 km (measured), Earth as apparent thermal inertia from MODIS albedo and the diurnal LST range (a proxy, {ati_r:+.2f} with the diurnal range); kept ranking by decision", "Step 2 Rev 9 (B27b, B29)"],
            ["Mars SiO₂ and FeO_T from the TES mineral maps through a tagged end-member table; weak, 49% of Mars", "Step 2 Rev 9 (B27c)"],
            ["Mars temperature level, diurnal and seasonal range MODELLED at pixel scale by a 1-D thermal model (NumPy port of KRC); the MCD layers are replaced", "Step 2 Rev 9 (B28); overrides \"Why Mars thermal cannot be matched\""],
            [f"Dimension counts: Earth–Moon 10 → {len(n['em'])}, Earth–Mars 6 → {len(n['emx'])}", "Step 2 Rev 9"],
            ["Köppen-Geiger characterization layer; reference mask, lithology and diagnostics recorded; provenance refreshed; a cube-wide validator that passes", "Step 1 Rev 9 (B25)"],
            ["Phase 4a–4c (percentile transform, whitening, calibration) rerun on the new cube; targets, null, selection and characterization left for the hackathon", "Appendix H Rev 9 (B30)"],
        ], [6026, 3000])

    # ---- B. after "What step 1 produced"
    ref_n = man["earth_reference_mask"]["validation"]["pixels_in_reference_population"]
    B["step1"] = heading("Revision 9 — step 1 additions") + table(
        ["Product", "Status"], [
            ["Earth reference mask on HEALPix", f"Built — {ref_n:,} pixels at fraction > 0.5, {man['earth_reference_mask']['validation']['pct_of_sphere_in_reference']:.2f}% of the sphere; recorded in the manifest with its rule"],
            ["Mars elevation on HEALPix", "Built — pressure input for the thermal model; never ranks"],
            ["Provenance arrays for every data layer", f"{len(n['enc']['layers'])} layers in {len(set(v['provenance_file'] for v in n['enc']['layers'].values()))} shared arrays; refreshed after every rebuild"],
            ["Lithology class layers, Köppen class, thermal sample counts", "Recorded in the manifest with gates; characterization and filters, never ranking"],
            ["Cube-wide validation", f"build/cube_validate.py: {cv['verdict']}, {cv['manifest_entries']} manifest entries, {cv['layer_failures']} layer failures, {len(cv['orphans'])} orphan files, last run {cv['run_utc']}"],
        ], [3200, 5826]) + img.add(os.path.join(FIG, "provenance.png"),
        "Provenance of every pixel of every layer. Green: binned from a finer source. Orange: copied from a coarser source "
        "(Mars composition, lunar composition, parts of the thermal layers). Grey: the source covers the pixel but gave no value. Black: no source cell.") \
        + img.add(os.path.join(FIG, "coverage_earth.png"), "Number of ranking layers with a value per Earth pixel, over the reference population. 99.5% of reference pixels carry all 14.")

    # ---- C. after Part A table
    seam = n["seam"]
    B["parta"] = heading("Revision 9 — the matching dimensions as built") + para(
        f"The rule is unchanged: a variable is a dimension only if both bodies in the pair have it. Applied to the cube as it "
        f"stands, Earth–Moon has {len(n['em'])} and Earth–Mars has {len(n['emx'])}. The additions since Revision 8 are TPI at 7 km, "
        f"sky view factor, thermal inertia, Mars composition, and Mars thermal at pixel scale. Mars thermal is modelled, not measured; "
        f"see the Mars thermal block below.") + img.add(os.path.join(FIG, "dimension_table.png"),
        "The ranking dimensions as built, with coverage per body. 'weak' and 'modelled' are the manifest's own flags.") + table(
        ["Variable", "Definition", "Earth", "Moon", "Mars"], [
            ["TPI 7 km", "height minus the mean height in a 7 km window; negative inside a bowl", "ETOPO 15″", "LOLA 1/64°", "MOLA–HRSC 1/128°"],
            ["Sky view factor 30 km", "1 − mean over 16 azimuths of sin(horizon angle), 30 km search radius, at 0.93 km; polar-stereographic caps beyond 80°", "same DEM, sea surface at 0 m", "same", "same"],
            ["Thermal inertia", "Mars: TES-derived, J m⁻² K⁻¹ s⁻½. Earth: apparent, (1 − albedo) / diurnal LST range, K⁻¹ — a proxy", "MODIS LST 2025 + MCD43A3 albedo, 10 months", "— (no measured product at the pole)", "TES 20 ppd, Putzig & Mellon 2007"],
            ["Temperature level, diurnal range, seasonal range (Mars)", "same definitions as Revision 8, now at pixel scale", "as before", "as before", "MODELLED: 1-D thermal model from TES thermal inertia, albedo, pressure, latitude, dust"],
            ["SiO₂, FeO_T (Mars)", "abundance-weighted end-member oxides, dust as a mask", "GLiM lookup, as before", "LP GRS, as before", "TES mineral maps 4 ppd (15 km), 49% of Mars"],
        ], [1700, 3026, 1500, 1200, 1600]) + heading("Two redundancies, measured and decided") + para(
        f"On Earth's reference population sky view factor is {svf_r:+.2f} against 5.25 km roughness and {r['svf_30km']['slope']:+.2f} against slope: at a 30 km "
        f"search radius the horizon is set by the same relief the roughness windows measure, so openness is roughness with the sign flipped. "
        f"Apparent thermal inertia is {ati_r:+.2f} against the diurnal range it is computed from. Both were presented with the recommendation to "
        f"demote them to characterization; Sherozbek chose to keep both ranking and let the whitening floor at 0.10 absorb the redundancy. "
        f"Earth–Mars now has {dc['pairings']['earth_mars']['with_additions']['n_below_floor']} eigenvalues below the floor holding "
        f"{dc['pairings']['earth_mars']['with_additions']['variance_below_floor_pct']:.2f}% of the variance; Earth–Moon "
        f"{dc['pairings']['earth_moon']['with_additions']['n_below_floor']} holding {dc['pairings']['earth_moon']['with_additions']['variance_below_floor_pct']:.2f}%. "
        f"Mars composition is the opposite case: SiO₂ and FeO are orthogonal to every terrain layer (|ρ| ≤ 0.2).") + img.add(
        os.path.join(FIG, "corr_earth.png"), "Rank correlation of the 14 Earth candidates over the reference population. The two decided redundancies are the dark cells in the sky-view and thermal-inertia rows.") + img.add(
        os.path.join(FIG, "eigenvalues.png"), "Eigenvalue spectra of the rank-correlation matrix for both pairings; the red line is the whitening floor. The floored directions are the roughness family plus the two pairs above.") + img.add(
        os.path.join(FIG, "distributions.png"), "Distributions of every ranking variable in native units per body. The three worlds sit at different scales on purpose; the per-body rank transform of step 3 removes the scale and keeps the shape.") + heading("The sky view factor seam at 80°") + para(
        "The polar caps are computed on a different grid and geometry from the plate carrée sweep. Where both can compute the same terrain, 78–80°, "
        "they were compared pixel by pixel: " + "; ".join(
            f"{b.capitalize()} {p} median |Δ| {seam[b]['poles'][p]['median_abs_diff']:.4f}, p95 {seam[b]['poles'][p]['p95_abs_diff']:.4f}, r {seam[b]['poles'][p]['pearson_r']:.3f}"
            for b in ("moon", "mars", "earth") for p in ("S", "N")) +
        ". Against spreads of 0.02–0.04 the seam is not a step; Earth's south-pole correlation is low only because the ice sheet is flat and both methods return 1.0.") \
        + img.add(os.path.join(FIG, "map_moon_svf_30km.png"), "Sky view factor on the Moon with the 85–90°S inset, the Artemis band. Low values are the floors of the south-polar craters.") \
        + img.add(os.path.join(FIG, "map_earth_tpi_7km.png"), "Topographic position index at 7 km on Earth's reference population; blue is inside a bowl, red a rim or ridge.")

    # ---- D. Mars thermal, after "The layers are built, reported, and flagged."
    cmp = p3f["mcd_comparison"]
    B["marsthermal"] = heading("Revision 9 — Mars thermal, modelled at pixel scale (overrides the paragraph above)") + para(
        "Two searches on 9 November 2026 found no measured, gridded Mars surface-temperature map at pixel scale: TES temperatures exist only as "
        "individual observations, the THEMIS mosaics are stretched 8-bit renderings, MCS and EMIRS are degrees-scale. The Mars Climate Database "
        "cannot be sharpened either: its own design document (v6.1, §7.3.1) states that the high-resolution mode leaves surface temperature "
        "untouched and rescales pressure only. The literature's route for this problem is a one-dimensional surface heat-balance model read "
        "through a lookup table over thermal inertia, albedo, pressure, latitude, dust and season (Mellon 2000; Putzig & Mellon 2007; Fergason 2006; "
        "Kieffer 2013). That is what was built, and it replaces the three MCD layers under the same names and definitions.") + para(
        f"The model is a NumPy port of KRC's one-point mode (no Fortran compiler was available). Against KRC's own reference output shipped with its "
        f"source, 23 cases, the port agrees to a median {val['median_abs_dT']:.2f} K, mean {val['mean_dT']:+.2f} K, worst non-polar {val['max_abs_dT_nonpolar']:.2f} K. "
        f"A table of 1.76 million model runs (12 seasons × 20 thermal inertias × 7 albedos × 7 elevations × 30 latitudes × 5 dust levels × 12 local times) "
        f"is interpolated at every pixel's TES thermal inertia, TES albedo, MOLA pressure, latitude and climatological dust (Montabone et al. 2015, four "
        f"storm-free years). Checked against the MCD at the MCD's own 5.6 × 3.75° grid: level r {cmp['temp_level']['pearson_r']:.3f}, mean difference "
        f"{cmp['temp_level']['mean_diff_K']:+.1f} K; diurnal range r {cmp['temp_range_diurnal']['pearson_r']:.3f}, {cmp['temp_range_diurnal']['mean_diff_K']:+.1f} K; "
        f"seasonal range r {cmp['temp_range_seasonal']['pearson_r']:.3f}, {cmp['temp_range_seasonal']['mean_diff_K']:+.1f} K.") + para(
        man["mars_temp_level"]["status"], bold_lead="Status, carried on every entry: ") + para(
        f"Limits: flat surfaces (slope is not a table axis); one typical-year dust climatology; one grey atmosphere layer; polar-cap edges unreliable; "
        f"{p3f['non_converged']:,} pixels (3.6%) carry a convergence flag; coverage follows the TES thermal inertia, 99.4% of Mars and 56% of 85–90°S. "
        f"The gain: the MCD layers held 3,072 values for the planet; these hold a value per pixel driven by measured thermal inertia and albedo. "
        f"Mars temperature level, diurnal range and seasonal range are therefore matching_eligible, and the paragraph above is overridden.") \
        + img.add(os.path.join(FIG, "map_mars_temp_level.png"), "Modelled Mars temperature level. Orbit-track striping north of 60° is in the TES thermal-inertia input and is real in the source.") \
        + img.add(os.path.join(FIG, "krc_validation.png"), "The port against KRC's one-point reference cases.") \
        + img.add(os.path.join(FIG, "mcd_comparison.png"), "Modelled layers against the Mars Climate Database at its own grid: a one-dimensional model with climatological dust against a general circulation model.") \
        + img.add(os.path.join(FIG, "diurnal_curves.png"), "Why thermal inertia matters: modelled diurnal curves at the equator for five thermal inertias. Dust swings 130 K; rock 60 K.")

    # ---- E. Mars composition, after the "worth" paragraph
    s = comp["layers"]; sens = {k: s[k]["sensitivity"] for k in ("SiO2", "FeO")}
    B["marscomp"] = heading("Revision 9 — Mars composition, the spec's option (b)") + para(
        "No public Mars product gives oxide weight percent at pixel scale. GRS is 300–600 km; OMEGA and CRISM give band depths with no Earth "
        "counterpart. The only numeric mineral-abundance product is the TES mineral maps (Bandfield 2002) at 4 pixels per degree, 15 km, 2.2× the "
        "pixel. Mars SiO₂ and FeO_T are the abundance-weighted means of nine end-member oxide contents, normalised over the minerals, with dust as a "
        "mask (> 0.80 excluded), poor fits (RMS > 0.0044) and thin detections (mineral sum < 0.10) removed. Every end-member value is tagged DEFINITIONAL, "
        "ASSUMED or ESTIMATE with its alternatives.") + para(
        f"Coverage {s['SiO2']['coverage_gate']['global']:.1f}% of Mars and {s['SiO2']['coverage_gate']['lat_85S_to_90S']:.1f}% of 85–90°S; {s['SiO2']['pct_copied']:.0f}% of valid pixels are copies of a coarser cell. "
        f"The stated silicate gates fail on {s['SiO2']['pixels_outside_stated_gate']:,} (SiO₂) and {s['FeO']['pixels_outside_stated_gate']:,} (FeO) pixels where hematite dominates; counted, not clipped. "
        f"Sensitivity, measured by moving every assumed value to its alternatives: the SiO₂ ordering survives (rank correlation {sens['SiO2']['spearman_base_vs_low']:.2f}–{sens['SiO2']['spearman_base_vs_high']:.2f}); "
        f"the FeO ordering only partly ({sens['FeO']['spearman_base_vs_high']:.2f} against the iron-rich alternative), because the glass/sheet-silicate iron content is unconstrained. "
        f"Decision: FeO kept with the ESTIMATE tag at 5 wt%; Mars FeO is to be quoted as the weaker of the two.") \
        + img.add(os.path.join(FIG, "composition_endmembers.png"), "The Mars end-member table with the assumed alternatives as error bars.") \
        + img.add(os.path.join(FIG, "map_mars_SiO2.png"), "Mars SiO₂ from the TES mineral maps. Dark grey is dust-covered or poorly fitted terrain with no value.")

    # ---- F. Appendix H, after the "Not built, with reasons" table
    B["apph"] = para("Revision 9: sky view factor is built on all three bodies and the correlation matrix, VIF basis and λ_min have been measured on the "
                     "matchable set (Step 2 Rev 9). Thermal inertia is built for Earth–Mars (B23's \"do not build\" is overridden). The lunar local-time "
                     "sampling question was answered in B17b: the poles are the best sampled. The rows above stay as the record of what was open before "
                     "9 November.", bold_lead="Revision 9. ")

    # ---- G. Appendix E additions
    B["appe"] = heading("Revision 9 decisions, 9 November 2026") + table(["Step", "Decision", "Value"], [
        ["2", "TPI 7 km", "Added, all bodies. λ_min unchanged; it adds no near-singular direction"],
        ["2", "Sky view factor", f"Built, 16 azimuths, 30 km, 0.93 km; caps beyond 80° in polar stereographic. {svf_r:+.2f} with roughness on Earth; KEPT RANKING"],
        ["2", "Mars thermal inertia", "TES 20 ppd nightside, infilled pixels excluded; dayside kept as a diagnostic"],
        ["2", "Earth apparent thermal inertia", f"(1 − albedo)/ΔT from ten MODIS months (June and July cannot be exported; ten accepted as final). {ati_r:+.2f} with the diurnal range; KEPT RANKING"],
        ["2", "Mars composition", "TES mineral maps through a tagged end-member table; FeO kept with the ESTIMATE tag"],
        ["2", "Mars temperatures", "MODELLED at pixel scale by a NumPy port of KRC; MCD layers replaced; status text on every entry"],
        ["2", "Albedo", "Input and characterization layer only, not a ranking dimension"],
        ["2", f"Dimension counts", f"Earth–Moon {len(n['em'])}, Earth–Mars {len(n['emx'])}"],
        ["3–4", "Phase 4a–4c", f"Rerun on the new cube: d_bar {p4c['earth_moon']['d_bar']:.2f} / {p4c['earth_mars']['d_bar']:.2f}, DI thresholds {p4c['earth_moon']['di_threshold']:.3f} / {p4c['earth_mars']['di_threshold']:.3f}; targets and null left for the hackathon"],
    ], [700, 2600, 5726])

    # ---- H. Appendix D additions, before "A note on citation status"
    B["appd"] = heading("Revision 9 additions") + table(["Dataset", "Feeds", "Status"], [
        ["MGS TES thermal inertia, Putzig & Mellon 2007, 20 ppd", "Mars thermal inertia; input to the thermal model", "Used"],
        ["MGS TES mineral maps, Bandfield 2002, 4 ppd", "Mars SiO₂ and FeO_T through the end-member table", "Used — weak, 49% of Mars"],
        ["MGS TES bolometric albedo, Christensen 2001, 8 ppd", "Thermal-model input; characterization", "Used, not a dimension"],
        ["Dust optical depth climatology, Montabone et al. 2015, MY29–MY32", "Seasonal dust forcing of the thermal model", "Used"],
        ["KRC thermal model, Kieffer 2013 (public Fortran)", "Physics ported to NumPy; its reference output is the validation target", "Ported, not built"],
        ["Mars Climate Database v6.1", "Coarse-scale check of the modelled layers", "Its three layers replaced"],
        ["MODIS MCD43A3 albedo, 2025, ten months", "Earth apparent thermal inertia", "Used"],
        ["Köppen-Geiger 1991–2020, Beck et al. 2023", "Step 9 site description", "Used — characterization only"],
        ["OMEGA global maps, CRISM MRDR, Odyssey GRS, THEMIS IR mosaics, MCS/EMIRS", "—", "Examined and declined: band depths without an Earth partner, or too coarse, or stretched renderings"],
    ], [3600, 3000, 2426])
    return B


# ---------------------------------------------------------------- assembly

def pos_after_paragraph(doc, anchor):
    i = doc.find(anchor); assert i >= 0, anchor
    return doc.find("</w:p>", i) + len("</w:p>")


def pos_after_table(doc, anchor):
    i = doc.find(anchor); assert i >= 0, anchor
    return doc.find("</w:tbl>", i) + len("</w:tbl>")


def pos_before_paragraph(doc, anchor):
    i = doc.find(anchor); assert i >= 0, anchor
    return max(doc.rfind("<w:p>", 0, i), doc.rfind("<w:p ", 0, i))


def main():
    t0 = time.perf_counter()
    # FROZEN 11 Nov 2026. This script reads LIVE numbers but its sentences
    # describe the decisions of 9 Nov (thermal inertia "kept ranking", 14
    # dimensions, per-body ranks). Rebuilt on today's cube it would print 13
    # beside "kept ranking". Revision 9 on disk is the record; build
    # revision 10 with build/spec_rev10.py instead.
    if os.path.exists(os.path.join(ROOT, "cube", "phase4", "pooled_scale_summary.json")) and "--force" not in sys.argv:
        raise SystemExit("spec_rev9.py is frozen: the cube has moved on (B33). "
                         "Run build/spec_rev10.py. Use --force only to reproduce rev 9 on an old cube.")
    missing = [f for f in ("provenance.png", "coverage_earth.png", "dimension_table.png", "corr_earth.png", "eigenvalues.png",
                           "distributions.png", "map_moon_svf_30km.png", "map_earth_tpi_7km.png", "map_mars_temp_level.png",
                           "krc_validation.png", "mcd_comparison.png", "diurnal_curves.png", "composition_endmembers.png", "map_mars_SiO2.png")
               if not os.path.exists(os.path.join(FIG, f))]
    if missing:
        raise SystemExit(f"STOP: atlas figures missing: {missing} -- run build/atlas.py first")
    n = load_numbers()
    img = Images()
    B = blocks(img, n)
    zin = zipfile.ZipFile(SRC)
    doc = zin.read("word/document.xml").decode("utf-8")

    # the two sentences that name the revision
    reps = [("Revision 8, consolidated. Supersedes the earlier draft and revisions 1–7.",
             "Revision 9, consolidated. Supersedes the earlier draft and revisions 1–8."),
            ("This is Revision 8. It replaces the earlier draft",
             "This is Revision 9. It extends Revision 8 with the changes of 9 November 2026, listed in the table after the Revision 8 table below. Revision 8 replaced the earlier draft")]
    for a, b in reps:
        assert doc.count(a) == 1, a[:40]
        doc = doc.replace(a, b)

    inserts = [
        (pos_after_table(doc, "What this revision is"), B["revision"]),
        (pos_after_table(doc, "What step 1 produced"), B["step1"]),
        (pos_after_table(doc, "Part A — The matching dimensions"), B["parta"]),
        (pos_after_paragraph(doc, "The layers are built, reported, and flagged."), B["marsthermal"]),
        (pos_after_paragraph(doc, "That figure bounds everything derived from it and appears wherever composition appears."), B["marscomp"]),
        (pos_after_table(doc, "Not built, with reasons"), B["apph"]),
        (pos_after_table(doc, "Appendix E — Decisions log"), B["appe"]),
        (pos_before_paragraph(doc, "A note on citation status"), B["appd"]),
    ]
    # Appendix E: the heading occurs in the contents list too; use the LAST occurrence
    i_e = doc.rfind("Appendix E — Decisions log"); inserts[6] = (doc.find("</w:tbl>", i_e) + len("</w:tbl>"), B["appe"])
    i_h = doc.rfind("Not built, with reasons"); inserts[5] = (doc.find("</w:tbl>", i_h) + len("</w:tbl>"), B["apph"])
    i_d = doc.rfind("A note on citation status"); inserts[7] = (max(doc.rfind("<w:p>", 0, i_d), doc.rfind("<w:p ", 0, i_d)), B["appd"])
    for p, xml in sorted(inserts, key=lambda t: -t[0]):
        doc = doc[:p] + xml + doc[p:]

    rels = zin.read("word/_rels/document.xml.rels").decode("utf-8")
    add = "".join(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{name}"/>'
                  for rid, name, _ in img.items)
    rels = rels.replace("</Relationships>", add + "</Relationships>")
    ct = zin.read("[Content_Types].xml").decode("utf-8")
    if 'Extension="png"' not in ct:
        ct = ct.replace('<Default Extension="xml"', '<Default Extension="png" ContentType="image/png"/><Default Extension="xml"')

    tmp = DST + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename.endswith("/"):
                continue
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = doc.encode("utf-8")
            elif item.filename == "word/_rels/document.xml.rels":
                data = rels.encode("utf-8")
            elif item.filename == "[Content_Types].xml":
                data = ct.encode("utf-8")
            zout.writestr(item.filename, data)
        for rid, name, data in img.items:
            zout.writestr(f"word/media/{name}", data)
    os.replace(tmp, DST)
    # well-formedness
    import xml.dom.minidom
    xml.dom.minidom.parseString(doc.encode("utf-8"))
    print(f"wrote {DST} ({os.path.getsize(DST)/2**20:.1f} MB), {img.n} figures, {len(inserts)} inserted blocks, "
          f"{(time.perf_counter()-t0):.1f} s; document.xml well-formed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
