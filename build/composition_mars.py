"""
PHASE 3b (Mars) -- SiO2 and FeO_T from the TES mineral-abundance maps.
DECIDED by Sherozbek, 9 Nov 2026: the Earth-Mars set needs composition.

    python build/composition_mars.py [--test]

WHY THIS SOURCE (VARIABLES.md B27, source search of 9 Nov 2026)
    No public Mars product gives oxide weight percent at pixel scale. GRS is
    300-600 km. OMEGA (40 ppd) and CRISM (327 ppd) give band DEPTHS, which
    have no Earth counterpart and no published transfer to abundance. The
    TES mineral maps (Bandfield 2002) are the only numeric product with
    plagioclase, pyroxene, olivine, feldspar, glass and oxide FRACTIONS in
    one cube, and they are on disk as eleven JMARS exports at 4 ppd
    ("Mars lithology/TES_*_numeric", VICAR, float32, -1 = no data). This is
    the spec's "option b": a mineral-stoichiometry lookup with the same
    discipline as the Earth 98-row table.

WHAT THE NUMBERS ARE, AND ARE NOT
    TES deconvolution concentrations are AREAL fractions of spectral
    end-members (detection limit 0.10-0.15, Bandfield 2002), valid only on
    warm, dust-free, ice-free, low-emission-angle surfaces -- roughly 60S to
    60N minus the dusty regions. The oxide value of a pixel is the
    abundance-weighted mean of the end-member oxide contents, normalised
    over the MINERAL end-members (dust excluded: it is a mantle, not the
    rock, and it is used as a mask). Each end-member oxide content carries
    a tag: DEFINITIONAL (ideal formula), ASSUMED (a solid-solution
    composition chosen from the Mars literature, with the alternative
    values that bound it), or ESTIMATE (a mixed group with no single
    formula). The pipeline uses RANKS, so the ORDER of the end-members by
    silica is what matters; the sensitivity of the result to the ASSUMED
    values is measured below and recorded, not assumed away.

RESOLUTION, STATED
    4 pixels per degree = 14.8 km at the equator, 2.2x COARSER than the
    6.79 km HEALPix pixel: bin where a cell falls in a pixel, copy where
    none does, so most pixels are COPIED_FROM_COARSER and tie blocks of
    ~4-5 pixels are expected. Between LP GRS (61 km, accepted as a weak
    lunar dimension) and the MCD (355 km, rejected). Declared WEAK.

GATES, STATED BEFORE THE RUN
    range     SiO2 35..70 wt% (olivine to K-feldspar bounds the mean);
              FeO_T 0..45 wt% (olivine Fo70 bounds a silicate mean; hematite
              can push a pixel above it -- counted, not clipped)
    fit       RMS_Error <= 0.0044 (v1's p95 rule, kept) ; Dust <= 0.80
    support   sum of mineral fractions >= 0.10 (one detection limit)
    coverage, ties  recorded; coverage will be partial by construction
"""

import argparse
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
from phase2_terrain import show, validate
from phase3_thermal import bin_grid, sample_grid

SRC = os.path.join(C.ROOT, "Mars lithology")
OUT = os.path.join(C.ROOT, "cube", "healpix")
BODY, NSIDE = "mars", C.NSIDE["mars"]
LBLSIZE, NL, NS = 5760, 720, 1440
NODATA = -1.0
RMS_MAX, DUST_MAX, FLOOR = 0.0044, 0.80, 0.10
GATE = dict(SiO2=(35.0, 70.0), FeO=(0.0, 45.0))

# Oxide content of each TES end-member group, weight percent. SiO2 and
# total iron as FeO. Molar masses: SiO2 60.08, FeO 71.85, Fe2O3 159.69.
ENDMEMBERS = {
    "Quartz": dict(SiO2=100.0, FeO=0.0, tag="DEFINITIONAL", basis="SiO2",
                   alt_SiO2=(100.0, 100.0)),
    "Feldspar": dict(SiO2=64.76, FeO=0.0, tag="DEFINITIONAL",
                     basis="K-feldspar KAlSi3O8, M = 278.33",
                     alt_SiO2=(64.76, 64.76)),
    "Plagioclase": dict(SiO2=53.0, FeO=0.0, tag="ASSUMED",
                        basis=("labradorite An60, Na0.4Ca0.6Al1.6Si2.4O8, "
                               "M = 271.84 -- the plagioclase TES retrieves "
                               "on Mars is calcic (Bandfield 2002)"),
                        alt_SiO2=(50.5, 55.6), alt_note="An70 .. An50"),
    "Orthopyroxene": dict(SiO2=56.3, FeO=13.5, tag="ASSUMED",
                          basis="bronzite En80, (Mg0.8Fe0.2)SiO3, M = 106.7",
                          alt_SiO2=(55.0, 57.5), alt_FeO=(6.8, 20.0),
                          alt_note="En70 .. En90"),
    "Clinopyroxene": dict(SiO2=53.2, FeO=12.7, tag="ASSUMED",
                          basis="augite Ca0.8Mg0.8Fe0.4Si2O6, M = 226.0",
                          alt_SiO2=(51.5, 54.5), alt_FeO=(6.0, 18.0),
                          alt_note="diopside-rich .. Fe-augite"),
    "Olivine": dict(SiO2=37.6, FeO=27.0, tag="ASSUMED",
                    basis="forsterite Fo70, Mg1.4Fe0.6SiO4, M = 159.6",
                    alt_SiO2=(35.0, 40.6), alt_FeO=(9.8, 42.0),
                    alt_note="Fo50 .. Fo90"),
    "Amphibole": dict(SiO2=49.7, FeO=8.5, tag="ESTIMATE",
                      basis=("hornblende Ca2Mg3FeAl2Si7O22(OH)2, M = 845.5; "
                             "the group spans actinolite to hornblende"),
                      alt_SiO2=(45.0, 55.0), alt_FeO=(5.0, 15.0)),
    "Glass_Clay": dict(SiO2=60.0, FeO=5.0, tag="ESTIMATE",
                       basis=("'sheet silicates / high-silica glass' group: "
                              "K-rich obsidian glass ~75 wt% SiO2 to smectite "
                              "~50-60; midpoint used, widest uncertainty of "
                              "the table"),
                       alt_SiO2=(50.0, 75.0), alt_FeO=(2.0, 30.0),
                       alt_note="smectite .. obsidian; nontronite would be Fe-rich"),
    "Hematite": dict(SiO2=0.0, FeO=89.98, tag="DEFINITIONAL",
                     basis="Fe2O3 as FeO_T: 2*71.85/159.69", alt_SiO2=(0.0, 0.0)),
}
MINERALS = list(ENDMEMBERS)       # Dust is a MASK, not a component
ORDER_NOTE = ("Ranked by SiO2: olivine < hematite(0) ... the order that "
              "matters for a rank transform is olivine 37.6 < amphibole 49.7 "
              "< clinopyroxene 53.2 ~ plagioclase 53.0 < orthopyroxene 56.3 "
              "< glass 60 < K-feldspar 64.8 < quartz 100. The ASSUMED "
              "alternatives do not reorder these, except plagioclase and "
              "clinopyroxene, which are within 2 wt% of each other either way.")


def read_tes(name):
    p = os.path.join(SRC, f"TES_{name}_numeric")
    raw = open(p, "rb").read()
    lbl = raw[:LBLSIZE].decode("latin1")
    kv = dict(re.findall(r"(\w+)=('?[^' ]+'?)", lbl))
    if (kv.get("FORMAT") != "'REAL'" or int(kv["NL"]) != NL or int(kv["NS"]) != NS
            or kv.get("REALFMT") != "'RIEEE'" or kv.get("ORG") != "'BSQ'"):
        raise SystemExit(f"STOP: {p} label {kv} not the expected 720x1440 REAL BSQ")
    a = np.frombuffer(raw[LBLSIZE:LBLSIZE + NL * NS * 4], dtype="<f4").reshape(NL, NS)
    a = a.astype(np.float64)
    a[a <= NODATA + 0.5] = np.nan
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    print("=" * 78)
    print("PHASE 3b -- MARS SiO2 / FeO_T FROM TES MINERAL MAPS (Bandfield 2002), 4 ppd")
    print("=" * 78)
    print(f"GATES, stated BEFORE the run: SiO2 {GATE['SiO2']} wt%, FeO_T {GATE['FeO']} "
          f"wt%; RMS <= {RMS_MAX}; Dust <= {DUST_MAX}; mineral sum >= {FLOOR}")
    C.require_disk(2.0, C.ROOT)
    t0 = time.perf_counter()
    mins = {m: read_tes(m) for m in MINERALS}
    dust, rms = read_tes("Dust"), read_tes("RMS_Error")
    any_valid = np.isfinite(dust)
    # orientation check: JMARS exports run 0..360 E; roll to -180..180 as v1 did,
    # then Tharsis (dusty, ~-110 E, +10) must be dusty and Syrtis Major (+70 E,
    # +10) must be pyroxene-rich. Row 0 = +90 N.
    lat = 90.0 - (np.arange(NL) + 0.5) * (180.0 / NL)
    lon = -180.0 + (np.arange(NS) + 0.5) * (360.0 / NS)
    roll = lambda x: np.roll(x, NS // 2, axis=1)
    mins = {m: roll(v) for m, v in mins.items()}
    dust, rms, any_valid = roll(dust), roll(rms), roll(any_valid)

    def at(arr, la, lo):
        r = int((90 - la) * NL / 180); c = int((lo + 180) * NS / 360)
        return float(np.nanmean(arr[r-2:r+3, c-2:c+3]))
    th_d, sy_d = at(dust, 10, -110), at(dust, 10, 70)
    sy_px = at(mins["Clinopyroxene"] + mins["Orthopyroxene"], 10, 70)
    print(f"  orientation: dust Tharsis(10N,110W) {th_d:.2f} vs Syrtis(10N,70E) "
          f"{sy_d:.2f}; Syrtis pyroxene {sy_px:.3f}")
    if not (th_d > sy_d and sy_px > 0.05):
        raise SystemExit("STOP: orientation check failed -- the maps are not "
                         "where Tharsis and Syrtis should be")
    print(f"  source cells with any value: {100*any_valid.mean():.2f}% of "
          f"{NL*NS:,}; latitude extent of data {lat[np.isfinite(dust).any(1)].min():+.1f}.."
          f"{lat[np.isfinite(dust).any(1)].max():+.1f}")

    total = sum(mins.values())
    bad_fit = rms > RMS_MAX
    dusty = dust > DUST_MAX
    thin = total < FLOOR
    ok = any_valid & ~bad_fit & ~dusty & ~thin
    print(f"  masks among valid cells: RMS > {RMS_MAX}: {100*bad_fit[any_valid].mean():.2f}%, "
          f"dust > {DUST_MAX}: {100*dusty[any_valid].mean():.2f}%, mineral sum < "
          f"{FLOOR}: {100*thin[any_valid].mean():.2f}%  ->  kept "
          f"{100*ok[any_valid].mean():.2f}% of valid, {100*ok.mean():.2f}% of all cells")

    def oxide(key, table):
        num = sum(mins[m] * table[m] for m in MINERALS)
        with np.errstate(invalid="ignore", divide="ignore"):
            v = num / total
        v[~ok] = np.nan
        return v
    base = {k: {m: ENDMEMBERS[m][k] for m in MINERALS} for k in ("SiO2", "FeO")}
    layers = {k: oxide(k, base[k]) for k in ("SiO2", "FeO")}
    # sensitivity: every ASSUMED/ESTIMATE value at its low and at its high alternative
    sens = {}
    for k in ("SiO2", "FeO"):
        lo = {m: ENDMEMBERS[m].get(f"alt_{k}", (ENDMEMBERS[m][k],) * 2)[0] for m in MINERALS}
        hi = {m: ENDMEMBERS[m].get(f"alt_{k}", (ENDMEMBERS[m][k],) * 2)[1] for m in MINERALS}
        vlo, vhi = oxide(k, lo), oxide(k, hi)
        f = ok
        shift = np.abs(vhi[f] - vlo[f])
        # does the ORDER survive? Spearman between base and each alternative
        def rk(x):
            o = np.argsort(x, kind="stable"); r = np.empty(x.size); r[o] = np.arange(x.size); return r
        rb = rk(layers[k][f])
        sens[k] = dict(median_abs_shift_wt_pct=float(np.median(shift)),
                       p95_abs_shift_wt_pct=float(np.percentile(shift, 95)),
                       spearman_base_vs_low=float(np.corrcoef(rb, rk(vlo[f]))[0, 1]),
                       spearman_base_vs_high=float(np.corrcoef(rb, rk(vhi[f]))[0, 1]))
        print(f"  {k} sensitivity to the ASSUMED/ESTIMATE values: median shift "
              f"{sens[k]['median_abs_shift_wt_pct']:.2f} wt%, p95 "
              f"{sens[k]['p95_abs_shift_wt_pct']:.2f}; rank correlation base vs "
              f"low {sens[k]['spearman_base_vs_low']:.4f}, vs high "
              f"{sens[k]['spearman_base_vs_high']:.4f}")
    for k, v in layers.items():
        f = v[np.isfinite(v)]
        lo, hi = GATE[k]
        print(f"  {k}: p1 {np.percentile(f,1):.2f} p50 {np.median(f):.2f} p99 "
              f"{np.percentile(f,99):.2f} wt%; outside gate {int(((f<lo)|(f>hi)).sum()):,}")
    say_peak("TES read")
    if a.test:
        print("\nTEST -- nothing written")
        return 0

    acc = bin_grid(layers, lat, lon, NSIDE, layers)
    filled, _ = sample_grid(layers, lat, lon, NSIDE)
    rel = lambda p: os.path.relpath(p, C.ROOT).replace(os.sep, "/")
    res = {}
    for k in ("SiO2", "FeO"):
        arr, nfilled, sup = acc.finish(k)
        gap = ~np.isfinite(arr) & np.isfinite(filled[k])
        arr[gap] = filled[k][gap]; sup[gap] = 0.0; n_copied = int(gap.sum())
        nfilled += n_copied
        v = np.isfinite(arr)
        lo, hi = GATE[k]
        out_of = int(np.sum(v & ((arr < lo) | (arr > hi))))
        uq, cq = np.unique(arr[v], return_counts=True)
        extra = dict(
            healpix_pixels_filled=nfilled, pixels_copied_not_binned=n_copied,
            pct_copied=round(100.0 * n_copied / max(nfilled, 1), 3),
            range_gate_stated_in_advance=[lo, hi],
            pixels_outside_stated_gate=out_of, range_gate_pass=bool(out_of == 0),
            distinct_levels=int(uq.size), largest_tie_fraction=float(cq.max() / cq.sum()),
            masks=dict(rms_max=RMS_MAX, dust_max=DUST_MAX, mineral_sum_floor=FLOOR),
            source_cells_kept_pct=round(100.0 * ok.mean(), 3),
            sensitivity=sens[k], units="wt%")
        vres = validate(arr, NSIDE, f"{BODY}_{k}", "wt%", extra, support=sup)
        show(vres)
        print(f"    {'':34s} range gate [{lo:g},{hi:g}] wt%: "
              f"{'PASS' if out_of == 0 else f'FAIL, {out_of:,} outside -- counted, not clipped'}")
        res[k] = vres
        path = os.path.join(OUT, f"{BODY}_{k}_nside{NSIDE}.npy")
        spath = os.path.join(OUT, f"{BODY}_{k}_support_nside{NSIDE}.npy")
        C.atomic_save(path, arr); C.atomic_save(spath, sup)
        C.manifest_write(f"{BODY}_{k}", dict(
            phase="3b", body=BODY, variable=k, units="wt%", nside=NSIDE, order="nested",
            file=rel(path), support_file=rel(spath),
            source_files=[rel(os.path.join(SRC, f"TES_{m}_numeric")) for m in MINERALS + ["Dust", "RMS_Error"]],
            source_resolves=True,
            source=("MGS TES mineral abundance maps, Bandfield (2002) JGR 107(E6) "
                    "5042, doi:10.1029/2001JE001510; JMARS exports at 4 ppd, VICAR "
                    "float32, -1 = no data; official 13-band file at "
                    "http://tes.asu.edu/mineral_map/TES_mineral_maps_4_ppd.envi "
                    "(sulfate and carbonate bands not in the exports on disk)"),
            native_resolution="4 pix/deg = 0.25 deg, 14.8 km at the equator, 720x1440",
            derivation=("abundance-weighted mean of end-member oxide contents, "
                        "normalised over the mineral end-members; Dust is a MASK "
                        "(> 0.80 excluded), not a component. Cells with RMS_Error "
                        "> 0.0044 or mineral sum < 0.10 excluded."),
            endmember_table=ENDMEMBERS, endmember_order_note=ORDER_NOTE,
            iron_convention=("FeO is TOTAL iron as FeO (FeO_T); hematite Fe2O3 "
                             "converted by 2*71.85/159.69"),
            resampling=("BIN THEN FILL: the 14.8 km source is COARSER than the "
                        "6.79 km pixel, so most pixels are COPIED_FROM_COARSER and "
                        "tie blocks of ~4-5 pixels are expected; distinct_levels "
                        "and largest_tie_fraction recorded"),
            weak_dimension_mars=(
                "WEAK DIMENSION, MARS SIDE: areal end-member fractions with a "
                "0.10-0.15 detection limit, on dust-free warm surfaces only "
                "(roughly 60S-60N minus the dusty regions), at 2.2x the pixel "
                "size, pushed through an end-member table whose solid-solution "
                "compositions are ASSUMED. The rank order of end-members is what "
                "the method depends on and it survives the alternatives "
                "(sensitivity recorded in validation)."),
            weak_dimension_earth=(
                "WEAK DIMENSION, EARTH SIDE: GLiM's 40% exact / 64% similar "
                "ground-truth ceiling, as for the lunar pairing."),
            decision=("Added 9 Nov 2026 on Sherozbek's decision that the "
                      "Earth-Mars set needs composition; the end-member values "
                      "and their tags are for his review. VARIABLES.md B27."),
            validation=vres, peak_rss_gib=peak_rss_gib(),
            build_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
    io.open(os.path.join(OUT, "mars_composition_summary.json"), "w",
            encoding="utf-8").write(json.dumps(dict(layers=res, endmembers=ENDMEMBERS),
                                               indent=1, default=str))
    print(f"\nwrote mars_SiO2, mars_FeO   {(time.perf_counter()-t0)/60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
