"""
TERRESTRIAL ANALOG FINDER -- THE ENGINE (spec steps 5 to 9 and 11).

Written on the hackathon day, 14 Nov 2026, to docs/TEST_SPEC_2026-11-10.md.
Every number it needs was calibrated before the day and is only loaded here.

    from analog_engine import Pairing
    P = Pairing("moon")
    doc, detail, state = P.run_preset("Haworth", system="earth_reachable_only", out_dir="runs/haworth")
    doc, detail, state = P.run_custom("circle", dict(lat=-43.3, lon=-11.4, radius_km=40), system="all_variables", name="Tycho")
    click = P.point(state, lat=-24.05, lon=-69.92)        # any Earth cell against that target

THE METHOD, as the test specification states it
    scale      one min-max scale per variable, shared by Earth and the body
    whitening  inside each group, from Earth's reference population
    score      DI = mean distance to ALL distinct target cells / d_bar
    systems    all_variables | earth_reachable_only   (ONE argument)
    rank       share of reference cells with a smaller DI; bands, no threshold
    chance     1,000 random compact patches, same size, same |latitude|,
               minimum against minimum on a fixed 100,000-cell Earth sample
    control    the Atacama patch, treated as a target on the other body
    sites      patches of the best 1%: cells that touch are one place
    describe   every variable, its gap, its verdict; the fixed use table

There is no k, no weight and no preset anywhere in this file.
"""

import csv
import io
import json
import os
import subprocess
import sys
import time

import numpy as np

ROOT = os.environ.get("ANALOG_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P4 = os.path.join(ROOT, "cube", "phase4")
HP = os.path.join(ROOT, "cube", "healpix")
CONTRACT = os.path.join(ROOT, "contract")

NSIDE = {"earth": 1024, "moon": 256, "mars": 512}
RADIUS_KM = {"earth": 6371.0, "moon": 1737.4, "mars": 3389.5}
PARENT = {"moon": {"all_dimensions": "earth_moon"},
          "mars": {"all_dimensions": "earth_mars", "without_composition": "earth_mars_no_composition"}}
SEED = 20261114            # the engine's own seed: Earth sample and null draws
B_NULL = 1000
EARTH_SAMPLE_N = 100_000
BAND_HALF_WIDTH_DEG = 2.0
SITE_TOP_SHARE = 0.01
RANK_BANDS = [0.01, 0.05]
MAX_SITES = 20
AGREES_BELOW, DIFFERS_ABOVE = 0.10, 0.25
P_SIGNIFICANT = 0.05
EARTH_CELL_KM2 = 4.0 * np.pi * RADIUS_KM["earth"] ** 2 / (12 * NSIDE["earth"] ** 2)

GROUP = {"slope": "terrain", "roughness_5.25km": "terrain", "roughness_10.5km": "terrain",
         "roughness_21km": "terrain", "roughness_42km": "terrain", "tpi_21km": "terrain",
         "tpi_7km": "terrain", "svf_30km": "terrain", "temp_level": "thermal",
         "temp_range_diurnal": "thermal", "temp_range_seasonal": "thermal",
         "SiO2": "composition", "FeO": "composition"}
EARTHS_LIMITS = [
    dict(what="Gravity", numbers="Moon 1.62 m/s2, Mars 3.72 m/s2, Earth 9.81 m/s2",
         invalidates="Regolith mechanics, dust settling, drill reaction forces, lander dynamics, human gait and load testing"),
    dict(what="Atmospheric pressure", numbers="Moon ~1e-12 bar, Mars ~0.006 bar, Earth 1 bar",
         invalidates="Vacuum seals, boiling points, convective heat rejection, anything pneumatic"),
    dict(what="Radiation", numbers="No global magnetic field and no thick atmosphere on either target",
         invalidates="Electronics tolerance, crew dose planning, material ageing"),
    dict(what="Day length", numbers="Lunar day about 29.5 Earth days; Mars 24.66 h",
         invalidates="Power and thermal cycling on the Moon; Mars is close enough that the swing is ranked"),
    dict(what="Weathering history", numbers="Earth's surfaces are water- and life-altered; the targets' are not",
         invalidates="Grain shape, soil chemistry, mineral alteration products"),
]
SOURCES = [
    dict(name="LOLA 118 m lunar DEM", url="https://pds-geosciences.wustl.edu/missions/lro/lola.htm", used_for="lunar terrain layers"),
    dict(name="MOLA 463 m Mars DEM", url="https://astrogeology.usgs.gov/search/map/Mars/GlobalSurveyor/MOLA/Mars_MGS_MOLA_DEM_mosaic_global_463m", used_for="Mars terrain layers"),
    dict(name="ETOPO 2022 15 arc-second", url="https://www.ncei.noaa.gov/products/etopo-global-relief-model", used_for="Earth terrain layers"),
    dict(name="Diviner GCP", url="https://doi.org/10.17189/1520655", used_for="lunar temperature level and diurnal range"),
    dict(name="MODIS MOD11C3 / MYD11C3", url="https://lpdaac.usgs.gov/products/mod11c3v061/", used_for="Earth temperature level and diurnal range"),
    dict(name="Lunar Prospector GRS", url="https://pds-geosciences.wustl.edu/missions/lunarp/", used_for="lunar SiO2 and FeO"),
    dict(name="GLiM, Hartmann & Moosdorf 2012", url="https://doi.org/10.1029/2012GC004370", used_for="Earth lithology, SiO2 and FeO"),
    dict(name="SCAR GeoMAP v.2022-08, Cox et al. 2023", url="https://doi.org/10.1594/PANGAEA.951482", used_for="rock class of exposed ground in Antarctica and South Georgia"),
    dict(name="Gard, Hasterok & Halpin 2019", url="https://doi.org/10.5281/zenodo.3359791", used_for="check of the class-to-composition lookup"),
]


def jl(*parts):
    return json.load(io.open(os.path.join(*parts), encoding="utf-8"))


def code_version():
    try:
        h = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "-C", ROOT, "status", "--porcelain", "--", "engine"], capture_output=True, text=True, timeout=10).stdout.strip()
        return (h or "unknown") + ("+engine-uncommitted" if dirty else "")
    except Exception:
        return "unknown"


# ====================================================================== distance
def mean_dist(A, T, chunk=200_000):
    """mean Euclidean distance from every row of A to ALL rows of T. THE distance function:
    the real target, the control and every null draw call this and nothing else."""
    T64 = np.asarray(T, dtype=np.float64)
    centre = T64.mean(0)                                   # a shift changes no distance; it keeps float32 exact near the target
    T = np.ascontiguousarray(T64 - centre, dtype=np.float32)
    centre = centre.astype(np.float32)
    out = np.empty(A.shape[0], dtype=np.float32)
    t2 = (T * T).sum(1)
    for i in range(0, A.shape[0], chunk):
        a = np.ascontiguousarray(A[i:i + chunk], dtype=np.float32) - centre
        d2 = (a * a).sum(1)[:, None] + t2[None, :] - 2.0 * (a @ T.T)
        np.maximum(d2, 0.0, out=d2)
        np.sqrt(d2, out=d2)
        out[i:i + chunk] = d2.mean(1)
    return out


def mean_pairwise(V):
    """mean distance between two distinct rows of V; None for a single row."""
    n = V.shape[0]
    if n < 2:
        return None
    V = V.astype(np.float64)
    d = np.sqrt(np.maximum(((V[:, None, :] - V[None, :, :]) ** 2).sum(-1), 0.0))
    return float(d[np.triu_indices(n, 1)].mean())


def rank_of(di):
    """share of scored cells with a SMALLER di. 0 = the best cell on Earth."""
    s = np.sort(di)
    return (np.searchsorted(s, di, side="left") / di.size).astype(np.float32)


def verdict_of(gap):
    if gap is None:
        return "withheld"
    a = abs(gap)
    return "agrees" if a < AGREES_BELOW else ("differs" if a > DIFFERS_ABOVE else "partial")


# ====================================================================== the pairing
class Pairing:
    """Earth and one target body: positions, calibrations, geometry. Load once."""

    def __init__(self, body):
        assert body in ("moon", "mars")
        t0 = time.perf_counter()
        self.body = body
        mm = jl(P4, "minmax_scale_summary.json")["pairings"][body]
        self.names = mm["names"]
        self.var = mm["variables"]
        self.E = np.load(os.path.join(P4, f"minmax_earth_{body}.npy"))            # (D_all, n) Earth positions
        self.Bd = np.load(os.path.join(P4, f"minmax_{body}.npy"))                 # (D_all, npix) body positions
        self.epix = np.load(os.path.join(P4, "ref_pixels.npy"))[np.load(os.path.join(P4, "complete_mask.npy"))]
        self.n = self.E.shape[1]
        assert self.epix.size == self.n and self.E.shape[0] == len(self.names)
        assert self.Bd.shape == (len(self.names), 12 * NSIDE[body] ** 2)
        self.parents = jl(P4, "phase4c_summary.json")
        self.rsets = jl(P4, "ranking_sets.json")
        self.targets_ranking = jl(CONTRACT, "targets_ranking.json")
        self.targets = {t["name"]: t for t in jl(CONTRACT, f"targets_{body}.json")["targets"]}
        self.use_table = jl(CONTRACT, "use_table.json")
        self._cal, self._VE, self._geo, self._desc = {}, {}, None, None
        rng = np.random.default_rng(SEED)
        self.sample = np.sort(rng.choice(self.n, size=EARTH_SAMPLE_N, replace=False))
        self.load_seconds = time.perf_counter() - t0

    # ---------------------------------------------------------------- calibration
    def cal(self, set_id):
        if set_id not in self._cal:
            s = self.parents[set_id] if set_id in self.parents else self.rsets["sets"][set_id]
            dims = s["dimensions"]
            mean, sd = np.load(os.path.join(P4, f"center_{set_id}.npy"))
            W = np.load(os.path.join(P4, f"whiten_{set_id}.npy"))
            assert W.shape == (len(dims), len(dims)) and mean.size == len(dims)
            self._cal[set_id] = dict(
                id=set_id, dims=dims, rows=[self.names.index(d) for d in dims], mean=mean, sd=sd, W=W,
                d_bar=float(s["d_bar"]), floored=int(s["eigenvalues_floored"]),
                groups={g: dict(a=v["index_range"][0], b=v["index_range"][1], d_bar=float(v["d_bar"])) for g, v in s["groups"].items()})
        return self._cal[set_id]

    def whiten(self, cal, positions):
        """positions: (cells, D) in the set's own column order -> whitened vectors."""
        return (((np.asarray(positions, dtype=np.float64) - cal["mean"]) / cal["sd"]) @ cal["W"]).astype(np.float32)

    def earth_vectors(self, set_id):
        if set_id not in self._VE:
            c = self.cal(set_id)
            out = np.empty((self.n, len(c["dims"])), dtype=np.float32)
            for i in range(0, self.n, 400_000):
                out[i:i + 400_000] = self.whiten(c, self.E[c["rows"], i:i + 400_000].T)
            self._VE[set_id] = out
        return self._VE[set_id]

    def body_vectors(self, cal, pixels):
        """whitened vectors of body pixels that have every variable of the set; DISTINCT rows."""
        X = self.Bd[cal["rows"]][:, np.asarray(pixels, dtype=np.int64)].T
        ok = np.isfinite(X).all(1)
        V = self.whiten(cal, X[ok])
        return np.unique(np.round(V, 6), axis=0), int(ok.sum())

    def earth_columns(self, earth_pixels):
        """columns of the Earth arrays for given Earth HEALPix pixels (must be complete reference cells)."""
        ep = np.asarray(earth_pixels, dtype=np.int64)
        order = np.argsort(self.epix)
        pos = np.searchsorted(self.epix[order], ep)
        col = order[np.clip(pos, 0, self.n - 1)]
        assert np.all(self.epix[col] == ep), "an Earth pixel is not in the complete reference population"
        return col

    # ---------------------------------------------------------------- the score
    def di_maps(self, set_id, VT):
        """di_combined and one map per group, for every scored Earth cell."""
        c = self.cal(set_id)
        VE = self.earth_vectors(set_id)
        out = {"combined": mean_dist(VE, VT) / c["d_bar"]}
        for g, v in c["groups"].items():
            out[g] = mean_dist(VE[:, v["a"]:v["b"]], VT[:, v["a"]:v["b"]]) / v["d_bar"]
        return out

    # ---------------------------------------------------------------- body geometry, for the null
    def geo(self):
        if self._geo is None:
            from astropy_healpix import HEALPix
            from scipy.spatial import cKDTree
            hp = HEALPix(nside=NSIDE[self.body], order="nested")
            lon, lat = hp.healpix_to_lonlat(np.arange(hp.npix))
            lat, lon = lat.rad, lon.rad
            U = np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], axis=1)
            self._geo = dict(U=U, abs_lat=np.abs(np.degrees(lat)), trees={},
                             cell_km2=4.0 * np.pi * RADIUS_KM[self.body] ** 2 / hp.npix, cKDTree=cKDTree)
        return self._geo

    def _complete_tree(self, parent_id):
        G = self.geo()
        if parent_id not in G["trees"]:
            rows = [self.names.index(d) for d in self.parents[parent_id]["dimensions"]]
            ok = np.flatnonzero(np.isfinite(self.Bd[rows]).all(0))
            G["trees"][parent_id] = (ok, G["cKDTree"](G["U"][ok]))
        return G["trees"][parent_id]

    def null(self, set_id, parent_id, n_cells, band, sample, B=B_NULL, seed=SEED, keep_pixels=False):
        """B random compact patches of n_cells in the |latitude| band, both hemispheres.
        Returns the minima over the Earth sample, each patch's own spread, the discard count."""
        c = self.cal(set_id)
        G = self.geo()
        ok, tree = self._complete_tree(parent_id)
        VS = self.earth_vectors(set_id)[sample]
        rng = np.random.default_rng(seed)
        r_km = np.sqrt(n_cells * G["cell_km2"] / np.pi)
        max_chord = 2.0 * np.sin(min(np.pi, 2.0 * r_km / RADIUS_KM[self.body]) / 2.0)
        s_lo, s_hi = np.sin(np.radians(band[0])), np.sin(np.radians(band[1]))
        minima, spreads, hemis, discards = np.empty(B), np.empty(B), np.empty(B, dtype=np.int8), 0
        kept = []
        k = 0
        while k < B:
            z = rng.uniform(s_lo, s_hi) * (1.0 if rng.random() < 0.5 else -1.0)
            lon = rng.uniform(0.0, 2.0 * np.pi)
            rxy = np.sqrt(max(0.0, 1.0 - z * z))
            d, idx = tree.query([rxy * np.cos(lon), rxy * np.sin(lon), z], k=n_cells)
            d, idx = np.atleast_1d(d), np.atleast_1d(idx)
            if d[0] > max_chord:
                discards += 1
                continue
            VP = self.whiten(c, self.Bd[c["rows"]][:, ok[idx]].T)
            minima[k] = float(mean_dist(VS, VP).min()) / c["d_bar"]
            sp = mean_pairwise(VP)
            spreads[k] = 0.0 if sp is None else sp / c["d_bar"]
            hemis[k] = 1 if z > 0 else -1
            if keep_pixels:
                kept.append(ok[idx].copy())
            k += 1
        return dict(minima=minima, spreads=spreads, hemispheres=hemis, discards=discards, patch_radius_km=float(r_km), pixels=kept)

    @staticmethod
    def p_value(di_observed, minima):
        return (1.0 + float(np.sum(minima <= di_observed))) / (1.0 + minima.size)

    # ---------------------------------------------------------------- which variables rank
    def ranking(self, target_name, construction, system):
        rec = [t for t in self.targets_ranking["targets"][self.body] if t["name"] == target_name][0]["constructions"][construction]
        parent = rec["base_set"]
        if system == "all_variables":
            set_id, ranked = parent, list(self.parents[parent]["dimensions"])
        elif system == "earth_reachable_only":
            set_id, ranked = rec["ranking_set"], list(rec["ranked_dimensions"])
        else:
            raise ValueError("system must be all_variables or earth_reachable_only")
        return dict(system=system, rule=self.targets_ranking["rule"], ranking_set=set_id, ranked_variables=ranked,
                    out_of_range=rec["out_of_range"]), parent

    # ---------------------------------------------------------------- the control
    def control(self, set_id, parent_id):
        """The Atacama patch, treated as a target on the other body (TEST_SPEC section 3)."""
        fx = jl(CONTRACT, "control_fixtures.json")["controls"]["positive_atacama"]
        c = self.cal(set_id)
        cols = self.earth_columns(fx["healpix_pixels"])
        VT = np.unique(np.round(self.earth_vectors(set_id)[cols], 6), axis=0)
        missing = np.setdiff1d(cols, self.sample)
        sample = np.sort(np.concatenate([self.sample, missing]))
        di_obs = float(mean_dist(self.earth_vectors(set_id)[sample], VT).min()) / c["d_bar"]
        L = abs(fx["centre_lat"])
        band = [round(max(0.0, L - BAND_HALF_WIDTH_DEG), 2), round(min(90.0, L + BAND_HALF_WIDTH_DEG), 2)]
        nl = self.null(set_id, parent_id, VT.shape[0], band, sample)
        p = self.p_value(di_obs, nl["minima"])
        sp = mean_pairwise(VT)
        return dict(name=fx["name"], di_observed=round(di_obs, 4), p=round(p, 6), passed=bool(p < P_SIGNIFICANT)), dict(
            set_id=set_id, band_abs_lat=band, patch_cells=int(VT.shape[0]), earth_sample_n=int(sample.size),
            atacama_cells_added_to_sample=int(missing.size), null_median=float(np.median(nl["minima"])),
            null_min=float(nl["minima"].min()), target_spread=None if sp is None else sp / c["d_bar"],
            null_spread_median=float(np.median(nl["spreads"])), discards=int(nl["discards"]))

    # ---------------------------------------------------------------- sites: patches of the best share
    def patches(self, di, rank, share=SITE_TOP_SHARE):
        from astropy_healpix import neighbours
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        top = np.flatnonzero(rank < share)
        if top.size == 0:
            return []
        pix = self.epix[top]
        order = np.argsort(pix)
        spix = pix[order]
        nb = np.asarray(neighbours(pix, NSIDE["earth"], order="nested"))            # (8, m), -1 where none
        src = np.repeat(np.arange(top.size)[None, :], 8, axis=0).ravel()
        nbf = nb.ravel()
        pos = np.clip(np.searchsorted(spix, nbf), 0, spix.size - 1)
        hit = (nbf >= 0) & (spix[pos] == nbf)
        g = coo_matrix((np.ones(int(hit.sum()), dtype=np.int8), (src[hit], order[pos[hit]])), shape=(top.size, top.size))
        _, lab = connected_components(g, directed=False)
        out = []
        for L in np.unique(lab):
            cells = top[lab == L]
            best = cells[np.argmin(di[cells])]
            out.append(dict(best=int(best), cells=cells, di=float(di[best])))
        out.sort(key=lambda q: (q["di"], q["best"]))
        return out

    # ---------------------------------------------------------------- describing a cell
    def _describers(self):
        if self._desc is None:
            from astropy_healpix import HEALPix
            man = jl(ROOT, "cube", "cube_manifest.json")["layers"]
            lith = man["earth_lithology_l1"]
            rows = [r for r in csv.DictReader(io.open(os.path.join(ROOT, "sources", "tier4_catalogues", "known_analog_sites_v2.csv"), encoding="utf-8"))
                    if r["lat"].strip() and r["lon"].strip()]
            self._desc = dict(
                hp=HEALPix(nside=NSIDE["earth"], order="nested"),
                koppen=np.load(os.path.join(HP, "earth_koppen_class_nside1024.npy"), mmap_mode="r"),
                legend=jl(ROOT, "cube", "koppen_legend.json")["classes"],
                l1=np.load(os.path.join(HP, "earth_lithology_l1_nside1024.npy"), mmap_mode="r"),
                gmc=np.load(os.path.join(HP, "earth_geomap_lithcode_nside1024.npy"), mmap_mode="r"),
                l1vocab=lith["vocabulary"], l1mean=lith["l1_meaning"],
                gm_mean={r["code"]: r["rock_type"] for r in csv.DictReader(io.open(os.path.join(ROOT, "sources", "geomap_composition_lookup.csv"), encoding="utf-8"))},
                cat=dict(name=[r["name"] for r in rows], source=[r["source"] for r in rows],
                         lat=np.radians(np.array([float(r["lat"]) for r in rows])), lon=np.radians(np.array([float(r["lon"]) for r in rows]))),
                ref_pixels=int(man["earth_reference_mask"]["validation"]["pixels_in_reference_population"]))
        return self._desc

    def physical(self, name, position):
        v = self.var[name]
        return v["lo"] + float(position) * (v["hi"] - v["lo"])

    def variable_rows(self, col, order, t_pos, ranked):
        rows = []
        for d in order:
            pe = float(self.E[self.names.index(d), col])
            pt = float(t_pos[d])
            gap = pe - pt
            rows.append(dict(name=d, group=GROUP[d], units=self.var[d]["units"], earth=round(self.physical(d, pe), 4),
                             target_median=round(self.physical(d, pt), 4), earth_position=round(pe, 4), target_position=round(pt, 4),
                             position_gap=round(gap, 4), physical_gap=round(gap * (self.var[d]["hi"] - self.var[d]["lo"]), 4),
                             verdict=verdict_of(gap), modelled=bool(self.body == "mars" and d.startswith("temp_")), ranked=d in ranked))
        return rows

    def use_block(self, vr, beyond):
        by = {r["name"]: r for r in vr}
        out = dict(succeeds=[], fails=[], beyond_earth=[])
        for row in self.use_table["rows"]:
            vs = [v for v in row["variables"] if v in by]
            if not vs:
                continue
            line = dict(key=row["key"], group=row["group"], label=row["label"], variables=vs)
            verdicts = [by[v]["verdict"] for v in vs]
            if any(v in beyond for v in vs):
                out["beyond_earth"].append(dict(line, text=row["if_beyond_earth"]))
            elif all(v == "agrees" for v in verdicts):
                out["succeeds"].append(dict(line, text=row["if_agrees"]))
            elif any(v == "differs" for v in verdicts):
                out["fails"].append(dict(line, text=row["if_differs"]))
        out["general"] = None if out["succeeds"] else self.use_table["general_sentence"]
        return out

    def describe(self, col, maps, order, t_pos, ranked, beyond, d_bar_target, d_bar):
        Dd = self._describers()
        pix = int(self.epix[col])
        lon, lat = Dd["hp"].healpix_to_lonlat(pix)
        lat, lon = float(lat.deg), float(((lon.deg + 180.0) % 360.0) - 180.0)
        vr = self.variable_rows(col, order, t_pos, ranked)
        rk = sorted([r for r in vr if r["ranked"]], key=lambda r: abs(r["position_gap"]))
        dg = {g: (round(float(maps[g][col]), 4) if g in maps else None) for g in ("terrain", "thermal", "composition")}
        worst = max(((g, v) for g, v in dg.items() if v is not None), key=lambda t: t[1])
        la, lo = np.radians(lat), np.radians(lon)
        c = Dd["cat"]
        dist = 2 * RADIUS_KM["earth"] * np.arcsin(np.sqrt(np.sin((c["lat"] - la) / 2) ** 2 + np.cos(la) * np.cos(c["lat"]) * np.sin((c["lon"] - lo) / 2) ** 2))
        i = int(np.argmin(dist))
        known = bool(dist[i] <= 100.0)
        k, li, gm = int(Dd["koppen"][pix]), int(Dd["l1"][pix]), int(Dd["gmc"][pix])
        di = float(maps["combined"][col])
        return dict(
            lat=round(lat, 4), lon=round(lon, 4), healpix_pixel=pix, di_combined=round(di, 4),
            di_target=None if not d_bar_target else round(di * d_bar / d_bar_target, 4),
            di_group=dg, worst_group=dict(name=worst[0], di=worst[1]), dims_used_here=len(rk),
            catalogue=dict(status="known" if known else "new candidate", name=c["name"][i] if known else None,
                           citation=c["source"][i] if known else None, distance_km=round(float(dist[i]), 1)),
            koppen=None if k == 0 else dict(code=k, symbol=Dd["legend"][str(k)]["symbol"], description=Dd["legend"][str(k)]["description"]),
            lithology=(dict(l1_code=chr(gm), description=Dd["gm_mean"].get(chr(gm), chr(gm)), source="GeoMAP") if gm > 0
                       else None if li == 255 else dict(l1_code=Dd["l1vocab"][str(li)], description=Dd["l1mean"].get(Dd["l1vocab"][str(li)], Dd["l1vocab"][str(li)]), source="GLiM")),
            variables=vr, agrees=[r["name"] for r in rk if r["verdict"] == "agrees"],
            partial=[r["name"] for r in rk if r["verdict"] == "partial"], differs=[r["name"] for r in rk if r["verdict"] == "differs"],
            best3=[r["name"] for r in rk[:3]], worst3=[r["name"] for r in rk[-3:][::-1]], use=self.use_block(vr, beyond))

    # ---------------------------------------------------------------- one full run, for ANY set of target cells
    def _run(self, name, selection, pixels, band, rk, parent, construction, out_dir=None, write_rasters=True, control=None):
        t0 = time.perf_counter()
        system = rk["system"]
        set_id = rk["ranking_set"]
        c = self.cal(set_id)
        ranked = set(rk["ranked_variables"])
        beyond = {o["variable"] for o in rk["out_of_range"]}
        VT, n_used = self.body_vectors(c, pixels)
        d_bar_target = mean_pairwise(VT)

        maps = self.di_maps(set_id, VT)
        di = maps["combined"]
        rank = rank_of(di)
        di_obs = float(di[self.sample].min())
        nl = self.null(set_id, parent, VT.shape[0], band, self.sample)
        p = self.p_value(di_obs, nl["minima"])
        if control is None:
            control, control_detail = self.control(set_id if system == "all_variables" else self._preset_control_set(parent), parent)
        else:
            control, control_detail = control

        order = [d for d in GROUP if d in self.parents[parent]["dimensions"]]
        t_pos = {d: float(np.nanmedian(self.Bd[self.names.index(d), pixels])) for d in order}
        pt = self.patches(di, rank)
        sites = []
        for i, q in enumerate(pt[:MAX_SITES]):
            s = self.describe(q["best"], maps, order, t_pos, ranked, beyond, d_bar_target, c["d_bar"])
            s.update(rank=i + 1, patch_cells=int(q["cells"].size), patch_area_km2=round(float(q["cells"].size * EARTH_CELL_KM2), 1))
            sites.append(s)

        G = self.geo()
        abs_lat = G["abs_lat"][pixels]
        groups = {g: dict(n_variables=sum(1 for d in order if GROUP[d] == g and d in ranked)) for g in ("terrain", "thermal", "composition")}
        Dd = self._describers()
        run = dict(
            code_version=code_version(), run_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            target=dict(body=self.body, name=name, selection=selection,
                        cells=int(pixels.size), cells_distinct=int(VT.shape[0]),
                        spread=0.0 if d_bar_target is None else round(d_bar_target / c["d_bar"], 4),
                        abs_lat_range=[round(float(abs_lat.min()), 2), round(float(abs_lat.max()), 2)]),
            variables=[dict(name=d, group=GROUP[d], units=self.var[d]["units"], modelled=bool(self.body == "mars" and d.startswith("temp_")),
                            weak=d in ("SiO2", "FeO"), ranked=d in ranked) for d in order],
            groups=groups, grid=dict(scheme="healpix_nested", nside_target=NSIDE[self.body], nside_earth=NSIDE["earth"]),
            target_cells_used="all", ranking=rk, rank_bands=RANK_BANDS,
            distance="mahalanobis_whitened", scale="minmax", eigen_floor=0.10, floored_directions=c["floored"],
            d_bar_earth=round(c["d_bar"], 4), d_bar_target=None if d_bar_target is None else round(d_bar_target, 4),
            dims_used=len(c["dims"]), verdict_thresholds=dict(agrees_below=AGREES_BELOW, differs_above=DIFFERS_ABOVE),
            site_rule="patches_of_top_share", site_top_share=SITE_TOP_SHARE, patches_total=len(pt),
            reference_population=dict(pixels=Dd["ref_pixels"],
                                      definition="Ice-free, water-free land with every used dimension present. Antarctica enters as exposed rock; the ice sheet is excluded from ranking."))
        null_test = dict(B=B_NULL, statistic="minimum di_combined over the Earth sample", null_source="live",
                         band_abs_lat=[float(band[0]), float(band[1])], patch_cells=int(VT.shape[0]), earth_sample_n=int(self.sample.size), seed=SEED,
                         di_observed=round(di_obs, 4), null_median=round(float(np.median(nl["minima"])), 4),
                         p=round(p, 6), p_at_floor=bool(p <= 1.0 / (1.0 + B_NULL) + 1e-12), positive_control=control)
        verdict = "significant" if p < P_SIGNIFICANT else "not significant"
        limits = (
            f"Chance test: {verdict}, p = {p:.3g}. Control (Atacama patch): {'passed' if control['passed'] else 'FAILED -- this test has no power; do not read p as evidence'}, p = {control['p']:.3g}. "
            f"Ranking system: {system}. The other system is reported in its own file; neither is 'the' result until the team names one. "
            "The index is a cell's mean distance to EVERY cell of the target, so it measures likeness to the region as a whole; "
            f"the target's own spread is {run['target']['spread']} and an index above 1 is expected for a varied target. Read ranks, not index values. "
            "With this score a patch that is uniform inside scores lower than a varied one whatever Earth looks like, so p partly measures how uniform the target is. "
            "A best 1% exists for every target: it is an order, not a quality. "
            + ("Variables no Earth cell reaches are reported in run.ranking.out_of_range and do not rank. " if system == "earth_reachable_only"
               else "Variables no Earth cell reaches are listed in run.ranking.out_of_range and DO rank in this file; they may carry most of the distance. ")
            + "Composition is a weak variable at both ends (a rock-class lookup on Earth, 60 km blocks on the Moon). "
            + ("Mars temperatures are modelled, not measured. " if self.body == "mars" else "")
            + "One cell is 6 to 7 km across; nothing here describes boulders or soil. Every site is a partial analog: see earths_limits.")
        doc = dict(contract_version="2.4", run=run, null_test=null_test, sites=sites, rasters=[], earths_limits=EARTHS_LIMITS,
                   limits=limits,
                   ai_disclosure="The data pipeline and this engine were written with Claude (Anthropic) under the team's direction. "
                                 "Every method decision was made by the team and is recorded in VARIABLES.md.",
                   sources=SOURCES)
        detail = dict(seconds=round(time.perf_counter() - t0, 1), set_id=set_id, parent=parent, construction=construction,
                      target_spread=run["target"]["spread"], null_spread_p5_p50_p95=[float(x) for x in np.percentile(nl["spreads"], [5, 50, 95])],
                      null_min_p5_p50_p95=[float(x) for x in np.percentile(nl["minima"], [5, 50, 95])], null_discards=int(nl["discards"]),
                      null_north_share=float(np.mean(nl["hemispheres"] > 0)), full_map_min=float(di.min()), control=control_detail,
                      best_cells_group_di={g: (float(maps[g][int(np.argmin(di))]) if g in maps else None) for g in ("terrain", "thermal", "composition")})
        if out_dir:
            os.makedirs(os.path.join(ROOT, out_dir), exist_ok=True)
            if write_rasters:
                import render
                doc["rasters"] = render.write_rasters(self, out_dir, maps, rank, groups, doc["run"]["code_version"])
            io.open(os.path.join(ROOT, out_dir, "output.json"), "w", encoding="utf-8").write(json.dumps(doc, indent=1, ensure_ascii=False))
            np.savez_compressed(os.path.join(ROOT, out_dir, "null_draws.npz"), minima=nl["minima"], spreads=nl["spreads"], hemispheres=nl["hemispheres"])
            io.open(os.path.join(ROOT, out_dir, "run_detail.json"), "w", encoding="utf-8").write(json.dumps(detail, indent=1))
        state = dict(name=name, maps=maps, rank=rank, patches=pt, VT=VT, order=order, t_pos=t_pos, ranked=ranked, beyond=beyond,
                     d_bar_target=d_bar_target, d_bar=c["d_bar"], limits=limits)
        return doc, detail, state

    def run_preset(self, target_name, system, construction=None, out_dir=None, write_rasters=True, control=None):
        tgt = self.targets[target_name]
        construction = construction or tgt["primary_construction"]
        rk, parent = self.ranking(target_name, construction, system)
        pixels = np.asarray(tgt["healpix_pixels"], dtype=np.int64)
        prow = [self.names.index(d) for d in self.parents[parent]["dimensions"]]
        pixels = pixels[np.isfinite(self.Bd[prow][:, pixels]).all(0)]                # the cells of this construction
        selection = dict(method="named_feature", params=dict(catalogue=f"targets_{self.body}", feature_id=target_name, construction=construction))
        return self._run(target_name, selection, pixels, tgt["abs_lat_band"], rk, parent, construction, out_dir, write_rasters, control)

    def _preset_control_set(self, parent):
        """Under earth_reachable_only the control runs on the ranking set the presets of this pairing use."""
        if self.body == "moon":
            return "earth_moon__minus__temp_level__temp_range_diurnal"
        return ("earth_mars__minus__temp_level__temp_range_diurnal" if parent == "earth_mars"
                else "earth_mars_no_composition__minus__temp_level__temp_range_diurnal")

    # ---------------------------------------------------------------- custom targets (spec step 5)
    def select_pixels(self, method, params):
        """A cell belongs to a target when its CENTRE is inside the shape. One rule for every way in."""
        G = self.geo()
        if "lat_deg" not in G:
            U = G["U"]
            G["lat_deg"] = np.degrees(np.arcsin(np.clip(U[:, 2], -1, 1)))
            G["lon_deg"] = np.degrees(np.arctan2(U[:, 1], U[:, 0]))
        if method == "circle":
            la, lo = np.radians(float(params["lat"])), np.radians(float(params["lon"]))
            c = np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
            return np.flatnonzero(G["U"] @ c >= np.cos(float(params["radius_km"]) / RADIUS_KM[self.body]))
        if method == "rectangle":
            lon = G["lon_deg"]
            l0 = ((float(params["lon_min"]) + 180.0) % 360.0) - 180.0
            l1 = ((float(params["lon_max"]) + 180.0) % 360.0) - 180.0
            inlon = (lon >= l0) & (lon <= l1) if l0 <= l1 else (lon >= l0) | (lon <= l1)       # a box may cross the 180 line
            if float(params["lon_max"]) - float(params["lon_min"]) >= 360.0:
                inlon = np.ones(lon.shape, dtype=bool)
            return np.flatnonzero(inlon & (G["lat_deg"] >= float(params["lat_min"])) & (G["lat_deg"] <= float(params["lat_max"])))
        if method == "pixel_list":
            if int(params["nside"]) != NSIDE[self.body]:
                raise ValueError(f"pixel_list must be at Nside {NSIDE[self.body]} for {self.body}")
            return np.unique(np.asarray(params["pixels"], dtype=np.int64))
        raise ValueError("selection method must be circle, rectangle or pixel_list")

    def earth_range(self, name):
        if not hasattr(self, "_erange"):
            self._erange = {}
        if name not in self._erange:
            r = self.E[self.names.index(name)]
            self._erange[name] = (float(r.min()), float(r.max()))
        return self._erange[name]

    def out_of_range(self, dims, pixels):
        """THE RULE (VARIABLES.md B36): a variable is out of Earth's range for a target when the median of the
        target's cells lies outside the WHOLE range of Earth's reference population. Applied here on positions;
        a position is a straight-line function of the value, so the outcome is the same as on physical units."""
        ranked, out = [], []
        for d in dims:
            v = self.Bd[self.names.index(d), pixels]
            v = v[np.isfinite(v)]
            if v.size == 0:
                continue
            lo, hi = self.earth_range(d)
            m = float(np.median(v))
            if m < lo or m > hi:
                ph = lambda x: round(self.physical(d, x), 3)
                out.append(dict(variable=d, units=self.var[d]["units"], target_median=ph(m), earth_min=ph(lo), earth_max=ph(hi),
                                side="below Earth's range" if m < lo else "above Earth's range",
                                gap=round(abs(self.physical(d, m) - self.physical(d, lo if m < lo else hi)), 3),
                                share_of_target_cells_outside=round(float(np.mean((v < lo) | (v > hi))), 3)))
            else:
                ranked.append(d)
        return ranked, out

    def _custom_cal(self, parent, ranked, out):
        """the calibration of a ranked list: from disk when it exists, else built now (about 20 s) and kept in memory."""
        set_id = parent if not out else parent + "__minus__" + "__".join(o["variable"] for o in out)
        if set_id in self.parents or set_id in self.rsets["sets"] or set_id in self._cal:
            return set_id
        sys.path.insert(0, os.path.join(ROOT, "build"))
        import ranking_sets
        info, W, cen = ranking_sets.calibrate(parent, ranked)
        self._cal[set_id] = dict(
            id=set_id, dims=info["dimensions"], rows=[self.names.index(d) for d in info["dimensions"]], mean=cen[0], sd=cen[1], W=W,
            d_bar=float(info["d_bar"]), floored=int(info["eigenvalues_floored"]),
            groups={g: dict(a=v["index_range"][0], b=v["index_range"][1], d_bar=float(v["d_bar"])) for g, v in info["groups"].items()})
        return set_id

    def run_custom(self, method, params, system, name=None, out_dir=None, write_rasters=True, control=None):
        pixels = self.select_pixels(method, params)
        if pixels.size == 0:
            raise ValueError("the shape contains no cell centre; make it larger (one cell is 6 to 7 km across)")
        if self.body == "moon":
            parent, construction = "earth_moon", "all_dimensions"
        else:   # composition covers half of Mars: use it only where at least 90% of the target has it (the rule of build/targets.py)
            comp = np.isfinite(self.Bd[[self.names.index(d) for d in self.parents["earth_mars"]["dimensions"]]][:, pixels]).all(0)
            parent, construction = (("earth_mars", "all_dimensions") if comp.mean() >= 0.9 else ("earth_mars_no_composition", "without_composition"))
        prow = [self.names.index(d) for d in self.parents[parent]["dimensions"]]
        pixels = pixels[np.isfinite(self.Bd[prow][:, pixels]).all(0)]
        if pixels.size == 0:
            raise ValueError("no cell of the shape carries every variable; nothing to match")
        ranked, out = self.out_of_range(self.parents[parent]["dimensions"], pixels)
        if system == "all_variables":
            set_id, ranked_used = parent, list(self.parents[parent]["dimensions"])
        elif system == "earth_reachable_only":
            if not ranked:
                raise ValueError("no variable of this target is within Earth's range; nothing can rank")
            set_id = self._custom_cal(parent, ranked, out)
            ranked_used = list(self.cal(set_id)["dims"])
        else:
            raise ValueError("system must be all_variables or earth_reachable_only")
        rk = dict(system=system, rule=self.targets_ranking["rule"], ranking_set=set_id, ranked_variables=ranked_used, out_of_range=out)
        G = self.geo()
        cm = G["U"][pixels].mean(0)
        L = abs(float(np.degrees(np.arcsin(np.clip(cm[2] / np.linalg.norm(cm), -1, 1)))))
        band = [round(max(0.0, L - BAND_HALF_WIDTH_DEG), 2), round(min(90.0, L + BAND_HALF_WIDTH_DEG), 2)]
        name = name or f"custom {method}"
        return self._run(name, dict(method=method, params=params), pixels, band, rk, parent, construction, out_dir, write_rasters, control)

    # ---------------------------------------------------------------- a finished run, read back from disk
    def target_pixels(self, selection, parent):
        """the cells of a run's target, from the selection written in its output file."""
        if selection["method"] == "named_feature":
            pixels = np.asarray(self.targets[selection["params"]["feature_id"]]["healpix_pixels"], dtype=np.int64)
        else:
            pixels = self.select_pixels(selection["method"], selection["params"])
        prow = [self.names.index(d) for d in self.parents[parent]["dimensions"]]
        return pixels[np.isfinite(self.Bd[prow][:, pixels]).all(0)]

    def state_from_disk(self, out_dir):
        """what point() needs, rebuilt from a run folder: the maps on disk and the target's medians."""
        doc = jl(ROOT, out_dir, "output.json")
        run = doc["run"]
        order = [v["name"] for v in run["variables"]]
        parent = [k for k, v in self.parents.items() if set(v["dimensions"]) == set(order)][0]
        pixels = self.target_pixels(run["target"]["selection"], parent)
        maps, rank = {}, None
        for r in doc["rasters"]:
            arr = np.load(os.path.join(ROOT, r["file"]), mmap_mode="r")[self.epix]
            if r["name"] == "rank_combined":
                rank = np.asarray(arr)
            else:
                maps[r["name"].replace("di_", "")] = np.asarray(arr)
        return dict(name=run["target"]["name"], maps=maps, rank=rank, order=order,
                    t_pos={d: float(np.nanmedian(self.Bd[self.names.index(d), pixels])) for d in order},
                    ranked={v["name"] for v in run["variables"] if v["ranked"]},
                    beyond={o["variable"] for o in run["ranking"]["out_of_range"]},
                    d_bar_target=run["d_bar_target"], d_bar=run["d_bar_earth"], limits=doc["limits"])

    # ---------------------------------------------------------------- click anywhere (contract/point_schema.json)
    def point(self, state, lat, lon):
        """Any Earth cell against the target of a finished run (`state` is the third value a run returns)."""
        from astropy import units as u
        Dd = self._describers()
        pix = int(Dd["hp"].lonlat_to_healpix(float(lon) * u.deg, float(lat) * u.deg))
        if not hasattr(self, "_epix_order"):
            self._epix_order = np.argsort(self.epix)
            self._epix_sorted = self.epix[self._epix_order]
        k = int(np.searchsorted(self._epix_sorted, pix))
        scored = k < self.n and int(self._epix_sorted[k]) == pix
        if scored:
            col = int(self._epix_order[k])
            s = self.describe(col, state["maps"], state["order"], state["t_pos"], state["ranked"], state["beyond"], state["d_bar_target"], state["d_bar"])
            return dict(contract_version="2.4", target_name=state["name"], lat=s["lat"], lon=s["lon"], healpix_pixel=pix,
                        in_reference_population=True, reason_excluded=None, di_combined=s["di_combined"], di_group=s["di_group"],
                        worst_group=s["worst_group"], dims_used_here=s["dims_used_here"], variables=s["variables"],
                        agrees=s["agrees"], partial=s["partial"], differs=s["differs"], best3=s["best3"], worst3=s["worst3"], use=s["use"],
                        koppen=s["koppen"], lithology=s["lithology"], catalogue=s["catalogue"],
                        limits=state["limits"] + f" This cell ranks at {100 * float(state['rank'][col]):.2f}% (0% is the best cell on Earth).")
        # a cell outside the ranking population still answers: what it is, and why it has no score
        plon, plat = Dd["hp"].healpix_to_lonlat(pix)
        plat, plon = float(plat.deg), float(((plon.deg + 180.0) % 360.0) - 180.0)
        kc, li, gm = int(Dd["koppen"][pix]), int(Dd["l1"][pix]), int(Dd["gmc"][pix])
        if "refmask" not in Dd:
            f = os.path.join(HP, "earth_reference_mask_nside1024.npy")
            Dd["refmask"] = np.load(f, mmap_mode="r") if os.path.exists(f) else None
        in_ref = bool(Dd["refmask"] is not None and np.isfinite(Dd["refmask"][pix]) and Dd["refmask"][pix] > 0.5)
        reason = "missing_dimension" if in_ref else ("ocean" if (kc == 0 and li == 255 and gm == 0) else "ice")
        la, lo = np.radians(plat), np.radians(plon)
        c = Dd["cat"]
        dist = 2 * RADIUS_KM["earth"] * np.arcsin(np.sqrt(np.sin((c["lat"] - la) / 2) ** 2 + np.cos(la) * np.cos(c["lat"]) * np.sin((c["lon"] - lo) / 2) ** 2))
        i = int(np.argmin(dist))
        known = bool(dist[i] <= 100.0)
        return dict(contract_version="2.4", target_name=state["name"], lat=round(plat, 4), lon=round(plon, 4), healpix_pixel=pix,
                    in_reference_population=in_ref, reason_excluded=reason, di_combined=None,
                    di_group=dict(terrain=None, thermal=None, composition=None), worst_group=None, dims_used_here=0, variables=[],
                    agrees=[], partial=[], differs=[], best3=[], worst3=[], use=dict(succeeds=[], fails=[], beyond_earth=[], general=None),
                    koppen=None if kc == 0 else dict(code=kc, symbol=Dd["legend"][str(kc)]["symbol"], description=Dd["legend"][str(kc)]["description"]),
                    lithology=(dict(l1_code=chr(gm), description=Dd["gm_mean"].get(chr(gm), chr(gm)), source="GeoMAP") if gm > 0
                               else None if li == 255 else dict(l1_code=Dd["l1vocab"][str(li)], description=Dd["l1mean"].get(Dd["l1vocab"][str(li)], Dd["l1vocab"][str(li)]), source="GLiM")),
                    catalogue=dict(status="known" if known else "new candidate", name=c["name"][i] if known else None,
                                   citation=c["source"][i] if known else None, distance_km=round(float(dist[i]), 1)),
                    limits="This cell is outside the ranking population (" + reason.replace("_", " ") + "), so it has no score. "
                           "'ocean' and 'ice' are told apart only by whether a climate or rock class exists for the cell.")
