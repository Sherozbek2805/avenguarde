"""
PHASE 3d -- MARS THERMAL INERTIA from MGS TES (Putzig & Mellon 2007).
DECIDED by Sherozbek, 9 Nov 2026: Mars needs measured thermal layers.

    python build/phase3d_thermal_inertia.py [--test]

WHY THIS AND NOT A TEMPERATURE PAIR
    A source search on 9 Nov 2026 (VARIABLES.md B27) found NO public gridded,
    measured Mars surface-temperature map at pixel scale: TES temperatures
    exist only as per-observation records, the THEMIS IR mosaics are
    stretched 8-bit renderings, MCS and EMIRS maps are degrees-scale. The one
    measured Mars thermal product at the right scale is this one: thermal
    inertia at 20 pixels per degree, 2.96 km, from three Mars years of TES
    bolometer temperatures. It is a MATERIAL property (grain size, rock
    abundance, induration), which for an analog question is the better
    quantity anyway (B23). It BINS to the 6.79 km pixel; nothing is copied.

THE SOURCE, READ FROM ITS OWN LABEL (rule A)
    mgst_9001/data/global_ti_{night,day}_2007.img  3600 x 7200, MSB 16-bit
    signed integer, units J m-2 K-1 s-1/2 (tiu), simple cylindrical 20 ppd,
    lat +90..-90, lon -180..180, planetocentric, east positive. No
    SCALING_FACTOR, no MISSING_CONSTANT. The readme states the derived range
    is 5..5000 tiu and that higher and lower values are NOT computed; the
    interpolation mask is 0 where the map was INFILLED (under 8%).
    Nightside = southbound (~2 AM), dayside = northbound (~2 PM), stated as
    nightside/dayside only in the label.

RULES
    nodata     value outside 5..5000 (README) OR mask == 0 (infilled, not
               measured). Both counted and recorded. GDAL is not involved.
    range gate [5, 5000] tiu, stated in advance -- the README's own range
    binning   area-weighted mean onto HEALPix NESTED Nside 512; gaps stay
               NaN (the source is finer, so an empty pixel is a real gap)
    layers    mars_thermal_inertia      nightside, THE candidate dimension
              mars_thermal_inertia_day  dayside, DIAGNOSTIC: day minus night
                                        apparent TI flags heterogeneous
                                        surfaces (Putzig & Mellon 2007)

PAIRING
    A variable counts only if both bodies have it. This layer becomes an
    Earth-Mars dimension the moment earth_thermal_inertia exists; until then
    it is a Mars characterization layer by the intersection rule alone.
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
from phase1_dems import peak_rss_gib, say_peak
from phase2_terrain import show, validate
from phase3_thermal import bin_grid

SRC = os.path.join(C.ROOT, "mgst_9001 (2)", "mgst_9001", "mgst_9001", "data")
OUT = os.path.join(C.ROOT, "cube", "healpix")
BODY, NSIDE = "mars", C.NSIDE["mars"]
H, W = 3600, 7200
GATE = (5.0, 5000.0)
DECISION = ("Added 9 Nov 2026 on Sherozbek's decision that the Earth-Mars set "
            "needs measured thermal and compositional layers, not only "
            "elevation-derived ones. VARIABLES.md B27.")


def read_pds(name, dtype, shape):
    p = os.path.join(SRC, name)
    a = np.fromfile(p, dtype=dtype)
    if a.size != shape[0] * shape[1]:
        raise SystemExit(f"STOP: {name} has {a.size} samples, expected "
                         f"{shape[0]*shape[1]} -- wrong dtype or truncated")
    return a.reshape(shape), p


def label_check(lbl, expect):
    txt = io.open(os.path.join(SRC, lbl), encoding="latin1").read()
    for k, v in expect.items():
        if f"{k}" not in txt or v not in txt:
            raise SystemExit(f"STOP: {lbl} does not state {k} = {v}")


def load_side(side):
    label_check(f"global_ti_{side}_2007.lbl",
                {"SAMPLE_TYPE": "MSB_INTEGER", "SAMPLE_BITS": "16",
                 "LINES": "3600", "LINE_SAMPLES": "7200",
                 "MAP_RESOLUTION": "20.0", "MAXIMUM_LATITUDE": "90.00",
                 "WESTERNMOST_LONGITUDE": "-180.0"})
    label_check(f"global_ti_msk_{side}_2007.lbl",
                {"SAMPLE_BITS": "8", "LINES": "3600"})
    raw, p = read_pds(f"global_ti_{side}_2007.img", ">i2", (H, W))
    msk, pm = read_pds(f"global_ti_msk_{side}_2007.img", "u1", (H, W))
    val = raw.astype(np.float32)
    in_range = (raw >= GATE[0]) & (raw <= GATE[1])
    measured = msk != 0
    n_zero = int((raw == 0).sum())
    n_out = int((~in_range & (raw != 0)).sum())
    n_infill = int((in_range & ~measured).sum())
    keep = in_range & measured
    val[~keep] = np.nan
    lat_rows = 90.0 - (np.arange(H) + 0.5) * (180.0 / H)
    pole_rows = np.abs(lat_rows) > 87.0
    stats = dict(
        source_file=os.path.relpath(p, C.ROOT).replace(os.sep, "/"),
        mask_file=os.path.relpath(pm, C.ROOT).replace(os.sep, "/"),
        cells=H * W, raw_min=int(raw.min()), raw_max=int(raw.max()),
        cells_zero_not_computed=n_zero,
        cells_nonzero_outside_5_5000=n_out,
        cells_infilled_excluded=n_infill,
        cells_kept=int(keep.sum()), pct_kept=round(100.0 * keep.mean(), 4),
        pct_kept_within_87deg=round(100.0 * keep[~pole_rows].mean(), 4),
        infilled_pct_of_in_range=round(100.0 * n_infill / max(in_range.sum(), 1), 4),
        kept_p1=float(np.percentile(val[keep], 1)),
        kept_p50=float(np.median(val[keep])),
        kept_p99=float(np.percentile(val[keep], 99)))
    return val, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="measure, write nothing")
    a = ap.parse_args()
    print("=" * 78)
    print("PHASE 3d -- MARS THERMAL INERTIA, MGS TES 20 ppd (Putzig & Mellon 2007)")
    print("=" * 78)
    print(f"RANGE GATE, stated BEFORE the run: {GATE[0]:g} .. {GATE[1]:g} tiu "
          f"(the README's derived range); mask == 0 (infilled) EXCLUDED")
    C.require_disk(2.0, C.ROOT)
    t0 = time.perf_counter()
    lat = 90.0 - (np.arange(H) + 0.5) * (180.0 / H)
    lon = -180.0 + (np.arange(W) + 0.5) * (360.0 / W)
    layers, stats = {}, {}
    for side, nm in (("night", "thermal_inertia"), ("day", "thermal_inertia_day")):
        v, s = load_side(side)
        layers[nm] = v
        stats[nm] = s
        print(f"  {side:5s}: raw {s['raw_min']}..{s['raw_max']}; zero (not "
              f"computed) {s['cells_zero_not_computed']:,}; outside 5..5000 "
              f"{s['cells_nonzero_outside_5_5000']:,}; infilled excluded "
              f"{s['cells_infilled_excluded']:,} ({s['infilled_pct_of_in_range']:.2f}% "
              f"of in-range); kept {s['pct_kept']:.3f}% of cells, "
              f"{s['pct_kept_within_87deg']:.3f}% within 87 deg; p50 "
              f"{s['kept_p50']:.0f} tiu")
    say_peak("TI read")
    acc = bin_grid(layers, lat, lon, NSIDE, layers)
    print(f"  binned {H}x{W} = {H*W:,} cells (2.96 km) onto {12*NSIDE**2:,} "
          f"pixels (6.79 km): source finer everywhere, nothing copied")
    res = {}
    for nm in layers:
        arr, nfilled, sup = acc.finish(nm)
        v = np.isfinite(arr)
        out_of = int(np.sum(v & ((arr < GATE[0]) | (arr > GATE[1]))))
        d_n = np.isfinite(layers["thermal_inertia"])
        extra = dict(
            healpix_pixels_filled=nfilled, units="tiu = J m-2 K-1 s-1/2",
            range_gate_stated_in_advance=list(GATE),
            pixels_outside_stated_gate=out_of, range_gate_pass=bool(out_of == 0),
            source=stats[nm], local_time=("nightside, southbound, ~2 AM" if nm ==
                                          "thermal_inertia" else
                                          "dayside, northbound, ~2 PM"),
            record="three Mars years, OCK 1583-24346, Feb 1999 - Apr 2004",
            surface_temperature_window_K=[160, 400])
        vres = validate(arr, NSIDE, f"{BODY}_{nm}", "tiu", extra, support=sup)
        show(vres)
        print(f"    {'':34s} range gate [{GATE[0]:g},{GATE[1]:g}] tiu: "
              f"{'PASS' if out_of == 0 else f'FAIL, {out_of:,} outside'}")
        res[nm] = vres
        if a.test:
            continue
        path = os.path.join(OUT, f"{BODY}_{nm}_nside{NSIDE}.npy")
        spath = os.path.join(OUT, f"{BODY}_{nm}_support_nside{NSIDE}.npy")
        C.atomic_save(path, arr)
        C.atomic_save(spath, sup)
        rel = lambda p: os.path.relpath(p, C.ROOT).replace(os.sep, "/")
        entry = dict(
            phase="3d", body=BODY, variable=nm, units="tiu = J m-2 K-1 s-1/2",
            nside=NSIDE, order="nested", file=rel(path), support_file=rel(spath),
            source_files=[stats[nm]["source_file"], stats[nm]["mask_file"],
                          "mgst_9001 (2)/mgst_9001/mgst_9001/aareadme.txt"],
            source_resolves=True,
            source=("MGS-M-TES-5-TIMAP-V1.0, mgst_9001, Putzig & Mellon (2007) "
                    "Icarus 191:68-94, doi:10.1016/j.icarus.2007.05.013; "
                    "PDS DOI 10.17189/1519489"),
            native_resolution="20 pix/deg, 2.96 km, 3600x7200, simple cylindrical",
            label_read=("MSB 16-bit signed integer, no scaling, no "
                        "MISSING_CONSTANT -- nodata taken from the README's "
                        "derived range 5..5000 and the interpolation mask "
                        "(rule A: never GDAL's nodata)"),
            nodata_rule=("value outside 5..5000 tiu (not computed) OR mask == 0 "
                         "(infilled by interpolation, not measured). Both "
                         "excluded and counted in validation.source."),
            binning=("area-weighted mean onto HEALPix NESTED with cos(lat) "
                     "weights; the 2.96 km source is finer than the 6.79 km "
                     "pixel everywhere, so every valid pixel is BINNED and an "
                     "empty pixel is a real gap (poleward of 87 deg, and "
                     "clusters of infilled cells)"),
            quantity=("thermal inertia, a MATERIAL property: grain size, rock "
                      "abundance, induration. Measured from TES bolometer "
                      "temperatures with a thermal model, not a temperature."),
            gates="range (stated), coverage, support",
            decision=DECISION,
            validation=vres, peak_rss_gib=peak_rss_gib(),
            build_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        if nm == "thermal_inertia_day":
            entry.update(
                role="diagnostic: dayside apparent thermal inertia",
                matching_eligible=False,
                matching_eligible_reason=(
                    "The nightside map is the standard thermal inertia; the "
                    "dayside map differs from it where the surface is "
                    "heterogeneous (rocks over fines, duricrust, slopes). "
                    "Carried so day-minus-night can be reported in step 9, "
                    "never as a second dimension of the same quantity."))
        else:
            entry.update(
                pairing_note=("Counts as an Earth-Mars dimension only once "
                              "earth_thermal_inertia exists (apparent thermal "
                              "inertia from MODIS LST and albedo). The "
                              "intersection rule enforces this; no flag is "
                              "needed."),
                not_a_temperature=(
                    "temp_level and temp_range_diurnal for Mars remain the MCD "
                    "layers flagged matching_eligible false. No measured "
                    "gridded surface-temperature map exists at pixel scale "
                    "(search of 9 Nov 2026, VARIABLES.md B27)."))
        C.manifest_write(f"{BODY}_{nm}", entry)
    if not a.test:
        io.open(os.path.join(OUT, "phase3d_mars_summary.json"), "w",
                encoding="utf-8").write(json.dumps(res, indent=1, default=str))
        print(f"\nwrote mars_thermal_inertia and mars_thermal_inertia_day")
    print(f"\nMARS TI {(time.perf_counter()-t0)/60:.1f} min   peak RAM "
          f"{peak_rss_gib()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
