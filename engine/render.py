"""
Maps of one run: the full-sphere arrays and three views of each (TEST_SPEC, contract 2.4).

    di_combined, di_<group>   coloured pictures (viridis reversed: bright = alike)
    rank_combined             DATA, not a picture: 8-bit grey v, rank = (v / 255) squared,
                              transparent where a cell has no rank. The website's
                              top-X% slider is a threshold on this image.
"""

import os

import numpy as np

from analog_engine import ROOT, NSIDE

GLOBAL_W, GLOBAL_H, POLAR_N, POLAR_EDGE_LAT = 2880, 1440, 1024, 55.0
_idx = {}


def _lookup(view):
    """Earth HEALPix pixel under every image pixel of a view (computed once)."""
    if view not in _idx:
        from astropy import units as u
        from astropy_healpix import HEALPix
        hp = HEALPix(nside=NSIDE["earth"], order="nested")
        if view == "global":
            lon = (np.arange(GLOBAL_W) + 0.5) / GLOBAL_W * 360.0 - 180.0
            lat = 90.0 - (np.arange(GLOBAL_H) + 0.5) / GLOBAL_H * 180.0
            LON, LAT = np.meshgrid(lon, lat)
            ok = np.ones(LON.shape, dtype=bool)
        else:
            sgn = 1.0 if view == "north_polar" else -1.0
            x = (np.arange(POLAR_N) + 0.5) / POLAR_N * 2.0 - 1.0
            X, Y = np.meshgrid(x, -x)
            rmax = 2.0 * np.tan(np.radians(90.0 - POLAR_EDGE_LAT) / 2.0)
            r = np.hypot(X, Y) * rmax
            LAT = sgn * (90.0 - 2.0 * np.degrees(np.arctan(r / 2.0)))
            LON = np.degrees(np.arctan2(X, -sgn * Y))
            ok = np.hypot(X, Y) <= 1.0
        pix = np.asarray(hp.lonlat_to_healpix(LON.ravel() * u.deg, LAT.ravel() * u.deg)).reshape(LON.shape)
        _idx[view] = (pix, ok)
    return _idx[view]


def _save(arr, path, mode):
    from PIL import Image
    Image.fromarray(arr, mode=mode).save(path, optimize=True)


def write_rasters(P, out_dir, maps, rank, groups, code_version):
    from matplotlib import colormaps
    cmap = colormaps["viridis_r"]
    npix = 12 * NSIDE["earth"] ** 2
    layers = [("di_combined", maps["combined"])] + [("di_" + g, maps[g]) for g in ("terrain", "thermal", "composition")
                                                     if groups[g]["n_variables"] and g in maps]
    layers.append(("rank_combined", rank))
    out = []
    for name, values in layers:
        full = np.full(npix, np.nan, dtype=np.float32)
        full[P.epix] = values
        base = os.path.join(out_dir, name)
        np.save(os.path.join(ROOT, base + "_nside1024.npy"), full)
        is_rank = name == "rank_combined"
        vmin = 0.0 if is_rank else float(np.nanmin(values))
        vmax = 1.0 if is_rank else float(np.nanpercentile(values, 99.0))
        views = {}
        for view, tag in (("global", "global"), ("north_polar", "north"), ("south_polar", "south")):
            pix, ok = _lookup(view)
            v = full[pix]
            have = np.isfinite(v) & ok
            if is_rank:
                img = np.zeros(v.shape + (2,), dtype=np.uint8)
                img[..., 0] = np.round(255.0 * np.sqrt(np.clip(np.where(have, v, 0.0), 0.0, 1.0))).astype(np.uint8)
                img[..., 1] = np.where(have, 255, 0)
                _save(img, os.path.join(ROOT, f"{base}_{tag}.png"), "LA")
            else:
                t = np.clip((np.where(have, v, vmin) - vmin) / max(vmax - vmin, 1e-9), 0.0, 1.0)
                img = (cmap(t) * 255).astype(np.uint8)
                img[~have] = 0                                  # masked cells: transparent, and no colour underneath
                img[..., 3] = np.where(have, 255, 0)
                _save(img, os.path.join(ROOT, f"{base}_{tag}.png"), "RGBA")
            views[view] = f"{base}_{tag}.png".replace(os.sep, "/")
        out.append(dict(
            name=name, file=(base + "_nside1024.npy").replace(os.sep, "/"), format="healpix_npy",
            units="rank among reference cells, 0 = best on Earth" if is_rank else "dimensionless (DI)",
            vmin=round(vmin, 4), vmax=round(vmax, 4), colormap="none (data)" if is_rank else "viridis_r",
            views=views, encoding="8-bit grey v; rank = (v / 255) squared" if is_rank else None))
    return out
