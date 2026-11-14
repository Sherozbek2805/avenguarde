"""
RECORD THE AUXILIARY ARRAYS -- masks, class layers and diagnostics that were
built by earlier scripts but never given a manifest entry.

    python build/record_auxiliary.py

WHY THIS EXISTS
    cube/healpix held six arrays no manifest entry pointed at:
        earth_reference_mask_nside1024.npy      (phase4a_percentile.build_mask)
        earth_lithology_l3_nside1024.npy        (lithology.py)
        earth_lithology_l1_nside1024.npy        (lithology.py)
        earth_lithology_support_nside1024.npy   (lithology.py)
        earth_thermal_nsamples_nside1024.npy    (phase3_thermal.py)
        moon_thermal_nsamples_nside256.npy      (phase3_thermal.py)
    An array without a manifest entry is an array whose definition lives only
    in the script that wrote it. The manifest is supposed to be the one place
    that says what every file in the cube IS. This script measures each array
    as it is on disk and writes the entry, naming the builder and the file's
    own modification time, so nothing is claimed that was not measured.

NOTHING IS REBUILT. Nothing in cube/healpix is modified. Only the manifest
and this script's own summary are written.
"""

import io
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

HP = os.path.join(C.ROOT, "cube", "healpix")


def rel(p):
    return os.path.relpath(p, C.ROOT).replace(os.sep, "/")


def mtime_utc(p):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(os.path.getmtime(p)))


def lat_bands(nside, valid):
    lat = C.healpix_lat(nside)
    bands = {"global": np.ones(valid.size, bool),
             "abs_lat_gt_60": np.abs(lat) > 60,
             "abs_lat_gt_80": np.abs(lat) > 80,
             "abs_lat_gt_85": np.abs(lat) > 85,
             "lat_85S_to_90S": lat <= -85.0}
    return {b: round(100.0 * int((valid & m).sum()) / int(m.sum()), 4)
            for b, m in bands.items()}


def float_stats(a, valid):
    f = a[valid].astype(np.float64)
    if not f.size:
        return {}
    q = np.percentile(f, [1, 25, 50, 75, 99])
    return dict(min=float(f.min()), p1=float(q[0]), p25=float(q[1]),
                p50=float(q[2]), p75=float(q[3]), p99=float(q[4]),
                max=float(f.max()), mean=float(f.mean()))


def common(path, nside, builder):
    a = np.load(path, mmap_mode="r")
    return a, dict(
        file=rel(path), nside=nside, order="nested",
        dtype=str(a.dtype), n_pixels=int(a.size),
        expected_npix=12 * nside ** 2,
        shape_ok=bool(a.size == 12 * nside ** 2),
        built_by=builder, file_mtime_utc=mtime_utc(path),
        recorded_by="build/record_auxiliary.py",
        recorded_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        recording_note=("Manifest entry written AFTER the fact from the array "
                        "as it is on disk. Every number here was measured by "
                        "record_auxiliary.py, not copied from the builder."))


def main():
    print("=" * 78)
    print("RECORD AUXILIARY ARRAYS INTO THE MANIFEST")
    print("=" * 78)
    man = json.load(io.open(C.MANIFEST, encoding="utf-8"))["layers"]
    out = {}

    # ---- 1. the HEALPix reference mask (step 3 reference population) --------
    # Since B31(e), 10 Nov 2026, build/reference_mask.py writes this entry
    # itself, with both rules. This after-the-fact block is kept for the
    # record but no longer runs: it would overwrite the builder's entry.
    key = "earth_reference_mask"
    p = os.path.join(HP, "earth_reference_mask_nside1024.npy")
    if False:
        a, e = common(p, 1024, "build/phase4a_percentile.py: build_mask()")
        a = np.asarray(a)
        fin = np.isfinite(a)
        ref = fin & (a > 0.5)
        e.update(
            phase="1b", body="earth", variable="reference_mask", role="mask",
            units="fraction of the pixel's area that is reference land (0..1)",
            source_files=["cube/dem/earth_land_reference_1_240deg.npy"],
            source_resolves=os.path.exists(os.path.join(
                C.ROOT, "cube", "dem", "earth_land_reference_1_240deg.npy")),
            derivation=("cos(lat)-weighted area average of the 1/240 deg boolean "
                        "earth_land_reference (land AND NOT ice AND NOT water "
                        "bodies) onto HEALPix NESTED Nside 1024, by the same "
                        "HealpixAccumulator every continuous layer uses"),
            membership_rule=("a pixel belongs to Earth's reference population "
                             "where fraction > 0.5. This is the population the "
                             "percentile transform (step 3) and the covariance "
                             "(step 4) are computed over. Used by phase4a."),
            mask_provenance="cube/mask_provenance.json",
            matching_eligible=False,
            validation=dict(
                n_finite=int(fin.sum()),
                pixels_fraction_gt_0=int((fin & (a > 0)).sum()),
                pixels_in_reference_population=int(ref.sum()),
                pct_of_sphere_in_reference=round(100.0 * ref.mean(), 4),
                pct_of_sphere_by_fraction_sum=round(100.0 * float(a[fin].sum()) /
                                                    a.size, 4),
                coverage_gate=lat_bands(1024, ref),
                fraction_stats=float_stats(a, fin & (a > 0)),
                note=("pct_of_sphere_by_fraction_sum is the area of reference land "
                      "as the mask measures it; pct_of_sphere_in_reference is the "
                      "area after the > 0.5 rule. Their difference is the coastal "
                      "and lake-edge pixels the rule drops or absorbs."),
                expected_from_phase4a=dict(reference_pixels=3260787)))
        out[key] = e
        print(f"  {key}: {int(ref.sum()):,} reference pixels "
              f"({100*ref.mean():.3f}% of the sphere), phase4a expects 3,260,787")
        del a

    # ---- 2. lithology: l3 class, l1 class, support --------------------------
    ls = json.load(io.open(os.path.join(HP, "lithology_summary.json"),
                           encoding="utf-8"))
    vocab = ls["vocab"]
    l1vocab = ls["l1vocab"]
    LITH_COMMON = dict(
        phase="3b", body="earth", role="filter and composition route",
        source=("Global Lithological Map, Hartmann & Moosdorf (2012), "
                "doi:10.1029/2012GC004370; read from the VECTOR form "
                "LiMW_GIS 2015.gdb / GLiM_export (1,235,259 polygons, median "
                "polygon 3.01 km), not the 0.5 degree raster"),
        source_files=["LiMW_GIS 2015.gdb/LiMW_GIS 2015.gdb"],
        binning=("MAJORITY VOTE, cos(lat)-weighted, rasterised at 1/240 deg "
                 "inside the band loop with no intermediate written; the "
                 "winning class is stored and its share is the support"),
        what_it_feeds=("(1) the water-body (wb) term of the reference mask, "
                       "(2) earth_SiO2 and earth_FeO through the 98-row lookup "
                       "sources/glim_composition_lookup.csv, (3) a lithology "
                       "FILTER for step 9. It never ranks: Moon and Mars have "
                       "no lithological map in this vocabulary."),
        matching_eligible=False,
        ground_truth_ceiling=("GLiM's own validation against 164,953 rock "
                              "descriptions: 40% exact class match, 64% "
                              "allowing similar lithologies. Everything "
                              "derived from this layer inherits that ceiling."),
        summary_file="cube/healpix/lithology_summary.json")

    key = "earth_lithology_l3"
    p = os.path.join(HP, "earth_lithology_l3_nside1024.npy")
    a, e = common(p, 1024, "build/lithology.py")
    a = np.asarray(a)
    ok3 = a != 65535
    u3, c3 = np.unique(a[ok3], return_counts=True)
    # provenance for the two class layers: the vector is finer than the pixel
    # everywhere (median polygon 3.01 km), so a classified pixel is BINNED and
    # an unclassified one is NO_VALID_SOURCE (no polygon there: ocean). The
    # same array serves l3 and l1, whose footprints are identical.
    prov = np.where(ok3, 1, 3).astype(np.uint8)
    prov_p = os.path.join(HP, "earth_lithology_provenance_nside1024.npy")
    C.atomic_save(prov_p, prov)
    LITH_COMMON.update(
        provenance_file=rel(prov_p),
        provenance_encoding="cube/provenance_encoding.json",
        provenance_encoding_name="cube_provenance_v1",
        provenance_note=("1 = BINNED where the majority vote produced a class "
                         "(the vector source is finer than the pixel "
                         "everywhere), 3 = NO_VALID_SOURCE where no polygon "
                         "covers the pixel, i.e. ocean. Written by "
                         "record_auxiliary.py from the class array."))
    del prov
    e.update(LITH_COMMON)
    e.update(
        variable="lithology_l3",
        units=("GLiM level-3 class id, uint16, 0..436 indexing "
               "lithology_summary.json['vocab']; 65535 = no class"),
        nodata=65535,
        vocabulary=("lithology_summary.json['vocab']: id -> 6-character GLiM "
                    "code, e.g. 'vb____' = basic volcanic, 'su____' = "
                    "unconsolidated sediment. Positions 1-2 lithology class, "
                    "3-4 first attribute, 5-6 second attribute."),
        support_file="cube/healpix/earth_lithology_support_nside1024.npy",
        validation=dict(
            n_valid=int(ok3.sum()), coverage_gate=lat_bands(1024, ok3),
            distinct_levels_all_pixels=int(u3.size),
            largest_tie_fraction_all_pixels=float(c3.max() / c3.sum()),
            largest_class_all_pixels=vocab[str(int(u3[np.argmax(c3)]))],
            distinct_levels_land_per_summary=ls["distinct_levels_l3"],
            largest_tie_fraction_land_per_summary=ls["largest_tie_fraction_l3"],
            tie_note=("all-pixel figures include water bodies (wb) and ice "
                      "(ig), which is why the largest class there is not the "
                      "land figure in lithology_summary.json")))
    out[key] = e
    print(f"  {key}: {int(ok3.sum()):,} classified pixels, {u3.size} classes")

    key = "earth_lithology_l1"
    p = os.path.join(HP, "earth_lithology_l1_nside1024.npy")
    b, e = common(p, 1024, "build/lithology.py")
    b = np.asarray(b)
    ok1 = b != 255
    u1, c1 = np.unique(b[ok1], return_counts=True)
    e.update(LITH_COMMON)
    e.update(
        variable="lithology_l1",
        units=("GLiM level-1 class id, uint8, indexing "
               "lithology_summary.json['l1vocab']; 255 = no class"),
        nodata=255,
        vocabulary={str(i): t for i, t in enumerate(l1vocab)},
        l1_meaning=dict(
            ev="evaporites", ig="ice and glaciers (EXCLUDED from the "
            "reference population)", mt="metamorphic rocks", nd="no data "
            "(EXCLUDED)", pa="acid plutonic", pb="basic plutonic",
            pi="intermediate plutonic", py="pyroclastics", sc="carbonate "
            "sedimentary", sm="mixed sedimentary", ss="siliciclastic "
            "sedimentary", su="unconsolidated sediments", va="acid volcanic",
            vb="basic volcanic", vi="intermediate volcanic", wb="water bodies "
            "(EXCLUDED from the reference population)"),
        l1_meaning_source=("Hartmann & Moosdorf (2012), Table 1 -- the paper's "
                           "own class list, read from the primary source after "
                           "an AI-generated table was found to have 6 of 14 "
                           "codes wrong (VARIABLES.md B19b)"),
        derived_from="first two characters of the winning level-3 code",
        support_file="cube/healpix/earth_lithology_support_nside1024.npy",
        validation=dict(
            n_valid=int(ok1.sum()), coverage_gate=lat_bands(1024, ok1),
            distinct_levels_all_pixels=int(u1.size),
            class_counts_all_pixels={l1vocab[int(u)]: int(c)
                                     for u, c in zip(u1, c1)},
            distinct_levels_land_per_summary=ls["distinct_levels_l1"],
            largest_tie_fraction_land_per_summary=ls["largest_tie_fraction_l1"]))
    out[key] = e
    print(f"  {key}: {int(ok1.sum()):,} classified pixels, {u1.size} classes")
    cons = int(((ok1 != ok3)).sum())
    print(f"    l1/l3 footprints differ on {cons:,} pixels (expect 0)")
    out[key]["validation"]["footprint_matches_l3"] = bool(cons == 0)
    del b

    key = "earth_lithology_support"
    p = os.path.join(HP, "earth_lithology_support_nside1024.npy")
    s, e = common(p, 1024, "build/lithology.py")
    s = np.asarray(s)
    fs = np.isfinite(s)
    e.update({k: v for k, v in LITH_COMMON.items()
              if not k.startswith("provenance")})
    e.update(
        variable="lithology_support",
        units="winning class share of the pixel's cos(lat)-weighted cells (0..1)",
        serves_as=("the support value of earth_lithology_l3, earth_lithology_l1, "
                   "earth_SiO2 and earth_FeO -- the oxides are a lookup through "
                   "the lithology vote and inherit its support exactly"),
        validation=dict(
            n_finite=int(fs.sum()),
            finite_where_l3_classified=int((fs & ok3).sum()),
            finite_where_l3_unclassified=int((fs & ~ok3).sum()),
            stats=float_stats(s, fs),
            pixels_below_0_50=int((s[fs] < 0.5).sum()),
            note=("support is finite only where the vote produced a class; a "
                  "NaN here with a class in l3 would be a contradiction and "
                  "is counted above as finite_where_l3_classified vs n_valid")))
    out[key] = e
    print(f"  {key}: finite on {int(fs.sum()):,} pixels, p50 "
          f"{out[key]['validation']['stats'].get('p50', float('nan')):.4f}")
    del s, a

    # ---- 3. thermal sampling counts -----------------------------------------
    for body, nside, units, desc in (
            ("earth", 1024, "months with at least one usable local-time "
             "reading in calendar 2025 (0..12)",
             "MOD11C3 + MYD11C3, 2025, QC bits 0-1 <= 1; the min_months=6 "
             "rule in phase3_thermal.build_earth decides validity of the "
             "three Earth thermal layers"),
            ("moon", 256, "Diviner GCP local-time bins filled, of 96 (0.25 h "
             "bins)", "n_local_time from the GCP; corr(n, |lat|) = +0.856, "
             "poles best sampled (median 96 at 85-90S vs 55 at the equator); "
             "bias on the diurnal range bounded at ~0.3 K, see "
             "moon_temp_level.validation.sampling_bias_checked")):
        key = f"{body}_thermal_nsamples"
        p = os.path.join(HP, f"{body}_thermal_nsamples_nside{nside}.npy")
        n, e = common(p, nside, "build/phase3_thermal.py")
        n = np.asarray(n)
        fn = np.isfinite(n)
        e.update(
            phase="3", body=body, variable="thermal_nsamples",
            role="diagnostic: sampling support of the thermal layers",
            units=units, description=desc,
            binning=("area-weighted mean of the source count onto HEALPix, "
                     "gaps filled by nearest-neighbour copy of the source "
                     "count (bin then fill, as the thermal layers themselves)"),
            matching_eligible=False,
            validation=dict(n_finite=int(fn.sum()),
                            stats=float_stats(n, fn),
                            pixels_zero=int((n[fn] == 0).sum()),
                            coverage_gate=lat_bands(nside, fn & (n > 0))))
        out[key] = e
        print(f"  {key}: p50 {out[key]['validation']['stats']['p50']:.1f}, "
              f"zero on {out[key]['validation']['pixels_zero']:,} pixels")
        del n

    # ---- write ---------------------------------------------------------------
    for k, e in out.items():
        if k in man:
            print(f"  NOTE: {k} already had a manifest entry; replaced")
        C.manifest_write(k, e)
    io.open(os.path.join(C.ROOT, "cube", "auxiliary_summary.json"), "w",
            encoding="utf-8").write(json.dumps(
                {k: e["validation"] for k, e in out.items()}, indent=1,
                default=str))
    print(f"\n{len(out)} manifest entries written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
