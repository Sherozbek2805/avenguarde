"""
SPEC REVISION 11 -- the method AS BUILT, written clean. 15 November 2026.

    python build/spec_rev11.py

Reads   docs/analog_finder_method_spec_rev10.docx   (styles, page setup and header only; never modified)
        cube/phase4/*.json, runs/*_summary.json, runs/*_system_comparison.json, runs/known_regions.json
Writes  docs/analog_finder_method_spec_rev11.docx

Revisions 8 to 10 grew by INSERTED blocks, so a reader had to meet every earlier decision
before the one that stands. Revision 11 changes NO method. It states, once and in order,
the method the engine runs, and adds what did not exist on 11 November: the engine, the
results of 14 November, the choice of the main ranking system, and the known-region check.
The history stays where it was: revision 10 and VARIABLES.md.

Every number in the tables is read from the project's own files when this script runs.

Written with AI assistance (Claude, Anthropic) under the team's direction; see AI_USE.md.
"""
import io
import json
import os
import re
import sys
import time
import zipfile
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C
import spec_rev9 as R9
from spec_rev9 import para, heading, table

ROOT = C.ROOT
SRC = os.path.join(ROOT, "docs", "analog_finder_method_spec_rev10.docx")
DST = os.path.join(ROOT, "docs", "analog_finder_method_spec_rev11.docx")
W = R9.TEXT_W_TWIPS


def jl(*parts):
    return json.load(io.open(os.path.join(ROOT, *parts), encoding="utf-8"))


def title(text, size, after, color="1f3864", bold=True):
    b = '<w:b w:val="1"/><w:bCs w:val="1"/>' if bold else ""
    return (f'<w:p><w:pPr><w:spacing w:after="{after}" w:lineRule="auto"/><w:jc w:val="center"/></w:pPr><w:r><w:rPr>{b}'
            f'<w:color w:val="{color}"/><w:sz w:val="{size}"/><w:szCs w:val="{size}"/></w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>')


def bullets(items):
    return "".join(para(t, bold_lead="•  ", after=60) for t in items) + para("", after=60)


def fmt_ll(s):
    la, lo = s["lat"], s["lon"]
    return f"{abs(la):.2f}°{'N' if la >= 0 else 'S'}, {abs(lo):.2f}°{'E' if lo >= 0 else 'W'}"


def main():
    t0 = time.perf_counter()
    p4c = jl("cube", "phase4", "phase4c_summary.json")
    rs = jl("cube", "phase4", "ranking_sets.json")
    mm = jl("cube", "phase4", "minmax_scale_summary.json")
    moon, mars = jl("runs", "moon_summary.json"), jl("runs", "mars_summary.json")
    cmp_moon, cmp_mars = jl("runs", "moon_system_comparison.json"), jl("runs", "mars_system_comparison.json")
    kr = jl("runs", "known_regions.json")
    n_ref = mm["earth_cells"]
    img = R9.Images()

    def figure(path, caption):
        return img.add(path, caption).replace("Figure R9-", "Figure ")

    main_rows = lambda rows: [r for r in rows if r["system"] == "all_variables"]
    any_sig = any(r["significant"] for r in moon + mars)
    ctl_all = sorted({round(r["control_p"], 6) for r in main_rows(moon + mars)})
    ctl_reach = sorted({round(r["control_p"], 3) for r in moon + mars if r["system"] == "earth_reachable_only"})

    B = []
    # ------------------------------------------------------------------ title page
    B += [para("", after=1800),
          title("Terrestrial Analog Finder", 56, 180),
          title("Method specification", 36, 180, bold=False),
          title("Revision 11: the method as built", 28, 600, color="404040", bold=False),
          title("NASA Space Apps Challenge 2026 · 15 November 2026", 22, 240, color="404040", bold=False),
          title("This revision changes no method. It states the method the engine runs, in order, and reports the results of 14 November 2026. "
                "The record of how each decision was reached is revision 10 and VARIABLES.md.", 20, 240, color="404040", bold=False),
          '<w:p><w:r><w:br w:type="page"/></w:r></w:p>']

    # ------------------------------------------------------------------ 1
    B += [heading("1. What the tool does", 1),
          para("The Terrestrial Analog Finder takes a place on the Moon or Mars and ranks every cell of Earth's ice-free land by how alike it is to that place. "
               "It then checks whether the best match is better than chance, and describes each listed site: what agrees, what differs, and what no place on Earth reaches."),
          para("It compares three groups of measures: terrain, temperature and rock composition. It does not compare gravity, air pressure, radiation or day length. "
               "No place on Earth copies those, so every site it returns is a partial analog."),
          heading("What changed since revision 10", 2),
          table(["Topic", "Revision 10 (11 November)", "Revision 11 (15 November)"],
                [["Engine", "Specified; not written", "Written and run: engine/, with a web API"],
                 ["Results", "None", "42 result sets for 15 NASA targets (section 12)"],
                 ["Website", "Not present", "Built and live; code in website/ (VARIABLES.md B40)"],
                 ["Main ranking system", "Two systems built; the choice left for the day", "all_variables is the main result; the other is the second view (VARIABLES.md B39)"],
                 ["Known-region check", "Not present", "Added as a plausibility check (section 13)"],
                 ["Form of this document", "Inserted blocks on revisions 8 and 9", "Rewritten in order; no method changed"]],
                [1800, 3400, 3826])]

    # ------------------------------------------------------------------ 2 data
    B += [heading("2. Data", 1),
          para("All input data is public. Each derived layer names its source in cube/cube_manifest.json and SOURCES.md."),
          table(["World", "Dataset", "Used for"],
                [["Moon", "LRO LOLA global elevation model, LOLA_Global_LDEM_118m_Mar2014 (118 m)", "The eight terrain measures"],
                 ["Moon", "LRO Diviner global cumulative products, LRO-L-DLRE-5-GCP-V1.0 (maximum and minimum temperature)", "Temperature level and day–night swing"],
                 ["Moon", "Lunar Prospector GRS element abundances, 2° (Prettyman et al. 2006)", "SiO2 and FeO"],
                 ["Mars", "MOLA – HRSC blended elevation model, 200 m (MGS MOLA with ESA Mars Express HRSC; USGS Astrogeology)", "The eight terrain measures"],
                 ["Mars", "MGS TES thermal inertia (Putzig & Mellon 2007) and albedo (Christensen et al. 2001); dust climatology (Montabone et al. 2015); KRC model (Kieffer 2013)", "Temperature level, day–night swing and seasonal swing. These are MODELLED, not measured"],
                 ["Mars", "MGS TES mineral maps (Bandfield 2002)", "SiO2 and FeO, where the maps have data"],
                 ["Earth", "ETOPO 2022, 15 arc-second (NOAA NCEI)", "The eight terrain measures"],
                 ["Earth", "MODIS land surface temperature, MOD11C3 and MYD11C3 (Terra and Aqua)", "Temperature level, day–night swing and seasonal swing"],
                 ["Earth", "GLiM rock map (Hartmann & Moosdorf 2012); SCAR GeoMAP (Cox et al. 2023); values checked against Gard et al. 2019", "SiO2 and FeO, as a value per rock class"],
                 ["Earth", "Köppen–Geiger climate classes (Beck et al. 2023); USGS terrestrial analog sites catalogue (doi:10.5066/P9J72921)", "Describing sites only; never ranked"],
                 ["Earth", "WorldClim 2.1; MODIS MCD43A3 albedo", "The land mask; a stored layer that does not rank"],
                 ["Targets", "NASA Artemis III candidate landing regions (update of 28 October 2024), polygons as published by LROC QuickMap; NASA Exploration Zone workshop, 2015", "The fifteen preset targets"]],
                [1100, 4700, 3226])]

    # ------------------------------------------------------------------ 3 grid
    B += [heading("3. The grid", 1),
          para("Each world is cut into equal-area cells with the HEALPix grid, in NESTED order. Equal area means a cell near a pole covers the same ground as a cell at the equator."),
          table(["World", "Nside", "Cells", "Cell side"],
                [["Earth", "1024", "12,582,912", "6.37 km"], ["Moon", "256", "786,432", "6.95 km"], ["Mars", "512", "3,145,728", "6.79 km"]],
                [2256, 2256, 2257, 2257]),
          para(f"Earth's reference population is every cell of ice-free land that carries all the variables: {n_ref:,} cells. Every rank in this document is a rank within that population.")]

    # ------------------------------------------------------------------ 4 variables
    B += [heading("4. The variables", 1),
          para("Twelve variables are compared between Earth and the Moon, thirteen between Earth and Mars. Where the Mars composition maps have no data, eleven are used."),
          table(["Variable", "Group", "What it measures", "Unit"],
                [["slope", "Terrain", "Steepness of the ground over a 7 km baseline", "degrees"],
                 ["roughness_5.25km, _10.5km, _21km, _42km", "Terrain", "How far the surface departs from a smooth plane, in windows of four sizes", "m"],
                 ["tpi_21km, tpi_7km", "Terrain", "Height of a place relative to its surroundings: negative in a basin, positive on a ridge", "m"],
                 ["svf_30km", "Terrain", "Share of the sky not hidden by terrain within 30 km", "0 to 1"],
                 ["temp_level", "Temperature", "The level about which surface temperature swings", "K"],
                 ["temp_range_diurnal", "Temperature", "Day–night swing of surface temperature", "K"],
                 ["temp_range_seasonal", "Temperature", "Seasonal swing of surface temperature. Earth–Mars only", "K"],
                 ["SiO2", "Composition", "Silica content", "wt%"],
                 ["FeO", "Composition", "Total iron, reported as FeO", "wt%"]],
                [2500, 1300, 4126, 1100]),
          para("Thermal inertia is stored but not ranked: Earth's layer and Mars's layer are different quantities and cannot share one scale.")]

    # ------------------------------------------------------------------ 5 scale
    B += [heading("5. Step 1: one shared scale per variable", 1),
          para("Each variable is put on one scale shared by Earth and the other world:"),
          para("position = (x − lo) / (hi − lo)", size=24, after=160),
          para("lo and hi are the smallest and the largest value found on Earth's reference cells or on the other world. A position of 0.30 means the same physical value on both worlds. "
               "Earth–Moon and Earth–Mars each have their own scale."),
          figure(os.path.join(ROOT, "docs", "figures", "atlas", "minmax_position.png"),
                 "Where Earth and the other world sit on the shared scale of each variable.")]

    # ------------------------------------------------------------------ 6 whitening
    sets_rows = [[k, str(len(v["dimensions"])), f"{v['d_bar']:.4f}", str(v["eigenvalues_floored"])] for k, v in p4c.items()]
    sets_rows += [[k, str(v["n_dims"]), f"{v['d_bar']:.4f}", str(v["eigenvalues_floored"])] for k, v in sorted(rs["sets"].items())]
    B += [heading("6. Step 2: removing double counting", 1),
          para("Several variables tell nearly the same story: the four roughness scales, for example. Left alone they would count one fact four times. "
               "Within each group (terrain, temperature, composition) the positions are standardised by Earth's mean and standard deviation, then rotated and rescaled by the inverse square root "
               "of that group's correlation matrix on Earth. Eigenvalues are floored at 0.10 so that a near-duplicate direction is not blown up. Correlation between groups is left alone. "
               "This step is called group-wise whitening."),
          para("The typical distance between two Earth cells in this space, d_bar, is the unit of every score. It is the mean pairwise distance within a random sample of Earth's reference cells."),
          table(["Variable set", "Variables", "d_bar", "Eigenvalues floored"], sets_rows, [5200, 1200, 1300, 1326]),
          para("The first three rows are the full sets. The last four leave out the variables Earth cannot reach (section 8).", size=19, italic=True)]

    # ------------------------------------------------------------------ 7 targets
    B += [heading("7. Step 3: the target", 1),
          para("Fifteen preset targets are taken from NASA's own lists: nine Artemis III candidate landing regions near the lunar south pole and six Exploration Zones on Mars, each a disc of 100 km radius. "
               "A cell belongs to a target when its centre lies inside the shape."),
          para("The engine also accepts a circle, a rectangle or a list of cells drawn by the user. In tests of 15 November a lunar circle of 25 km radius (41 cells) ran in 40 s, "
               "50 km (164 cells) in about 2 minutes and 100 km (649 cells) in about 10 minutes. On Mars a zone of 680 cells takes about 10 minutes.")]

    # ------------------------------------------------------------------ 8 score
    B += [heading("8. Step 4: the score, the rank and the two ranking systems", 1),
          para("The score of an Earth cell is its mean distance to ALL cells of the target, divided by d_bar. It is called the dissimilarity index, DI. "
               "A DI of 1 means the cell is as far from the target as two typical Earth cells are from each other. Smaller is more alike."),
          para("The rank of a cell is the share of Earth's reference cells with a smaller DI. Maps show bands: the best 1% and the best 5%."),
          para("Two ranking systems are always run:"),
          bullets(["all_variables: every variable of the set counts, also those where the target lies outside Earth's whole range. THIS IS THE MAIN RESULT (decided 14 November 2026).",
                   "earth_reachable_only: a variable is left out when the median of the target's cells lies outside the whole range of Earth's reference population. It is reported as one of Earth's limits. This is the second view."]),
          para("Both views report the variables Earth cannot reach, in physical units.")]

    # ------------------------------------------------------------------ 9 chance
    B += [heading("9. Step 5: the check against chance, and the control", 1),
          para("A best match always exists. The question is whether it is unusually good. The engine draws 1,000 random compact patches on the same world, each with as many cells as the target "
               "and within 2° of the target's latitude, in either hemisphere. For each patch it finds the best score on a fixed sample of 100,000 Earth cells (seed 20261114). "
               "The p-value is (1 + number of random patches matched at least as well as the target) / (1 + 1,000). A target passes when p is below 0.05. This is a Monte Carlo test."),
          para("One control checks the test itself. A patch of the Atacama Desert near Yungay (20 Earth cells) is given to the engine as if it were a target on the other world. "
               "Earth must match it far better than chance. There is no negative control.")]

    # ------------------------------------------------------------------ 10 sites, description
    B += [heading("10. Step 6: sites and their description", 1),
          para("Cells of the best 1% that touch (eight neighbours) form one patch. A patch is one site. Up to 20 sites are listed, and the total number of patches is reported."),
          para("For each site the output gives, per variable, Earth's position, the target's position and the gap between them. A gap below 0.10 is reported as 'agrees', above 0.25 as 'differs'. "
               "A fixed table (contract/use_table.json) turns these into plain sentences: what the site can stand in for, what it cannot, and what lies beyond Earth. "
               "The output also names the Köppen climate class, the rock class, and the nearest site of a catalogue of known analogs within 100 km.")]

    # ------------------------------------------------------------------ 11 outputs
    B += [heading("11. Outputs", 1),
          para("Each run writes one output.json (contract version 2.4; schema in contract/output_schema.json), maps as PNG in three views, and the values behind them. "
               "A second schema (contract/point_schema.json) covers the answer for any single cell of Earth. "
               "engine/api.py serves finished runs, starts new ones and answers point queries over HTTP. The website in website/ reads these files and is live at avenguarde.eengineer.net.")]

    # ------------------------------------------------------------------ 12 results
    def rows_for(rows):
        out = []
        for r in sorted(main_rows(rows), key=lambda r: (r["target"], r["construction"])):
            name = r["target"] + ("" if r["construction"] in ("all_dimensions",) and rows is moon else (" (with composition)" if r["construction"] == "all_dimensions" else ""))
            out.append([name, str(r["cells"]), str(r["variables"]), fmt_ll(r["best_site"]), f"{r['p']:.3f}", "yes" if r["significant"] else "no"])
        return out

    def shared(c, system):
        lo, md, hi = c[system]["q1_shared_best1pct_all_pairs_min_median_max"]
        return f"{100 * md:.0f}% (from {100 * lo:.0f}% to {100 * hi:.0f}%)"

    B += [heading("12. Results of 14 November 2026", 1),
          para(f"The engine was run for all fifteen targets under both systems: 18 lunar and 24 martian result sets. The Mars zones are run with and without the composition variables. "
               f"The tables give the main system, all_variables."),
          heading("Moon: nine Artemis III regions", 2),
          table(["Target", "Cells", "Variables", "Best cell on Earth", "p", "Passes"], rows_for(moon), [2900, 800, 1100, 2400, 900, 926]),
          heading("Mars: six Exploration Zones", 2),
          table(["Target", "Cells", "Variables", "Best cell on Earth", "p", "Passes"], rows_for(mars), [2900, 800, 1100, 2400, 900, 926]),
          heading("What the results say", 2),
          bullets([("None of the fifteen NASA targets passes the check against chance under either system. Two test areas drawn by hand on the Moon, at Tycho crater and near Copernicus, did pass under all_variables (p = 0.001); they have not been examined (VARIABLES.md B39g, B40c)." if not any_sig else "At least one target passes the check against chance; see the tables."),
                   f"The control passes under all_variables (p = {', '.join(f'{p:.4g}' for p in ctl_all)}) and fails under earth_reachable_only (p = {', '.join(f'{p:.3g}' for p in ctl_reach)}). "
                   "Under all_variables it passes partly because random patches of the Moon or Mars lie far from Earth in temperature.",
                   f"Under all_variables the targets share much of their best ground. The share of one target's best 1% that is also in another's: Moon, median {shared(cmp_moon, 'all_variables')}; "
                   f"Mars, median {shared(cmp_mars, 'all_variables')}. Under earth_reachable_only: Moon {shared(cmp_moon, 'earth_reachable_only')}; Mars {shared(cmp_mars, 'earth_reachable_only')}.",
                   "Temperature carries much of the score under all_variables. The best ground is high, cold and dry: the Altiplano and Atacama, the Tibetan Plateau, the summit of Mauna Loa."]),
          figure(os.path.join(ROOT, "docs", "figures", "tested_areas.png"), "Every target the engine was run on, and the best cell on Earth for each run.")]

    # ------------------------------------------------------------------ 13 known regions
    def kr_rows():
        out = []
        for k in kr["regions"]:
            a, b = kr["bodies"]["moon"]["regions"][k], kr["bodies"]["mars"]["regions"][k]
            out.append([k, f"{a['best1_percent_median']:.0f}%", f"{a['best5_percent_median']:.0f}%", f"{b['best1_percent_median']:.0f}%", f"{b['best5_percent_median']:.0f}%"])
        return out

    B += [heading("13. The known-region check", 1),
          para("The engine is never given a list of analog sites. As a check of plausibility, build/known_regions.py asks how much of five well-known analog regions falls inside Earth's best 1% and best 5%. "
               "By chance the answers would be 1% and 5%. The numbers are medians over the main-system runs of each world."),
          table(["Region", "Moon: in best 1%", "Moon: in best 5%", "Mars: in best 1%", "Mars: in best 5%"], kr_rows(), [3026, 1500, 1500, 1500, 1500]),
          para("The ranking agrees with expert choice in several places and not in Iceland. This is a check, not a validation: the regions are rough boxes drawn by hand, "
               "several of them are high, cold, dry ground, and temperature carries much of the score. Iceland is used for geology at the scale of an outcrop, which a 6 km cell does not describe.")]

    # ------------------------------------------------------------------ 14 limits
    B += [heading("14. Limits", 1),
          bullets(["The closest ground on Earth is not close. None of the fifteen NASA targets passes the check against chance, mainly because of temperature: the Artemis regions are about 50 to 105 K colder than the coldest ice-free ground on Earth.",
                   "One cell is 6 to 7 km across. Nothing here describes boulders, soil or single outcrops.",
                   "Mars temperatures are modelled, not measured.",
                   "Earth's rock chemistry is a value per rock class, not a measurement at each cell.",
                   "The score uses every cell of the target. A large or varied target is therefore far from every single place, and the chance statistic follows the spread of the target.",
                   "The known-region check uses hand-drawn boxes.",
                   "Gravity, air pressure, radiation and day length are not compared."])]

    # ------------------------------------------------------------------ 15 reproduce
    B += [heading("15. Reproducing the results", 1),
          para("The repository holds the cube layers, the calibration, the engine and the result files. README.md gives the commands. Three calibration files are too large for the repository; "
               "build/phase4b_minmax_scale.py rebuilds them. All random draws use fixed seeds (20261108 for d_bar, 20261114 for the chance test)."),
          para("Automated checks as recorded on 14 November 2026: engine/tests.py 46 of 47 (the one difference is known: a group distance estimated on two different subsamples differs by 0.9%), "
               "engine/tests_custom.py 14 of 14, engine/tests_mars_custom.py 5 of 5, engine/test_api.py 15 of 15. build/cube_validate.py passes.")]

    # ------------------------------------------------------------------ 16 AI
    B += [heading("16. Use of AI", 1),
          para("An AI assistant, Claude (Anthropic), was used throughout. The full statement is AI_USE.md in the repository. In short:"),
          bullets(["Code: the build scripts, the engine, the web API and the tests were written with the assistant and run by the team.",
                   "Documents: this specification, the README, the test specification and the decision log were drafted with the assistant and reviewed by the team.",
                   "Decisions: every method decision was made by the team. The assistant proposed options with measurements and a recommendation; the team chose, in several cases against the recommendation. Each decision is dated in VARIABLES.md.",
                   "Website: its code and text were written with the assistant. Three decorative pictures on it (the opening picture and two globe pictures) were made with Google Flow, an AI tool, and are marked as AI-generated.",
                   "Data and figures: every number, map and chart comes from the public datasets through the code. No data, map, chart, audio or video is AI-generated."])]

    # ------------------------------------------------------------------ 17 references
    B += [heading("17. References", 1),
          bullets(["Beck, H. E., et al. (2023). High-resolution (1 km) Köppen-Geiger maps for 1901–2099. Scientific Data 10, 724.",
                   "Fergason, R. L., Hare, T. M., Laura, J. (2018). HRSC and MOLA blended digital elevation model at 200 m, v2. USGS Astrogeology.",
                   "Bandfield, J. L. (2002). Global mineral distributions on Mars. Journal of Geophysical Research 107(E6).",
                   "Christensen, P. R., et al. (2001). Mars Global Surveyor Thermal Emission Spectrometer experiment. Journal of Geophysical Research 106(E10).",
                   "Cox, S. C., et al. (2023). A continent-wide detailed geological map dataset of Antarctica (GeoMAP). Scientific Data 10.",
                   "Gard, M., Hasterok, D., Halpin, J. (2019). Global whole-rock geochemical database compilation. Earth System Science Data 11, 1553–1566.",
                   "Górski, K. M., et al. (2005). HEALPix. The Astrophysical Journal 622, 759–771.",
                   "Hartmann, J., Moosdorf, N. (2012). The new global lithological map database GLiM. Geochemistry, Geophysics, Geosystems 13.",
                   "Kieffer, H. H. (2013). Thermal model for analysis of Mars infrared mapping. Journal of Geophysical Research: Planets 118, 451–470.",
                   "Meyer, H., Pebesma, E. (2021). Predicting into unknown space? Methods in Ecology and Evolution 12, 1620–1633.",
                   "Montabone, L., et al. (2015). Eight-year climatology of dust optical depth on Mars. Icarus 251, 65–95.",
                   "Preston, L. J., Dartnell, L. R. (2014). Planetary habitability: lessons learned from terrestrial analogues. International Journal of Astrobiology 13(1), 81–98.",
                   "Prettyman, T. H., et al. (2006). Elemental composition of the lunar surface. Journal of Geophysical Research 111(E12).",
                   "Putzig, N. E., Mellon, M. T. (2007). Apparent thermal inertia and the surface heterogeneity of Mars. Icarus 191, 68–94."])]

    body = "".join(B)
    zin = zipfile.ZipFile(SRC)
    doc = zin.read("word/document.xml").decode("utf-8")
    i, j = doc.find("<w:body>") + len("<w:body>"), doc.rfind("<w:sectPr")
    assert i > 8 and j > i
    doc = doc[:i] + body + doc[j:]
    import xml.dom.minidom
    xml.dom.minidom.parseString(doc.encode("utf-8"))

    rels = zin.read("word/_rels/document.xml.rels").decode("utf-8")
    rels = re.sub(r'<Relationship [^>]*relationships/image"[^>]*/>', "", rels)
    rels = rels.replace("</Relationships>", "".join(
        f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{name}"/>' for rid, name, _ in img.items) + "</Relationships>")

    tmp = DST + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename.endswith("/") or item.filename.startswith("word/media/"):
                continue
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = doc.encode("utf-8")
            elif item.filename.startswith("word/header"):
                data = data.decode("utf-8").replace("Revision 10", "Revision 11").encode("utf-8")
            elif item.filename == "word/_rels/document.xml.rels":
                data = rels.encode("utf-8")
            zout.writestr(item.filename, data)
        for rid, name, data in img.items:
            zout.writestr(f"word/media/{name}", data)
    os.replace(tmp, DST)
    print(f"wrote {DST} ({os.path.getsize(DST) / 2**20:.1f} MB), {img.n} figures, {time.perf_counter() - t0:.1f} s; document.xml well-formed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
