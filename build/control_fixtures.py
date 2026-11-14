"""
CONTROL FIXTURES -- the exact pixels the hackathon-day control tests run on.

    python build/control_fixtures.py

This is NOT engine code. It computes no distance, no DI and no p-value. It
only fixes WHICH pixels the controls use, so that the pass criteria in
docs/TEST_SPEC_2026-11-10.md are written against inputs chosen before any
result exists. Choosing the control patch after seeing a result would be
p-hacking the control.

Writes contract/control_fixtures.json. Reads the cube only.

RULES, stated before running
  * A control patch is a centre pixel plus its nearest neighbours by
    great-circle distance, 20 cells in all, drawn only from pixels that are
    complete in every ranking dimension of the pairing.
  * POSITIVE (Earth): centre = the reference pixel nearest Yungay, Atacama
    (-24.08, -69.92), the driest core of the desert and a long-used Mars
    analog station.
  * NEGATIVE (Moon): centre = the coldest complete pixel of moon_temp_level.
  * NEGATIVE (Mars): centre = the coldest complete pixel of mars_temp_level.
  * SECOND POSITIVE: the Apollo field-training sites from the catalogue, as
    Earth pixels; and the six Apollo landing sites as Moon patches.
"""

import io
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

HP = os.path.join(C.ROOT, "cube", "healpix")
P4 = os.path.join(C.ROOT, "cube", "phase4")
OUT = os.path.join(C.ROOT, "contract", "control_fixtures.json")
N_CELLS = 20
NSIDE = {"earth": 1024, "moon": 256, "mars": 512}
YUNGAY = (-24.08, -69.92)
APOLLO_LANDING = [
    ("Apollo 11", 0.674, 23.473), ("Apollo 12", -3.012, -23.422),
    ("Apollo 14", -3.645, -17.471), ("Apollo 15", 26.132, 3.634),
    ("Apollo 16", -8.973, 15.500), ("Apollo 17", 20.191, 30.772),
]


def hpx(body):
    from astropy_healpix import HEALPix
    return HEALPix(nside=NSIDE[body], order="nested")


def lonlat(body, pix):
    lo, la = hpx(body).healpix_to_lonlat(np.asarray(pix))
    lo = ((lo.deg + 180.0) % 360.0) - 180.0
    return lo, la.deg


def to_pix(body, lat, lon):
    from astropy import units as u
    return int(hpx(body).lonlat_to_healpix(lon * u.deg, lat * u.deg))


def unit(lat, lon):
    la, lo = np.radians(lat), np.radians(lon)
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo),
                     np.sin(la)], axis=-1)


def nearest_patch(body, centre_pix, allowed, n):
    """centre + nearest (n-1) allowed pixels by great-circle distance."""
    lo_c, la_c = lonlat(body, [centre_pix])
    cand = np.flatnonzero(allowed)
    lo, la = lonlat(body, cand)
    d = np.arccos(np.clip(unit(la, lo) @ unit(la_c, lo_c)[0], -1.0, 1.0))
    o = np.argsort(d, kind="stable")[:n]
    km = d[o] * C.BODY_RADIUS_M[body] / 1000.0
    return cand[o].astype(int).tolist(), float(km.max())


def complete(body, dims):
    ok = None
    for d in dims:
        v = np.load(os.path.join(HP, f"{body}_{d}_nside{NSIDE[body]}.npy"),
                    mmap_mode="r")
        f = np.isfinite(v)
        ok = f if ok is None else (ok & f)
    return ok


def patch_record(body, name, why, pix, radius_km, extra=None):
    lo, la = lonlat(body, pix)
    r = dict(name=name, body=body, nside=NSIDE[body], ordering="nested",
             why=why, n_cells=len(pix), healpix_pixels=pix,
             centre_lat=round(float(la[0]), 4), centre_lon=round(float(lo[0]), 4),
             abs_lat_range=[round(float(np.abs(la).min()), 3),
                            round(float(np.abs(la).max()), 3)],
             patch_radius_km=round(radius_km, 2))
    if extra:
        r.update(extra)
    return r


def main():
    cfg = json.load(io.open(os.path.join(P4, "phase4c_summary.json"),
                            encoding="utf-8"))
    dims = {k: cfg[k]["dimensions"] for k in ("earth_moon", "earth_mars")}
    out = dict(
        written_by="build/control_fixtures.py",
        note="Pixel selections only. No distance, DI or p-value is computed "
             "here; those are hackathon-day engine work.",
        n_cells=N_CELLS, dimensions=dims, controls={})

    # ---- Earth: complete in the union of both pairings' dimensions
    e_dims = sorted(set(dims["earth_moon"]) | set(dims["earth_mars"]))
    ref = np.load(os.path.join(HP, "earth_reference_mask_nside1024.npy"),
                  mmap_mode="r") > 0.5
    e_ok = complete("earth", e_dims) & ref
    print(f"Earth complete reference pixels (union of dims): {int(e_ok.sum()):,}")
    c = to_pix("earth", *YUNGAY)
    if not e_ok[c]:
        cand, _ = nearest_patch("earth", c, e_ok, 1)
        print(f"  Yungay pixel {c} is not complete; nearest complete {cand[0]}")
        c = cand[0]
    pix, rk = nearest_patch("earth", c, e_ok, N_CELLS)
    t = np.load(os.path.join(HP, "earth_temp_level_nside1024.npy"), mmap_mode="r")
    out["controls"]["positive_atacama"] = patch_record(
        "earth", "Atacama, Yungay core", "Earth matched against Earth: the "
        "patch is its own best analog. Easiest possible question.",
        pix, rk, dict(temp_level_median_K=round(float(np.median(t[pix])), 2)))
    print("  Atacama patch:", out["controls"]["positive_atacama"]["centre_lat"],
          out["controls"]["positive_atacama"]["centre_lon"], f"radius {rk:.1f} km")

    # ---- Moon and Mars: coldest complete pixel
    for body, key in (("moon", "earth_moon"), ("mars", "earth_mars")):
        ok = np.asarray(complete(body, dims[key]))
        t = np.load(os.path.join(HP, f"{body}_temp_level_nside{NSIDE[body]}.npy"))
        tt = np.where(ok, t, np.inf)
        c = int(np.argmin(tt))
        pix, rk = nearest_patch(body, c, ok, N_CELLS)
        rec = patch_record(
            body, f"coldest complete patch, {body}",
            "A place Earth has no version of. Must NOT come back significant.",
            pix, rk, dict(temp_level_centre_K=round(float(t[c]), 2),
                          temp_level_median_K=round(float(np.median(t[pix])), 2),
                          complete_pixels_on_body=int(ok.sum()),
                          body_percentile_of_centre=round(
                              float((t[ok] < t[c]).mean()), 6)))
        out["controls"][f"negative_{body}"] = rec
        print(f"  {body} negative: lat {rec['centre_lat']} lon {rec['centre_lon']} "
              f"T {rec['temp_level_centre_K']} K, radius {rk:.1f} km, "
              f"complete pixels {int(ok.sum()):,}")
        if body == "moon":
            moon_ok = ok

    # ---- Apollo landing sites as Moon patches
    land = []
    for name, la, lo in APOLLO_LANDING:
        c = to_pix("moon", la, lo)
        pix, rk = nearest_patch("moon", c, moon_ok, N_CELLS)
        land.append(patch_record("moon", name, "Apollo landing site; the "
                                 "terrain the training sites were chosen for.",
                                 pix, rk, dict(centre_complete=bool(moon_ok[c]))))
    out["controls"]["apollo_landing_sites"] = land
    print(f"  Apollo landing patches: {len(land)}, "
          f"centre complete {[r['centre_complete'] for r in land]}")

    # ---- Apollo training sites as Earth pixels
    gj = json.load(io.open(os.path.join(
        C.ROOT, "export", "site_assets", "catalogue",
        "apollo_training_sites.geojson"), encoding="utf-8"))
    tr = []
    for f in gj["features"]:
        lo, la = f["geometry"]["coordinates"][:2]
        p = to_pix("earth", la, lo)
        nm = f["properties"].get("name") or f["properties"].get("site") or "?"
        near, _ = nearest_patch("earth", p, e_ok, 1)
        lo_n, la_n = lonlat("earth", near)
        dk = float(np.arccos(np.clip(unit(np.array([la]), np.array([lo]))[0]
                                     @ unit(la_n, lo_n)[0], -1, 1))
                   * C.BODY_RADIUS_M["earth"] / 1000.0)
        tr.append(dict(name=nm, lat=la, lon=lo, healpix_pixel=p,
                       in_reference=bool(ref[p]), complete=bool(e_ok[p]),
                       nearest_complete_pixel=int(near[0]),
                       nearest_complete_km=round(dk, 2)))
    out["controls"]["apollo_training_sites"] = tr
    print(f"  Apollo training sites: {len(tr)}, complete "
          f"{sum(r['complete'] for r in tr)}")
    for r in tr:
        print(f"     {r['name'][:40]:40s} {r['lat']:8.3f} {r['lon']:9.3f} "
              f"complete={r['complete']} nearest {r['nearest_complete_km']} km")

    tmp = OUT + ".part"
    with io.open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    os.replace(tmp, OUT)
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
