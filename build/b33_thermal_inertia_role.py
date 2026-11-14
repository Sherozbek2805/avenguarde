"""
B33 -- thermal inertia stops ranking. Manifest flags only; no array changes.

    python build/b33_thermal_inertia_role.py

Sherozbek, 11 Nov 2026: one combined scale per variable is the only result.
Earth's layer is APPARENT thermal inertia, (1 - albedo) / diurnal range, in
K^-1. Mars's is TES thermal inertia in tiu. They are different quantities and
cannot share one pooled scale (gate G1 of phase4b_pooled_scale.py refuses
them). Asked directly, he chose to drop it from ranking rather than keep one
variable on per-body ranks.

Both layers stay in the cube as CHARACTERIZATION: shown for a site, never
used for a distance. This reverses "keep thermal inertia ranking" (B29), for
a reason that did not exist then.
"""

import io
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

NOTE = ("NOT A RANKING DIMENSION since 11 Nov 2026 (VARIABLES.md B33). Matching "
        "uses one pooled scale per variable; Earth apparent thermal inertia "
        "(K^-1) and Mars TES thermal inertia (tiu) are different quantities "
        "and cannot share one. Kept as a characterization layer.")


def main():
    man = json.load(io.open(C.MANIFEST, encoding="utf-8"))["layers"]
    for key in ("earth_thermal_inertia", "mars_thermal_inertia"):
        e = dict(man[key])
        e["matching_eligible"] = False
        e["role"] = "characterization: thermal inertia, shown per site, never ranked (B33)"
        e["b33_note"] = NOTE
        C.manifest_write(key, e)
        print("updated", key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
