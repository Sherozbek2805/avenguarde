"""Generate CUBE_STATE.md -- one page saying what the cube IS, right now.

    python build/cube_state.py

VARIABLES.md is a 2,365-line append-only decision LOG. It records why every
choice was made and must stay that way. It is the wrong thing to read when
the question is "what is built". This generates the answer to that question
from the manifest, so it cannot drift out of date by hand.
"""
import io
import json
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

OUT = os.path.join(C.ROOT, "CUBE_STATE.md")
PH = {"0-smoke": "0 smoke", "1": "1 DEMs", "1b": "1b ice",
      "2": "2 terrain", "2c": "2c sky view factor", "3": "3 thermal",
      "3b": "3b composition", "3c": "3c characterization",
      "3d": "3d Mars thermal inertia", "3e": "3e Earth apparent TI",
      "3f": "3f Mars temperature, modelled"}


def main():
    man = json.load(io.open(os.path.join(C.ROOT, "cube", "cube_manifest.json"),
                            encoding="utf-8"))["layers"]
    by = defaultdict(lambda: {"ok": [], "hold": [], "inel": [], "diag": [],
                              "aux": []})
    phases = defaultdict(int)
    for k, e in man.items():
        p = str(e.get("phase"))
        phases[p] += 1
        b = e.get("body")
        if b is None or p not in ("1b", "2", "2c", "3", "3b", "3c", "3d", "3e", "3f"):
            continue
        v = e.get("validation", {})
        n = k.replace(b + "_", "", 1)
        role = e.get("role")
        if role is not None:
            # masks, class layers, diagnostics and characterization layers
            # never rank; they are listed, not counted
            by[b]["aux"].append((n, role))
        elif p == "1b":
            continue
        elif "HOLD" in str(v.get("status", "")):
            by[b]["hold"].append(n)
        elif v.get("matching_eligible") is False or e.get("matching_eligible") is False:
            by[b]["inel"].append(n)
        elif n.endswith("scaling_exponent_r2"):
            by[b]["diag"].append(n)
        else:
            by[b]["ok"].append(n)
    e, mo, ma = (set(by[x]["ok"]) for x in ("earth", "moon", "mars"))
    em, emx = sorted(e & mo), sorted(e & ma)

    L = []
    w = L.append
    w("# CUBE STATE")
    w("")
    w(f"*Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} by "
      f"`build/cube_state.py` from `cube/cube_manifest.json`. "
      f"Do not edit by hand -- re-run it.*")
    w("")
    w("**VARIABLES.md is the decision LOG and explains WHY. This file says "
      "WHAT, and only what is true now.**")
    w("")
    w("## Matchable dimensions")
    w("")
    w("| pairing | count | dimensions |")
    w("|---|---|---|")
    w(f"| **Earth-Moon** | **{len(em)}** | {', '.join(em)} |")
    w(f"| **Earth-Mars** | **{len(emx)}** | {', '.join(emx)} |")
    w("")
    w("These are the sets the engine ranks with. Correlated variables (the four roughness scales, for example) are not dropped: "
      "double counting is removed by group-wise whitening (VARIABLES.md B34).")
    w("")
    w("## Per body")
    w("")
    w("| body | Nside | pixel | matchable | held back | ineligible |")
    w("|---|---|---|---|---|---|")
    px = {"earth": 6.37, "moon": 6.95, "mars": 6.79}
    for b in ("earth", "moon", "mars"):
        d = by[b]
        w(f"| {b} | {C.NSIDE[b]} | {px[b]} km | **{len(d['ok'])}** | "
          f"{', '.join(d['hold']) or '-'} | {', '.join(d['inel']) or '-'} |")
    w("")
    w("## Excluded, and why")
    w("")
    w("| what | why |")
    w("|---|---|")
    w("| `roughness_scaling_exponent` (all 3 bodies) | **HOLD.** Signal-to-"
      "noise 2.12x against its own estimator noise; 21.8% of pixels exceed "
      "H=1, detecting discrete features rather than fractal texture. It is "
      "NOT redundant with ruggedness (measured -0.157) -- the B8 prediction "
      "was wrong. Built and stored. VARIABLES.md B12, B15. |")
    w("| Mars thermal (3 layers) | **Built, MODELLED.** Three layers from a thermal model driven by TES thermal inertia and albedo "
      "(VARIABLES.md B28). The coarse climate grid first considered (B17a) is not used. |")
    w("| Mars composition | **Built where the maps have data.** `mars_SiO2` and `mars_FeO` "
      "from the TES mineral maps (VARIABLES.md B27c). |")
    w("| `temp_range_seasonal` on the Moon | The Moon has no meaningful "
      "seasonal cycle (axial tilt 1.54 deg). Correctly absent. |")
    w("| Thermal inertia | **Stored, never ranked.** Earth's layer and Mars's layer are "
      "different quantities and cannot share one scale (VARIABLES.md B27, B38). |")
    w("")
    w("## Health warnings that must travel with the data")
    w("")
    w("1. **Never test `support` against zero to decide usability.** "
      "`support == 0.0` means COPIED_FROM_COARSER on some layers and "
      "NO_VALID_SOURCE on others. Read `provenance_file` against "
      "`cube/provenance_encoding.json`. VARIABLES.md B21/Task 2.")
    w("2. **Composition is a WEAK dimension at both ends.** Moon: ~3.4 "
      "effective levels for SiO2 at the targets (nominal 24), acting as a "
      "near-fixed offset toward mafic terrain. Earth: GLiM's 40% exact / "
      "64% similar ground-truth ceiling.")
    w("3. **Earth's `temp_range_diurnal` is max minus min over FOUR local "
      "times** (Terra ~10:30/22:30 + Aqua ~13:30/01:30) -- the same quantity "
      "the Moon (96 local times) and Mars (12) carry. Four fixed overpass "
      "times are still not the true daily extremes, so Earth's value is a "
      "LOWER BOUND, loosest at high latitude. Rebuilt 9 Nov 2026; the "
      "earlier two-sample Terra day-minus-night could go negative and is "
      "gone.")
    w("4. **Earth thermal is calendar 2025 only, 12 months, Terra AND "
      "Aqua** -- one year, not climatology, so a single anomalous season is "
      "not averaged out. Chosen so the four local times share one time span.")
    w("5. **Aggregation is the area-weighted MEAN, not the median** the "
      "spec originally specified. Deliberate; VARIABLES.md B13.")
    w("")
    w("## Never ranked: masks, filters, characterization, diagnostics")
    w("")
    w("These describe, select or qualify. None may enter a dimension set.")
    w("")
    w("| body | layer | role |")
    w("|---|---|---|")
    for b in ("earth", "moon", "mars"):
        for n, role in sorted(by[b]["aux"]):
            w(f"| {b} | `{n}` | {role} |")
    w("")
    vp = os.path.join(C.ROOT, "cube", "cube_validation.json")
    if os.path.exists(vp):
        vj = json.load(io.open(vp, encoding="utf-8"))
        w("## Validation")
        w("")
        w(f"`build/cube_validate.py` last ran {vj.get('run_utc')}: "
          f"**{vj.get('verdict')}** -- {vj.get('layer_failures')} layer "
          f"failures, {len(vj.get('orphans', []))} orphan files, "
          f"{len(vj.get('encoding_issues', []))} encoding issues, "
          f"{len(vj.get('pairing_failures', []))} pairing mismatches. "
          f"Details in `cube/cube_validation.json`.")
        w("")
    w("## Gates every layer carries")
    w("")
    w("| gate | question |")
    w("|---|---|")
    w("| range | are the values plausible? (stated BEFORE each run) |")
    w("| coverage | did the pixel get anything? |")
    w("| support | how much of the pixel contributed? |")
    w("| distinct_levels / largest_tie_fraction | categorical and copied "
      "layers only -- the other three are blind to copied values |")
    w("")
    w("## Files")
    w("")
    w("```")
    w("cube/cube_manifest.json        every layer, every decision")
    w("cube/provenance_encoding.json  the 4 provenance codes, ONE named place")
    w("cube/dead_files.json           files that look like data and are not")
    w("cube/cube_validation.json      build/cube_validate.py report: manifest vs disk")
    w("cube/koppen_legend.json        Koppen class code -> symbol -> description")
    w("cube/healpix/                  the cube")
    w("cube/dem/                      working-resolution DEMs and masks")
    w("SOURCES.md                     context sources and what they are NOT for")
    w("VARIABLES.md                   the decision log (B1-B39)")
    w("```")
    w("")
    w(f"Manifest entries by phase: " +
      ", ".join(f"{PH.get(k, k)} = {v}" for k, v in sorted(phases.items())))
    io.open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
    print(f"wrote {OUT} ({os.path.getsize(OUT):,} bytes)")
    print(f"  Earth-Moon {len(em)} matchable, Earth-Mars {len(emx)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
