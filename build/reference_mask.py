"""
THE EARTH REFERENCE MASK ON HEALPIX -- one builder, one definition.

    python build/reference_mask.py [--check] [--test]

WHAT THE MASK IS
    earth_reference_mask_nside1024.npy holds, per pixel, the fraction of the
    pixel that is reference land. A pixel belongs to Earth's reference
    population where fraction > 0.5. Percentiles (step 3), the covariance
    (step 4) and the site search all run over that population.

TWO RULES, ONE PER REGION -- Sherozbek's decision, 10 Nov 2026 (B31e)
    north of 60 S   fraction = share of the pixel that is land AND NOT ice
                    AND NOT water body, binned from the 1/240 degree mask
                    (ETOPO surface minus bed for ice; GLiM wb for water).
                    Unchanged from 8 Nov.
    south of 60 S   fraction = exposed rock + moraine as a share of the
                    pixel, measured by SCAR GeoMAP (Cox et al. 2023),
                    earth_geomap_rock_fraction.

WHY (VARIABLES.md B31e, measured)
    The ice-thickness rule is wrong in Antarctica in both directions. It
    admitted 3,155 pixels whose median exposed-rock share is about 8%, and it
    left out 105 pixels that are more than half rock, the Vestfold Hills
    among them. "An Antarctic analog site" must mean rock, not ice sheet.

    60 S, not 53 S: GeoMAP also maps South Georgia, but the decision taken
    was for Antarctica. South Georgia keeps the ice-thickness rule.

GATES, stated before running
    G1  the north-of-60S part reproduces the mask as it stood before this
        change EXACTLY (max difference 0.0). --check does only this, against
        a snapshot copy in cube/_work, so no path is both read and written.
    G2  south of 60 S the reference population is exactly the set of pixels
        with GeoMAP rock fraction > 0.5.
    G3  no pixel north of 60 S changes membership.
"""

import argparse
import io
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C
from phase1_dems import DEM_DIR
from phase2_terrain import HealpixAccumulator

NSIDE = 1024
HP = os.path.join(C.ROOT, "cube", "healpix")
MASK = os.path.join(HP, f"earth_reference_mask_nside{NSIDE}.npy")
SNAP = os.path.join(C.ROOT, "cube", "_work", "reference_mask_before_B31e",
                    f"earth_reference_mask_nside{NSIDE}.npy")
SRC = os.path.join(DEM_DIR, "earth_land_reference_1_240deg.npy")
ROCK = os.path.join(HP, f"earth_geomap_rock_fraction_nside{NSIDE}.npy")
MASK_PROV = os.path.join(C.ROOT, "cube", "mask_provenance.json")
LAT_RULE = -60.0


def bin_etopo_rule():
    """The 8 Nov construction, unchanged: bin the 1/240 degree boolean."""
    a = np.load(SRC, mmap_mode="r")
    H, W = a.shape
    acc = HealpixAccumulator(NSIDE, ["m"])
    lat = 90.0 - (np.arange(H) + 0.5) * (180.0 / H)
    lon = -180.0 + (np.arange(W) + 0.5) * (360.0 / W)
    cos = np.maximum(np.cos(np.radians(lat)), 1e-9)
    for r0 in range(0, H, 240):
        r1 = min(H, r0 + 240)
        idx = acc.index_for_band(lat[r0:r1], lon).ravel()
        wt = np.repeat(cos[r0:r1], W)
        acc.add_reference(idx, wt)
        acc.add("m", (np.asarray(a[r0:r1]) > 0).astype(np.float32), idx, wt)
        del idx, wt
    f, _, _ = acc.finish("m")
    return f


def bands(ref, lat):
    out = {}
    for name, m in (("global", np.ones_like(ref)), ("abs_lat_gt_60", np.abs(lat) > 60),
                    ("abs_lat_gt_80", np.abs(lat) > 80), ("abs_lat_gt_85", np.abs(lat) > 85),
                    ("lat_60S_to_90S", lat < -60.0), ("lat_85S_to_90S", lat <= -85.0)):
        out[name] = round(100.0 * float((ref & m).sum()) / float(m.sum()), 4)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="G1 only, write nothing")
    ap.add_argument("--test", action="store_true", help="all gates, write nothing")
    a = ap.parse_args()
    t0 = time.perf_counter()
    print("=" * 78)
    print("EARTH REFERENCE MASK -- ETOPO rule north of 60 S, GeoMAP rule south")
    print("=" * 78)

    base = bin_etopo_rule()
    print(f"binned the 1/240 degree mask in {(time.perf_counter()-t0)/60:.1f} min")
    snap = np.load(SNAP)
    same_nan = bool(np.array_equal(np.isfinite(snap), np.isfinite(base)))
    f = np.isfinite(snap) & np.isfinite(base)
    md = float(np.max(np.abs(snap[f] - base[f])))
    g1 = same_nan and md == 0.0
    print(f"G1 {'pass' if g1 else 'FAIL'}: the 8 Nov construction is reproduced, "
          f"NaN pattern identical {same_nan}, max |diff| {md:g}")
    if a.check or not g1:
        return 0 if g1 else 1

    lat = C.healpix_lat(NSIDE)
    south = lat < LAT_RULE
    rock = np.load(ROCK)
    frac = base.copy()
    frac[south] = rock[south]
    frac = frac.astype(np.float32)

    ref_old = np.isfinite(base) & (base > 0.5)
    ref_new = np.isfinite(frac) & (frac > 0.5)
    g2 = bool(np.array_equal(ref_new[south], (rock > 0.5)[south]))
    g3 = bool(np.array_equal(ref_new[~south], ref_old[~south]))
    print(f"G2 {'pass' if g2 else 'FAIL'}: south of 60 S the population is "
          f"GeoMAP rock fraction > 0.5")
    print(f"G3 {'pass' if g3 else 'FAIL'}: no membership change north of 60 S")
    A = 4.0 * np.pi * (C.BODY_RADIUS_M["earth"] / 1000.0) ** 2 / frac.size
    rec = dict(
        decided="Sherozbek, 10 Nov 2026; VARIABLES.md B31(e), option B",
        rule_north_of_60S="land AND NOT ice (ETOPO surface - bed) AND NOT wb (GLiM), binned from cube/dem/earth_land_reference_1_240deg.npy; unchanged",
        rule_south_of_60S="exposed rock + moraine share of the pixel, SCAR GeoMAP v.2022-08 (earth_geomap_rock_fraction)",
        reference_pixels_before=int(ref_old.sum()),
        reference_pixels_after=int(ref_new.sum()),
        south_of_60S=dict(
            before=int((ref_old & south).sum()), after=int((ref_new & south).sum()),
            kept=int((ref_old & ref_new & south).sum()),
            added=int((ref_new & ~ref_old & south).sum()),
            removed=int((ref_old & ~ref_new & south).sum()),
            reference_area_km2_before=round(float((ref_old & south).sum() * A), 0),
            reference_area_km2_after=round(float((ref_new & south).sum() * A), 0),
            exposed_rock_km2_inside_after=round(float(rock[ref_new & south].sum() * A), 0),
            exposed_rock_km2_all=round(float(rock[south].sum() * A), 0)),
        gates=dict(G1=g1, G2=g2, G3=g3),
        superseded_array="the 8 Nov mask, kept as a copy in cube/_work/reference_mask_before_B31e/ (not part of the cube)",
        written_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    print(json.dumps(rec, indent=1))
    if not (g2 and g3):
        print("A GATE FAILED -- nothing written")
        return 1
    if a.test:
        print("TEST MODE -- nothing written")
        return 0

    C.atomic_save(MASK, frac)
    fin = np.isfinite(frac)
    pos = frac[fin & (frac > 0)]
    q = np.percentile(pos, [1, 25, 50, 75, 99])
    C.manifest_write("earth_reference_mask", dict(
        file=f"cube/healpix/earth_reference_mask_nside{NSIDE}.npy",
        nside=NSIDE, order="nested", dtype="float32",
        n_pixels=int(frac.size), expected_npix=12 * NSIDE ** 2, shape_ok=True,
        built_by="build/reference_mask.py",
        built_utc=rec["written_utc"],
        phase="1b", body="earth", variable="reference_mask", role="mask",
        units="fraction of the pixel's area that is reference land (0..1)",
        source_files=["cube/dem/earth_land_reference_1_240deg.npy",
                      f"cube/healpix/earth_geomap_rock_fraction_nside{NSIDE}.npy"],
        derivation=("TWO RULES. North of 60 S: cos(lat)-weighted area average "
                    "of the 1/240 deg boolean earth_land_reference (land AND "
                    "NOT ice AND NOT water bodies), by the same "
                    "HealpixAccumulator every continuous layer uses. South of "
                    "60 S: the exposed rock + moraine share of the pixel "
                    "measured by SCAR GeoMAP (Cox et al. 2023, "
                    "doi:10.1594/PANGAEA.951482), because the ice-thickness "
                    "rule is wrong there in both directions (B31e)."),
        membership_rule=("a pixel belongs to Earth's reference population "
                         "where fraction > 0.5. This is the population the "
                         "percentile transform (step 3) and the covariance "
                         "(step 4) are computed over. Used by phase4a."),
        mask_provenance="cube/mask_provenance.json",
        matching_eligible=False,
        validation=dict(
            n_finite=int(fin.sum()),
            pixels_fraction_gt_0=int((fin & (frac > 0)).sum()),
            pixels_in_reference_population=int(ref_new.sum()),
            pct_of_sphere_in_reference=round(100.0 * float(ref_new.mean()), 4),
            pct_of_sphere_by_fraction_sum=round(
                100.0 * float(frac[fin].sum()) / frac.size, 4),
            coverage_gate=bands(ref_new, lat),
            fraction_stats=dict(min=float(pos.min()), p1=float(q[0]),
                                p25=float(q[1]), p50=float(q[2]),
                                p75=float(q[3]), p99=float(q[4]),
                                max=float(pos.max()), mean=float(pos.mean())),
            b31e=rec)))
    mp = json.load(io.open(MASK_PROV, encoding="utf-8"))
    mp["b31e_antarctic_rule"] = rec
    tmp = MASK_PROV + ".part"
    io.open(tmp, "w", encoding="utf-8").write(json.dumps(mp, indent=1, ensure_ascii=False))
    os.replace(tmp, MASK_PROV)
    print(f"wrote the mask, its manifest entry and mask_provenance.json "
          f"({(time.perf_counter()-t0)/60:.1f} min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
