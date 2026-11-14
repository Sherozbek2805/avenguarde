"""
PHASE 4d / 5 -- Artemis III targets, DI, and the Earth analog ranking.

    python build/phase4d_targets.py

THE TARGET SET
    NASA's nine Artemis III candidate landing regions, October 2024, named
    verbatim from
    nasa.gov/news-release/nasa-provides-update-on-artemis-iii-moon-landing-regions/
    NASA publishes NO geometry for them -- no coordinates, no bounds, no
    polygon, no shapefile. What NASA does state (2022 release, for the
    earlier 13): "Each region is approximately 9.3 by 9.3 miles (15 by 15
    kilometers)" and all lie "within six degrees of latitude of the lunar
    South Pole".

    So each region is placed at the IAU-gazetteer centre of the feature it is
    named after, as a disc of equal area to NASA's 15 x 15 km square
    (radius 8.46 km). Coordinates are planetographic, +East, -180..180,
    control network LOLA 2011 -- the same convention as this cube.

    THREE LIMITATIONS, ALL STRUCTURAL, NONE HIDDEN:
      1. Two pairs COLLAPSE. "Mons Mouton Plateau" and "Mons Mouton" are two
         NASA regions and one IAU feature. So are "Nobile Rim 1" and
         "Nobile Rim 2". Nine named regions give SEVEN distinct points.
      2. Four regions are OFFSET from their feature centre. "Rim" regions sit
         about one crater radius away at an unknown azimuth (Nobile 39.6 km,
         de Gerlache 16.4 km); "Peak near" and "Plain" regions are offset by
         an unknown amount. For de Gerlache the centre is a permanently
         shadowed crater floor, not the illuminated rim NASA means.
      3. A 15 x 15 km region is about 4.7 pixels at Nside 256, below
         k = min(5, distinct target cells). The k rule degrades gracefully,
         but these targets are 4-5 pixels, not hundreds.

RANKING WITHIN EACH BODY, THEN COMPARING
    Lunar values are percentile-transformed over the MOON, Earth values over
    EARTH's reference population. Only the spatial pattern is compared, so
    the 250-300 K lunar diurnal range and Earth's 10-15 K never meet on one
    axis. Absolute scale is irrelevant by construction.
"""

import csv
import io
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

P4 = os.path.join(C.ROOT, "cube", "phase4")
HP = os.path.join(C.ROOT, "cube", "healpix")
REG = os.path.join(C.ROOT, "sources", "artemis3_regions.csv")
NS_MOON, NS_EARTH = 256, 1024
REGION_KM2 = 15.0 * 15.0
RADIUS_KM = float(np.sqrt(REGION_KM2 / np.pi))      # 8.46 km, equal area
R_MOON = 1737.4
TOPN = 25


def rank_pct(v):
    n = v.size
    o = np.argsort(v, kind="stable")
    r = np.empty(n, dtype=np.float64)
    sv = v[o]
    i = 0
    while i < n:
        j = i + 1
        while j < n and sv[j] == sv[i]:
            j += 1
        r[o[i:j]] = (i + j - 1) / 2.0
        i = j
    return (r + 0.5) / n


def main():
    cfg = json.load(io.open(os.path.join(P4, "phase4c_summary.json"),
                            encoding="utf-8"))["earth_moon"]
    dims = cfg["dimensions"]
    dbar = cfg["d_bar"]
    thr = cfg["di_threshold"]
    W = np.load(os.path.join(P4, "whiten_earth_moon.npy"))
    cen = np.load(os.path.join(P4, "center_earth_moon.npy"))
    mu, sd = cen[0], cen[1]

    print("=" * 78)
    print("PHASE 4d / 5 -- ARTEMIS III TARGETS, DI, EARTH ANALOG RANKING")
    print("=" * 78)
    print(f"{len(dims)} dimensions, d_bar {dbar:.4f}, DI threshold {thr:.4f}")
    print(f"target disc radius {RADIUS_KM:.2f} km (equal area to NASA's "
          f"15 x 15 km region)")

    # ---------- lunar percentiles, ranked WITHIN the Moon ----------------
    from astropy_healpix import HEALPix
    from astropy import units as u
    hp = HEALPix(nside=NS_MOON, order="nested")
    npix_m = int(hp.npix)
    Lm = np.full((len(dims), npix_m), np.nan)
    for i, d in enumerate(dims):
        p = os.path.join(HP, f"moon_{d}_nside{NS_MOON}.npy")
        if not os.path.exists(p):
            raise SystemExit(f"STOP: moon layer missing: {p}")
        Lm[i] = np.load(p)
    good = np.all(np.isfinite(Lm), axis=0)
    print(f"\nMoon: {int(good.sum()):,} of {npix_m:,} pixels have all "
          f"{len(dims)} dimensions ({100*good.mean():.3f}%)")
    LP = np.full_like(Lm, np.nan)
    for i in range(len(dims)):
        LP[i, good] = rank_pct(Lm[i, good])

    # ---------- targets ---------------------------------------------------
    rows = list(csv.DictReader(io.open(REG, encoding="utf-8")))
    plon, plat = hp.healpix_to_lonlat(np.arange(npix_m))
    plon = plon.to_value(u.deg); plat = plat.to_value(u.deg)
    plon = np.where(plon > 180.0, plon - 360.0, plon)
    rad = np.radians
    results = []
    print(f"\n{'region':24s} {'px':>4s} {'allvalid':>9s} {'DI':>8s} "
          f"{'covered':>8s}  offset")
    for r in rows:
        la0, lo0 = float(r["center_lat"]), float(r["center_lon"])
        d_ang = np.degrees(np.arccos(np.clip(
            np.sin(rad(plat)) * np.sin(rad(la0)) +
            np.cos(rad(plat)) * np.cos(rad(la0)) *
            np.cos(rad(plon - lo0)), -1, 1)))
        sel = d_ang <= np.degrees(RADIUS_KM / R_MOON)
        if sel.sum() == 0:                      # always keep the nearest pixel
            sel = d_ang <= d_ang.min() + 1e-9
        ok = sel & good
        n_px, n_ok = int(sel.sum()), int(ok.sum())
        if n_ok == 0:
            print(f"{r['nasa_region']:24s} {n_px:4d} {0:9d}  -- no valid data")
            continue
        tgt = np.median(LP[:, ok], axis=1)      # median percentile vector
        zt = ((tgt - mu) / sd) @ W
        results.append((r, n_px, n_ok, tgt, zt, sel))

    # ---------- Earth side -------------------------------------------------
    P = np.load(os.path.join(P4, "percentiles.npy"))
    meta = json.load(io.open(os.path.join(P4, "phase4a_summary.json"),
                             encoding="utf-8"))
    names = meta["names"]
    idx = [names.index(d) for d in dims]
    XE = P[idx].T.astype(np.float64)
    ZE = ((XE - mu) / sd) @ W
    refpix = np.load(os.path.join(P4, "ref_pixels.npy"))
    complete = np.load(os.path.join(P4, "complete_mask.npy"))
    earth_pix = refpix[complete]
    print(f"\nEarth reference cloud: {ZE.shape[0]:,} pixels, "
          f"{ZE.shape[1]} whitened dimensions")

    from scipy.spatial import cKDTree
    tree = cKDTree(ZE)
    hpE = HEALPix(nside=NS_EARTH, order="nested")

    out = []
    for r, n_px, n_ok, tgt, zt, sel in results:
        dist, who = tree.query(zt, k=TOPN, workers=-1)
        di = float(dist[0] / dbar)
        cov = di <= thr
        print(f"{r['nasa_region']:24s} {n_px:4d} {n_ok:9d} {di:8.4f} "
              f"{'YES' if cov else 'no':>8s}  {r['offset_class']}"
              f"{'' if r['offset_class']=='CENTRE' else ' ~'+r['offset_km_est']+' km'}")
        lonE, latE = hpE.healpix_to_lonlat(earth_pix[who])
        lonE = lonE.to_value(u.deg); latE = latE.to_value(u.deg)
        lonE = np.where(lonE > 180.0, lonE - 360.0, lonE)
        out.append(dict(
            nasa_region=r["nasa_region"], iau_feature=r["iau_feature"],
            center_lat=float(r["center_lat"]), center_lon=float(r["center_lon"]),
            offset_class=r["offset_class"],
            offset_km_est=float(r["offset_km_est"]),
            target_pixels=n_px, target_pixels_valid=n_ok,
            k_effective=int(min(5, n_ok)),
            target_percentiles={d: float(tgt[i]) for i, d in enumerate(dims)},
            DI=di, covered=bool(cov), di_threshold=thr, d_bar=dbar,
            top_matches=[dict(rank=i + 1, lat=float(latE[i]),
                              lon=float(lonE[i]),
                              distance=float(dist[i]),
                              DI=float(dist[i] / dbar))
                         for i in range(min(TOPN, len(dist)))],
            caveat=r["notes"]))

    io.open(os.path.join(P4, "phase4d_targets.json"), "w",
            encoding="utf-8").write(json.dumps(dict(
                dimensions=dims, d_bar=dbar, di_threshold=thr,
                radius_km=RADIUS_KM, nside_moon=NS_MOON,
                nside_earth=NS_EARTH,
                source=("NASA Artemis III candidate landing regions, "
                        "October 2024 update; coordinates from the IAU/USGS "
                        "Gazetteer of Planetary Nomenclature, planetographic "
                        "+East -180..180, control network LOLA 2011"),
                structural_limitations=[
                    "Mons Mouton Plateau and Mons Mouton are two NASA "
                    "regions and ONE IAU feature; Nobile Rim 1 and Nobile "
                    "Rim 2 likewise. Nine regions give SEVEN distinct points.",
                    "Four regions are offset from their feature centre by an "
                    "unknown azimuth: Nobile ~39.6 km, de Gerlache ~16.4 km, "
                    "Cabeus B and Slater unknown. For de Gerlache the centre "
                    "is a permanently shadowed floor, not the lit rim.",
                    "A 15x15 km region is ~4.7 pixels at Nside 256, below "
                    "k = min(5, distinct target cells)."],
                targets=out,
                built_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
                indent=1))
    print(f"\nwrote {P4}/phase4d_targets.json")

    print(f"\nTOP 5 EARTH ANALOGS PER REGION (lat, lon, DI)")
    for o in out:
        print(f"\n  {o['nasa_region']}  (DI {o['DI']:.4f}, "
              f"{'COVERED' if o['covered'] else 'OUTSIDE Earth cover'})")
        for m in o["top_matches"][:5]:
            print(f"     {m['rank']:2d}. {m['lat']:+8.3f}, {m['lon']:+9.3f}   "
                  f"DI {m['DI']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
