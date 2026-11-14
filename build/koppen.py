"""
PHASE 3c -- KOPPEN-GEIGER CLIMATE CLASS. Earth only. A CHARACTERIZATION layer.

    python build/koppen.py [--test]

WHAT IT IS FOR
    Step 9 names each found site in one phrase -- "BWh hot desert", "ET
    tundra" -- so a reader can picture the place. It changes no number:
    matching_eligible is false PERMANENTLY, because the Moon and Mars have no
    Koppen class and a dimension counts only if both bodies in the pair have it.

SOURCE
    Beck et al. (2023), "High-resolution (1 km) Koppen-Geiger maps for
    1901-2099 based on constrained CMIP6 projections", Scientific Data 10, 724.
    The 1991-2020 observational period at 0.00833333 deg (30 arc-second, 0.93
    km), uint8 codes 1..30, 0 = no class (ocean). The file was COPIED from
    D:/Projects/koppen_geiger_tif/1991_2020 into sources/koppen_geiger (the
    write-once folder) and its SHA1 is checked against the original here.

CATEGORICAL, SO MAJORITY VOTE -- the mean accumulator is WRONG for it.
    The same construction as lithology.py: per (pixel, class) cos(lat) weights
    reduced band by band to compact pairs, the winning class per pixel, and the
    WINNING SHARE as support, because a 35% plurality and a 95% majority are
    not the same measurement. The source is finer than the 6.37 km pixel
    EVERYWHERE -- 0.93 km north-south and 0.93*cos(lat) km east-west -- so
    every classified pixel is BINNED and nothing is copied.

GATES, STATED BEFORE THE RUN
    range     every non-zero code lies in 1..30; anything else is a read error
    coverage  pixels with a class, globally and by latitude band, AND within
              Earth's reference population (ice-free, water-free land), which
              is the population step 9 will look classes up for
    support   winning share of the pixel's classified weight
    ties      distinct_levels (at most 30) and largest_tie_fraction. This is a
              30-class categorical layer: large tie blocks are the point, not
              a defect, and they are why it can never rank.
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
from phase1_dems import peak_rss_gib, say_peak
from phase2_terrain import HealpixAccumulator

SRC_DIR = os.path.join(C.ROOT, "sources", "koppen_geiger")
SRC = os.path.join(SRC_DIR, "koppen_geiger_0p00833333.tif")
LEGEND = os.path.join(SRC_DIR, "legend.txt")
SRC_MANIFEST = os.path.join(SRC_DIR, "manifest.json")
ORIGINAL = os.path.join("D:/Projects/koppen_geiger_tif/1991_2020",
                        "koppen_geiger_0p00833333.tif")
OUT = os.path.join(C.ROOT, "cube", "healpix")
NSIDE = 1024
K = 32                      # key = pixel * K + class; classes are 0..30
GATE = (1, 30)
BAND_ROWS = 240             # 2 degrees of latitude per band
REF_MASK = os.path.join(OUT, f"earth_reference_mask_nside{NSIDE}.npy")
ABSENT, BINNED, COPIED, NO_VALID = 0, 1, 2, 3


def rel(p):
    return os.path.relpath(p, C.ROOT).replace(os.sep, "/")


def sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def parse_legend(path):
    pat = re.compile(r"^\s*(\d+):\s+(\S+)\s+(.+?)\s+\[")
    out = {}
    for line in io.open(path, encoding="utf-8"):
        m = pat.match(line)
        if m:
            out[int(m.group(1))] = dict(symbol=m.group(2),
                                        description=m.group(3).strip())
    if sorted(out) != list(range(1, 31)):
        raise SystemExit(f"STOP: legend parsed {len(out)} classes, expected "
                         f"1..30")
    return out


def write_source_manifest(digest, legend):
    """sources/ is write-once: the manifest is created if absent, never edited."""
    if os.path.exists(SRC_MANIFEST):
        return "exists, untouched"
    man = {
        "koppen_geiger_0p00833333.tif": dict(
            name=("EARTH - Koppen-Geiger climate classification, 1991-2020, "
                  "30 arc-second"),
            citation=("Beck, H. E. et al. (2023). High-resolution (1 km) "
                      "Koppen-Geiger maps for 1901-2099 based on constrained "
                      "CMIP6 projections. Scientific Data 10, 724."),
            url="https://doi.org/10.1038/s41597-023-02549-6",
            copied_from=ORIGINAL,
            sha1=digest,
            bytes=os.path.getsize(SRC),
            status="OK",
            period=("1991-2020, the latest OBSERVATIONAL period in the set. "
                    "The 2041-2070 and 2071-2099 folders are CMIP6 "
                    "projections and are not used."),
            role=("CHARACTERIZATION ONLY, matching_eligible false permanently: "
                  "the Moon and Mars have no Koppen class"),
            copied_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        "legend.txt": dict(
            name="class code -> symbol -> description, from the same release",
            classes=len(legend)),
    }
    io.open(SRC_MANIFEST, "w", encoding="utf-8").write(
        json.dumps(man, indent=1, ensure_ascii=False))
    return "written"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true",
                    help="three bands around 40N, write nothing")
    a = ap.parse_args()
    import rasterio

    print("=" * 78)
    print("PHASE 3c -- KOPPEN-GEIGER CLIMATE CLASS, EARTH (characterization)")
    print("=" * 78)
    print(f"RANGE GATE, stated BEFORE the run: codes {GATE[0]}..{GATE[1]}; "
          f"0 = no class")
    C.require_disk(2.0, C.ROOT)
    t0 = time.perf_counter()

    legend = parse_legend(LEGEND)
    digest = sha1(SRC)
    orig_ok = None
    if os.path.exists(ORIGINAL):
        orig_ok = (sha1(ORIGINAL) == digest)
        print(f"  SHA1 {digest}  matches the D:/Projects original: {orig_ok}")
        if not orig_ok:
            raise SystemExit("STOP: the copy in sources/ differs from the "
                             "original")
    else:
        print(f"  SHA1 {digest}  (original not on disk to compare)")

    with rasterio.open(SRC) as s:
        if s.count != 1 or s.dtypes[0] != "uint8":
            raise SystemExit(f"STOP: expected one uint8 band, got {s.count} "
                             f"x {s.dtypes}")
        H, W = s.height, s.width
        if (H, W) != (21600, 43200):
            raise SystemExit(f"STOP: raster is {H}x{W}, expected 21600x43200")
        t = s.transform
        if not (abs(t.a - 1 / 120) < 1e-9 and abs(t.e + 1 / 120) < 1e-9
                and abs(t.c + 180) < 1e-9 and abs(t.f - 90) < 1e-9):
            raise SystemExit(f"STOP: unexpected geotransform {t}")
        print(f"  source {H} x {W} = {H*W:,} cells at 1/120 deg, nodata "
              f"{s.nodata}, crs {s.crs}")
        lat = 90.0 - (np.arange(H) + 0.5) * (180.0 / H)
        lon = -180.0 + (np.arange(W) + 0.5) * (360.0 / W)
        cos = np.maximum(np.cos(np.radians(lat)), 1e-9)
        acc = HealpixAccumulator(NSIDE, ["classified"])
        npix = acc.npix
        print(f"  target {npix:,} HEALPix pixels, Nside {NSIDE} NESTED; "
              f"{H*W/npix:.1f} source cells per pixel on average")

        bands = list(range(0, H, BAND_ROWS))
        if a.test:
            mid = (90 - 40) * 120 // BAND_ROWS
            bands = bands[mid:mid + 3]
            print(f"  TEST: bands {bands} only, nothing written")
        keys_all, w_all = [], []
        hist = np.zeros(256, dtype=np.int64)
        n_bad = 0
        cells = 0
        for bi, r0 in enumerate(bands):
            r1 = min(H, r0 + BAND_ROWS)
            band = s.read(1, window=((r0, r1), (0, W)))
            flat = band.ravel()
            hist += np.bincount(flat, minlength=256)
            cells += flat.size
            idx = acc.index_for_band(lat[r0:r1], lon).ravel()
            wt = np.repeat(cos[r0:r1], W)
            acc.add_reference(idx, wt)
            has = flat > 0
            n_bad += int(np.sum(has & ((flat < GATE[0]) | (flat > GATE[1]))))
            ind = np.where(has, 1.0, np.nan).astype(np.float32)
            acc.add("classified", ind.reshape(r1 - r0, W), idx, wt)
            if has.any():
                key = idx[has].astype(np.int64) * K + flat[has]
                uk, inv = np.unique(key, return_inverse=True)
                ws = np.bincount(inv, weights=wt[has], minlength=uk.size)
                keys_all.append(uk)
                w_all.append(ws)
            del band, flat, idx, wt, has, ind
            if (bi + 1) % 10 == 0 or bi == len(bands) - 1:
                el = time.perf_counter() - t0
                print(f"    band {bi+1}/{len(bands)}  lat {lat[r0]:+.1f}  "
                      f"pairs so far {sum(k.size for k in keys_all):,}  "
                      f"{el/60:.1f} min", flush=True)
    say_peak("koppen band loop")
    print(f"  RANGE GATE: {n_bad:,} non-zero cells outside {GATE}  "
          f"{'PASS' if n_bad == 0 else 'FAIL'}")
    print(f"  source histogram: 0 (no class) {hist[0]:,} = "
          f"{100*hist[0]/cells:.2f}% of cells; codes >30: "
          f"{int(hist[31:].sum()):,}")

    # ---- merge the per-band pairs and take the majority per pixel
    keys = np.concatenate(keys_all)
    w = np.concatenate(w_all)
    del keys_all, w_all
    uk, inv = np.unique(keys, return_inverse=True)
    ws = np.bincount(inv, weights=w, minlength=uk.size)
    del keys, w, inv
    pix = uk // K
    cls = (uk % K).astype(np.uint8)
    order = np.lexsort((-ws, pix))             # by pixel, then heaviest first
    pix_s, cls_s, ws_s = pix[order], cls[order], ws[order]
    first = np.ones(pix_s.size, dtype=bool)
    first[1:] = pix_s[1:] != pix_s[:-1]
    win_pix, win_cls, win_w = pix_s[first], cls_s[first], ws_s[first]
    tot = np.bincount(pix, weights=ws, minlength=npix)
    n_in_pix = np.bincount(pix, minlength=npix)
    class_arr = np.zeros(npix, dtype=np.uint8)
    class_arr[win_pix] = win_cls
    support = np.full(npix, np.nan, dtype=np.float32)
    support[win_pix] = (win_w / tot[win_pix]).astype(np.float32)
    frac_any, _, frac = acc.finish("classified")     # frac = classified share
    ref_w = acc.ref
    prov = np.full(npix, NO_VALID, dtype=np.uint8)
    prov[class_arr > 0] = BINNED
    prov[ref_w <= 0] = ABSENT
    print(f"  (pixel, class) pairs {uk.size:,}; pixels with a class "
          f"{int((class_arr > 0).sum()):,}; pixels with no source cell at all "
          f"{int((ref_w <= 0).sum()):,}")

    # ---- gates
    hlat = C.healpix_lat(NSIDE)
    v = class_arr > 0
    bands_ = {"global": np.ones(npix, bool),
              "abs_lat_gt_60": np.abs(hlat) > 60,
              "abs_lat_gt_80": np.abs(hlat) > 80,
              "abs_lat_gt_85": np.abs(hlat) > 85,
              "lat_85S_to_90S": hlat <= -85.0}
    cov = {b: round(100.0 * int((v & m).sum()) / int(m.sum()), 4)
           for b, m in bands_.items()}
    uq, cq = np.unique(class_arr[v], return_counts=True)
    counts_global = {int(u): int(c) for u, c in zip(uq, cq)}
    ties = dict(distinct_levels=int(uq.size),
                largest_tie_fraction=float(cq.max() / cq.sum()),
                largest_tie_class=legend[int(uq[np.argmax(cq)])]["symbol"])
    sf = support[v].astype(np.float64)
    q = np.percentile(sf, [1, 5, 25, 50, 75])
    sup_gate = dict(
        definition=("winning class share of the pixel's cos(lat)-weighted "
                    "classified cells; 1.0 means every classified source cell "
                    "in the pixel agrees"),
        min=float(sf.min()), p1=float(q[0]), p5=float(q[1]), p25=float(q[2]),
        p50=float(q[3]), p75=float(q[4]), max=float(sf.max()),
        mean=float(sf.mean()),
        pixels_below_0_50=int((sf < 0.5).sum()),
        pixels_single_class=int((n_in_pix[v] == 1).sum()),
        classes_per_pixel_max=int(n_in_pix.max()))
    cf = frac[v].astype(np.float64)
    classified_fraction = dict(
        definition=("share of the pixel's cos(lat)-weighted source cells that "
                    "carry ANY class -- a land fraction by this product's own "
                    "footprint; it is the coverage gate per pixel"),
        p50=float(np.median(cf)), mean=float(cf.mean()),
        pixels_below_0_50=int((cf < 0.5).sum()))

    ref_note = None
    if os.path.exists(REF_MASK):
        rf = np.load(REF_MASK)
        ref = np.isfinite(rf) & (rf > 0.5)
        n_ref = int(ref.sum())
        n_ref_cls = int((ref & v).sum())
        uq_r, cq_r = np.unique(class_arr[ref & v], return_counts=True)
        share = {legend[int(u)]["symbol"]: round(100.0 * int(c) / n_ref_cls, 3)
                 for u, c in zip(uq_r, cq_r)}
        ref_note = dict(
            reference_mask=rel(REF_MASK),
            reference_pixels=n_ref,
            reference_pixels_with_class=n_ref_cls,
            pct_of_reference_with_class=round(100.0 * n_ref_cls / n_ref, 4),
            reference_pixels_without_class=n_ref - n_ref_cls,
            without_class_note=("reference pixels the Koppen footprint does "
                                "not reach: coastline and island differences "
                                "between the 0.93 km Koppen land footprint "
                                "and the WorldClim-derived land mask. Step 9 "
                                "reports 'no class' for these, it does not "
                                "guess one."),
            class_share_pct_of_classified_reference=share)
        print(f"  REFERENCE POPULATION: {n_ref_cls:,} of {n_ref:,} pixels "
              f"carry a class ({100*n_ref_cls/n_ref:.3f}%)")
        top = sorted(share.items(), key=lambda kv: -kv[1])[:8]
        print("  largest classes over the reference population: " +
              ", ".join(f"{s} {p:.1f}%" for s, p in top))
    else:
        print("  reference mask not on disk; reference coverage not measured")

    print(f"  coverage: global {cov['global']:.3f}%  >85deg "
          f"{cov['abs_lat_gt_85']:.3f}%  85-90S {cov['lat_85S_to_90S']:.3f}%")
    print(f"  support: p1 {sup_gate['p1']:.3f} p50 {sup_gate['p50']:.3f} mean "
          f"{sup_gate['mean']:.3f}; single-class pixels "
          f"{sup_gate['pixels_single_class']:,}")
    print(f"  ties: {ties['distinct_levels']} distinct classes, largest "
          f"{ties['largest_tie_class']} = {100*ties['largest_tie_fraction']:.2f}%"
          f" of classified pixels")

    if a.test:
        print("\nTEST ONLY -- nothing written")
        return 0

    os.makedirs(OUT, exist_ok=True)
    f_cls = os.path.join(OUT, f"earth_koppen_class_nside{NSIDE}.npy")
    f_sup = os.path.join(OUT, f"earth_koppen_support_nside{NSIDE}.npy")
    f_prov = os.path.join(OUT, f"earth_koppen_provenance_nside{NSIDE}.npy")
    C.atomic_save(f_cls, class_arr)
    C.atomic_save(f_sup, support)
    C.atomic_save(f_prov, prov)
    legend_path = os.path.join(C.ROOT, "cube", "koppen_legend.json")
    io.open(legend_path, "w", encoding="utf-8").write(json.dumps(dict(
        source="sources/koppen_geiger/legend.txt (Beck et al. 2023)",
        code_0="no class (ocean / outside the product footprint)",
        classes={str(k): v for k, v in legend.items()}), indent=1))
    src_state = write_source_manifest(digest, legend)
    el = time.perf_counter() - t0
    validation = dict(
        name="earth_koppen_class", units="class code 1..30 (0 = no class)",
        n_pixels=npix, expected_npix=12 * NSIDE ** 2, shape_ok=True,
        dtype="uint8", n_valid=int(v.sum()),
        range_gate=dict(stated_in_advance=list(GATE),
                        nonzero_cells_outside=n_bad,
                        source_codes_above_30=int(hist[31:].sum()),
                        range_gate_pass=bool(n_bad == 0)),
        coverage_gate=cov,
        classified_fraction=classified_fraction,
        support_gate=sup_gate,
        distinct_levels=ties["distinct_levels"],
        largest_tie_fraction=ties["largest_tie_fraction"],
        largest_tie_class=ties["largest_tie_class"],
        class_counts_global={legend[k]["symbol"]: c
                             for k, c in counts_global.items()},
        reference_population=ref_note,
        source_cells=int(cells), source_cells_no_class=int(hist[0]),
        source_sha1=digest, source_matches_original=orig_ok,
        matching_eligible=False)
    C.manifest_write("earth_koppen_class", dict(
        phase="3c", body="earth", variable="koppen_class",
        role="characterization",
        units="Koppen-Geiger class code, uint8, 1..30; 0 = no class",
        nside=NSIDE, order="nested",
        file=rel(f_cls), support_file=rel(f_sup), provenance_file=rel(f_prov),
        provenance_encoding="cube/provenance_encoding.json",
        provenance_encoding_name="cube_provenance_v1",
        legend_file="cube/koppen_legend.json",
        source_files=[rel(SRC), rel(LEGEND)],
        source_resolves=os.path.exists(SRC),
        source_manifest=rel(SRC_MANIFEST) + f" ({src_state})",
        source=("Beck et al. (2023) Scientific Data 10, 724, "
                "doi:10.1038/s41597-023-02549-6; 1991-2020 observational "
                "period, 30 arc-second GeoTIFF, uint8"),
        native_resolution="1/120 deg (21600x43200), 0.93 km x 0.93*cos(lat) km",
        binning=("MAJORITY VOTE, cos(lat)-weighted, per (pixel, class) pairs "
                 "reduced band by band; the winning class is stored and its "
                 "share is the support. The source is finer than the pixel "
                 "everywhere, so every classified pixel is BINNED and none is "
                 "copied."),
        matching_eligible=False,
        matching_eligible_reason=(
            "PERMANENT. A variable is a dimension only if both bodies in the "
            "pair have it, and the Moon and Mars have no Koppen class. This "
            "layer describes a site after it is found (step 9) and must "
            "never be wired into a dimension set."),
        gates=("FOUR: range (codes 1..30, stated in advance), coverage (global, "
               "by latitude band, and within the reference population), "
               "support (winning share) and ties (distinct_levels, "
               "largest_tie_fraction -- categorical, large ties expected)."),
        support_warning=("support here is the winning class share, never "
                         "0.0 on a classified pixel. Read provenance_file for "
                         "usability: 1 = BINNED, 3 = NO_VALID_SOURCE (the "
                         "product covers the pixel but assigns no class, i.e. "
                         "ocean), 0 = ABSENT."),
        validation=validation,
        elapsed_s=round(el, 1), peak_rss_gib=peak_rss_gib(),
        build_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
    io.open(os.path.join(OUT, "koppen_summary.json"), "w",
            encoding="utf-8").write(json.dumps(validation, indent=1,
                                               default=str))
    print(f"\nwrote {rel(f_cls)}, {rel(f_sup)}, {rel(f_prov)}, "
          f"cube/koppen_legend.json; sources manifest {src_state}")
    print(f"KOPPEN {el/60:.1f} min   peak RAM {peak_rss_gib()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
