"""
THE PRESET TARGETS -- which pixels each one is, and how much data it has.

    python build/targets.py

This is NOT engine code. It computes no distance, DI or p-value. It turns a
sourced list of places into HEALPix pixel sets and counts how many of those
pixels carry every ranking dimension. Step 5 of the spec starts from its
output.

Reads   sources/targets_moon_artemis3_v2.csv      nine Artemis III regions
        sources/targets_mars_v1.csv               Mars candidate sites
Writes  contract/targets_moon.json
        contract/targets_mars.json

ONE RULE FOR "WHICH PIXELS"
    A pixel belongs to a target when its CENTRE lies inside the region.
    N cells times the cell area then equals the region area, to within the
    grid. (The 9 Nov prototype used this; the contract example used "any
    overlap", which returned twice as many cells. One convention: centres.)

    disc      centre + radius_km, great-circle distance
    polygon   vertices given as lon/lat; tested in a stereographic plane
              centred on the region, where a small polygon is undistorted

WHAT IS REPORTED, per target and per pairing
    cells                 pixels whose centre is inside
    cells_complete        of those, pixels with EVERY ranking dimension
    (no k)                the score uses ALL of a target's cells (B36), so a
                          target needs only one usable cell
    constructions         TWO per target where composition is patchy:
                          "without_composition" (terrain + thermal) over
                          every cell that has those, and "all_dimensions"
                          over the cells that also have SiO2 and FeO.
                          Composition covers 49% of Mars, in patches, so a
                          100 km zone is rarely complete. The PRIMARY
                          construction is the one that covers at least 90%
                          of the target's cells; the other is the second
                          construction the spec asks for (invariant 3: no
                          result from a single construction).
    dims_available        dimension count of the primary construction
    abs_lat_band          centre |latitude| +/- 2 degrees, for the null
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

HP = os.path.join(C.ROOT, "cube", "healpix")
P4 = os.path.join(C.ROOT, "cube", "phase4")
SRC = os.path.join(C.ROOT, "sources")
OUT = os.path.join(C.ROOT, "contract")
NSIDE = {"moon": 256, "mars": 512}
PAIR = {"moon": "earth_moon", "mars": "earth_mars"}
FILES = {"moon": "targets_moon_artemis3_v2.csv", "mars": "targets_mars_v1.csv"}
COMPOSITION = ("SiO2", "FeO")
BAND_DEG = 2.0


def unit(lat, lon):
    la, lo = np.radians(lat), np.radians(lon)
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo),
                     np.sin(la)], axis=-1)


def stereo(lat, lon, lat0, lon0, R):
    """Oblique stereographic plane centred on (lat0, lon0), km."""
    la, lo = np.radians(lat), np.radians(lon)
    a0, o0 = np.radians(lat0), np.radians(lon0)
    cosc = np.sin(a0) * np.sin(la) + np.cos(a0) * np.cos(la) * np.cos(lo - o0)
    k = 2.0 * R / (1.0 + cosc)
    x = k * np.cos(la) * np.sin(lo - o0)
    y = k * (np.cos(a0) * np.sin(la) - np.sin(a0) * np.cos(la) * np.cos(lo - o0))
    return x, y


def densify_sps(vlon, vlat, R, n=40):
    """Rebuild polygon edges as straight lines in SOUTH POLAR STEREOGRAPHIC.

    The Artemis III regions were drawn as rectangles in that plane and are
    published as four corners. A straight line between two corners in
    longitude / latitude is a different curve, so the edges are rebuilt
    where they are straight, then returned as lon / lat points.
    """
    rho = 2.0 * R * np.tan(np.radians(90.0 + vlat) / 2.0)
    x, y = rho * np.sin(np.radians(vlon)), rho * np.cos(np.radians(vlon))
    xs, ys = [], []
    m = len(x)
    for i in range(m):
        j = (i + 1) % m
        t = np.linspace(0.0, 1.0, n, endpoint=False)
        xs.append(x[i] + t * (x[j] - x[i]))
        ys.append(y[i] + t * (y[j] - y[i]))
    xs, ys = np.concatenate(xs), np.concatenate(ys)
    r = np.hypot(xs, ys)
    return (np.degrees(np.arctan2(xs, ys)),
            2.0 * np.degrees(np.arctan(r / (2.0 * R))) - 90.0)


def in_polygon(x, y, vx, vy):
    inside = np.zeros(x.shape, dtype=bool)
    n = len(vx)
    j = n - 1
    for i in range(n):
        cond = ((vy[i] > y) != (vy[j] > y))
        with np.errstate(divide="ignore", invalid="ignore"):
            xi = (vx[j] - vx[i]) * (y - vy[i]) / (vy[j] - vy[i]) + vx[i]
        inside ^= cond & (x < xi)
        j = i
    return inside


def main():
    from astropy_healpix import HEALPix
    cfg = json.load(io.open(os.path.join(P4, "phase4c_summary.json"),
                            encoding="utf-8"))
    print("=" * 78)
    print("PRESET TARGETS -- pixel sets and data coverage (no distances)")
    print("=" * 78)
    for body in ("moon", "mars"):
        path = os.path.join(SRC, FILES[body])
        if not os.path.exists(path):
            print(f"{body}: {FILES[body]} not on disk yet -- skipped")
            continue
        ns = NSIDE[body]
        R = C.BODY_RADIUS_M[body] / 1000.0
        hp = HEALPix(nside=ns, order="nested")
        lon_p, lat_p = hp.healpix_to_lonlat(np.arange(hp.npix))
        lon_p = ((lon_p.deg + 180.0) % 360.0) - 180.0
        lat_p = lat_p.deg
        up = unit(lat_p, lon_p)
        dims = cfg[PAIR[body]]["dimensions"]
        fin = {d: np.isfinite(np.load(os.path.join(
            HP, f"{body}_{d}_nside{ns}.npy"), mmap_mode="r")) for d in dims}
        ok_all = np.logical_and.reduce([fin[d] for d in dims])
        no_comp = [d for d in dims if d not in COMPOSITION]
        ok_nc = np.logical_and.reduce([fin[d] for d in no_comp])
        cell_km2 = 4.0 * np.pi * R * R / hp.npix
        rows = list(csv.DictReader(io.open(path, encoding="utf-8", newline="")))
        out = []
        print(f"\n{body.upper()}  Nside {ns}, cell {cell_km2:.1f} km2, "
              f"{len(dims)} dimensions, {len(rows)} targets")
        print(f"{'name':30s} {'lat':>8s} {'lon':>9s} {'cells':>6s} "
              f"{'all dims':>9s} {'no comp.':>9s} {'dims':>5s}")
        for r in rows:
            la0, lo0 = float(r["center_lat"]), float(r["center_lon"])
            lo0 = ((lo0 + 180.0) % 360.0) - 180.0
            if r["geometry"] == "polygon":
                v = json.loads(r["vertices_lonlat"])
                vlon = np.array([p[0] for p in v], dtype=float)
                vlat = np.array([p[1] for p in v], dtype=float)
                if r.get("edges_straight_in") == "south_polar_stereographic":
                    vlon, vlat = densify_sps(vlon, vlat, R)
                near = np.arccos(np.clip(up @ unit(la0, lo0), -1, 1)) * R < 400.0
                x, y = stereo(lat_p[near], lon_p[near], la0, lo0, R)
                vx, vy = stereo(vlat, vlon, la0, lo0, R)
                sel = np.zeros(hp.npix, dtype=bool)
                sel[np.flatnonzero(near)[in_polygon(x, y, vx, vy)]] = True
                area = 0.5 * abs(np.dot(vx, np.roll(vy, -1)) - np.dot(vy, np.roll(vx, -1)))
                geom = dict(type="polygon", vertices_lonlat=v,
                            edges_straight_in=r.get("edges_straight_in") or "great circle",
                            area_km2=round(float(r["area_km2_ground"]) if r.get("area_km2_ground") else float(area), 1))
            else:
                rad = float(r["radius_km"])
                d = np.arccos(np.clip(up @ unit(la0, lo0), -1, 1)) * R
                sel = d <= rad
                geom = dict(type="disc", radius_km=rad,
                            area_km2=round(float(np.pi * rad * rad), 1))
            pix = np.flatnonzero(sel)
            n_all = int(ok_all[pix].sum())
            n_nc = int(ok_nc[pix].sum())
            cons = dict(
                all_dimensions=dict(
                    n_dims=len(dims), dimensions=dims, cells=n_all,
                    share_of_target=round(n_all / max(1, pix.size), 3),
                    usable=bool(n_all >= 1)),
                without_composition=dict(
                    n_dims=len(no_comp), dimensions=no_comp, cells=n_nc,
                    share_of_target=round(n_nc / max(1, pix.size), 3),
                    usable=bool(n_nc >= 1)))
            primary = ("all_dimensions" if n_all >= 0.9 * pix.size
                       else "without_composition")
            secondary = [c for c in cons if c != primary and cons[c]["usable"]
                         and cons[c]["cells"] != cons[primary]["cells"]]
            has_comp = primary == "all_dimensions"
            dims_av = cons[primary]["n_dims"]
            n_use = cons[primary]["cells"]
            L = abs(la0)
            rec = dict(
                name=r["name"], body=body, center_lat=la0, center_lon=lo0,
                geometry=geom, nside=ns, ordering="nested",
                membership_rule="pixel centre inside the region",
                healpix_pixels=pix.astype(int).tolist(),
                cells=int(pix.size),
                cells_complete_all_dims=n_all,
                cells_complete_without_composition=n_nc,
                dims_available=dims_av,
                dimensions=(dims if has_comp else no_comp),
                primary_construction=primary,
                second_construction=(secondary[0] if secondary else None),
                constructions=cons,
                cells_used_by_the_score="all",
                enough_for_distribution_statistics=bool(n_use >= 30),
                abs_lat_band=[round(max(0.0, L - BAND_DEG), 2),
                              round(min(90.0, L + BAND_DEG), 2)],
                per_dimension_valid={d: int(fin[d][pix].sum()) for d in dims},
                geometry_source=r["geometry_source"], source_url=r["source_url"],
                source_kind=r["source_kind"], notes=r["notes"])
            for extra in ("kind", "selection_basis", "ez_radius_km"):
                if r.get(extra):
                    rec[extra] = r[extra]
            out.append(rec)
            print(f"{r['name'][:30]:30s} {la0:8.3f} {lo0:9.3f} {pix.size:6d} "
                  f"{n_all:9d} {n_nc:9d} {dims_av:5d}")
        # overlaps
        ov = []
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                n = len(set(out[i]["healpix_pixels"]) & set(out[j]["healpix_pixels"]))
                if n:
                    ov.append([out[i]["name"], out[j]["name"], n])
        doc = dict(
            written_by="build/targets.py",
            written_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            note=("Pixel sets and data coverage only. No distance, DI or "
                  "p-value is computed here."),
            source_file=f"sources/{FILES[body]}", body=body, nside=ns,
            cell_km2=round(cell_km2, 2), pairing=PAIR[body],
            pairing_dimensions=dims, overlapping_targets=ov, targets=out)
        dst = os.path.join(OUT, f"targets_{body}.json")
        tmp = dst + ".part"
        with io.open(tmp, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1, ensure_ascii=False)
        os.replace(tmp, dst)
        print(f"overlaps: {ov if ov else 'none'}")
        print("wrote", dst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
