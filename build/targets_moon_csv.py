"""
THE NINE ARTEMIS III REGIONS, FROM THE PUBLISHED POLYGONS.

    python -I build/targets_moon_csv.py

Reads   sources/artemis3_regions_2024/A3_9regions-lonlat-simplified.geojson
Writes  sources/targets_moon_artemis3_v2.csv      (write-once)

SOURCE
    LROC QuickMap, layer "A3: Candidate Landing Regions 2024",
    https://files.actgate.com/lunar/A3_9regions-lonlat-simplified.geojson
    3,545 bytes, Last-Modified 28 Oct 2024 (the day of NASA's update),
    collection name A3_9regions, fields Region / RegionCode / Area_km2.
    NASA's own release of 28 Oct 2024 carries a map image and no
    coordinates. No licence is stated in the file.

WHAT THIS REPLACES
    sources/artemis3_regions.csv placed each region as a 15 x 15 km disc at
    the IAU centre of the feature it is named after, and said so. Those
    centres were proxies: a rim, a peak or a plateau is not the crater
    centre. The file is kept; this one supersedes it.

GATE, stated before running
    In south polar stereographic (sphere R = 1737.4 km, true scale at the
    pole) every region must be an axis-aligned rectangle whose area equals
    the file's own Area_km2 to 0.1%. That is how the regions were drawn, so
    it is also the proof that the projection used to rebuild their edges is
    the right one. A region that fails stops the script.

The CSV keeps the four published corners. Edges are straight in the polar
stereographic plane, NOT in longitude / latitude; build/targets.py rebuilds
them there before testing which pixels are inside.
"""

import csv
import io
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

SRC_DIR = os.path.join(C.ROOT, "sources", "artemis3_regions_2024")
GJ = os.path.join(SRC_DIR, "A3_9regions-lonlat-simplified.geojson")
GJ_MD5 = "9d7a9b2c296dca3da3c4ba8463f7027e"
URL = "https://files.actgate.com/lunar/A3_9regions-lonlat-simplified.geojson"
OUT = os.path.join(C.ROOT, "sources", "targets_moon_artemis3_v2.csv")
R = 1737.4
# NASA's names, 28 Oct 2024 release, in the release's order
NASA_ORDER = ["Peak near Cabeus B", "Haworth", "Malapert Massif",
              "Mons Mouton Plateau", "Mons Mouton", "Nobile Rim 1",
              "Nobile Rim 2", "de Gerlache Rim 2", "Slater Plain"]


def sps(lon, lat):
    """south polar stereographic, x east, y toward lon 0, km."""
    rho = 2.0 * R * np.tan(np.radians(90.0 + np.asarray(lat)) / 2.0)
    lo = np.radians(np.asarray(lon))
    return rho * np.sin(lo), rho * np.cos(lo)


def sps_inv(x, y):
    rho = np.hypot(x, y)
    lat = 2.0 * np.degrees(np.arctan(rho / (2.0 * R))) - 90.0
    lon = np.degrees(np.arctan2(x, y))
    return lon, lat


def main():
    import hashlib
    got = hashlib.md5(open(GJ, "rb").read()).hexdigest()
    if got != GJ_MD5:
        raise SystemExit(f"geojson md5 {got} != recorded {GJ_MD5}")
    d = json.load(io.open(GJ, encoding="utf-8"))
    feats = {f["properties"]["Region"].lower(): f for f in d["features"]}
    if len(feats) != 9:
        raise SystemExit(f"expected 9 regions, file has {len(feats)}")
    rows = []
    print(f"{'region':22s} {'centre lat':>10s} {'centre lon':>10s} "
          f"{'size km':>13s} {'area km2':>9s} {'file':>9s}")
    for name in NASA_ORDER:
        f = feats.get(name.lower())
        if f is None:
            raise SystemExit(f"region '{name}' not in the file")
        ring = f["geometry"]["coordinates"][0]
        if ring[0] != ring[-1] or len(ring) != 5:
            raise SystemExit(f"{name}: not a closed four-corner ring")
        v = ring[:4]
        x, y = sps([p[0] for p in v], [p[1] for p in v])
        w, h = x.max() - x.min(), y.max() - y.min()
        # axis-aligned rectangle: each corner sits on two of the four edges
        on_x = np.isclose(x, x.min(), atol=0.01) | np.isclose(x, x.max(), atol=0.01)
        on_y = np.isclose(y, y.min(), atol=0.01) | np.isclose(y, y.max(), atol=0.01)
        area = float(w * h)
        want = float(f["properties"]["Area_km2"])
        if not (on_x.all() and on_y.all()) or abs(area / want - 1.0) > 1e-3:
            raise SystemExit(f"GATE FAIL {name}: rectangle {on_x.all() and on_y.all()}, "
                             f"area {area:.2f} against the file's {want:.2f}")
        cx, cy = (x.min() + x.max()) / 2.0, (y.min() + y.max()) / 2.0
        clon, clat = sps_inv(cx, cy)
        # true ground area: the stereographic plane inflates area by k^2
        k = 2.0 / (1.0 + np.sin(np.radians(-float(clat))))
        rows.append(dict(
            name=name, region_code=f["properties"]["RegionCode"],
            center_lat=round(float(clat), 4), center_lon=round(float(clon), 4),
            geometry="polygon", radius_km="",
            vertices_lonlat=json.dumps([[p[0], p[1]] for p in v]),
            edges_straight_in="south_polar_stereographic",
            width_km=round(float(w), 2), height_km=round(float(h), 2),
            area_km2_projected=round(area, 2),
            area_km2_ground=round(area / (k * k), 2),
            geometry_source=("LROC QuickMap layer 'A3: Candidate Landing "
                             "Regions 2024', file A3_9regions-lonlat-"
                             "simplified.geojson, Last-Modified 28 Oct 2024"),
            source_url=URL,
            source_kind="published vector polygon (LROC QuickMap); not hosted by nasa.gov",
            notes=("Four corners as published. Centre computed here as the "
                   "rectangle centre in south polar stereographic; the file "
                   "states no centre.")))
        print(f"{name:22s} {clat:10.4f} {clon:10.4f} {w:6.1f}x{h:5.1f} "
              f"{area:9.1f} {want:9.1f}")
    print("GATE pass: nine axis-aligned rectangles, areas equal the file's to 0.1%")

    buf = io.StringIO()
    w_ = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), lineterminator="\n")
    w_.writeheader()
    w_.writerows(rows)
    text = buf.getvalue()
    if os.path.exists(OUT):
        if io.open(OUT, encoding="utf-8", newline="").read() == text:
            print("unchanged, already on disk:", OUT)
            return 0
        raise SystemExit(f"REFUSED: {OUT} exists and differs; sources/ is write-once")
    io.open(OUT + ".part", "w", encoding="utf-8", newline="").write(text)
    os.replace(OUT + ".part", OUT)
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
