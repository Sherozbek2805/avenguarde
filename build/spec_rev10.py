"""
SPEC REVISION 10 -- rev 9 docx + the changes of 10 and 11 November 2026.

    python build/spec_rev10.py

Reads  docs/analog_finder_method_spec_rev9.docx   (never modified)
Writes docs/analog_finder_method_spec_rev10.docx

Same method as build/spec_rev9.py, whose helpers are reused: nothing in the
existing text is rewritten except the two sentences naming the revision.
Every change is an INSERTED block headed "Revision 10 ...", placed directly
under the heading of the step it changes, so a reader meets it before the
text it overrides. Numbers are read from the cube's own files at build time.

The largest change is step 3. Revision 8 argued for ranking each body
separately. On 11 November 2026 Sherozbek decided ONE SHARED SCALE per
variable (VARIABLES.md B33), and that night made it a MIN-MAX scale instead
of a rank (B38). Steps 6 to 9 follow: all target cells, two ranking systems
with the choice left for the day, one control, patches as sites, a use table.
Each block states the method as it stands and what it overrides.
"""

import io
import json
import os
import sys
import time
import zipfile
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C
import spec_rev9 as R9
from spec_rev9 import para, heading, table, TEXT_W_TWIPS, EMU_PER_TWIP

ROOT = C.ROOT
SRC = os.path.join(ROOT, "docs", "analog_finder_method_spec_rev9.docx")
DST = os.path.join(ROOT, "docs", "analog_finder_method_spec_rev10.docx")
FIG = os.path.join(ROOT, "docs", "figures", "atlas")
P4 = os.path.join(ROOT, "cube", "phase4")


class Images(R9.Images):
    """Same picture XML as rev 9, with ids and names that cannot collide."""

    def add(self, png_path, caption):
        from PIL import Image
        self.n += 1
        im = Image.open(png_path)
        w, h = im.size
        cx = TEXT_W_TWIPS * EMU_PER_TWIP
        cy = int(cx * h / w)
        rid = f"rIdRev10x{self.n}"
        name = f"rev10_{self.n}.png"
        self.items.append((rid, name, open(png_path, "rb").read()))
        did = 6000 + self.n
        drawing = (
            f'<w:p><w:pPr><w:keepNext w:val="1"/><w:spacing w:after="40" w:before="120"/><w:jc w:val="center"/></w:pPr><w:r><w:drawing>'
            f'<wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:docPr id="{did}" name="Figure R10-{self.n}" descr="{escape(os.path.basename(png_path))}"/>'
            f'<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
            f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:pic><pic:nvPicPr><pic:cNvPr id="{did}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
            f'</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>')
        return drawing + para(f"Figure R10-{self.n}. {caption}", size=18, italic=True, after=160)


def jl(*parts):
    return json.load(io.open(os.path.join(ROOT, *parts), encoding="utf-8"))


def blocks(img):
    p4c = jl("cube", "phase4", "phase4c_summary.json")
    mm = jl("cube", "phase4", "minmax_scale_summary.json")
    desc = jl("cube", "phase4", "minmax_description_b38.json")
    rs = jl("cube", "phase4", "ranking_sets.json")
    spread = jl("cube", "phase4", "target_spread_b36.json")
    use = jl("contract", "use_table.json")
    tm = jl("contract", "targets_moon.json")["targets"]
    tx = jl("contract", "targets_mars.json")["targets"]
    man = jl("cube", "cube_manifest.json")["layers"]
    gard = jl("cube", "gard_verification.json")["classes"]
    ex = jl("contract", "example_output.json")
    mask = man["earth_reference_mask"]["validation"]
    em, ex13, ex11 = p4c["earth_moon"], p4c["earth_mars"], p4c["earth_mars_no_composition"]
    pm, px = mm["pairings"]["moon"]["variables"], mm["pairings"]["mars"]["variables"]
    n_ver = sum(1 for v in gard.values() if v.get("verdict_sio2") == "VERIFIED" and v.get("verdict_feo_t") == "VERIFIED")
    n_tested = sum(1 for v in gard.values() if v.get("verdict_sio2") in ("VERIFIED", "OUTSIDE"))
    B = {}

    def rng(body, cons, var):
        v = [o["target_median"] for t in rs["targets"][body] for cn, c in t["constructions"].items() if cn == cons
             for o in c["out_of_range"] if o["variable"] == var]
        return f"{min(v):.0f}–{max(v):.0f}"

    def nranked(body, cons):
        return sorted({c["n_ranked"] for t in rs["targets"][body] for cn, c in t["constructions"].items() if cn == cons})

    def sp(body, cons, key):
        v = [r[key] for r in spread if r["body"] == body and r["construction"] == cons]
        return f"{min(v):.1f} – {max(v):.1f}"

    def sdr(body, d):
        a, b = desc[body][d]["targets_median_in_earth_sd"]
        return f"{a:+.0f} to {b:+.0f}"

    e_any = rs["targets"]["moon"][0]["constructions"]["all_dimensions"]["out_of_range"]
    e_lo = [o for o in e_any if o["variable"] == "temp_level"][0]["earth_min"]
    e_hi = [o for o in e_any if o["variable"] == "temp_range_diurnal"][0]["earth_max"]
    n_moon = nranked("moon", "all_dimensions")[0]
    n_mars_nc = nranked("mars", "without_composition")[0]
    n_mars_c = max(nranked("mars", "all_dimensions"))
    copy_moon = sp("moon", "all_dimensions", "copy_all_median")
    copy_mars = sp("mars", "without_composition", "copy_all_median")

    # ------------------------------------------------ A. the revision table
    B["revision"] = heading("Revision 10 — what changed on 10 and 11 November 2026") + para(
        "Revision 10 adds the decisions and measurements of 10 and 11 November 2026. As before, nothing above is rewritten. "
        "Each addition is an inserted block headed \"Revision 10\", placed directly under the heading of the step it changes. "
        "A Revision 10 block states the method as it stands on the night of 11 November; where it overrides older text, it says so.") + table(
        ["Change", "Where"], [
            ["ONE shared MIN-MAX scale per variable replaces ranking each body separately. It is the only scale used for matching", "Step 3 Rev 10 (B33, B38)"],
            [f"Thermal inertia no longer ranks. Earth–Mars has {len(ex13['dimensions'])} dimensions, {len(ex11['dimensions'])} without composition; Earth–Moon stays at {len(em['dimensions'])}", "Step 2 Rev 10 (B33)"],
            ["The targets are fixed: nine Artemis III regions from published polygons, six NASA Exploration Zones on Mars", "Step 5 Rev 10 (B32)"],
            ["Antarctic reference land is defined by measured exposed rock (SCAR GeoMAP), not by ice thickness; Antarctic composition comes from GeoMAP", "Step 2 Rev 10, Step 3 Rev 10 (B31)"],
            [f"The Earth composition lookup was checked against one million analysed rocks: {n_ver} of {n_tested} testable classes verified, no value changed", "Step 2 Rev 10 (B31)"],
            ["Step 4 calibration rebuilt as this document decides: whitening within groups, not across all variables", "Step 4 Rev 10 (B34)"],
            ["The score uses every target cell; the map carries percentile bands and a slider; two ranking systems are built, with and without the variables no Earth cell reaches, and choosing between them is the one decision left for the hackathon day", "Step 6 Rev 10 (B36, B37, B38)"],
            ["One control, the Atacama patch; results are reported as they come out", "Step 7 Rev 10 (B38)"],
            ["Sites are patches of the best 1% of Earth; the spacing rule is not built in version 1", "Step 8 Rev 10 (B38)"],
            ["A gap is a share of the variable's full range; a fixed use table for every variable, in three groups, says where a site succeeds, fails and where Earth's limits are", "Step 9 Rev 10 (B38)"],
            ["Step 10, the weight check, and the weight presets are removed from version 1", "Step 10 Rev 10 (B35)"],
            ["Test specification and null-table design rewritten; output contract 2.4", "Appendix E Rev 10"],
        ], [6426, 2600])

    # ------------------------------------------------ B. step 2, Part A
    B["parta"] = heading("Revision 10 — the matching dimensions on 11 November 2026", 3) + para(
        f"Thermal inertia has left the ranking. Earth's layer is apparent thermal inertia in K⁻¹, a proxy computed from albedo and the "
        f"day–night range. Mars's layer is TES thermal inertia in J m⁻² K⁻¹ s⁻½. They are different quantities. Step 3 now puts each "
        f"variable of a pairing on one shared scale, and two different quantities cannot share one. Asked directly, Sherozbek chose to "
        f"drop it from ranking rather than keep one variable on separate ranks. Both layers stay as characterization. Little is lost: "
        f"on Earth it is −0.96 with the day–night range, which stays. This overrides \"kept ranking\" in the Revision 9 block below.") + table(
        ["Dimension set", "Dimensions", "Used for"], [
            ["Earth–Moon", f"{len(em['dimensions'])}: slope, roughness at four scales, landform position at 7 and 21 km, sky view, temperature level, day–night range, SiO₂, FeO", "every lunar target"],
            ["Earth–Mars", f"{len(ex13['dimensions'])}: the same eight terrain variables, SiO₂, FeO, temperature level, day–night range, seasonal range", "Mars target cells that have composition"],
            ["Earth–Mars without composition", f"{len(ex11['dimensions'])}: the eight terrain and three temperature variables", "the primary run of every Mars preset zone; any Mars target on dusty ground"],
        ], [2300, 4426, 2300]) + para(
        f"Composition, two changes. First, the lookup that turns a rock class into weight percent was checked against the global "
        f"whole-rock database of Gard, Hasterok and Halpin (2019), 1,022,092 samples. The rule was fixed before the database was opened: "
        f"a value is verified when it lies inside the measured interquartile range of the matching rock class. {n_ver} of the {n_tested} "
        f"classes that could be tested are verified on both oxides, and no value changed. The one miss is mixed sedimentary rock, 15.6% "
        f"of ice-free land: the database has no clean counterpart for it, so its value is kept and stays rated high-uncertainty. "
        f"Second, in Antarctica and South Georgia the rock class now comes from SCAR GeoMAP (Cox et al. 2023), a 1:250,000 compilation of "
        f"exposed rock, wherever it names a class. One pixel takes one source, never a blend.")

    # ------------------------------------------------ C. step 3
    def vrow(label, d, unit, fmt="{:,.0f}"):
        e, b = pm[d]["earth_value_p1_p50_p99"], pm[d]["body_value_p1_p50_p99"]
        f = lambda v: " / ".join(fmt.format(x) for x in v) + unit
        return [label, f(e), f(b), f"{pm[d]['prob_body_above_earth']:.2f}"]

    overlap_rows = [
        vrow("Roughness at 21 km", "roughness_21km", " m"), vrow("Slope", "slope", "°", "{:.2f}"),
        vrow("SiO₂", "SiO2", " wt%", "{:.1f}"), vrow("Temperature level", "temp_level", " K"),
        vrow("Day–night range", "temp_range_diurnal", " K"),
    ]

    def srow(label, d, fmt="{:,.0f}", unit=""):
        v = pm[d]
        return [label, fmt.format(v["lo"]) + " – " + fmt.format(v["hi"]) + unit,
                f"{v['earth_position_p1_p50_p99'][1]:.2f}", f"{v['body_position_p1_p50_p99'][1]:.2f}",
                f"{v['earth_position_p1_p50_p99'][0]:.2f} – {v['earth_position_p1_p50_p99'][2]:.2f}",
                fmt.format(v["tenth_of_scale_in_units"]) + unit]

    scale_rows = [srow("Slope", "slope", "{:.1f}", "°"), srow("Roughness at 21 km", "roughness_21km", "{:,.0f}", " m"),
                  srow("Landform position at 21 km", "tpi_21km", "{:,.0f}", " m"), srow("Sky view", "svf_30km", "{:.2f}"),
                  srow("Temperature level", "temp_level", "{:.0f}", " K"), srow("Day–night range", "temp_range_diurnal", "{:.0f}", " K"),
                  srow("SiO₂", "SiO2", "{:.0f}", " wt%"), srow("FeO", "FeO", "{:.1f}", " wt%")]
    B["step3"] = heading("Revision 10 — one shared min-max scale per variable (overrides the per-body ranking in this step)", 2) + para(
        "From 11 November 2026 every variable of a pairing is put on ONE scale shared by Earth and the target body:",
        bold_lead="The decision (Sherozbek). ") + para(
        "position  =  (value − lowest) / (highest − lowest),   lowest and highest taken over Earth and the target body together") + para(
        "Earth–Moon and Earth–Mars each have their own scale. It is the only scale used for matching.") + para(
        "Two decisions on one day. In the morning Sherozbek replaced separate ranks by one shared scale; his example is below. "
        "The first build of that shared scale was still a rank, followed by a bell-shaped score. At night he replaced the rank by "
        "min-max: \"the ranking system is min-max instead of percentile ranking\", because the structure of the real values is "
        "kept. Both are recorded in VARIABLES.md, sections B33 and B38.", bold_lead="How it was reached. ") + para(
        "\"What it does\" (rank inside its own body's distribution), \"Why per body, and not pooled together\", the normal score, "
        "\"What the transform costs\", and the tests at the end of this step that assume ranks. They stay on the page as the "
        "record of what was decided before and why.", bold_lead="Overridden below. ") + para(
        "The reference population of each body, the treatment of masked cells, and the rule that the raw cube is never replaced.",
        bold_lead="Unchanged below. ") + heading("Why one shared scale", 3) + para(
        "Separate ranks answer \"does this place play the same role on its own world\". They do not answer \"is this place physically "
        "alike\". Sherozbek's example: suppose 40 units is the 95th percentile on Mars and 50 is the 95th on Earth. Separate ranks match "
        "the Mars place to the Earth place at 50. The Earth place that really is at 40 sits at Earth's 98th percentile and is ranked as "
        "a worse match. For choosing where to test a rover or train a crew, the place at 40 is the analog.") + para(
        "Measured on the cube, this is not a small effect. The table gives the 1st percentile, median and 99th percentile of the raw "
        "values, and the chance that a lunar cell is above an Earth cell: 0.5 means the two bodies are fully mixed on that variable, "
        "0 or 1 means they hardly overlap.") + table(
        ["Variable", "Earth", "Moon", "Chance Moon is above Earth"], overlap_rows, [2400, 2400, 2400, 1826]) + img.add(
        os.path.join(FIG, "pooled_overlap.png"),
        "Earth and the target body on one physical axis: roughness at 21 km (drawn on a log axis so both shapes can be seen), silica "
        "and temperature level, for the Moon (top) and Mars (bottom). Where the shapes share ground a physical match exists; where "
        "they do not touch, none does.") + heading("Why min-max and not a rank", 3) + para(
        "A rank keeps only the order. Two rough cells at the 90th and the 99.5th percentile look like neighbours on a rank scale, "
        "although the second is about twice as rough. Min-max is one straight line from the smallest value to the largest, so equal "
        "physical differences are equal distances on the scale. That is what \"the structure is kept\" means. It also needs no "
        "mixing weight: the rank version needed a choice of how much of the combined population should be Earth, and that choice "
        "is gone. There is no bell-shaped score either; the position itself goes to step 4.") + img.add(
        os.path.join(FIG, "minmax_position.png"),
        "The min-max scale for Earth and the Moon. The bottom axis is the physical value, the top axis the position between 0 and 1; "
        "they are the same axis. Dots mark each world's median cell.") + heading("What it costs, measured", 3) + para(
        "Terrain has long tails, so a few extreme cells set the ends of the scale and ordinary ground sits in a small part of it. "
        "The table gives the ends of each scale, where the median Earth and Moon cells land, the span that holds the middle 98% of "
        "Earth's cells, and what one tenth of the scale is in real units.", bold_lead="Ordinary ground is squeezed. ") + table(
        ["Variable (Earth–Moon)", "Lowest – highest", "Earth median", "Moon median", "Earth, middle 98%", "One tenth of the scale"],
        scale_rows, [2500, 1700, 1000, 1000, 1500, 1326]) + para(
        "Step 4 measures every variable in units of Earth's own standard deviation. A straight-line rescaling cancels there, so the "
        "lowest and highest value do not enter any distance: the distance is the same as on the raw values. They decide what is "
        "displayed (positions, gaps, verdicts). One absurd extreme cell can therefore squeeze the display of a variable but cannot "
        f"move a ranking. One such value was noticed: the largest FeO on Mars is {px['FeO']['hi']:.1f} wt%, which is not believable "
        "for bulk rock. It is flagged and was not changed.", bold_lead="The ends set what is shown, not what is measured. ") + para(
        "The rank scale bounded every gap; min-max does not. In units of Earth's standard deviation, the typical cell of an Artemis "
        f"region lies {sdr('moon','slope')} from Earth's average on slope, {sdr('moon','roughness_21km')} on roughness at 21 km, "
        f"{sdr('moon','tpi_21km')} on landform position at 21 km, {sdr('moon','temp_level')} on temperature level and "
        f"{sdr('moon','temp_range_diurnal')} on the day–night range. A variable with a gap that large can carry a distance alone. "
        "Step 6 deals with that.", bold_lead="Large gaps now reach the distance. ") + para(
        "The older text below chose ranks so that \"outliers and skew cannot dominate\". That protection is given up knowingly, in "
        "exchange for a scale on which a difference means a physical difference.", bold_lead="What is given up. ") + heading(
        "Gates and what was built", 3) + table(
        ["Gate, stated before running", "Result"], [
            ["G1. Both layers of a variable carry the same unit", f"{len(pm)} of 12 Moon and {len(px)} of 14 Mars variables pass. Thermal inertia is refused and no longer ranks"],
            ["G2. Highest is above lowest; every position lies between 0 and 1, and 0 and 1 are reached", "pass on every variable"],
            ["G3. The position turned back into a value gives the physical value again (the scale is one straight line)", "pass on every variable, error below one part in ten million of the range"],
        ], [5026, 4000]) + table(
        ["Dimension set", "Dimensions", "Complete Earth cells", "Floored eigenvalues", "d-bar"], [
            ["Earth–Moon", str(len(em["dimensions"])), f"{em['n_reference']:,}", str(em["eigenvalues_floored"]), f"{em['d_bar']:.4f}"],
            ["Earth–Mars", str(len(ex13["dimensions"])), f"{ex13['n_reference']:,}", str(ex13["eigenvalues_floored"]), f"{ex13['d_bar']:.4f}"],
            ["Earth–Mars without composition", str(len(ex11["dimensions"])), f"{ex11['n_reference']:,}", str(ex11["eigenvalues_floored"]), f"{ex11['d_bar']:.4f}"],
        ], [3026, 1300, 1900, 1500, 1300]) + para(
        f"Earth's reference population is ice-free, water-free land, {mask['pixels_in_reference_population']:,} cells. South of 60°S it is "
        f"now defined by measured exposed rock: a cell belongs when SCAR GeoMAP maps more than half of it as rock or moraine. The "
        f"ice-thickness rule was wrong there in both directions; it admitted 3,155 cells with a median of about 8% exposed rock and "
        f"left out 105 cells that are more than half rock, the Vestfold Hills among them. 390 Antarctic cells replace 3,155.",
        bold_lead="The reference population. ") + heading("Tests that replace the per-body tests below", 3) + table(
        ["Test in the list below", "Replaced by"], [
            ["The weighted mean rank is about 0.5 on every body", "REMOVED. Nothing is ranked"],
            ["Multiplying the values of one body by a constant leaves its ranks unchanged", "REMOVED. On a shared scale it must change the positions; that is the point"],
            ["The normal-score output has mean 0 and standard deviation 1 on every body", "REMOVED. There is no normal score"],
            ["(new)", "The same physical value gives the same position through the Earth route and through the body route"],
            ["(new)", "A map computed from positions and a map computed from raw values through the same calibration agree: the ends of the scale enter no distance"],
        ], [4026, 5000]) + para(
        "cube/phase4/minmax_earth_<body>.npy and minmax_<body>.npy hold the positions; minmax_scale_summary.json holds the ends of "
        "each scale; phase4b_minmax_scale.py builds them. The rank scale of the morning is parked in cube/_work and its builder "
        "is frozen. percentiles.npy still holds per-body ranks for a redundancy check. The engine reads neither.", bold_lead="Files. ")

    # ------------------------------------------------ C2. step 4
    def gd(s, g, key="d_bar"):
        return f"{s['groups'][g][key]:.4f}" if g in s["groups"] else "—"

    def shr(s, g):
        return (f"{100*s['groups'][g]['share_of_squared_distance_between_earth_cells']:.0f}%"
                if g in s["groups"] else "—")

    sets3 = (("Earth–Moon", em), ("Earth–Mars", ex13), ("Earth–Mars without composition", ex11))
    B["step4"] = heading("Revision 10 — step 4 as built: whitening within groups", 2) + para(
        "This step decides block-diagonal whitening: terrain variables are decorrelated among themselves, thermal among themselves, "
        "composition among themselves, and correlation between groups is left alone. The calibration built from 6 to 11 November did "
        "something else: it whitened all variables of a set together. That was never a decision; it had not been checked against this "
        "step. After a joint whitening no difference can be assigned to a group, so the per-group index and the worst group of the "
        "output contract had nothing to stand on. On 11 November the calibration was rebuilt as this step decides.",
        bold_lead="A correction. ") + para(
        "A cell's positions from step 3 are centred and scaled by Earth's mean and standard deviation, then each group is multiplied "
        "by the inverse square root of that group's own Earth correlation matrix. The combined distance is the plain distance between "
        "two such vectors: one matrix product and one ordinary distance. Where this step says \"add a small ridge\", what is built is "
        "the eigenvalue floor at 0.10 accepted on 6 November (B8): eigenvalues below the floor are raised to it. Four floored "
        "directions are in terrain, the slope and roughness family. On real values Earth's three temperature variables of the Mars "
        "sets are also close to redundant, so one thermal direction is floored there too.", bold_lead="What is built. ") + table(
        ["Dimension set", "d-bar", "d-bar terrain / thermal / composition", "Floored", "Largest correlation left between groups"], [
            [nm, f"{s['d_bar']:.4f}", f"{gd(s,'terrain')} / {gd(s,'thermal')} / {gd(s,'composition')}", str(s["eigenvalues_floored"]),
             f"{max(s['cross_group_max_abs_correlation'].values()):.2f}"] for nm, s in sets3
        ], [2500, 1200, 2726, 900, 1700]) + para(
        "Version 1 has none. The \"Group weights\" decision and the weight discussion below are deferred with step 10 (see the "
        "Revision 10 block there). Every group counts once. That is equal weight per group, not equal influence: between two Earth "
        "cells the squared distance splits as below, and terrain carries about half, because its eight variables are worth about "
        "four independent directions after whitening.",
        bold_lead="No group weights. ") + table(
        ["Dimension set", "Terrain", "Thermal", "Composition"], [
            [nm, shr(s, "terrain"), shr(s, "thermal"), shr(s, "composition")] for nm, s in sets3
        ], [3626, 1800, 1800, 1800]) + para(
        "That split is between Earth cells. Between an Earth cell and a lunar or martian target it is different, because the "
        "target sits many standard deviations away on some variables (step 3, Revision 10). That is why the group scores are always "
        "shown beside the combined one, and why step 6 builds two ranking systems.")

    # ------------------------------------------------ C3. the invariant and step 10
    B["invariant"] = para(
        "relaxed for version 1. Step 10, the weight check, is removed from version 1 (see its Revision 10 block), so a result is no "
        "longer reported under two weightings. Every preset target is still reported from more than one construction: under both "
        "ranking systems of step 6, and a Mars zone with and without composition.",
        bold_lead="Revision 10 — the third invariant is ")
    B["step10"] = heading("Revision 10 — this step is removed from version 1 and listed as future work", 2) + para(
        "On 11 November 2026 Sherozbek removed the weight check and the four weight presets (balanced, mobility, thermal, geology) "
        "from the method. Version 1 gives every group a weight of 1. Nothing below is built for the hackathon. It stays on the "
        "page as the design for later.", bold_lead="The decision. ") + para(
        "Sensitivity to the group weights moves to future work, named so that it is not forgotten. Two other items that were on "
        "this list no longer exist: the mixing weight of the rank scale went with the rank scale (step 3), and the number of "
        "nearest target cells went when step 6 began to use every target cell.", bold_lead="What moves to future work. ") + para(
        "The output contract (2.4) has no preset and no rank interval, alternative rank or weight-sensitive flag. The step 4 "
        "calibration stores one d-bar per dimension set and one per group. The per-group index and the worst group stay: they "
        "describe a result and need no weights.", bold_lead="What changes with it. ") + para(
        "A reader should know that \"every group counts once\" is itself a choice, and that the effect of changing it has not been "
        "measured. That sentence goes in the limits of the write-up.", bold_lead="The limit to state. ")

    # ------------------------------------------------ D. step 5
    moon_rows = [[t["name"], f"{t['center_lat']:.2f}, {t['center_lon']:.2f}", f"{t['geometry']['area_km2']:,.0f} km²", str(t["cells"])] for t in tm]
    mars_rows = [[t["name"], f"{t['center_lat']:.3f}, {t['center_lon'] % 360:.3f}", t["geometry_source"].split(";")[0].replace("2015 NASA Exploration Zone proposal, ", ""),
                  str(t["cells"]), f"{t['constructions']['all_dimensions']['cells']} ({100*t['constructions']['all_dimensions']['share_of_target']:.0f}%)"] for t in tx]
    B["step5"] = heading("Revision 10 — the targets are fixed", 2) + para(
        "LROC QuickMap publishes the nine regions of NASA's 28 October 2024 update as polygons (layer \"A3: Candidate Landing Regions "
        "2024\"). They replace the placeholders, which put each region as a 15 × 15 km disc at the IAU centre of the feature it is named "
        "after and were 3 to 67 km from the real region. The regions are 16 to 30 km squares and one 77 × 58 km plateau, drawn as "
        "rectangles in south polar stereographic; a stated gate checks that and all nine pass. Mons Mouton and Mons Mouton Plateau, and "
        "Nobile Rim 1 and 2, are now four different targets. NASA's own release carries a map image and no coordinates; the polygon "
        "file is not hosted on nasa.gov and states no licence.", bold_lead="Moon. ") + table(
        ["Region", "Centre (lat, lon)", "Ground area", "Cells"], moon_rows, [3326, 2300, 1900, 1500]) + para(
        "Two pairs overlap and are not independent: Mons Mouton Plateau shares 3 cells with Mons Mouton, and Mons Mouton shares 1 with "
        "Nobile Rim 1. Every cell of every region carries all 12 dimensions.") + para(
        "The targets are Exploration Zones proposed at NASA's 2015 workshop on human landing sites. NASA defines a zone as the regions "
        "of interest within about 100 km of a landing site, so each target is a disc of that radius centred where the proposing team "
        "wrote its centre. Nothing in the geometry is invented. Six were chosen by source, before any distance existed: every zone "
        "inside which a rover has since driven, and one zone in each of the two mid-latitude ice provinces that drew several "
        "independent proposals. Data coverage was not a criterion.", bold_lead="Mars. ") + table(
        ["Zone", "Centre (lat, lon °E)", "Proposal", "Cells", "Cells with composition"], mars_rows, [2400, 1900, 2026, 900, 1800]) + para(
        "Composition is patchy on Mars because dusty ground is masked, and that is where the ice sites are. So every Mars preset runs "
        f"on two constructions. PRIMARY: terrain and temperature, {len(ex11['dimensions'])} dimensions, over every cell of the zone, which makes the six "
        f"comparable with each other. SECOND: all {len(ex13['dimensions'])} dimensions over the cells that have composition. Both are printed with the "
        "difference between them. A Mars zone is about 31,000 km², seven times the largest Artemis region; it holds crater floor, rim "
        "and plains together.") + para(
        "A cell belongs to a target when its centre is inside the region. The pixel lists are in contract/targets_moon.json and "
        "contract/targets_mars.json, written by build/targets.py, which computes no distance.", bold_lead="One rule. ")

    # ------------------------------------------------ D2. step 6
    preset_sets = sorted({c["ranking_set"] for b in rs["targets"] for t in rs["targets"][b] for c in t["constructions"].values()},
                         key=lambda k: (rs["sets"][k]["pooled_with"] != "moon", "no_comp" not in k, -rs["sets"][k]["n_dims"]))
    label = {"earth_moon": "Earth–Moon", "earth_mars": "Earth–Mars", "earth_mars_no_composition": "Earth–Mars without composition"}
    set_rows = [[label[rs["sets"][k]["base_set"]], str(rs["sets"][k]["n_dims"]),
                 ", ".join(f"{g} {len(v['dimensions'])}" for g, v in rs["sets"][k]["groups"].items()),
                 ", ".join(d for d in p4c[rs["sets"][k]["base_set"]]["dimensions"] if d not in rs["sets"][k]["dimensions"]),
                 f"{rs['sets'][k]['d_bar']:.4f}"] for k in preset_sets]
    B["step6"] = heading("Revision 10 — which variables rank, which target cells count, and percentile bands", 2) + para(
        "Three decisions of 11 November 2026 change this step. Two of them override text below, which stays on the page as the "
        "record of what was argued before.", bold_lead="The decisions (Sherozbek). ") + heading(
        "1. Two ranking systems; choosing between them is the one decision left for the day", 3) + para(
        "System 1 ranks on every variable of the set, also those no Earth cell reaches. System 2 ranks only on what Earth can "
        "match, by the rule below. The engine takes the system as one argument and everything else is the same code. Sherozbek: "
        "\"this is the only thing we decide on the hackathon\", after both have been run on real maps. For every preset target both "
        "are run and both results are printed, p-values included, never only the better one.", bold_lead="Both are built. ") + para(
        "For one target and one variable, take the median of the target's cells in physical units. If it lies outside the whole "
        "range of Earth's reference population, below Earth's smallest value or above its largest, the variable is out of Earth's "
        "range. Both systems report it as one of Earth's limits, with the gap in its own unit. System 2 also leaves it out of every "
        "distance for that target. \"Whole range\" is the most permissive choice: a variable stays in unless no Earth cell at all "
        "reaches the target. The rule has no parameter.", bold_lead="The rule of system 2. ") + table(
        ["Targets", "Variables Earth can match", "Out of Earth's range (median of each target)"], [
            ["Nine Artemis III regions", f"{n_moon}: the eight terrain variables, SiO₂, FeO",
             f"Temperature level {rng('moon', 'all_dimensions', 'temp_level')} K; Earth's coldest reference cell is {e_lo:.1f} K. "
             f"Day–night range {rng('moon', 'all_dimensions', 'temp_range_diurnal')} K; Earth's largest is {e_hi:.1f} K"],
            ["Six Mars zones, without composition", f"{n_mars_nc}: the eight terrain variables and the seasonal range",
             f"Temperature level {rng('mars', 'without_composition', 'temp_level')} K. Day–night range {rng('mars', 'without_composition', 'temp_range_diurnal')} K"],
            ["Six Mars zones, with composition", f"{n_mars_c}; {min(nranked('mars', 'all_dimensions'))} for Meridiani, whose FeO is above every Earth value",
             "The same two temperature variables"],
        ], [2400, 2700, 3926]) + para(
        "System 1 uses the dimension sets of step 4. Each ranked list of system 2 is calibrated in the same way:") + table(
        ["Parent set", "Ranked", "Groups", "Left out", "d-bar"], set_rows, [2300, 900, 2426, 2300, 1100]) + para(
        f"Under system 1, for an Artemis region, temperature level lies {sdr('moon','temp_level')} Earth standard deviations from "
        f"Earth's average and the day–night range {sdr('moon','temp_range_diurnal')}; the terrain variables lie 2 to 15. Temperature "
        "will carry most of every distance, and different regions will probably point at the same Earth ground. Sherozbek expects "
        "that and holds that showing it is the honest result: Antarctica may simply be the best Earth has for the Moon. Under "
        "system 2 a lunar polar result has no thermal score, and the rule is all-or-nothing at Earth's extreme: a target just inside "
        "Earth's range keeps the variable.", bold_lead="What to expect, written before any map. ") + table(
        ["Question, answered for both systems in the write-up", "What is reported"], [
            ["Does the answer depend on the target?", "The share of cells that the best 1% of Earth for Haworth and for Mons Mouton Plateau have in common"],
            ["Does the control behave?", "The Atacama patch is significant"],
            ["Which group carries the result?", "The per-group index at the best cell"],
        ], [3800, 5226]) + para(
        "The team then names one system the main result; the other is shown beside it. No rule forces the pick.") + heading(
        "2. Every target cell counts", 3) + para(
        "The score of an Earth cell is its mean distance to ALL distinct cells of the target, divided by d-bar of the variables in "
        "use. This overrides \"k = min(5, distinct target cells)\" below. Of the four claims in the table below it is nearest to (b), "
        "the typical cell, without collapsing the target to a centroid.", bold_lead="The decision. ") + para(
        "Five is a number nobody could justify: why not four, or six? \"All\" has no number to justify, and every cell of the "
        "region is represented in every score.", bold_lead="His reason. ") + para(
        "The text below argues against this setting (\"k = all cannot tell them apart\"), and the measurement agrees with the text. "
        "The preset targets are varied inside. The table gives each target's own spread, the mean distance between two of its "
        "cells divided by d-bar, where 1.0 is two random Earth cells; and what an exact copy of one target cell would score. "
        "Only target cells enter this measurement.", bold_lead="What it costs, measured. ") + table(
        ["Targets", "Own spread", "Exact copy of one cell, scored on all cells", "The same, scored on the 5 nearest"], [
            ["Nine Artemis III regions (5 to 90 cells)", sp("moon", "all_dimensions", "spread"), copy_moon, sp("moon", "all_dimensions", "copy_5_median")],
            ["Six Mars zones (about 680 cells)", sp("mars", "without_composition", "spread"), copy_mars, sp("mars", "without_composition", "copy_5_median")],
        ], [2700, 1500, 2526, 2300]) + para(
        "On real values the cells of an Artemis region differ from each other several times more than two random Earth cells do. "
        "So the index of an Artemis region will be well above 1 everywhere on Earth, and an Earth cell identical to one part of a "
        "region scores no better than many others. Sherozbek kept all cells knowing this (\"I know it's absurd, but for the sake "
        "of representation\"): the question the tool answers is which Earth place is like the region as a whole.",
        bold_lead="The decision, taken knowing this. ") + para(
        "The index is read as \"like the region as a whole\" and never as \"like some part of it\". The target's own spread is "
        "printed beside every index. Ranks and percentile bands lead the result page, not the index value. The chance test changes "
        "meaning with it: a uniform patch scores lower than a varied one whatever Earth looks like, so the spread of every random "
        "patch is recorded and shown beside p. The nearest-index layer described below is optional in version 1.",
        bold_lead="How to read the index now. ") + para(
        "Timed on the real grid sizes with stand-in rows: one map of all 3.2 million Earth cells takes 0.4 s for a 15-cell target "
        "and 13.5 s for a 680-cell zone; 1,000 chance draws take 0.2 and 6.9 minutes.", bold_lead="Cost. ") + heading(
        "3. Percentile bands and a slider", 3) + para(
        "Every scored Earth cell gets a rank: the share of reference cells with a smaller index. The map shows the best 1% and the "
        "best 5% as bands, and the website has a slider for the share. This is the slider the text below already allows. It is a "
        "statement about order, as \"No threshold — here or anywhere\" requires: no value of the index is called good. A best 1% "
        "exists for every target, even a hopeless one, so the chance result is displayed beside it.")

    # ------------------------------------------------ D3. step 7
    B["step7"] = heading("Revision 10 — one control, and results reported as they come out", 2) + para(
        "On 11 November 2026 Sherozbek reduced the controls to one: the Atacama patch. The negative control and the Apollo "
        "training sites are not run. \"The two controls\" below is overridden to that extent.", bold_lead="The decision. ") + para(
        "If every real target comes back not significant, there are two explanations: Earth has no standout match, or the test "
        "cannot see one. The Atacama patch tells them apart. It is 20 cells of Earth ground, so somewhere on Earth matches it "
        "exactly. If the test cannot find that, no p-value from it means anything, and every p-value is printed with that "
        "sentence beside it.", bold_lead="What the one control is for. ") + para(
        "The text below matches the Atacama patch \"against Earth itself\". That cannot work as a null: every Earth patch is its "
        "own best match, so every random minimum would be near zero. Instead the Atacama patch is used as if it were a target on "
        "the other body, and the null is the ordinary one: random compact patches on the Moon or Mars at the same distance from "
        "the equator. Under system 2 of step 6 it runs on the variables the preset targets rank on.", bold_lead="How it is run. ") + para(
        "The cold patch was chosen as a place Earth has no version of, because of its temperature. Under system 2 of step 6 "
        "temperature does not rank for that patch, so the reason for expecting \"not significant\" is gone there.",
        bold_lead="Why the negative control went. ") + para(
        "Random patches are drawn at the target's absolute latitude, within 2 degrees, from both hemispheres. \"Significant\" means "
        "p below 0.05, and p is always printed. The spread of every random patch is recorded beside its minimum (step 6, "
        "Revision 10).", bold_lead="Three additions to the test. ") + para(
        "The chance test is reported as it comes out. \"Not significant\" is printed as plainly as \"significant\", with no "
        "adjectives. Sherozbek: maybe the tests will show something insignificant, and that is all right. The promise below "
        "stands: no target, setting or system is changed until p drops.", bold_lead="Wording. ")

    # ------------------------------------------------ D4. step 8
    B["step8"] = heading("Revision 10 — sites are patches of the best 1%; the spacing rule below is not built in version 1", 2) + para(
        "Take the best share of reference cells by rank; 1% by default, the share the slider of step 6 shows. Cells that touch "
        "form one patch. Each patch is one entry: its best cell, its number of cells and its area. Patches are ordered by their "
        "best cell, and at most 20 are listed, with the total stated.", bold_lead="The rule (Sherozbek, 11 November 2026). ") + para(
        "The spacing rule below \"just chooses an area but it doesn't choose those which are highly similar\": a later pick can "
        "be listed because it is far from the others, not because it ranks high. A patch list contains only cells from the best "
        "1%. It has no parameter but the share the user sets, nothing has to be measured first, and the same map always gives "
        "the same list. If the best cells are all in one valley, the list has one entry, and that is the honest answer.",
        bold_lead="His reasons. ") + para(
        "The problem this step names is still solved: one valley is one entry, however many of its cells are in the band. A patch "
        "is not clustering in variable space. It is geographic adjacency, which this document already names as where regions come "
        "from. The decorrelation length, the greedy selector and the guard rail below are not built.",
        bold_lead="What stays and what goes. ") + table(
        ["Tests for this rule"], [
            ["Every cell of the best share belongs to exactly one patch; no patch holds a cell outside it"],
            ["The same map and share give the identical list; one broad basin gives one patch, 20 separate minima give 20"],
            ["Raising the share never loses a cell: patches grow or merge, none disappears"],
            ["The first entry is the best cell on Earth"],
        ], [9026])

    # ------------------------------------------------ E. step 9
    rows9 = []
    for v in ex["sites"][0]["variables"] if False else [s for s in ex["sites"] if abs(s["lat"] + 77.52) < 0.01][0]["variables"]:
        if v["name"] in ("slope", "roughness_21km", "roughness_42km", "temp_level", "temp_range_diurnal", "SiO2"):
            rows9.append([v["name"], f"{v['earth']:g} {v['units']}", f"{v['target_median']:g}", f"{v['position_gap']:+.2f}", v["verdict"],
                          "no" if any(o["variable"] == v["name"] for o in e_any) else "yes"])
    grp = {"terrain": "Terrain", "thermal": "Thermal", "composition": "Composition"}
    use_rows = [[grp[r["group"]], r["label"], r["if_agrees"], r["if_differs"]] for r in use["rows"]]
    B["step9"] = heading("Revision 10 — what a gap means on the min-max scale, and the use table", 2) + para(
        "The gap of a variable is now the Earth cell's position minus the target's position on the min-max scale of step 3: the "
        "physical gap divided by the full range of the variable on both worlds. Zero means the same physical value. The verdict "
        "thresholds are unchanged, agrees below 0.10 and differs above 0.25, and were not re-tuned. One tenth of the scale is "
        f"{pm['slope']['tenth_of_scale_in_units']:.1f}° of slope, {pm['roughness_21km']['tenth_of_scale_in_units']:.0f} m of "
        f"roughness at 21 km, {pm['temp_level']['tenth_of_scale_in_units']:.0f} K of temperature level and "
        f"{pm['SiO2']['tenth_of_scale_in_units']:.1f} wt% of silica for Earth and the Moon. The physical gap in native units is "
        "still printed beside every row. An example read from the cube, a cell of the McMurdo Dry Valleys against the Haworth "
        "region:", bold_lead="The gap. ") + table(
        ["Variable", "Earth cell", "Target median", "Gap", "Verdict", "Can Earth match it?"], rows9, [1900, 1826, 1400, 1000, 1200, 1700]) + para(
        "Every variable is shown, whichever ranking system is used. For an Antarctic site the rock class shown is GeoMAP's, and "
        "the share of the cell that is exposed rock is shown with it.") + para(
        "The lookup table below replaces the five-row table of this step. It covers every ranking variable, in the three groups, "
        "and for each it says what follows when the variable agrees and when it differs. It is written once, by hand, and lives in "
        "contract/use_table.json; the engine reads it and writes no sentence of its own. Thermal inertia is not in it, because it "
        "no longer ranks.", bold_lead="The use table (Sherozbek, 11 November 2026). ") + table(
        ["Group", "Variables", "If they agree", "If one differs"], use_rows, [1450, 1650, 3050, 2876]) + para(
        "Where the analog succeeds: the rows whose variables all agree. Where it fails: the rows with a variable that differs. "
        "Where Earth's limits are: the rows with a variable no Earth cell reaches for this target, with the gap in its own unit; "
        "under them, the fixed block on gravity, air, radiation, day length and weathering. A row that is only partial is not "
        "listed. If nothing succeeds, the site carries one general sentence and no use is named.",
        bold_lead="Each site carries three lists. ") + para(
        use["scale_warning"].replace("The sentences below", "The sentences above"), bold_lead="The limit of every sentence in the table. ")

    # ------------------------------------------------ F. Appendix E
    B["appe"] = heading("Revision 10 decisions, 10 and 11 November 2026") + table(["Step", "Decision", "Value"], [
        ["3", "Scale", "ONE shared MIN-MAX scale per variable for Earth and the target body: position = (value − lowest) / (highest − lowest). No rank, no normal score, no mixing weight. Overrides per-body ranking (Sherozbek, 11 Nov)"],
        ["2", "Thermal inertia", "No longer ranks: Earth's and Mars's layers are different quantities. Characterization only (Sherozbek, 11 Nov)"],
        ["2", "Dimension counts", f"Earth–Moon {len(em['dimensions'])}; Earth–Mars {len(ex13['dimensions'])}; Earth–Mars without composition {len(ex11['dimensions'])}"],
        ["4", "Whitening", "Within groups (block-diagonal), eigenvalue floor 0.10, as step 4 decides (Sherozbek confirmed, 11 Nov)"],
        ["6", "Ranking system", f"TWO are built: every variable ranks, or only the variables Earth can match (Artemis regions then rank on {n_moon}, Mars zones on {n_mars_nc}, or {n_mars_c} with composition). The ONE choice left for the hackathon day; both are printed for every preset target (Sherozbek, 11 Nov)"],
        ["6", "Target cells", f"ALL distinct target cells; overrides k = 5. Kept knowing that an exact copy of one target cell would score {copy_moon} for an Artemis region (Sherozbek, 11 Nov)"],
        ["6", "Percentile bands", "Rank among reference cells; bands at the best 1% and 5%; a slider on the website. No threshold on the index"],
        ["7", "Controls", "One: the Atacama patch, used as a target on the other body. No negative control, no Apollo control (Sherozbek, 11 Nov)"],
        ["7", "Significance and wording", "\"Significant\" when p is below 0.05; p always printed; no marginal band; results reported as they come out"],
        ["8", "Sites", "Patches of the best 1% of Earth, one entry per patch. The spacing rule is not built in version 1 (Sherozbek, 11 Nov)"],
        ["9", "Use table", "Every ranking variable, in three groups; each site lists where the analog succeeds, where it fails, and where Earth's limits are (Sherozbek, 11 Nov)"],
        ["10", "Weight check and presets", "REMOVED from version 1. Every group counts once. Group weights are future sensitivity work (Sherozbek, 11 Nov)"],
        ["—", "Third invariant", "\"No result from a single construction\" is relaxed to: both ranking systems for every preset target; a Mars zone with and without composition"],
        ["3", "Antarctic reference land", "South of 60°S: SCAR GeoMAP exposed rock above half the cell. 390 cells replace 3,155 (Sherozbek, 10 Nov)"],
        ["2", "Earth composition", f"Lookup checked against Gard et al. 2019: {n_ver} of {n_tested} testable classes verified, no value changed. GeoMAP supplies the rock class in Antarctica and South Georgia"],
        ["5", "Lunar targets", "The nine Artemis III regions as the polygons LROC QuickMap publishes"],
        ["5", "Mars targets", "Six NASA 2015 Exploration Zones, 100 km radius: Jezero, Gale, Meridiani, Gusev, Erebus Montes, Deuteronilus Mensae. With and without composition"],
        ["5", "Mars target without composition", "Runs on the dimensions present and says so; never refused"],
        ["11", "Output contract", "2.4: run.scale is \"minmax\"; position fields; run.ranking with the ranking system; rank_combined; patches; one control; a use block per site"],
    ], [700, 2400, 5926])

    # ------------------------------------------------ G. Appendix D
    B["appd"] = heading("Revision 10 additions") + table(["Dataset", "Feeds", "Status"], [
        ["SCAR GeoMAP v.2022-08, Cox et al. 2023, doi:10.1594/PANGAEA.951482", "Antarctic rock class and composition; Antarctic reference land", "Used"],
        ["Global whole-rock geochemical database, Gard, Hasterok & Halpin 2019, doi:10.5281/zenodo.3359791", "The check of the composition lookup; two rock classes GLiM has no row for", "Used — a check, not a map"],
        ["Artemis III candidate landing regions 2024, LROC QuickMap polygon file", "The nine lunar targets", "Used — not hosted on nasa.gov, no licence stated"],
        ["NASA Exploration Zone workshop 2015, abstracts (LPI)", "The six Mars targets; 44 proposals listed", "Used — conference abstracts, latitude type not stated"],
        ["Golombek et al. 2021, LPSC abstract 2420", "The reason Erebus Montes was chosen in the Arcadia province", "Used"],
    ], [4000, 3200, 1826])
    return B


def after_heading(doc, text):
    """end of the paragraph that holds `text` AND has a heading style."""
    i = -1
    while True:
        i = doc.find(text, i + 1)
        if i < 0:
            raise SystemExit(f"heading not found: {text}")
        a = max(doc.rfind("<w:p>", 0, i), doc.rfind("<w:p ", 0, i))
        b = doc.find("</w:p>", i) + len("</w:p>")
        if 'w:pStyle w:val="Heading' in doc[a:b]:
            return b


def after_table_following(doc, text):
    i = doc.find(text)
    if i < 0 or doc.count(text) != 1:
        raise SystemExit(f"anchor not unique: {text}")
    return doc.find("</w:tbl>", i) + len("</w:tbl>")


def main():
    t0 = time.perf_counter()
    for f in ("pooled_overlap.png", "minmax_position.png"):
        if not os.path.exists(os.path.join(FIG, f)):
            raise SystemExit(f"STOP: {f} missing -- run build/figure_pooled_scale.py --overlap-only and build/figure_minmax_scale.py first")
    img = Images()
    B = blocks(img)
    zin = zipfile.ZipFile(SRC)
    doc = zin.read("word/document.xml").decode("utf-8")
    if "Revision 10" in doc:
        raise SystemExit("the source already contains Revision 10 text")

    reps = [("Revision 9, consolidated. Supersedes the earlier draft and revisions 1–8.",
             "Revision 10, consolidated. Supersedes the earlier draft and revisions 1–9."),
            ("This is Revision 9. It extends Revision 8",
             "This is Revision 10. It extends Revision 9 with the changes of 10 and 11 November 2026, listed in the table after the "
             "Revision 9 table below. The most important is in step 3: one shared min-max scale per variable replaces ranking "
             "each body separately. Steps 6 to 9 change with it: every target cell counts, two ranking systems are built, one "
             "control is kept, sites are patches of the best 1%, and a use table covers every variable. "
             "Revision 9 extended Revision 8")]
    for a, b in reps:
        assert doc.count(a) == 1, a[:40]
        doc = doc.replace(a, b)

    inserts = [
        (after_table_following(doc, "Revision 9 — what changed on 9 November 2026"), B["revision"]),
        (after_heading(doc, "Part A — The matching dimensions"), B["parta"]),
        (after_heading(doc, "Step 3 — The percentile transform"), B["step3"]),
        (R9.pos_after_paragraph(doc, "No result is reported from a single construction."), B["invariant"]),
        (after_heading(doc, "Step 4 — Whitening"), B["step4"]),
        (after_heading(doc, "Step 10 — The weight check"), B["step10"]),
        (after_heading(doc, "Step 5 — The target"), B["step5"]),
        (after_heading(doc, "Step 6 — The dissimilarity map"), B["step6"]),
        (after_heading(doc, "Step 7 — The null test"), B["step7"]),
        (after_heading(doc, "Step 8 — Site selection"), B["step8"]),
        (after_heading(doc, "Step 9 — Characterization"), B["step9"]),
        (after_table_following(doc, "Revision 9 decisions, 9 November 2026"), B["appe"]),
        (after_table_following(doc, "Revision 9 additions"), B["appd"]),
    ]
    for p, xml in sorted(inserts, key=lambda t: -t[0]):
        doc = doc[:p] + xml + doc[p:]

    rels = zin.read("word/_rels/document.xml.rels").decode("utf-8")
    add = "".join(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{name}"/>'
                  for rid, name, _ in img.items)
    rels = rels.replace("</Relationships>", add + "</Relationships>")

    import xml.dom.minidom
    xml.dom.minidom.parseString(doc.encode("utf-8"))
    tmp = DST + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename.endswith("/"):
                continue
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = doc.encode("utf-8")
            elif item.filename.startswith("word/header"):
                # the running header still named the revision this file started from
                h = data.decode("utf-8")
                for old in ("Revision 8", "Revision 9"):
                    h = h.replace(old, "Revision 10")
                data = h.encode("utf-8")
            elif item.filename == "word/_rels/document.xml.rels":
                data = rels.encode("utf-8")
            zout.writestr(item.filename, data)
        for rid, name, data in img.items:
            zout.writestr(f"word/media/{name}", data)
    os.replace(tmp, DST)
    print(f"wrote {DST} ({os.path.getsize(DST)/2**20:.1f} MB), {img.n} new figures, {len(inserts)} inserted blocks, "
          f"{time.perf_counter()-t0:.1f} s; document.xml well-formed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
