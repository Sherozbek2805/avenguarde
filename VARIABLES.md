# VARIABLES.md — the decision log

> **Read this first (added 15 November 2026).**
>
> **What this file is.** The team's working log: every method decision, the
> measurement behind it, and every correction, in the order they happened
> (B1 to B40). It is long and blunt on purpose. Nothing is deleted: a
> statement that was later found wrong is struck through and the correction
> is written beside it.
>
> **When the work was done.** Sections B1 to B38 (6 to 11 November) are the
> PREPARATION before the hackathon weekend: choosing the variables, building
> the data cube, fixing the method. The local organisers confirmed that
> preparing data in advance is allowed. Section B39 (14 November) is the
> hackathon day: the engine, all the results and the choice of the main
> ranking system. Section B40 (14 and 15 November) is the website and its
> server.
>
> **Who decided.** The team. An AI assistant (Claude, Anthropic) wrote most
> of the text and the code, proposed options with measurements and gave
> recommendations. The team chose, sometimes against the recommendation, and
> the log says so each time. See `AI_USE.md`.
>
> **Paths that are not in the repository.** `HANDOVER.md`, `CONTEXT.md` and
> `cube/_work/`, named in places below, are local working files.
>
> **Where to read the method without the history.** The method as it stands
> is in `docs/analog_finder_method_spec_rev11.docx` (10 pages). Sections B33
> to B39 below hold the same thing with the reasons.

~~**Specifications only. Nothing here is implemented.** Read on hackathon day and
turned into code then.~~ *(True on 6 November 2026, when this file began. The
cube, the calibration and the engine now exist; see B24, B25 and B39.)*
Formulas, parameters, costs and pseudocode.

Settled and not re-opened: HEALPix NESTED, Nside 1024 Earth / 256 Moon / 512 Mars
(pixel sides 6.37 / 6.95 / 6.79 km, no area weighting); slope 7 km and ruggedness
21 km on all bodies; SI units, temperature in kelvin; ~~no lunar silica dimension;
thermal inertia dropped;~~ *(superseded: lunar SiO2 was built, B22; thermal inertia is stored and does not rank, B27 and B38)* lunar targets polar at 85–89.9°S.

HEALPix pixel counts that drive every cost below:
Earth 12 × 1024² = **12,582,912**; Mars 12 × 512² = **3,145,728**;
Moon 12 × 256² = **786,432**.

---

## Summary — read this at 2am

1. **Concavity: specify it as Topographic Position Index**, `TPI = z − mean(z within R)`.
   Cheap, standard, citable, and all three bodies already have elevation.
2. **Sign convention: TPI < 0 means INSIDE A BOWL.** Store TPI, not "concavity",
   and name the layer `*_tpi` so the sign can never be misread.
3. **R = 21 km radius**, matching the ruggedness window. Justified by landform
   scale, not symmetry: Shackleton is ~21 km across, so a 21 km *radius* window
   spans 42 km and the crater floor reads strongly negative against the highlands.
4. **Use a summed-area table.** TPI then costs O(N) *independent of R* — the
   window size becomes free. **2–15 min per body.** This is the cheap win.
5. **Sky view factor: `SVF = 1 − (1/n)·Σ sin(γ_i)`**, Zakšek et al. 2011; horizon
   sweep after Dozier, Bruno & Downey 1981.
6. **A naive ray cast is ~34 billion steps for Earth alone — hours to days.** The
   horizon sweep is ~1.1 billion cheap operations instead.
7. **SVF at 1 km, 16 azimuths, 30 km radius: 10–40 min per body.** Under the
   one-hour bar, but only with vectorised row sweeps. Fallbacks given if not.
8. **Compute both natively, then bin to HEALPix** — confirmed, with one honest
   caveat: TPI does not aggregate exactly, only approximately, and the
   approximation is good because R (21 km) ≫ pixel (6.4–7.0 km).
9. **Mars temperature level: recompute as a midrange.** All 48 MCD files are
   present (4 Ls × 12 local times, verified complete). `mars_temp_swing` needs
   **no change** — it already uses the same max and min.
10. **Dimension count goes 4 → 6 Earth–Moon polar**, which is the number that
    matters, and 5 → 7 Earth–Mars global.

---

## B1 — CONCAVITY

### The measure

**Topographic Position Index.** For a cell at elevation `z`:

> **TPI = z − mean(z over all valid cells whose centre lies within radius R)**

Units: **metres**, same as elevation. Positive and negative both meaningful.

Source: **Weiss, A. D. (2001), "Topographic Position Index and Landform
Analysis", poster, ESRI International User Conference, San Diego.** The
underlying formulation is from **Guisan, A., Weiss, S. B. & Weiss, A. D. (1999),
"GLM versus CCA spatial modeling of plant species distribution", *Plant Ecology*
143:107–122**, which introduces the elevation-minus-neighbourhood-mean term. For
a worked treatment of the scale dependence see **De Reu, J. et al. (2013),
"Application of the topographic position index to heterogeneous landscapes",
*Geomorphology* 186:39–49.**

Why TPI rather than curvature: curvature is a **second derivative** and therefore
amplifies DEM noise and grid artefacts, which is exactly the wrong property at
85–89.9°S where the lat/lon grid is already degenerate. TPI is a **difference of
means** — a smoothing operation minus a point value — so it is numerically
stable, and it answers the question actually being asked ("is this place low
relative to its surroundings?") rather than "how fast is the slope changing?".

### Sign convention — state it on every output

| TPI | meaning | landform |
|---|---|---|
| **TPI < 0** | the cell is **LOWER** than its surroundings | **inside a bowl** — crater floor, basin, valley |
| TPI ≈ 0 | at the local mean | plain, or a uniform slope |
| TPI > 0 | higher than its surroundings | rim, ridge, peak, massif |

**Store TPI and name the layers `earth_tpi_21km`, `moon_tpi_21km`,
`mars_tpi_21km`.** Do **not** name them `*_concavity`: "concavity" invites the
opposite sign and there is no convention to appeal to. If a positive-means-concave
variable is wanted for presentation, derive it at display time as `−TPI` and say
so in the label. The percentile transform is monotone, so the sign convention
affects ranking direction and must be fixed once, in the manifest, in words.

### R — the radius

**Recommend R = 21 km, matching the ruggedness window.** The justification is
landform scale, not aesthetic symmetry with ruggedness:

- A TPI window must be **comparable to or larger than** the landform it is meant
  to detect. If R is smaller than the feature, the window sits entirely inside it
  and the mean converges on the cell's own elevation, driving TPI → 0. A crater
  floor would then read as flat ground.
- **Shackleton crater is ~21 km in diameter.** R = 21 km *radius* gives a 42 km
  window — comfortably wider than the crater — so a floor cell is differenced
  against the surrounding highlands and reads strongly negative. This is the
  single most important target in the project and it fixes the scale.
- The same radius is sane on Mars (Jezero ~45 km, Gale ~154 km — both larger than
  the window, so their floors read negative) and on Earth (Ries ~24 km, Barringer
  1.2 km — note Barringer is *smaller* than the window and will read near zero,
  which is correct behaviour, not a bug).

**Secondary recommendation, nearly free:** also compute **R = 7 km**, matching the
slope baseline. With a summed-area table the marginal cost of a second radius is
one extra pass, and TPI is strongly scale-dependent — a 7 km TPI distinguishes
small craters and rille floors that a 21 km window averages away. Two radii give a
crude landform decomposition for the cost of one extra subtraction. Decide on
hackathon day whether the extra dimension is wanted; **do not** add both to the
matching set without re-reading §B5, because adding a dimension can only lower
coverage.

**Window shape:** a **disc** (cells whose centre is within R), not a square. A
square window is anisotropic — its corners reach `R√2` — and on a lat/lon grid
that anisotropy rotates with latitude. If a square is used for speed, record it
in the manifest as a square and state the effective radius range.

### Where it is computed — compute native, then bin. CONFIRMED.

**Compute TPI on the native lat/lon source raster at the stated physical scale,
then area-average the RESULT onto HEALPix.** Arguing *for* this, as asked:

1. **HEALPix has no regular neighbour lattice.** A 21 km disc query per pixel means
   12.58 million `query_disc` calls on Earth. That is workable but it is both
   slower and more code than a summed-area table, and it buys nothing.
2. **Computing on HEALPix would compute from already-aggregated elevation.** The
   terrain detail inside a 6.37 km pixel is exactly what distinguishes a crater
   floor from its rim, and aggregation has already discarded it. Deriving a
   terrain descriptor from a terrain average is a measurable loss, not a
   convenience.
3. **It matches the existing rule.** The manifest's `resampling_policy` already
   states `downsampling: GDAL average (area-weighted incl. partial pixels);
   nodata skipped; NaN only if no valid source pixel`. Computing native and
   aggregating the result is that rule applied to a derived quantity.

**The honest caveat, which must go in the manifest.** TPI does **not** aggregate
exactly. Let `A` denote averaging over a HEALPix pixel and `M` the 21 km
neighbourhood mean. Binning the native result gives `A(z) − A(M(z))`. Computing
TPI from aggregated elevation would give `A(z) − M(A(z))`. These are equal only
when `M` and `A` commute, which they do not in general. The error is governed by
the ratio of scales: with R = 21 km against a 6.37–6.95 km pixel, the
neighbourhood is ~3× the pixel in radius and ~9× in area, so the two means are
dominated by the same terrain and the discrepancy is small. **It is not zero.**
Record the choice as `computed_on: native lat/lon raster; aggregated_after: area
average` and note the non-commutation rather than implying exactness.

### Nodata behaviour at the edge of valid data

- A cell whose own elevation is nodata → **TPI is nodata.** Never substitute 0.
- For the neighbourhood mean, **skip nodata cells and require ≥50% of the disc's
  cells to be valid**, otherwise TPI is nodata. This matches the existing
  roughness rule exactly (`NaN if < half the window valid`), so the two 21 km
  quantities share one validity footprint — which is what makes them comparable.
- **Record the valid-cell count per output pixel.** A TPI computed from 51% of its
  window is not the same measurement as one from 100%, and a downstream reader
  cannot tell them apart otherwise.
- **The polar case, which is the one that matters.** On a lat/lon grid at 89°S a
  fixed-km disc spans almost all 3600 columns, and the existing `polar_policy`
  already widens the east–west stencil as `1/cos(lat)` with
  `reduced_reliability_beyond_lat: 85.0`. For TPI this degeneracy is worse than
  for slope because the window is larger. **Recommendation: for |lat| > 80 on the
  Moon, compute TPI on a polar stereographic reprojection of LOLA** (both poles),
  then bin that result to HEALPix alongside the global pass. The manifest's own
  `proper_fix` field already says `resample polar regions to a polar stereographic
  projection`. This is the one place where the extra projection is unavoidable,
  because 85–89.9°S *is* the target band.

### Pseudocode

```
for each body:
    load native elevation raster (tiled if it exceeds memory)
    if body is Moon and |lat| > 80:
        reproject that cap to polar stereographic at native scale
    # neighbourhood mean via summed-area table -- cost independent of R
    build S  = cumulative sum of z over rows then columns      (float64)
    build Sv = cumulative sum of valid-mask over rows then columns
    for each cell:
        determine the disc in cell units from R and the local pixel size
        sum_z      = rectangle sums from S  over the disc's row runs
        n_valid    = rectangle sums from Sv over the disc's row runs
        if n_valid < 0.5 * n_cells_in_disc:  TPI = nodata
        else:                                TPI = z - sum_z / n_valid
    area-average TPI onto HEALPix NESTED at the body's Nside
    write the valid-cell count per HEALPix pixel alongside
```

Use **float64 for the summed-area table.** Earth's ETOPO at 1 arc-min accumulates
2.3 × 10⁸ values; in float32 the running sum loses low-order bits long before the
end of a row and the differenced rectangle sums become visibly wrong. This is a
real failure mode, not a theoretical one.

For a true disc, accumulate the per-row horizontal runs (two SAT lookups per row
of the disc) rather than one rectangle. Cost is `O(N × R_rows)` lookups, still far
below a direct window sum, and `scipy.ndimage.uniform_filter` offers a separable
square alternative at `O(N)` if a square is accepted.

### Runtime estimate per body

Assumptions, stated: single commodity workstation, NumPy/SciPy vectorised, float32
rasters with a float64 SAT, tiled I/O from local disk at ~200 MB/s, no GPU, no
parallelism beyond NumPy's own.

| body | native raster | pixels | approach | estimate |
|---|---|---|---|---|
| **Earth** | `ETOPO_2022_v1_60s_N90W180_surface.tif`, 1 arc-min | 10,800 × 21,600 = **233 M** | SAT directly, tiled with 21 km halo | **2–6 min** |
| **Mars** | `Mars_MGS_MOLA_DEM_mosaic_global_463m.tif`, 463 m | 23,040 × 46,080 = **1.06 G** | downsample to ~1 km first, then SAT | **5–15 min** |
| **Moon** | `Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif`, 118 m | 46,080 × 92,160 = **4.25 G** | **must** downsample; one I/O pass over 8.1 GB dominates | **8–25 min**, plus **3–10 min** for the two polar stereographic caps |

Why the Moon must be downsampled: 4.25 G pixels in float32 is **17 GB** for the
raster alone and ~34 GB for a float64 SAT. It will not fit. LOLA at 118 m is
**59× finer** than the 6.95 km output pixel, so downsampling to ~1 km before
computing a **21 km** TPI discards nothing the output can represent. State the
intermediate resolution in the manifest.

**Total for all three bodies: roughly 15–55 minutes.** This is the cheapest real
dimension available and should be done first.

---

## B2 — SKY VISIBILITY (sky view factor)

### The formula

For a cell, with the horizon elevation angle `γ_i` measured upward from
horizontal in each of `n` equally spaced azimuths:

> **SVF = 1 − (1/n) · Σᵢ sin(γᵢ)**

Dimensionless, on **[0, 1]**. SVF = 1 is a flat plain with a free horizon; SVF → 0
is the floor of a deep, steep-walled pit.

The derivation, so the formula is checkable rather than trusted: for a horizontal
surface with the horizon at angle `γ` in every direction, sky is visible for
zenith angles `0` to `90° − γ`. The solid angle is
`Ω = 2π(1 − cos(90° − γ)) = 2π(1 − sin γ)`, and dividing by the full hemisphere
`2π` gives `1 − sin γ`. Averaging over azimuths gives the expression above.

Source: **Zakšek, K., Oštir, K. & Pokrajac, Z. (2011), "Sky-View Factor as a
Relief Visualization Technique", *Remote Sensing* 3(2):398–415.**

**Variant to be aware of, and to choose deliberately.** For radiative transfer the
cosine-weighted form is the correct one:

> `SVF_cos = (1/n) · Σᵢ cos²(γᵢ)`

from **Dozier, J. & Frew, J. (1990), "Rapid calculation of terrain parameters for
radiation modeling from digital elevation data", *IEEE Transactions on Geoscience
and Remote Sensing* 28(5):963–969.** The two are not interchangeable: the
cosine-weighted version down-weights sky near the horizon, which is physically
right for energy balance and wrong for "how much sky can be seen". **Recommend
the Zakšek form**, because the dimension being added is *openness*, and because
the thermal dimensions already carry the radiative information. Record which form
was used; a reader cannot tell from the values alone, since both live on [0, 1].

### Azimuths and search radius

- **n = 16 azimuths** (22.5° spacing). 8 is visibly faceted in enclosed terrain
  and 32 doubles the cost for a change below the DEM's own noise. 16 is the usual
  compromise in the visualisation literature. Record `n` in the manifest — SVF is
  not comparable across different `n`.
- **Search radius 30 km.** Reasoning: the horizon that matters for a lunar polar
  crater is its own rim. Shackleton's rim stands ~4 km above its floor over a
  ~10 km horizontal run, an angle of ~21°; terrain beyond ~30 km contributes
  horizon angles below a few degrees, whose `sin γ` contribution is under 0.05.
  A 50 km radius is defensible and costs ~1.7× more; **anything under 10 km
  truncates the rim itself and is wrong.**
- Record the radius. An SVF at 30 km and one at 50 km are different variables.

### The algorithm — and what not to do

**Do not ray-cast per pixel.** Cost is `N_pixels × n_azimuths × steps_per_ray`.
For Earth land at 1 km with 16 azimuths and a 30 km radius that is
`70 M × 16 × 30 ≈ 3.4 × 10¹⁰` steps, and at full ETOPO resolution it is
`233 M × 16 × 16 ≈ 6 × 10¹⁰`. In NumPy that is hours; in pure Python, days. The
user is right that it will not finish.

**Use a horizon sweep.** Source: **Dozier, J., Bruno, J. & Downey, P. (1981), "A
faster solution to the horizon problem", *Computers & Geosciences* 7(2):145–151.**
The structure:

```
for each of the n azimuths:
    rotate (or shear/resample) the elevation grid so the azimuth runs along +x
    for each row of the rotated grid:
        sweep once along the row maintaining a monotonic stack/deque of
        candidate horizon points
        at each cell, the deque front gives the maximum horizon ANGLE
        within the search radius -- angle, not elevation, because the
        relevant quantity is (dz / horizontal distance)
        evict candidates that fall outside the search radius
    rotate the per-azimuth horizon-angle field back
accumulate sin(gamma) across azimuths, then SVF = 1 - mean
```

The deque gives **amortised O(1) per cell per azimuth**, so total cost is
`N_pixels × n_azimuths` cheap operations rather than
`N_pixels × n_azimuths × radius_in_cells`. For Earth land at 1 km that is
`70 M × 16 ≈ 1.1 × 10⁹` — a **30× reduction** against the naive form, before any
vectorisation.

Two correctness points that are easy to get wrong:

- **Compare angles, not elevations.** A nearer low ridge can occlude a farther
  high one. Maintaining the running maximum of `z` instead of `dz/d` is the
  classic bug and it produces a plausible, smooth, wrong field.
- **The rotation resamples.** Rotating a grid by 22.5° interpolates, which
  smooths terrain and biases horizon angles low, i.e. SVF high. Either rotate
  once per azimuth with nearest-neighbour (preserving extremes, costing
  aliasing) or sweep along Bresenham lines in the unrotated grid (no resampling,
  more bookkeeping). **Recommend Bresenham sweeps** and record the choice.

### Resolution — and the approximation being made

**Compute at 1 km, not at native resolution.** The reasoning is explicit:

- The search radius is **30 km**. At 1 km the radius is 30 cells, which resolves a
  crater rim profile adequately.
- Native LOLA at 118 m would give a 254-cell radius and **59× the pixel count**
  for horizon angles that differ by a fraction of a degree, because a rim 10 km
  away is not better resolved by 118 m sampling than by 1 km sampling at that
  distance.
- **The approximation stated plainly:** sub-kilometre terrain is invisible to this
  SVF. A 200 m boulder field, a small rille, or a pit a few hundred metres across
  will not reduce it. The variable measures **basin-scale openness**, and the
  manifest must say so, because a reader will otherwise assume a 118 m DEM
  produced a 118 m-faithful answer.
- If a finer answer is wanted for the lunar polar targets specifically, compute a
  **second** SVF at 250 m over the two polar caps only. That is a small area and
  therefore cheap — see the fallback table.

**Same native-then-bin answer as B1: compute on the native (downsampled) raster,
then area-average onto HEALPix.** SVF is a bounded ratio, and averaging a ratio
over a HEALPix pixel is not the SVF of the averaged terrain. The same
non-commutation caveat applies and must be recorded. For the Moon, **the polar
caps must be done in polar stereographic** — more so than for TPI, because a
horizon sweep along a lat/lon row at 89°S sweeps a path that is physically
curved and converging, and the azimuths are not the azimuths they claim to be.
**This is not a refinement; a lat/lon sweep at the lunar south pole is simply
wrong**, and 85–89.9°S is the target band.

### Runtime estimate — and the honest verdict

Assumptions: as B1, plus vectorised row sweeps (the per-row deque applied across
many rows at once), 16 azimuths, 30 km radius, computed at 1 km, Earth restricted
to land (34.64% of cells).

| body | grid at 1 km | pixels swept | ops (`px × 16`) | estimate |
|---|---|---|---|---|
| **Earth** (land only) | ~40,000 × 20,000, 34.64% land | **~277 M** | 4.4 × 10⁹ | **20–50 min** |
| **Mars** | 21,300 × 10,650 | **227 M** | 3.6 × 10⁹ | **15–45 min** |
| **Moon** | 10,920 × 5,460 | **60 M** | 0.95 × 10⁹ | **5–15 min** |
| **Moon polar caps**, polar stereographic, 250 m, |lat| > 80 | 2 × ~(2,000 × 2,000) | 8 M | 1.3 × 10⁸ | **1–3 min** |

**Verdict, stated plainly: this is at or slightly over the one-hour bar for
Earth, and comfortably under it for the Moon and Mars.** The Earth figure is the
uncertain one — it spans 20–50 min and could exceed an hour if the rotation or
sweep is not properly vectorised, if memory pressure forces extra I/O passes, or
if the land restriction is not exploited. Treat one hour as the budget, not the
expectation, and **measure one azimuth before committing to sixteen** — the cost
is almost exactly linear in `n`, so a single timed azimuth predicts the total to
within the noise.

### Cheaper variants, in the order I would reach for them

1. **Drop to n = 8 azimuths.** Exactly halves the cost. The loss is faceting in
   enclosed terrain — visible in a visualisation, largely harmless in a
   percentile rank, because the error is systematic rather than random and the
   transform is monotone. **This is the first thing to do if Earth overruns.**
2. **Compute at 2 km instead of 1 km.** Quarters the pixel count, so Earth drops
   to ~5–13 min. The radius becomes 15 cells, which still resolves a rim profile.
   Combined with n = 8 this is ~8× cheaper than the headline plan.
3. **Restrict Earth to plausible candidates.** The engine ranks land only; if
   candidate centres are on a lattice rather than every pixel, SVF is needed only
   in neighbourhoods of those centres, not globally. This is the largest possible
   saving and costs nothing in fidelity — but it couples the variable to the
   candidate set, so a later lattice change invalidates it. **Record the coupling
   if this route is taken.**
4. **Fall back to a proxy and label it as one.** `−TPI` at 21 km already carries
   much of the same information: a cell low relative to its surroundings usually
   has a restricted horizon. The correlation is strong but not one, and the proxy
   fails exactly where it matters most — a wide flat crater floor has very
   negative TPI and a fairly *open* sky, while a narrow rille has modest TPI and
   a very closed one. **Use this only as a stopgap, name it `tpi_proxy`, and do
   not call it a sky view factor.**

If none of these fits the day's budget, **ship five dimensions and say so.** A
missing dimension is a known limitation; a wrong one computed from a lat/lon
sweep at the pole is a result that has to be retracted.

---

## B3 — RECOMPUTE MARS TEMPERATURE LEVEL AS A MIDRANGE

### Why midrange wins

| body | current definition | kind |
|---|---|---|
| Earth | `mean over 12 months of (tmin + tmax)/2` | midrange |
| Moon | `(tbol_max + tbol_min)/2` | midrange |
| Mars | `mean over 4 Ls of (mean over 12 local times)` | **true mean** |

Mean and midrange differ whenever the diurnal curve is skewed, which it always
is — a surface sits near its minimum through the night and spikes near noon, so
the midrange sits **above** the true mean. Ranks survive the mismatch because all
three are monotone in "how hot is this place"; **physical-unit comparisons do
not**, so a claim like "within 5 K of the target" is currently invalid across the
pair.

**The Moon is the binding constraint.** Only `diviner_tbol_max.xyz` and
`diviner_tbol_min.xyz` are held — two extremes at 0.5°, no local-time series. A
true mean cannot be constructed there at all. So the common definition must be the
midrange, and **Mars is the one that moves.**

### Source files — located and verified

**`D:\NASA hacathon\sources\mcd_prototype\`**

- **48 files present, `tsurf_ls{000,090,180,270}_lt{00,02,…,22}.txt`.**
- Ls values: `000, 090, 180, 270` (**4**).
- Local times: `00, 02, 04, 06, 08, 10, 12, 14, 16, 18, 20, 22` (**12**, 2-hour steps).
- **The 4 × 12 grid is complete — all 48 combinations verified present, none
  missing.**
- Units read from the file header, not inferred:
  `### Columns 2+ are Surface temperature (K)`.
  Also in the header: `### MCD_v6.2 with climatology average solar scenario.`,
  `### Ls 0.0deg. Altitude 10.0 m ALS. Local time 0.0h (fixed at all longitudes)`,
  `### Column 1 is East longitude (degrees)`.
- Native grid **64 × 48** (5.625° × 3.75°), per the manifest's
  `native_resolution`.
- `sources\mcd_prototype\manifest.json` records `source`, `cgi`, `scenario`,
  `variable`, `grid`, `hrkey`, `isfixedlt`, `ls_values`, `local_times`,
  `delay_seconds`, `files`.

**Carry the PROVISIONAL status forward.** The existing manifest marks these
`status: PROVISIONAL` with `provisional_because` listing: built from the **web
interface, not the full database**; **4 solar longitudes out of 12 MCD months**;
12 local times per sol; **climatology scenario, average solar EUV only
(dust = 1), no dust-storm or EUV extremes**; *"for development only, not for the
final result"*. `replaced_by` names a bake from the full MCD 6.2 netCDF files —
**which are not present anywhere under this root.** Recomputing as a midrange
fixes the *definition* mismatch; it does not upgrade the *source*.

### The recomputation

```
for each of the 4 Ls values:
    read the 12 local-time grids for that Ls        -> 12 x (48 x 64) in K
    per cell:
        t_max_ls   = max over the 12 local times
        t_min_ls   = min over the 12 local times
        midrange_ls = (t_max_ls + t_min_ls) / 2
mars_temp_level = mean of the 4 midrange_ls grids
    units: K          (no conversion -- the MCD is already kelvin)
    nodata: none; the MCD returns a value at every grid point
    then resample 48 x 64 -> HEALPix Nside 512, nearest neighbour (upsampling)
```

**The approximation to record, because it is not small.** A 2-hour sampling
interval does not capture the true daily extremes. The real maximum falls between
samples, so `t_max_ls` is biased **low** and `t_min_ls` biased **high** — the
midrange error partly cancels, but the *swing* is biased **low** on both ends.
With 12 samples the peak is missed by up to 1 hour of local time. Record this as
`sampling_bias: daily extremes are under-sampled at 2-hour steps; the midrange
error partly cancels while the swing is biased low`.

Also record the definitional change explicitly, with the old value kept for
traceability: `superseded_method: "mean over 4 Ls of (mean of surface temperature
over 12 local times)"`, and a note that stored percentile ranks change even though
the variable's meaning is now *more* comparable, so any cached run is invalidated.

### Does `mars_temp_swing` need the same treatment? — **No. It is already consistent.**

Its current method, verbatim from the manifest:

> `mean over 4 Ls of (max - min of surface temperature over 12 local times). The
> MCD has no daily-maximum or daily-minimum variable, so the daily range is
> derived from the local-time sampling.`

It already computes `max` and `min` over the same 12 local times, per Ls, then
averages. **Those are exactly the two statistics the new level needs**, so after
B3 the Mars pair becomes:

- `mars_temp_level = mean over Ls of (max + min)/2`
- `mars_temp_swing = mean over Ls of (max − min)`

— the sum and difference of one pair of extremes, which is the same relationship
the Moon's two layers already have. **Implement them in one pass**, since the max
and min are computed once and feed both. No change to the swing's definition, no
re-download, no new source.

One residual mismatch, out of scope here but worth recording: for **swing**,
Earth and Mars are *means of ranges* while the Moon is a *single range of
extremes*. A sample extremum grows with the number of observations, so the lunar
swing is sensitive to how much Diviner coverage a cell received in a way the other
two are not. B3 does not address this and does not need to — but do not let anyone
later believe the swing triple is fully harmonised.

---

## B4 — REMOVE THERMAL INERTIA AS A DIMENSION

No pair exists. Evidence, with units read from the manifests:

| layer | units | coverage | verdict |
|---|---|---|---|
| `mars_thermal_inertia` | `tiu = J m-2 K-1 s-1/2` | 95.39% global, 37.92% above 85° | real thermal inertia, Mars only |
| `moon_thermal_behav` | `K (deviation from global mean)` | 65.47% global, **0.000% poleward of 60°** | a temperature **anomaly**, not inertia |
| Earth | — | — | **no layer at all, and no source held** |

Different physical dimensions entirely, so no conversion closes the gap, and the
Earth side is absent regardless.

### What must change

**1. Layers that become CHARACTERIZATION, never dimensions**

| layer | new role | why |
|---|---|---|
| `mars_thermal_inertia` | characterization | genuinely informative about Mars surface properties; simply unpaired |
| `moon_rock_abundance` | characterization | `areal fraction`, no Earth counterpart, and ±60° |
| `moon_thermal_behav` | characterization, **with a polar warning** | 0.000% at the target band, so it is blank for every lunar polar target — a site sheet must print "no data" rather than an empty cell |
| `moon_cf` | characterization (already decided) | `µm`, non-monotonic in SiO₂, ±60° |
| `earth_lithology_class` | characterization | categorical, Earth only |
| `earth_srad`, `earth_temp_seasonal` | characterization | Earth only |
| `mars_non_silicate` | **recommend dropping entirely** | see Part A5 — no units, no method, no source, unpaired, 1.39% polar |

Define the distinction once, in writing: a **dimension** enters the distance
computation and the percentile space, and requires a counterpart on both bodies. A
**characterization** variable is reported for a site but never contributes to a
score. The engine must refuse to add a characterization layer to the matching set,
rather than relying on a convention.

**2. Manifests and spec sections that mention thermal inertia**

| location | change |
|---|---|
| `grids/manifest.json` → `variables.mars_thermal_inertia` | add `role: "characterization"` and `not_a_dimension_because: "no Earth or Moon counterpart; moon_thermal_behav is a K anomaly, not inertia"` |
| `grids/manifest_parts/mars.json` | same entry, same fields |
| `grids/manifest.json` → `variables.moon_thermal_behav` | add `role: "characterization"`, `not_a_dimension_because`, and `polar_warning: "0.000% valid poleward of 60 deg; blank for every lunar polar target"` |
| `grids/manifest.json` → `matching_notes` | add a `thermal_inertia` key stating the pair does not exist and why, alongside the existing `moon_composition` note that already does this for the Christiansen Feature |
| `DECISIONS.md` Task 3c and Task 5 | already state the finding; mark the decision as **settled** rather than open |
| `INGESTION.md` | `mars_thermal_inertia` row stays (the layer is still built) but is labelled characterization; the unrecorded day-vs-night choice remains an open question |
| `VARIABLES.md` (this file) | §B5 is the authoritative table |

**3. What the output contract should say**

- The dimension list is **explicit and named per body pair**, never inferred from
  which layers happen to exist. A layer appearing in `grids/` must not become a
  dimension by accident.
- Every result carries `dimensions_used: [...]` and `n_dimensions`, because
  coverage is **monotone decreasing** in dimension count — adding one can only
  lower it — so a coverage figure without its dimension count is unreadable.
- Characterization values appear in a separate `characterization: {...}` block,
  **with units**, and are explicitly marked as not contributing to the score.
- A characterization variable with no data at the target prints its **reason**
  (`"0.000% valid poleward of 60 deg"`), never a blank and never a zero. For a
  lunar polar target that applies to `moon_cf`, `moon_rock_abundance` and
  `moon_thermal_behav` simultaneously — three of the site sheet's entries will be
  empty, and the sheet must say why.
- `thermal_inertia` must **not** appear in any dimension list, any weight vector,
  or any percentile space. If a weight preset names it, that preset is malformed.

---

## B5 — THE FROZEN DIMENSION TABLE

Authoritative. Supersedes the table in `DECISIONS.md` Task 5.

A dimension counts for a pair only when **both** bodies carry a layer measuring
the same quantity. Usability threshold ≥50% valid in the relevant band; Earth
measured **of land cells** (2,244,499 of 6,480,000 = 34.637%), target bodies
measured globally and in the lunar polar band 85–90°S.

### Now — before B1 and B2

| dimension | Earth | Moon | Mars | E–Moon | E–Mars | polar-safe |
|---|---|---|---|---|---|---|
| slope | 99.84 | 99.78 | 99.89 | **yes** | **yes** | **yes** (Moon 96.0 at 85–90S) |
| ruggedness | 99.84 | 99.67 | 99.89 | **yes** | **yes** | **yes** (Moon 94.0) |
| temperature level | 100.0 | 100.0 | 100.0 | **yes**¹ | **yes**¹ | **yes** (Moon 100.0) |
| diurnal swing | 100.0 | 100.0 | 100.0 | **yes**² | **yes**² | **yes** (Moon 100.0) |
| silica | 67.90 | — | 61.54 | no³ | **yes** | **no** (Mars 1.34 above 85) |
| ~~thermal inertia~~ | — | — | 95.39 | **DROPPED** | **DROPPED** | — |

¹ harmonised by **B3**; before B3 the three definitions differ and physical-unit
comparison is invalid.
² Earth and Mars are means of ranges, the Moon a single range of extremes — see
the residual note in B3.
³ no lunar composition dimension by decision.

### After B1 (concavity) and B2 (sky visibility)

| dimension | Earth | Moon | Mars | E–Moon | E–Mars | polar-safe |
|---|---|---|---|---|---|---|
| slope | 99.84 | 99.78 | 99.89 | yes | yes | yes |
| ruggedness | 99.84 | 99.67 | 99.89 | yes | yes | yes |
| temperature level | 100.0 | 100.0 | 100.0 | yes | yes | yes |
| diurnal swing | 100.0 | 100.0 | 100.0 | yes | yes | yes |
| silica | 67.90 | — | 61.54 | no | yes | **no** |
| **TPI / concavity (new)** | from elevation 100.0 | from elevation 100.0 | from elevation 100.0 | **yes** | **yes** | **yes**⁴ |
| **sky view factor (new)** | from elevation 100.0 | from elevation 100.0 | from elevation 100.0 | **yes** | **yes** | **yes**⁴ |

⁴ polar-safe **conditional on the polar stereographic treatment in B1/B2**. All
three elevation layers are 100% valid at 85–90°S, so the inputs exist; a lat/lon
computation at 89°S would still be wrong. **If the polar caps are skipped, both
new dimensions are polar-unsafe and the polar counts below do not hold.**

### The four counts

| | now | after B1 + B2 |
|---|---|---|
| Earth–Moon, global | **4** | **6** |
| **Earth–Moon, POLAR** | **4** | **6** ← the number that matters |
| Earth–Mars, global | **5** | **7** |
| Earth–Mars, polar | **4** | **6** |

### Two things to hold in mind before adding both

**Coverage will fall, and that is expected.** Coverage is the fraction of the
target inside the candidate's area of applicability, and each added dimension adds
a dimension to the distance space, so every nearest-neighbour distance can only
grow and coverage can only fall. Going from 4 to 6 dimensions will reduce every
reported coverage figure. **This is not a regression** and must be stated wherever
the before/after numbers appear, or it will read as the new variables having
broken something.

**TPI and SVF are correlated, and the correlation is the point of weakness.** Both
derive from the same elevation raster, and a cell low relative to its surroundings
usually has a restricted horizon. Adding both therefore adds less independent
information than the count suggests, while costing the full coverage penalty of
two dimensions. **Measure the rank correlation between them on each body before
committing both to the matching set.** If Spearman exceeds ~0.8 on the Moon, ship
TPI alone — it is 20× cheaper to compute and polar-safe with less work — and keep
SVF as characterization.

---
---

# FOLLOW-UP — B6, B7, B8

Appended. §B1–B5 above are unchanged. Same rules: specifications, formulas,
parameters, costs and pseudocode. Nothing implemented, no data changed.

## Summary of the follow-up — read this at 2am

1. **Citation corrected.** The Shepard paper's title is longer than quoted, and
   it has six authors. Full reference in §B6. **It also defines the Hurst
   exponent from a different estimator than the one this pipeline would use** —
   that matters and is spelled out.
2. **B6 baselines: I argue against 7/14/28/56 and recommend 5.25/10.5/21/42.**
   Same pure doubling, same even log spacing, but it contains **21 km exactly**,
   so the existing ruggedness layer *is* one of the four points and stays
   byte-identical.
3. **B6 needs a common working resolution across bodies (~500 m), not each
   body's native pixel.** H is fitted over windows measured in *pixels*; if the
   pixel differs per body, H is not comparable across bodies. This also cuts
   Moon cost 16× and Mars 6×.
4. **B6 cost: 1–3 hours for all three bodies.** The most expensive item in this
   document after SVF. Store R² and withhold H where the fit is poor — that is
   not optional, it is the detector for "this surface is not self-affine here".
5. **B7: your hypothetical was wrong, in a way that matters.** Earth does **not**
   use the range of monthly means. It uses `max(tmax over months) − min(tmin over
   months)` — an envelope of extremes. Verified median over land **33.38 K**.
6. **So Mars must be the max-of-maxima minus min-of-minima over all 48
   (Ls, local-time) grids.** That is what I matched. All 4 Ls confirmed present.
7. **B7 carries a one-sided bias:** 4 Ls and 12 local times both under-sample the
   true extremes, so the Mars envelope reads **systematically low** against
   Earth's 12-month sampling. Ranks survive; physical comparison does not.
8. **B8's real finding: 5 of the 7 Earth–Moon candidates come from one raster.**
   Slope, ruggedness, concavity, scale exponent and sky view factor are all
   elevation-derived; only 2 are thermal. The effective dimensionality is far
   below 7, which is the whole problem.
9. **The ceiling is not a count, it is effective dimensionality** — so the
   selection rule and the ceiling are one problem, and the stopping test must be
   measured, not fixed at 8.
10. **Recommended: 6 for Earth–Moon, 7 for Earth–Mars.** Elevation-rank is
    **OUT**. Scale exponent is the first thing dropped.

---

## B6 — ROUGHNESS SCALE EXPONENT

### The citation — verified, and corrected

The reference as given ("Shepard et al. (2001), *The roughness of natural
terrain*") is **incomplete**. Verified full reference:

> **Shepard, M. K., Campbell, B. A., Bulmer, M. H., Farr, T. G., Gaddis, L. R., &
> Plaut, J. J. (2001). "The roughness of natural terrain: A planetary and remote
> sensing perspective." *Journal of Geophysical Research: Planets*, 106(E12),
> 32777–32795. DOI 10.1029/2000JE001429.**

Six authors, not "et al." after one; the subtitle **"A planetary and remote
sensing perspective"** is part of the title. The paper analyses topographic data
from ~60 surfaces collected by five groups and argues that scale-dependent
roughness parameters are almost always required and seldom used — which is
precisely the argument for this variable.

**Two findings in that paper that cut against the motivation, and must be carried
into the manifest rather than quietly dropped:**

- Shepard et al. report that natural surfaces tend to cluster near **H ≈ 0.5**,
  while noting this may be an artefact of limited data. If terrestrial and
  planetary surfaces both cluster near 0.5, **the dynamic range of this dimension
  may be small**, and a dimension with little spread contributes little to a
  distance however independent it is. **Measure the spread on each body before
  committing a slot** — §B8 makes this a gate, not a hope.
- They also caution that **H values are not uniquely diagnostic of geologic
  process** — they are a measure of roughness, not a process label. So the
  motivating example (a sand sea versus a blocky lava field) is a *plausible*
  discriminator, not a guaranteed one. Do not claim in the write-up that H
  identifies terrain type.

**A technical mismatch that must be named.** Shepard et al. define the Hurst
exponent from the **RMS height difference between point pairs separated by a lag
`r`** (the structure function, or deviogram), scaling as

> `ν(r) ∝ r^H`,  where `ν(r) = RMS[ z(x + r) − z(x) ]`

This pipeline's existing `*_roughness` layers are a **moving-window standard
deviation** (`NaN-aware std` over a window), which is a different estimator. The
two are related for a self-affine surface but are not the same number, and they
respond differently to long-wavelength trends: a window σ on a uniform slope is
non-zero and grows with window size, whereas a deviogram at lag `r` on the same
slope is also non-zero but with a different exponent. **A regional tilt therefore
biases a window-σ exponent toward H = 1.**

Two defensible routes:

| route | estimator | pros | cons |
|---|---|---|---|
| **(a) recommended** | window σ at four scales, fit the exponent | reuses the existing ruggedness machinery exactly; the four intermediate layers are directly comparable to the current 21 km layer | **not Shepard's estimator**; biased by regional slope |
| (b) | deviogram at four lags, per Shepard | the citable quantity; insensitive to the mean, less slope-biased | needs a second parameter (the estimation neighbourhood, separate from the lag); diverges from the existing roughness definition |

**Take route (a) for pipeline consistency — but name the output
`*_roughness_scaling_exponent`, not `*_hurst`,** and record
`estimator: "window standard deviation at four scales, log-log slope"` with
`not_shepard_deviogram: true`. Attaching a named quantity to a different
estimator is how a number becomes uncheckable. If the slope bias proves material
(test it: fit H on a synthetic uniform ramp, which must return H ≈ 1 and will
reveal the bias immediately), **detrend each window before taking σ**, or switch
to route (b).

### Baselines — argued, and I recommend against the proposal

The proposal is **7 / 14 / 28 / 56 km**. Pure doubling is the right *idea* and I
accept the reasoning: four points evenly spaced in `log` space give equal leverage
in a log-log least-squares fit, which is what a power law wants. Unevenly spaced
points let the extremes dominate the slope.

**But 21 km is not in that series, and it should be.** The existing ruggedness
dimension is defined at a 21 km window. With 7/14/28/56 none of the four
roughness layers reproduces it, so the project ends up holding **five** roughness
numbers per body at five scales, with the one that feeds the matching set sitting
outside the family the exponent was fitted to.

**Recommend 5.25 / 10.5 / 21 / 42 km.** Still pure doubling, still evenly spaced
in log space, and:

1. **21 km is literally one of the four points**, so the existing ruggedness layer
   is reused unchanged — no recompute, no risk of a subtly different 21 km value,
   and nothing already derived from it is invalidated.
2. The exponent and the level are then measured on **one family**, so "roughness
   at 21 km" and "how roughness scales" are two statistics of the same curve
   rather than two unrelated measurements.
3. The top window is **42 km rather than 56 km**, which is cheaper everywhere and
   materially so on the Moon (356 px instead of 475 px at 118 m native).

Keep 7/14/28/56 only if matching the **slope** baseline is judged more important
than matching the **ruggedness** baseline. I do not think it is: the exponent is a
property of roughness, and slope is a different quantity measured with a different
operator.

**Either way, record the series.** H is not comparable across different baseline
sets — a four-point fit over 5.25–42 km and one over 7–56 km are different
variables that happen to share a name.

**Centre the predictor in the fit.** Fit `log σ = a + H · (log s − mean(log s))`
rather than `log σ = a + H · log s`. Centering makes the fitted slope and
intercept **orthogonal**, so H carries only the scaling and not a share of the
overall roughness level. Without centering, H and the roughness level are
correlated by construction, which would manufacture exactly the redundancy §B8
then has to detect. With the recommended series the centre is the geometric mean,
`(5.25 × 10.5 × 21 × 42)^(1/4) ≈ 14.85 km`.

### Why it must be computed at native resolution — confirmed, with an addition

The argument as given is correct and decisive. At HEALPix Nside 1024/256/512 the
pixel sides are 6.37 / 6.95 / 6.79 km, so a **7 km window is about one pixel** and
a standard deviation of one value is undefined. Even the 21 km window would be
~3 pixels across, i.e. ~9 cells — below any sane variance estimate, and far below
the existing rule that a roughness window needs ≥50% of a much larger window
valid.

Measured native geometry, so the window sizes are not guesses:

| body | native raster | shape | pixels | 5.25 km | 21 km | 42 km | float32 size |
|---|---|---|---|---|---|---|---|
| Earth | ETOPO 2022 15 arc-sec surface, **288 tiles present, 4.9 GB** | 86,400 × 43,200 | **3.73 G** | 11 px | 45 px | 91 px | 13.9 GiB |
| Moon | LOLA LDEM 118 m | 92,160 × 46,080 | **4.25 G** | 44 px | 178 px | 356 px | 15.8 GiB |
| Mars | HRSC/MOLA blend 200 m, **11.4 GB present** | ~106,690 × 53,345 | **5.69 G** | 26 px | 105 px | 280 px | 21.2 GiB |

**An addition the brief did not ask for but which changes the method: use a common
working resolution of ~500 m on all three bodies, not each body's native pixel.**

The reason is comparability, not cost. H is estimated from a fit over windows
measured **in pixels**. At 118 m the 5.25 km window holds 44 px and at 463 m it
holds 11 px; the variance estimate at 11 px is noisier and, more importantly, the
*discretisation* of the window differs. Two bodies fitted over differently
sampled windows produce exponents that are not on the same footing, and the whole
point of the percentile transform is that the two sides measure the same thing
before ranking. **Resample Moon and Mars to ~463 m (Earth's native 15 arc-sec) and
fit all three identically.** Record it as
`working_resolution: 463 m (ETOPO 15 arc-sec), common to all three bodies`.

Side benefit: it cuts Moon pixels by ~16× and Mars by ~6×, which is most of the
cost below. There is no fidelity loss that the output can represent — the smallest
window is 5.25 km, which is 11 px at 463 m.

### The fit, and what to do when it is poor

Four points, one fit per pixel, ordinary least squares in log-log:

```
per pixel:
    s = [5.25, 10.5, 21, 42] km                   # the four baselines
    sigma = [roughness at each s]                 # metres, from the SATs
    drop any s whose roughness is nodata
    if fewer than 3 points remain:  H = nodata, R2 = nodata
    x = ln(s) - mean(ln(s))                       # CENTERED -- see above
    y = ln(sigma)
    H  = sum(x*y) / sum(x*x)                      # slope; intercept is orthogonal
    R2 = 1 - SS_resid / SS_total
```

**Store R². It is not optional.** A single exponent only exists if the surface is
self-affine over 5.25–42 km. Shepard et al. note that real surfaces have an
**outer scale** at which the trend flattens, interpreted as the scale where the
dominant formative process changes. A four-point fit spanning 8× may straddle such
a breakpoint, and when it does the fitted slope is an average of two regimes and
means nothing. **R² is the detector for exactly that**, and it is the only way a
downstream reader can tell a well-fitted H from a meaningless one.

Rules:

- **Withhold H where R² < 0.90** — emit nodata with
  `reason: "no single power law over 5.25-42 km (R2 below threshold)"`. A
  percentile rank computed over a mixture of well-fitted and badly-fitted
  exponents is not a ranking of anything.
- Record the **fraction of valid pixels withheld per body**. If that fraction is
  large on a body, the dimension does not exist there and should be dropped for
  that pair — this is a measurement, so make it before claiming the dimension.
- Clip H to **[0, 1]** per Shepard's definition and **count the clips**. An
  out-of-range fit is a diagnostic: `H > 1` usually means a regional trend
  dominating the window σ (see the estimator caveat above), `H < 0` means
  roughness falling with scale, which a self-affine surface cannot do.
- Keep the **four intermediate roughness layers** as output, as instructed. They
  are free once the SATs exist, they let a reader see the curve the exponent was
  fitted to, and the 21 km one is the existing ruggedness dimension.

### Cost — and the approach that finishes

**The naive form does not finish, and the brief is right about why.** A 42 km
moving σ at 463 m is a 91 × 91 window; at 56 km it is 121 × 121. Over 3.73 G
pixels that is `3.73e9 × 121²  ≈ 5.5 × 10¹³` operations for one scale on one body.

**Summed-area tables make each window O(1) per pixel, independent of window
size.** Variance needs two tables:

```
build S1 = cumulative sum of z    over rows then columns   (float64)
build S2 = cumulative sum of z*z  over rows then columns   (float64)
build Sv = cumulative sum of the valid mask                (int64)
for each of the four window sizes:
    for each pixel:
        n    = rectangle sum from Sv
        if n < 0.5 * window_cells:  roughness = nodata; continue
        m1   = rectangle sum from S1 / n
        m2   = rectangle sum from S2 / n
        var  = m2 - m1*m1
        roughness = sqrt(max(var, 0))
```

Three implementation requirements, each of which is a real failure mode:

- **float64 for S1 and S2, without exception.** S2 accumulates squared elevations:
  Earth elevations reach ~8,800 m, so `z²` reaches ~7.7 × 10⁷, and summing 3.7 × 10⁹
  of them reaches ~10¹⁷. float32 has ~7 decimal digits; the running sum loses the
  low-order bits long before the end of a row and the differenced rectangle sums
  come out visibly wrong. **This is the single most likely way to get a plausible
  but wrong H.**
- **`var = m2 − m1²` is catastrophically cancelling** when the window is nearly
  flat (ocean floor, mare interior, a playa). Both terms are large and nearly
  equal, and the difference loses most of its significant digits. Clamp negatives
  to zero as shown, and prefer a **shifted** accumulation — subtract a per-tile
  mean elevation from `z` before building the tables — which removes almost all of
  the cancellation for free.
- **Tile with a halo.** None of these tables fits in memory: Earth's S2 alone is
  3.73 G × 8 B = **29.9 GiB**. Tile the raster and carry a halo of at least half
  the largest window (46 px at 42 km, 463 m), so every output pixel has its full
  window. All four scales come from one pass per tile.

**Runtime estimate.** Assumptions, stated: one commodity workstation; NumPy
vectorised cumulative sums; float32 rasters read from local disk at ~200 MB/s;
float64 SATs; tiled with a 64-px halo; all four window sizes computed in the same
pass; resampled to a common 463 m working grid first; no GPU, no parallelism
beyond NumPy.

| body | working grid at 463 m | pixels | dominant cost | estimate |
|---|---|---|---|---|
| **Earth** | 86,400 × 43,200 (native) | 3.73 G | 3 SAT passes + 4 window evaluations, tiled | **25–60 min** |
| **Mars** | ~46,100 × 23,050 (from 200 m) | 1.06 G | one resample pass over 11.4 GB, then SAT | **20–50 min**, of which 10–25 is the resample |
| **Moon** | ~23,050 × 11,520 (from 118 m) | 0.27 G | one resample pass over 8.1 GB dominates | **15–35 min**, of which 10–25 is the resample |

**Total 1–2.5 hours for all three bodies**, with the resampling passes — pure
sequential I/O over 24 GB of source rasters — accounting for roughly half. This is
the second most expensive item in this document, behind sky view factor, and it is
**more expensive than concavity by roughly an order of magnitude** while being the
candidate most at risk of redundancy. §B8 weighs that explicitly.

Without the common-resolution step, Moon and Mars run at full native resolution
(4.25 G and 5.69 G pixels) and the total rises to **3–7 hours**, with H not
comparable across bodies. The resample is not an optimisation; it is the method.

---

## B7 — MARS SEASONAL SWING (Earth–Mars only)

### First: what `earth_temp_seasonal` actually computes

Read from `grids/manifest.json`, verbatim, not inferred:

| field | value |
|---|---|
| `method` | **`max(tmax over months) - min(tmin over months)`** |
| `units` | `°C (difference)` |
| `source` | WorldClim 2.1 10′ tmin + tmax, 12 months each |
| `native_resolution` | 10 arc-min (1080 × 2160) |
| `nodata` | `-3.4e38 (GeoTIFF header), masked read` |

Measured over Earth's 2,244,499 land cells: min 1.00, p25 26.11, **median 33.38**,
p75 41.31, max 72.30. This confirms the 33.4 K figure in the brief. Note a
`°C` *difference* **equals** a `K` difference, so **no 273.15 offset applies** —
applying one here is the same silent error flagged for the other difference layers
in §B5.

### The trap, and which quantity I matched — stated explicitly

**The brief's hypothetical is wrong, and the correction changes the formula.** It
says *"If Earth uses the annual range of monthly means, Mars must use the range
across Ls of the same quantity."* Earth does **not** use monthly means. It uses
**`max` of the monthly `tmax` minus `min` of the monthly `tmin`** — an **envelope
of extremes**, not a range of means. The two differ by roughly the mean diurnal
range, which over land is tens of kelvin, so matching the wrong one would be a
large error in the same family as the B3 midrange problem.

**I matched the envelope of extremes.** Therefore:

> **`mars_temp_seasonal` = max over all 48 (Ls, local-time) grids of T
> − min over all 48 (Ls, local-time) grids of T**

equivalently, since the inner maximum and minimum are already computed per Ls for
`mars_temp_swing` and `mars_temp_level` (§B3):

> `= max over the 4 Ls of (t_max_ls) − min over the 4 Ls of (t_min_ls)`

**Not** `max over Ls of midrange_ls − min over Ls of midrange_ls`, which would be
the range-of-means version and would not match Earth.

This also means all three Mars thermal layers come from **one pass** over the 48
files, sharing the same per-Ls `t_max_ls` and `t_min_ls`:

| layer | from the same two arrays |
|---|---|
| `mars_temp_level` (§B3) | `mean over Ls of (t_max_ls + t_min_ls)/2` |
| `mars_temp_swing` (§B3, unchanged) | `mean over Ls of (t_max_ls − t_min_ls)` |
| `mars_temp_seasonal` (new) | `max over Ls of t_max_ls − min over Ls of t_min_ls` |

### Source confirmation

All **4 Ls values confirmed present** in `D:\NASA hacathon\sources\mcd_prototype\`:
**`000, 090, 180, 270`**, each with all 12 local times (`00, 02, …, 22`) — the
4 × 12 grid is complete, 48 files, none missing. Units read from the file header:
`### Columns 2+ are Surface temperature (K)`. Output units therefore **K
(difference)**, no conversion.

### The bias, which is one-sided and must be recorded

Three separate under-samplings all push the Mars envelope the **same way — too
narrow**:

1. **4 Ls out of a Martian year.** The MCD carries 12 months; only Ls 0, 90, 180,
   270 are held. The true seasonal extremes fall between samples, particularly
   near perihelion (Ls ≈ 251), which is **not** one of the four. Mars's orbital
   eccentricity (0.0934) makes the southern summer substantially hotter than the
   northern, and Ls 270 is close to but not at the peak.
2. **12 local times at 2-hour steps.** The true daily maximum falls between
   samples, so `t_max_ls` is biased low and `t_min_ls` biased high.
3. **Climatology scenario, `dust = 1`, average solar EUV** — the existing
   `provisional_because` already records that there are no dust-storm or EUV
   extremes. A global dust storm is precisely a seasonal temperature excursion.

Earth's figure, by contrast, comes from **12 monthly climatologies**, so it samples
its year three times more finely. **The Mars seasonal swing will therefore read
systematically low relative to Earth's.** Percentile ranks within each body are
unaffected — the bias is near-uniform and the transform is monotone — but any
physical-unit comparison across the pair is invalid in a *known direction*, which
is worth more than an unknown one. Record as:

```
sampling_bias: "4 of 12 MCD months and 12 local times per sol both under-sample
                the true extremes; perihelion (Ls ~251) is not sampled. The
                envelope is biased NARROW relative to Earth's 12-month
                climatology. Ranks unaffected; physical-unit comparison is not."
```

One further mismatch, smaller but real: WorldClim `tmin`/`tmax` are **climatological
monthly means of daily extremes**, not absolute extremes, so Earth's
`max(tmax)` is the hottest monthly-mean-daily-maximum. Mars's `t_max_ls` is the
diurnal maximum of a climatological field at one Ls. Both are "extreme of a
climatology" rather than "extreme ever recorded", which is the right pairing — but
they are not identical constructions and the manifest should say so.

### Why the Moon is correctly excluded

Lunar obliquity is 1.54°, so there is no meaningful seasonal cycle, and the two
Diviner inputs held (`tbol_max`, `tbol_min`) carry no seasonal axis at all —
there is nothing to compute from. **This is the pairwise rule working normally,
not a gap**, and it should be recorded as a deliberate exclusion so nobody later
files it as missing data:

```
matching_notes.seasonal_swing: "Earth-Mars only. Lunar obliquity is 1.54 deg, so
  there is no seasonal cycle to measure, and the held Diviner products have no
  seasonal axis. Not a gap -- the dimension does not exist on the Moon."
```

### Cost

**Negligible.** The 48 MCD files are 48 KB each, ~2.3 MB total, on a 64 × 48
native grid. Reading all 48, taking per-cell max and min, and differencing is
**under a second**. Resampling 48 × 64 to HEALPix Nside 512 by nearest neighbour
is seconds. **This is the cheapest dimension in the entire document and it is
free with §B3**, since it reuses the same two arrays.

---

## B8 — WHICH DIMENSIONS TO KEEP  —  **ACCEPTED 2026-11-06**

> **STATUS: ACCEPTED AS WRITTEN.** The VIF-greedy selection with the
> smallest-eigenvalue stopping test, the percentile-IQR pre-filter,
> elevation-rank OUT, and a dimension set FIXED per body-pair are all
> accepted. The eleven other places that must change as a consequence are
> listed in `INGESTION.md` §B11; those edits have **not** been made.
> The build-order constraint this creates — every candidate must be built
> before the set can be frozen, so the expensive ones are built
> speculatively — is recorded there too.


### The ceiling — and why it is not a number

The brief's reasoning is right and the references are worth naming:

> **Beyer, K., Goldstein, J., Ramakrishnan, R., & Shaft, U. (1999). "When Is
> Nearest Neighbor Meaningful?" *ICDT 1999*, LNCS 1540, pp. 217–235.**

shows that under broad conditions — much broader than independent, identically
distributed dimensions — as dimensionality grows the distance to the nearest point
converges on the distance to the farthest. The nearest neighbour stops being
meaningfully nearer. That is exactly the failure mode described: with a ~20-cell
target, distance stops discriminating.

> **Aggarwal, C. C., Hinneburg, A., & Keim, D. A. (2001). "On the Surprising
> Behavior of Distance Metrics in High Dimensional Space." *ICDT 2001*, Springer,
> pp. 420–434.**

builds on it and examines the L_k norms, arguing that fractional metrics (k < 1)
remain more meaningful in high dimensions than L2. Worth knowing as a fallback
lever if the dimension count has to rise: **changing the metric is an alternative
to dropping a dimension**, though it would change every stored distance and
invalidate every cached run.

**But Beyer et al. also state the result is not universal** — they note workloads
for which nearest neighbour stays meaningful in high dimensions. The condition
that matters is **how much the data actually fills the space**. Strongly
correlated or clustered data has a lower **effective dimensionality** than its
nominal count, and concentration sets in later.

**That is the key synthesis, and it collapses the brief's two questions into
one.** The ceiling is not "6 to 8 dimensions"; it is "effective dimensionality of
6 to 8". Seven dimensions with an effective dimensionality of 3 are not a problem
of too many dimensions — they are a problem of a wasted coverage penalty, because
**coverage falls with every nominal dimension added while discrimination only
improves with effective ones.** So:

- the **selection rule** (choose non-redundant candidates) and
- the **stopping rule** (stop before distance loses meaning)

are the same measurement. **The stopping test must be computed from the data, not
fixed at 8.**

### The finding that should drive the decision

**Of the 7 Earth–Moon candidates, 5 are derived from one raster.**

| derived from | candidates |
|---|---|
| **elevation** | slope, ruggedness, concavity (TPI), scale exponent (H), sky view factor |
| temperature | temperature level, diurnal swing |

Five terrain descriptors from a single DEM against two thermal ones. They cannot
be independent: a steep place is usually rough, a rough place usually has a
restricted horizon, a basin floor is usually low relative to its surround and
often smoother than its rim. **The expected effective dimensionality of the
7-candidate Earth–Moon set is well under 7** — my estimate is 4 to 5, which is a
prediction to test, not a finding.

This is why a selection rule is needed rather than a preference, and why the
answer is probably "6, not 7".

### The procedure — the proposed rule, and a better one

**The proposed greedy rule** — start from the four that exist, then repeatedly add
whichever remaining candidate has the **lowest maximum absolute correlation** with
those already selected — is sound, cheap, interpretable, and I would accept it if
nothing better fitted the day. It is a standard max-relevance/min-redundancy
greedy step.

**It has one failure mode that matters here, and it is not hypothetical.**
Pairwise correlation cannot see multicollinearity among three or more variables.
Concrete counterexample: let `x` and `y` be independent, and `z = x + y`. Then

> `corr(x, z) = corr(y, z) = 1/√2 ≈ 0.707`

Every pairwise correlation is 0.707, comfortably under a 0.8 rejection threshold —
yet `{x, y, z}` is **exactly rank-deficient**. The set adds a third nominal
dimension and zero effective one. This is not a contrived case for terrain
variables: roughness at a scale, the scaling exponent, and the slope are plausibly
near-additive in log space by construction.

**Recommend instead: greedy by variance inflation factor, with an eigenvalue
stopping test.** This is the multivariate version of the same idea and it sees the
case above.

```
# inputs: the candidate matrix over Earth's reference population, standardised
# C = correlation matrix over the currently SELECTED set
selected = [slope, ruggedness, temp_level, diurnal_swing]   # the four that exist

loop:
    for each remaining candidate j:
        regress j on `selected` (ordinary least squares, standardised)
        R2_j  = coefficient of determination
        VIF_j = 1 / (1 - R2_j)                 # >5 means R2 > 0.80
    pick the candidate with the LOWEST VIF_j
    if VIF_j > VIF_MAX:               stop -- nothing left adds enough
    tentatively add it; form C over the new set
    lambda_min = smallest eigenvalue of C
    if lambda_min < LAMBDA_MIN:       reject it, stop
    else:                             commit it and continue
    if len(selected) == D_MAX:        stop
```

Parameters, with the reasoning rather than round numbers:

| parameter | value | why |
|---|---|---|
| `VIF_MAX` | **5.0** | the conventional multicollinearity threshold; equals R² = 0.80 against the selected set, i.e. the candidate is 80% explained by what is already in |
| `LAMBDA_MIN` | **0.10** | on a correlation matrix the eigenvalues sum to `d`, so a mean of 1.0; a smallest eigenvalue below 0.10 means one direction carries under a tenth of the average variance and the whitening that follows will amplify noise in that direction by `1/√λ` ≈ 3× or more |
| `D_MAX` | **7** | the affordable ceiling, but it should rarely bind — the eigenvalue test should bind first, and if `D_MAX` binds while `λ_min` is healthy, that is evidence the ceiling could be raised |

Why the eigenvalue test rather than the condition number: they are equivalent in
practice here (the largest eigenvalue is bounded by `d`), but `λ_min` has a direct
reading — **it is the variance left in the least-determined direction after
whitening**, which is exactly what the distance metric will divide by.

**Why this is better, in one line:** VIF catches the `z = x + y` case that
max-|corr| waves through, and `λ_min` is a direct measurement of whether whitening
is about to become numerically meaningless.

**Also gate on dynamic range, not just redundancy.** A candidate can be perfectly
independent and still useless if it barely varies — which is the specific risk
Shepard et al. flag for H ("natural surfaces tend to cluster near 0.5"). Add a
pre-filter: **reject any candidate whose interquartile range in percentile space
is below 0.15**, i.e. half the uniform expectation of 0.5, and record the measured
IQR per body. An independent dimension with no spread adds a coverage penalty and
no discrimination.

### (c) Dependency — stated

The procedure needs the **correlation matrix of all candidates over Earth's
reference population** (the 2,244,499 land cells, or a seeded subsample of them —
10⁵ cells is ample for a correlation matrix and reduces this to seconds).

**That matrix is already computed by the whitening step**, so the dependency is on
work that happens anyway. The ordering constraint is the real content:

> **the candidates must all be built, and the correlation matrix formed, BEFORE
> the dimension set is frozen.**

Which means the expensive candidates (H at 1–2.5 h, SVF at up to 1 h/body) must be
built **speculatively**, before it is known whether they will be kept. That is
unavoidable — redundancy cannot be measured on a variable that does not exist —
and it should be planned for rather than discovered on the day. Budget the build
time for all candidates and treat selection as a cheap final step.

One honest consequence: **if the day runs short, the fallback order below must be
decided without the correlation matrix**, on the reasoning in this section rather
than on measurement.

### (d) Fallback order if sky view factor proves too slow

Ordered by what gets dropped first. Each line is a shippable configuration.

| ships | Earth–Moon set | Earth–Mars set | trigger |
|---|---|---|---|
| **7 / 8** | the six below + H | the seven below + H | everything builds and `λ_min` stays ≥ 0.10 |
| **6 / 7** ← **recommended target** | slope, ruggedness, temp level, diurnal swing, TPI, SVF | + silica, seasonal swing | H is redundant or over budget |
| **5 / 7** | slope, ruggedness, temp level, diurnal swing, TPI | + silica, seasonal swing | **SVF too slow** — this is the expected failure |
| **4 / 6** | the four that exist | + silica, seasonal swing | TPI also fails (it should not; it is the cheapest) |
| **4 / 5** | the four that exist | + silica | nothing new builds — today's state |

**Drop order: H first, then SVF, then TPI.** The reasoning:

- **H first** despite being interesting, because it is expensive (1–2.5 h), its
  dynamic range is the most doubtful (Shepard's clustering near 0.5), and it is
  built *from* roughness so it is the most likely to be redundant with a dimension
  already in.
- **SVF second**, because it is the item most likely to overrun and the only one
  whose cost is genuinely uncertain, but it carries real information TPI does not
  — a wide flat crater floor has very negative TPI and a fairly open sky.
- **TPI last**, because it is the cheapest by an order of magnitude, polar-safe
  with the least extra work, and the one most clearly answering a question the
  current four cannot ("is this inside a bowl?").

Note that **Earth–Mars never drops below 6** in any scenario, because silica and
seasonal swing are both cheap and already available — seasonal swing is free with
§B3. The Earth–Mars pair is in much better shape than Earth–Moon and the attention
should go to the lunar side.

### (e) Fixed per body-pair, or varying per target? — FIXED

**Fixed per body-pair.** The reason is not tidiness:

- **`d_bar` is computed in the dimension space.** It is the mean distance between
  two random reference cells *in that space*, so it changes with the dimension
  set. Two runs with different sets have different `d_bar`, so their DI values are
  divided by different normalisers and **their coverage figures are not
  comparable** — the same Earth location would score differently for reasons
  unrelated to the target.
- **The DI threshold is calibrated in DI units**, so it inherits the same problem.
- **The percentile space itself is per-dimension-set**, so the null distribution
  and every p-value are too.
- The project already has the machinery to refuse incomparable runs; a per-target
  dimension set would make **every pair of runs incomparable**, which is the one
  configuration where that machinery protects nothing because nothing can ever be
  compared.

A varying set is defensible only in one narrow case: a target where a dimension is
**wholly absent** (no valid data anywhere in the target window), which the engine
already handles by dropping the variable **for that pair** and renormalising
against the reduced space's own `d_bar` and threshold. That is a documented,
measured reduction with its own ruler — not a varying dimension set. Keep that
mechanism and do not generalise it into per-target selection.

### (f) Elevation ranked within each body — **OUT**

Evaluated as asked. It is genuinely free (all three elevation layers exist at
100% validity, including 85–90°S on the Moon) and it pairs everywhere. I still
recommend **against** it, for four reasons in descending weight:

1. **It means different things on the three bodies, and ranking does not fix
   that.** On Earth, height *causes* conditions — the lapse rate, pressure,
   insolation. On the Moon there is no atmosphere, so height above a reference
   sphere causes nothing; it is a position relative to an arbitrary datum. The
   percentile transform removes the datum offset but **not** the absence of
   mechanism. "90th-percentile elevation" is a mountain on Earth and a patch of
   highlands on the Moon, and the analogy between them is nominal.
   `DECISIONS.md` already flagged this for raw elevation; ranking within body
   makes the numbers commensurable without making the quantity meaningful.
2. **It is predictably redundant with temperature on Earth.** The environmental
   lapse rate is ~6.5 K/km, so over land `earth_elevation` and
   `earth_temp_level` should correlate strongly and negatively. This is a
   prediction, not a measured fact — **the procedure above will measure it**, and
   I expect elevation to be rejected on VIF against `temp_level` alone. The
   asymmetry is the problem: the redundancy exists on Earth and not on the Moon,
   so the dimension would carry different information on the two sides of the same
   pair.
3. **TPI already captures the part of height that matters.** Concavity is height
   *relative to the surround at a stated physical scale* — a well-posed local
   quantity. Absolute rank adds the regional and datum-dependent component, which
   is the part with no cross-body meaning.
4. **Slots are scarce.** At a ceiling of 6–8, spending one on the weakest-justified
   candidate is the decision this whole section exists to avoid.

**If a slot is left over** after the procedure runs — `λ_min` healthy, VIF low,
`D_MAX` not binding — it is a reasonable 8th and costs nothing to add. But it
should be **last in line**, behind H.

### The table

Cost assumptions as stated in each section: one commodity workstation, NumPy
vectorised, local disk ~200 MB/s, no GPU.

| candidate | pairs on | cost | expected redundancy | IN / OUT | reason |
|---|---|---|---|---|---|
| **slope** | E–Moon, E–Mars | built | **moderate–high** with ruggedness (both elevation-derived, same operator family) | **IN** | existing, established, direct physical meaning for trafficability |
| **ruggedness** (21 km) | E–Moon, E–Mars | built | moderate–high with slope | **IN** | existing; the scale anchor for H |
| **temperature level** | E–Moon, E–Mars | §B3, minutes | **low** — the only non-terrain axis besides swing | **IN** | one of just two thermal dimensions; §B3 harmonises the definition |
| **diurnal swing** | E–Moon, E–Mars | built | **low–moderate** with temp level | **IN** | the other thermal axis; the lunar day/night amplitude is the headline contrast |
| **concavity (TPI 21 km)** | E–Moon, E–Mars | **2–25 min/body** | **moderate** with ruggedness and SVF | **IN** | cheapest real gain; answers "inside a bowl?", which nothing else does; polar-safe with least work |
| **sky view factor** | E–Moon, E–Mars | **5–50 min/body, Earth uncertain** | **moderate–high** with TPI | **IN, conditional** | genuinely distinct from TPI (flat crater floor = very negative TPI, open sky); **first to drop if Earth overruns an hour** |
| **scale exponent (H)** — see §B12 CORRECTION: this row's *reason* is wrong | E–Moon, E–Mars | **1–2.5 h total** | ~~**HIGH risk** with ruggedness~~ → **LOW: measured −0.157 global, −0.306 polar** | **OUT (hold)** — verdict unchanged, reason replaced | ~~most redundant by construction~~ — it is **not** redundant; the fit is centred, so the slope is orthogonal to the level. It is held out for **signal-to-noise of 2.12×** against its own estimator noise, and because **21.8% of pixels exceed H = 1**, detecting discrete features rather than fractal texture. Shepard et al. feared a small dynamic range; the range is adequate but contaminated. Built for all three bodies; admission still needs Earth's VIF. See §B12, §B12a, §B12b. |
| **silica** | **E–Mars only** | built | **low** — the only compositional axis | **IN (E–Mars)** | independent of terrain and thermal; no lunar counterpart by decision; **not polar-safe** (1.34% above 85°) |
| **seasonal swing** | **E–Mars only** | **free with §B3** | **low–moderate** with diurnal swing | **IN (E–Mars)** | cheapest dimension in this document; a genuinely different timescale; Moon correctly excluded (1.54° obliquity) |
| **elevation rank within body** | E–Moon, E–Mars | free | **high on Earth** (lapse rate), **and asymmetric** — redundant on one side of the pair only | **OUT** | no causal mechanism on the Moon; TPI already carries the meaningful part; see (f) |

### Final count per pair

| pair | now | recommended | if SVF overruns | ceiling |
|---|---|---|---|---|
| **Earth–Moon, global** | 4 | **6** | 5 | 7 with H |
| **Earth–Moon, POLAR** | 4 | **6** | 5 | 7 with H |
| **Earth–Mars, global** | 5 | **7** | 6 | 9 with H and elevation rank |
| **Earth–Mars, polar** | 4 | **6** | 5 | — silica is not polar-safe |

**Recommended sets, explicitly:**

- **Earth–Moon (6):** slope, ruggedness, temperature level, diurnal swing,
  concavity, sky view factor.
- **Earth–Mars (7):** the same six, plus silica and seasonal swing — **minus one**
  if the procedure rejects any on VIF. At 8 nominal candidates for Earth–Mars the
  eigenvalue test is likely to bind, and the first casualty should be whichever of
  {diurnal swing, seasonal swing} has the higher VIF against the other.

**Three things to carry into the write-up, because they will otherwise read as
bugs:**

1. **Coverage will fall when dimensions are added**, by construction — each new
   dimension can only lengthen nearest-neighbour distances. Going from 4 to 6 will
   reduce every coverage figure reported so far. Say so wherever before/after
   numbers appear.
2. **`d_bar`, the DI threshold, the null and every p-value are all per
   dimension-set.** Freezing the set is what makes any of them quotable; every
   stored run from the 4-dimension era is invalidated the moment the set changes.
3. **The polar-safe column is conditional on the polar stereographic treatment in
   §B1 and §B2.** If the lunar polar caps are skipped, concavity and sky view
   factor are not polar-safe and the Earth–Moon polar count stays at 4 — which
   would make this entire section moot for the targets that matter.

---

# PHASE 2 MEASUREMENTS — corrections to B6 and B8, and two new recorded decisions

*Written 2026-11-06, after the terrain layers were built on HEALPix. Everything
below is measured on real data, not predicted. Where it contradicts an earlier
section, the earlier section is wrong and says so.*

## §B12 — CORRECTION to B8: the redundancy prediction was wrong

B8's dimension table gives the scale exponent a verdict of **OUT (hold)** and
the reason **"HIGH risk with ruggedness — built from it, and the fit shares its
input"**, adding that it is "most redundant by construction".

**That reason is wrong.** Measured on the Moon, binned to Nside 256:

| correlation of `roughness_scaling_exponent` with | value |
|---|---|
| `roughness_21km` (the ruggedness dimension), global | **−0.157** |
| `roughness_21km`, 85–90°S only (1,496 pixels) | **−0.306** |
| `scaling_exponent_r2` | +0.282 |

A shared input does not imply a shared signal. H is the *slope* of log roughness
against log scale; ruggedness is the *level* at one scale. The fit is
deliberately centred on the geometric mean of the achieved scales, which makes
the slope orthogonal to the intercept, so H carries none of the overall
roughness level by construction. The near-zero correlation is what that
orthogonality looks like in the data.

**H carries information nothing else in the candidate set carries.**

**The verdict of HOLD nevertheless stands, for a different reason: noise.**

## §B12a — the real problem with H, and why B8's pre-filter cannot see it

B8 §(b) adds a dynamic-range pre-filter: *"reject any candidate whose
interquartile range in percentile space is below 0.15"*. Measured on the Moon:

| layer | IQR in percentile space |
|---|---|
| `roughness_scaling_exponent` | **0.5000** |
| `roughness_21km` | **0.5000** |
| `slope` | **0.5000** |

**The pre-filter is vacuous.** A rank transform returns ≈0.5 for *any* layer
without mass ties, so the gate measures tie density, not discrimination. It
would pass pure noise. It is retained only as a tie detector; it must not be
cited as evidence that a dimension discriminates.

The quantity that actually matters was measured instead. Synthetic fractional
Brownian surfaces at *constant* known H, through the identical estimator and the
Moon's achieved scales, block-averaged 15×15 to stand in for the HEALPix pixel
(7.11 km against the 6.95 km pixel side). Any spread recovered is noise by
construction:

| H true | per-cell IQR | per-pixel IQR | reduction from binning |
|---|---|---|---|
| 0.30 | 0.1604 | 0.1252 | 1.28× |
| 0.50 | 0.2176 | 0.1712 | 1.27× |
| 0.70 | 0.2606 | 0.2037 | 1.28× |

- **Noise floor at HEALPix scale: 0.1667 IQR.**
- **Observed on the Moon: 0.3531 IQR.**
- **Signal-to-noise: 2.12×.**

Binning buys only **1.28×**, nowhere near √225 ≈ 15, because the 42 km window is
six times wider than a HEALPix pixel: neighbouring cells share most of their
input, so their errors are correlated and do not average away. **Going to a
coarser Nside would not fix this.** The noise is set by the window-to-pixel
ratio, and widening the pixel only widens that ratio's denominator.

Shepard et al. (2001) warned the dynamic range might be small. It is not small —
it is *contaminated*. About a third of the observed spread is estimator noise.

## §B12b — 22.6% of H is a real measurement of the wrong quantity

| range | pixels | share |
|---|---|---|
| inside [0, 1] | 592,190 | **77.399%** |
| below 0 | 6,158 | 0.805% |
| above 1 | 166,762 | **21.796%** |

min −0.864, max +2.999.

**These are not errors.** The layer is correctly named
`roughness_scaling_exponent` and not `hurst`. It is the slope of log roughness
against log scale, and that slope may legitimately exceed 1: it does so where a
widening window swallows a discrete feature such as a crater rim and roughness
grows faster than linearly. Below 0 says roughness *falls* as the window widens.

Such pixels are **detecting discrete features rather than fractal texture** — a
real measurement of the wrong quantity, for a fifth of the map. **R² does not
screen them out**, because the power law is clean; only its exponent is
meaningless as a texture descriptor. Median R² is 0.942.

**Status: built and stored for all three bodies, marked HOLD, not wired into the
default dimension set.** B8 cannot decide admission without Earth's VIF, which
is why it is built rather than skipped.

## §B13 — NEW DECISION: the aggregation statistic is the MEAN, not the median

**This is a departure from the spec and it went in unflagged. Recorded here and
in every Phase 2 manifest entry. The spec is to be updated.**

> **Spec says:** a HEALPix cell's value is the **median** of the native values
> inside it.
>
> **Implemented:** the **area-weighted mean**, cos(lat) weights, accumulated
> inside the band loop.

Reasoning:

1. **A mean streams; a median does not.** The mean needs two accumulators of
   length npix — 96 MB for the Moon, 201 MB for Earth — and a pixel never has to
   be complete within one band. A median needs every contributing value present
   at once, which means writing a working-resolution intermediate: **13.9 GiB
   per Earth layer, ~97 GiB over the seven layers**, then reading it back. At
   measured disk rates that is hours of pure I/O. *This is not a disk-space
   argument — the drive now has 129 GB free. It is a time argument.*
2. Each HEALPix pixel averages **~215 native cells**, so sampling error on the
   mean is small.
3. All three DEMs passed their range *and* coverage gates in Phase 1, so the
   outlier robustness a median buys has no known outliers to defend against.
4. The aggregated quantities are already window statistics over 5–42 km
   footprints, so within one ~7 km pixel they vary little and mean and median
   nearly coincide.

**Consequence, stated:** where a pixel straddles a sharp boundary — a crater
rim, a coastline — the mean is pulled toward the extreme while a median would
ignore it. **The support gate is what exposes those pixels.**

**Action required: update the method spec to say area-weighted mean.** Silent
drift is how this project ended up with three different temperature definitions.

## §B14 — NEW DECISION: three gates, not two

Phase 1 established that the **range gate can pass on broken data** — the Mars
scale gate passed on a DEM that was 99.68% nodata. Phase 2 found the same trap
one level down: **the coverage gate lies too.**

A HEALPix pixel counts as valid if **even one** of its ~215 contributing cells
carried a usable value. On the Moon's scaling exponent:

- **HEALPix pixels reporting valid: 97.2888%**
- **Underlying working cells that survived: 72.1714%**

The pixel-level figure hides that **27.83% of contributing cells were
withheld**, and says nothing about *which* pixels rest on thin support.

**Every binned layer therefore carries three gates:**

| gate | question | failure mode it catches |
|---|---|---|
| **range** | are the values plausible? | wrong units, wrong scale factor, sign errors |
| **coverage** | did the pixel get anything at all? | whole regions missing |
| **support** | how much of the pixel actually contributed? | a pixel resting on 3 cells of 215 reporting as confidently as one resting on 215 |

**Support** = achieved weight total ÷ expected weight total, i.e. the
cos(lat)-weighted fraction of native cells falling in the pixel that carried a
usable value. Both totals are already held in the binning accumulators, so this
costs one extra array of length npix and no extra pass over the DEM.

Stored as a companion array per layer:
`<body>_<layer>_support_nside<N>.npy`, named in each manifest entry under
`support_file`.

**Support 0 is distinct from support NaN.** Zero means the pixel has native
cells but none were usable; NaN means no native cell maps to the pixel at all.
Downstream code must **filter on support, not on validity alone.** A pixel
passing the coverage gate on a small support fraction is a *weak* measurement,
not a missing one, and the two must not be treated alike.

---

# §B15 — H SETTLED: three independent defects, but a real signal

*Measured 2026-11-07. Supersedes nothing in §B12; it completes it.*

## (a) The crosstab — the three strikes are LARGELY DISJOINT

Per-pixel sets. `OUT` = H outside [0,1]. `THIN` = support < 0.50. `NOISY` needs
a per-pixel proxy because "signal-to-noise 2.12×" is a global statistic; the
OLS slope standard error supplies one in closed form from stored quantities:

> `SSR = (1−R²)·SST`, `SST = H²·denom/R²`, n = 4
> **`SE(H) = |H|·√((1−R²)/(2R²))`**, cut at **0.125**, the σ equivalent of the
> 0.1667 noise-floor IQR.

It needs no new pass over the DEM. It is approximate — H and R² here are pixel
means, not per-cell values — and that is stated rather than hidden.

**OUT and THIN are statistically independent:**

| body | OUT∩THIN observed | expected if independent | φ | Jaccard |
|---|---|---|---|---|
| Moon | 36,950 | 37,359 | **−0.0031** | 0.123 |
| Mars | 183,938 | 179,051 | **+0.0087** | 0.142 |
| Earth | 419,576 | 564,504 | **−0.0706** | 0.087 |

THIN∩NOISY is moderate (φ +0.377 Moon, +0.371 Mars, +0.392 Earth) and OUT∩NOISY
weaker (+0.324, +0.299, +0.194). Stable for SE cuts from 0.08 to 0.20.

**A support ≥ 0.50 filter does not rescue H — it makes the ratio worse:**

| | kept | still outside [0,1] | signal/noise | corr w/ roughness_21km |
|---|---|---|---|---|
| Moon | 78.40% | 22.669% (was 22.601%) | **1.94× (was 2.12×)** | −0.208 (was −0.157) |
| Mars | 75.64% | 23.788% (was 23.999%) | **2.07× (was 2.34×)** | +0.062 (was +0.067) |
| Earth | 78.47% | **23.117% (was 21.596%)** | **2.18× (was 2.42×)** | −0.027 (was −0.033) |

Filtering strips spread without removing noise, so the ratio falls; on Earth the
out-of-range fraction gets *worse*. **Three independent defects, one filter, no
gain. The HOLD is correct and final.**

## (b) The map — but H is NOT an estimator artefact

The three medians land within 0.025 (Moon 0.776, Mars 0.778, Earth 0.753). The
maps settle which reading is right, and the answer is **H is real and noisy**,
not the estimator measuring its own window geometry.

**Earth is the strongest evidence.** Continental interiors blue (~0.5), abyssal
plains green (~0.8), **Antarctica and Greenland uniformly orange (~1.0–1.1)** —
ice sheets are smooth at small scale and domed at large, so roughness grows fast
with scale. Ridges, trenches and coastlines trace as red lines. Decisively,
**Greenland reads high while northern Canada and Siberia at the same latitude
read low.** Same latitude, opposite values: geology, not latitude.

**Moon:** crater rims trace as rings; the maria form a visibly lower-H region.
**Mars:** Tharsis high, northern lowlands low, Valles Marineris and Olympus Mons
outlined.

## (c) The zonal profile — the Moon is the control, and it is flat

An east-west stencil artefact would be **symmetric in |latitude|**, because the
stencil widens as 1/cos(lat) identically in both hemispheres. Measured:

| body | min | at | max | at | spread | symmetric? |
|---|---|---|---|---|---|---|
| Moon | 0.688 | +88.5° | 0.831 | −85.5° | **0.142** | flat, no trend |
| Mars | 0.598 | +76.5° | 0.984 | +85.5° | 0.385 | **no** |
| Earth | 0.564 | +61.5° | 0.955 | −73.5° | 0.392 | **no** |

Earth's curve is strongly asymmetric (+0.96 at −73° against +0.56 at +61°), and
every feature maps to known geography: the Antarctic ice sheet, the glacially
scoured northern shields, Greenland. Mars peaks at both polar caps and dips over
Vastitas Borealis.

**The Moon is the control.** It has no latitude-dependent surface process, and
its zonal profile is flat to within 0.14 across 180° of latitude. If the
estimator manufactured a latitude signal, the Moon would show it. It does not.
The support ≥ 0.50 curves track the unfiltered ones closely, so the pattern
survives the filter.

## (d) The verdict, with the reason corrected twice over

**HOLD stands. Final.** But the record now carries three different reasons, and
only the last is right:

1. ~~B8: highly redundant with ruggedness~~ — **wrong**, measured −0.157.
2. ~~Shepard et al.: dynamic range too small~~ — **wrong**, the range is ample.
3. **Signal-to-noise of 2.12×, falling to 1.94–2.18× under any support filter,
   with 21.8% of pixels above H = 1 detecting discrete features rather than
   fractal texture.** A third of the observed spread is estimator noise, and
   filtering cannot separate the three defects because they are independent.

What the maps add is that **H is not junk** — it tracks ice sheets, cratered
versus smooth terrain, and tectonic edges, and carries information no other
candidate carries. It is simply too noisy per pixel to serve as a distance
dimension. **Do not delete these layers.** If a future dimension set needs a
texture descriptor, H at a coarser Nside, or H estimated over more than four
scales, is the thing to revisit — not a new variable.

Built and stored for all three bodies. `status: HOLD` in every manifest entry.

---

# §B16 — EARTH COMPOSITION: the GLiM categorical-to-numeric lookup

*Built 2026-11-07. Table only — not wired into the pipeline.*
*File: `sources/glim_composition_lookup.csv` (14 rows, 11,922 bytes).*

Moon and Mars composition is numeric — measured SiO₂ and FeO weight percent
from orbit. GLiM is categorical — 16 rock-type names and no numbers. A name
cannot be compared to a number, so this table is the bridge.

## (a) Method and what was optimised

The pipeline rank-transforms every variable before any comparison, so **only the
ordering matters**. Effort went into the order and the uncertainty column, not
into decimal places.

**Igneous classes are definitional, and that is the table's strongest footing.**
GLiM's acid / intermediate / basic labels *are* silica ranges: IUGS gives
ultrabasic <45, basic 45–52, intermediate 52–63, acid >63 wt% SiO₂ (Le Maitre
et al. 2002, verified). Those six rows therefore need no estimation for their
ordering — it follows from the class definition.

**Iron is recorded as FeO_T, total iron expressed as FeO**, because that is what
lunar and martian orbital spectroscopy reports. Mixing FeO_T against FeO-only
would be the same class of error as celsius against kelvin, which this project
has already made once. Where a source splits them, FeO_T = FeO + 0.8998·Fe₂O₃.

Resulting order, SiO₂ descending:

> **va > pa > ss > su > mt > py > vi > pi > vb > pb > sm > sc > ev**

Acid above intermediate above basic for both plutonic and volcanic; carbonates
and evaporites at the bottom. **No ties in either column** (13 distinct SiO₂
values, 13 distinct FeO_T values) — deliberate, because a rank transform turns
duplicate values into tie blocks.

**SiO₂ and FeO_T correlate only +0.369 across the classes**, not strongly
negative as the igneous differentiation trend alone would predict. The
sedimentary classes break the trend: carbonates and evaporites are low in
*both*. The two oxides therefore carry genuinely different information and
should not be assumed redundant in the VIF step.

## (b) Uncertainty ratings

| class | share of ice-free land | rating | why |
|---|---|---|---|
| va, pa, vi, pi, vb, pb | 14.1% combined | **LOW** | defined *by* silica content |
| py | 0.62% | MEDIUM | explosive eruptions skew silicic; basaltic pyroclastics are volumetrically minor |
| sc | 7.70% | MEDIUM | chemistry is tight; see the extreme question below |
| ev | 0.33% | MEDIUM | stoichiometric; mapped units include interbedded clastics |
| ss | 17.73% | MEDIUM | sandstone ~78 wt% SiO₂ against shale ~60 under one label |
| mt | 13.93% | **HIGH** | inherits an unknown protolith |
| sm | 15.60% | **HIGH** | a mixture *by definition* |
| su | **27.41%** | **HIGH** | spans quartz sand to clay to till |

**Are the carbonate and evaporite extremes real, or a lumping artifact?**
**Real, in both cases, and for the same reason.** Carbonate rock is dominantly
CaCO₃ or CaMg(CO₃)₂ and silica enters only as detrital or biogenic impurity;
evaporite chemistry is essentially mineral stoichiometry. Lumping limestone with
dolomite costs almost nothing *here*, because the two differ mainly in MgO,
which this table does not carry. The genuine caveats are different in kind:
argillaceous limestones reach 20–30 wt% SiO₂, and mapped evaporite units are
rarely pure salt. Neither threatens the ordering.

**Is one number defensible for `su`?** Honestly, no. It is the largest class,
27.41% of ice-free land, and it spans roughly 20–95 wt% SiO₂. The value given is
little more than "average continental detritus".

## (c) The masking question — and why the premise is not the real problem

The decisive finding is not about uncertainty at all. It is about **ties**.

> **Earth's composition takes only 13 distinct values over the whole planet.**
> Its interquartile range in percentile space is **0.3646**, against **0.5000**
> for every continuous layer measured so far.

That number matters twice. First, it is the **first time §B8's percentile-IQR
pre-filter has carried any information**: §B12a showed the gate measures tie
density rather than discrimination, and here there is finally tie density to
measure. It still passes the 0.15 threshold, but the margin is real.

Second, it restates the user's own concern about GLiM resolution in a sharper
form. The resolution problem puts ~75 *neighbouring* cells at one value.
**This puts 28% of the planet's land at one value, globally scattered** — every
`su` pixel in the Sahara is an exact composition twin of every `su` pixel in
Siberia. That is far more corrosive to an exclusion radius than local copying.

**Masking does not fix it.** Masking the three HIGH-uncertainty classes removes
**58.56% of ice-free land** and moves the percentile IQR only from 0.3646 to
**0.3353**, with 10 levels instead of 13. Enormous cost, no cure.

**Recommendation: do not mask. Record the tie structure instead, and fix the
level count.**

Arguing the other side fairly: a wrong number does propagate silently through
the ranking, a mask is honest, and the support gate would see a mask — all true,
and it is the stronger argument *if* the choice is genuinely binary. What tips
it is that masking is not honesty here, it is a smaller dishonesty: it removes
the pixels whose composition is uncertain while leaving `ss` (17.73%, MEDIUM,
two rock types that differ by 18 wt% SiO₂) in place at a single value. The
defect is structural and shared, not confined to the HIGH rows.

Three actions instead:

1. **Keep every class, `su` included.** Masking costs 28–59% of the reference
   population — which also sets `d_bar` and the DI threshold — and does not
   remove the ties.
2. **Add a fourth diagnostic for any lookup-derived layer: `distinct_levels`
   and `largest_tie_fraction`.** The existing three gates are all blind to this.
   Range passes, coverage reads 100%, and **support reads 1.0000 and is
   correct** — every cell did get data. A copied-value defect is invisible to
   all three, exactly as the coverage gate was blind to thin support.
3. **The real fix is more levels.** GLiM's full classification is three
   two-digit codes (`xxyyzz`), and the `LiMW_GIS 2015.gdb` layer carries a
   `Litho` field (str:255) alongside the level-1 `xx` code. Reading the
   subclasses would multiply the level count and break up the `su` block. That
   should be checked before this table is wired in, because if it works, most
   of this section's problem disappears.

## (d) Cross-check: are `wb` and `ig` already excluded? — PARTLY

Measured against `earth_ice_free_land_1_240deg.npy`, area-weighted:

| class | % of all land | % of ice-free land | verdict |
|---|---|---|---|
| **ig** ice and glaciers | 8.8637% | **0.1921%** | **excluded, 97.8% removed** ✓ |
| **wb** water bodies | 0.8936% | **0.9710%** | **NOT excluded** ✗ |

**The assumption holds for `ig` and fails for `wb`.** The ice mask does its job —
ice and glaciers drop from 8.86% of land to 0.19% of ice-free land. But water
bodies are not ice, nothing removes them, and their share actually *rises*
slightly because ice left the denominator.

So the classes carrying no composition total **2.77% of ice-free land**:
`wb` 0.9710 + `ig` 0.1921 + `nd` 0.0777 + GLiM NODATA 1.5267. The NODATA term is
the largest and is mostly coastline mismatch between the 0.5° GLiM raster and
the 1/240° land mask — an artifact of the resolution gap, not missing geology.

**`wb` needs an explicit exclusion when this is wired in.** It must not inherit
a composition value.

## (e) Citation status — read this before using the table in Appendix D

Every citation below was **checked for bibliographic accuracy in this session**.
The numeric values were **not** read from the primary tables, because Wiley,
`permanent.fdlp.gov` and `pubs.usgs.gov` all returned **HTTP 403** to automated
fetches. Each row's `source` field carries a token saying which is which:

| token | meaning |
|---|---|
| `[DEFINITIONAL]` | follows from the class definition — the strongest rows |
| `[VERIFIED]` | numeric value confirmed from a source retrieved this session |
| `[UNVERIFIED-VALUE]` | citation confirmed, value NOT read from the primary table |

Verified outright: the IUGS silica boundaries; Rudnick & Gao's upper-crust
SiO₂ 66.6 ± 1.18 and **FeO_T 5.04 ± 0.53 with iron as total Fe as FeO**; GLiM's
1,235,400 polygons (1,235,259 counted in the local file) and its 64% sediments /
13% metamorphics / 7% plutonics / 6% volcanics / 10% water-or-ice split.

Citations confirmed but tables not opened: Nockolds (1954) GSA Bull. 65(10)
1007–1032; Le Maitre (1976) J. Petrology 17(4) 589–637; Turekian & Wedepohl
(1961) GSA Bull. 72(2) 175–192; Pettijohn (1963) USGS PP 440-S, p. S1–S21.

**Before Appendix D is submitted, the `[UNVERIFIED-VALUE]` rows should be
checked against the printed tables through a library copy.** The ordering does
not depend on it — that rests on the definitional boundaries — but the quoted
weight percents do.

---

# §B17 — THERMAL SOURCES SETTLED (Decisions 1, 2 and 4)

*Measured 2026-11-07. Everything below was checked, not assumed.*

## §B17a — Mars: no finer grid exists. Build at 355 km, `matching_eligible: false`

**The grid, exactly:** 64 longitudes × 48 latitudes = **3,072 cells for the
whole planet**, against 3,145,728 HEALPix pixels at Nside 512 — **1,024 pixels
per distinct value**. Latitude step 180/47 = 3.8298° (227.0 km); longitude
360/63 = 5.714° (355.6 km), printed to integer precision in the ASCII output.

**That is the GCM's own grid.** The MCD v6.1 user manual gives the model grid as
5.625° × 3.75°. There is no downsampling to undo — the output grid *is* the
physics grid.

**A high-resolution mode exists and does not apply to map output.** `hrkey=1`
uses 32 pixels/degree MOLA topography (~1850 m at the equator). The same field
was fetched at `hrkey=0` and `hrkey=1` and compared:

> **3,072 values compared. Maximum absolute difference 0.000000 K. Zero values
> differ.** The flag is ignored for map requests.

It *does* work in point mode — a single-point query at lat −85°, lon 0°, Ls 0,
LT 12 loaded `high_resol/dust_clim.nc` and returned 156.03055 K. But point mode
is one HTTP request per location. A 1° grid would need 64,800 requests per
(Ls, local time) pair and **9.3 million** for all 144 — not feasible, and not
acceptable to that server.

**Decision: build Mars thermal at 355 km and set `matching_eligible: false`.**

**Recorded honestly, and this must stay in the manifest:** MCD is a GCM product.
A finer output grid would have added the **topographic correction**, which is
real and large on Mars because surface temperature depends strongly on
elevation through pressure — but it would **not** add 6 km of physical
information. A finer grid must never be read as finer knowledge.

**Future upgrade, logged and not acted on:** TES-derived thermal inertia
(Putzig & Mellon, ~3 km) is a *measured* product at the right scale and is the
better source. Out of scope this week.

## §B17b — Moon: the GCP gives max AND min, and the parse validates exactly

There is no `tbol_min` raster at PDS. The level-4 rasters already on disk are a
derived UCLA set from which the minimum is simply absent — only a description
file exists. **The GCP is the source those rasters were derived from**, and it
holds tbol binned by local time, so maximum and minimum both fall out directly.
No least-squares reconstruction, as instructed.

Downloaded: 18 latitude bands, **2.62 GiB, 18/18 complete, 0 failed**, 36.5 min.
Dataset LRO-L-DLRE-5-GCP-V1.0, DOI 10.17189/1520655, observations 2009-07-05 to
2015-04-01, Williams et al. (2017) Icarus 283, 300–325.

Structure, verified on read rather than assumed: 113-byte fixed records,
1,382,400 per band = 720 lon × 20 lat × 96 local-time bins; 0.5° spatial,
0.25 h local time; tbol is column 11 at byte 103, **unit K**. Local time varies
fastest, confirmed from the data (`lt[0]=0.12, lt[1]=0.38, lt[2]=0.62`).

**Two fill constants, not one — the label caught this and it would otherwise
have been wrong:** `−9999` unknown (no observations) and `−9998` invalid.
**Negative brightness temperatures are valid data**, arising from negative
radiance below a channel's sensitivity. Discarding all negatives would have
silently deleted the coldest places on the Moon, which are precisely the polar
cold traps this project exists to find.

**The validation is exact.** The published `diviner_tbol_max.xyz` was derived
from this same GCP by the Diviner team, so recomputing the maximum tests the
parse, the fill handling and the grid alignment at once:

| | |
|---|---|
| cells compared | **259,200** (all of them) |
| mean difference | **+0.0000 K** |
| maximum absolute difference | **0.000 K** |
| within 1 K | **100.000%** |
| correlation | **1.000000** |

The maximum is the only thing that *can* be checked — the minimum has no
published counterpart, which is the whole reason for this work. An exact match
on the maximum is therefore the strongest available evidence that the minimum
is right too.

Results, 0.5° global, 100% valid including both poles:

| layer | min | p50 | max |
|---|---|---|---|
| `tbol_max` | 51.31 K | 353.60 K | 439.00 K |
| `tbol_min` | 19.39 K | 87.83 K | 131.98 K |
| **diurnal range** | 22.11 K | **265.72 K** | 345.82 K |

The diurnal range median of 265.72 K sits squarely in the 250–300 K expected.

**Local-time coverage varies and must feed the support gate:** bins per cell
range from **40 to 96 of 96**, median 62. A cell sampled at 40 local times has
a less well determined maximum and minimum than one sampled at 96, and
`diviner_tbol_nlt_0p5deg.npy` records it.

**Is a finer Diviner tbol product available? No, not globally.** The GCP at 0.5°
is the finest *global* tbol. The 32 ppd DGDR cylindrical products cover ±60°
only and hold *anomalies* — deviation from the global average per local time —
not absolute temperature. So 15.2 km against a 6.95 km pixel, 4.8× coarser, is
what exists and what we accept.

## §B17c — `wb` is a bug in the land mask, and the bias is measurable

Water bodies are **0.9710% of ice-free land** and nothing removed them. A lake
surface is flat, so those pixels read as very smooth terrain in slope,
roughness and TPI — a false analog signal already sitting in the eight
geometric layers.

**31,845 of 3,290,265** majority-ice-free-land HEALPix pixels are majority
water (0.9679%).

| layer | set | p1 | p25 | p50 | p75 | p99 |
|---|---|---|---|---|---|---|
| slope | water | **0.0000** | 0.0189 | 0.1347 | 0.4933 | 6.6113 |
| slope | clean land | 0.0128 | 0.1565 | 0.3851 | 1.2495 | 7.4624 |
| roughness_21km | water | **0.0013** | 3.0628 | 17.4051 | 54.4803 | 521.9346 |
| roughness_21km | clean land | 1.3924 | 14.7544 | 35.2623 | 112.1905 | 564.8103 |

**They cluster smooth in the lower quartile, not at the median.** The median
water pixel sits at the **21.60th percentile of clean land in slope** and the
**29.69th in roughness_21km**. But the lower quartile is where it bites: water
p25 slope 0.0189° against land 0.1565° is **8.3×**, and roughness p25 3.06 m
against 14.75 m is **4.8×**.

**Why the median is not more extreme is itself the finding.** The `wb` class
came from the 0.5° GLiM raster, which is 55 km, so every lake is wrapped in a
55 km block and most "water" pixels are mostly land. The mask dilutes its own
signal. Two consequences:

1. True water pixels are **smoother** than this table shows.
2. ~~The 0.9710% being removed is roughly double the genuine inland-water
   area, so about half a percent of legitimate land is being discarded.~~
   **THIS PREDICTION WAS WRONG AND IS CORRECTED BELOW (§B18).** Rebuilding the
   mask from the 3 km vector removed **1.0102%** of ice-free land against the
   raster's 0.9710% — very slightly MORE, not half as much. GLiM's `wb` class
   genuinely covers about 1% of land because it includes the great lakes
   (Caspian, Superior, Victoria, Baikal), which add up. The raster's blocks
   over-cover some lakes and under-cover others and it roughly cancels in
   total area. The vector is still the right source, but for PLACEMENT at 3 km
   rather than 55 km, not for total area.

**Practical impact on matching is likely small** — the lunar polar targets are
rough crater terrain, the opposite end of the distribution. What it distorts is
the percentile rank of genuinely smooth land: deserts and plains are pushed up
the ranking by ~1% of the population crowding below them.

`earth_ice_free_land_nowater_1_240deg.npy` is written and is **PROVISIONAL**.
It should be superseded from the LiMW vector, whose median polygon is 3.01 km
against the raster's 55 km, in the same pass that builds lithology. The
original mask is untouched.

---

# §B19 — THE 84-ROW SUBCLASS COMPOSITION TABLE

*Built 2026-11-07 from the Hartmann & Moosdorf (2012) paper itself.*
*File: `sources/glim_composition_lookup.csv`, 98 rows (14 level-1 fallback +
84 subclass), 70,243 bytes.*

## (a) The vector read is validated against the paper's own Table 1

Before any composition was assigned, the measured class shares were compared
with the published global percentages. **All 42 codes — 16 level-1, 12
level-2, 14 level-3 — agree to within 0.05 percentage points.**

| level | codes | worst disagreement |
|---|---|---|
| 1 (xx) | 16/16 | 0.04 pp (`sm`, `mt`) |
| 2 (yy) | 12/12 | 0.05 pp (`sh`) |
| 3 (zz) | 14/14 | 0.05 pp (`mt`, `cl`) |

That independently confirms the vector read, the `xxyyzz` parsing of the
`Litho` field, and that the local geodatabase is genuine GLiM v1.0.

## (b) A warning about AI-summarised classification tables

An AI-generated rendering of Table A2 was offered alongside the paper. **Six
of its fourteen level-3 expansions were wrong, and the level-2 list was
missing a code.**

| code | the AI version said | the paper says | share of land |
|---|---|---|---|
| `cl` | "clay-rich matrix inclusions" | **fossil plant organic material (coal)** | 2.6% |
| `sr` | "reef or biostrome traits" | **subordinate sedimentary rocks mentioned** | 0.7% |
| `vr` | "variegated structures" | **subordinate volcanics mentioned** | 2.0% |
| `pr` | "permafrost attributes" | **subordinate plutonics mentioned** | 0.6% |
| `su` | "sulfidic / pyritic properties" | **subordinate unconsolidated sediments** | 1.7% |
| `pt` | "peat / high organic matter" | **pyrite mentioned** | 0.02% |
| `gr` | "granulite facies" | **greenstone mentioned** | 0.1% |
| `py` (L2) | *omitted entirely* | **pyroclastics mentioned** | 4.0% |

Two of them invert the compositional direction: `sr` as "reef" would have
pushed `vb__sr` — basalt with minor sedimentary interbeds — toward
*carbonate*, and `cl` as "clay" instead of *coal* reverses the organic
signal. Together these codes touch roughly 8% of ice-free land. **Only the
paper was used.** This belongs in the record because the table looked
entirely plausible and the errors are invisible without the source.

## (c) The model — two mechanisms, because the codes do two different things

Not 84 independent literature lookups, which could not be audited. One
transparent rule that anyone can re-derive:

1. **Dominant-material codes** (`mx`, `sh`, `ss`, `ad`, `ds`, `lo`, `or`,
   `la`) describe what the rock mostly *is*, and **SET** the composition from
   a per-base table. Per-base, because the paper makes the meaning depend on
   the first level: on a carbonate or mixed unit the grain-size code
   describes the **siliciclastic fraction** (A4.1.2), so it *raises* silica,
   while on a siliciclastic unit it describes the whole rock.
2. **Admixture codes** (`pu`, `py`, `am`, `gr`, and every level-3 code) say
   some *other* material is present, and **PULL** the composition a fixed
   fraction toward that material's endmember — level-2 weight 0.35, level-3
   0.15, since every level-3 code is a "mentioned"/"subordinate" flag.

**A pull is sign-correct against any base; a fixed delta is not.** An earlier
delta model drove `scsh__` to the clamp at 0.5 wt% SiO₂ and made `scpy__`
*less* siliceous than pure limestone — ash in a limestone must raise silica.
After the fix:

```
scpu__  4.8   scmx__ 10.0   scsh__ 12.0   scss__ 16.0   scpy__ 24.4
mtpu__ 28.0   sula__ 37.0 (FeO_T 22.0)    vb__sr 50.3   suds__ 87.0
```

No value sits on a clamp. 65 of 84 SiO₂ values and 70 of 84 FeO_T values are
distinct; the remaining ties are codes whose differing flag is compositionally
neutral — `ssss__` and `ssssmt` tie because metamorphism is isochemical for
major oxides, and forcing them apart would invent a distinction.

**The endmembers and pull weights are this project's construction and are not
claimed to be from the literature.** Every row's `source` field says so. The
level-1 bases and all code meanings are sourced.

## (d) What it buys, measured on the built layer

| | level-1 only | with 84 subclass rows |
|---|---|---|
| pixels from a subclass row | 0 | **3,185,605 of 3,352,458 (95.0%)** |
| `distinct_levels`, SiO₂ | 13 | **66** |
| `distinct_levels`, FeO_T | 13 | **71** |
| **`largest_tie_fraction`** | **0.2714** | **0.1167** |
| percentile-space IQR | 0.4493 | 0.4600 |

**The largest tie block more than halves.** That is the number that matters
for the exclusion radius in Step 5: the worst case drops from 27% of Earth's
land sharing one composition value to 12%.

`corr(SiO₂, FeO_T) = +0.128` over land pixels — the two oxides are **not**
redundant and should both go to the VIF step. SiO₂ p1 4.8, p50 64.0, p99 87.0
wt%.

Layers written: `earth_SiO2_nside1024.npy`, `earth_FeO_nside1024.npy`.

## (e) Uncertainty that applies to the whole lithology layer, from the paper

These are the authors' own figures and they bound everything above:

- **Ground truth: 40% of 164,953 independent rock-description points match the
  GLiM class exactly; 64% match if similar lithologies are allowed.** That is
  the ceiling on any composition derived from it.
- **A level-2 code exists for only 68% of units, a level-3 code for 20%.**
  Absence of a code does **not** mean absence of the attribute — the paper is
  explicit. So `ss____` is not "siliciclastic with no coal"; it is
  "siliciclastic, coal not recorded".
- **`sm` is partly an unknown-sediment class**: it holds "all sediments where
  carbonate is mentioned but not dominant, **plus some units that were
  identified as sediments, but no information on the type of sediment was
  available**". That confirms the HIGH rating on `sm` independently.
- The map scale is 1:3,750,000 area-weighted, and `pu` is also applied to
  non-sedimentary units to flag minor carbonate — so `mtpu__` is
  marble-bearing metamorphic rock, not a carbonate rock.
- The paper's volcanic and plutonic classes are explicitly "classed after
  Le Maitre [2004]", which is the same IUGS scheme §B16 rests on. **The
  definitional footing for the six igneous rows is now confirmed by the source
  rather than inferred.**

**Not wired into the pipeline.** The table and the two layers exist; nothing
downstream consumes them yet.

---

# §B20 — CAN COMPOSITION BE A MATCHABLE DIMENSION? Verified 2026-11-07

## (a) What is on disk

**Moon — nothing usable was on disk.** The Clementine file was *not* deleted,
but it is unusable twice over:

```
sources/tier3_composition/Lunar_Clementine_UVVIS_FeO_ClrBinned_70S70N_1km.tif
  10918 x 4246, 3 bands, uint8 RGB   <- a COLOUR image, not FeO wt%
  bounds +/-2,123,024 m / 1,737,400 m = +/- 70.0 deg latitude
  plus a stale 73 MB .part from an interrupted download
```

"ClrBinned" means colour-binned: three uint8 RGB bands with 79/97/119
distinct values. **The same trap as the Diviner level-4 TIFs.** And even as a
rendering it stops at ±70°, excluding every lunar target at 85–90°S.

**Mars — the TES mineral maps are real and on disk.** 11 mineral maps plus an
RMS error map, 1440 × 720 = **0.25°**, float32, fill −1 covering **27.73%**.
On Mars 0.25° is 14.8 km against the 6.79 km pixel, about 4.7 pixels per cell
— the same ballpark as Diviner and acceptable. Two cautions: the files carry
**no geotransform**, so georeferencing has to be assumed, and the `Dust` layer
reaches 2.52, so it is not a simple fraction.

## (b) Corrections to the available-source claims

An AI search summary offered alongside this task asserted that a global lunar
SiO₂ map is "available via the Christiansen Feature from Diviner" and that
"TES Oxide Weight Percent Maps (Wyatt et al.)" can simply be pulled.

**My own first reaction was also wrong, and in the opposite direction.** I
called the Diviner SiO₂ map a non-existent product. It exists:

- **Greenhagen et al. (2010, Science 329:1507) gives the CF *position*, not
  SiO₂.** That much was right.
- **Lucey et al. (2021, JGR Planets, doi 10.1029/2020JE006777)** calibrated CF
  against synthetic glasses spanning 0.5–97.6 wt% SiO₂ and produced a global
  lunar SiO₂ map. **Stated calibration uncertainty ±3.4 wt% SiO₂.** So the map
  is real; it is a 2021 derived product rather than a standard PDS download.
- **The TES oxide grid is NOT confirmed as a download.** McSween, Taylor &
  Wyatt (2009, Science 324:736) derive oxides from TES mineralogy to **±5 wt%**
  at 4 pixels per degree, but no PDS gridded oxide product was found. Deriving
  it means building a mineral-stoichiometry lookup from the 11 mineral maps —
  a second table needing the same primary-source discipline the GLiM table
  just proved necessary.

## (c) The source that actually settles the Moon: Lunar Prospector GRS

`pds-geosciences.wustl.edu/lunar/lp-l-grs-5-elem-abundance-v1/lp_9001/`

There is **no 0.5° product** — only 2°, 5° and 20° equal-area. The 2° table
is 9.95 MB, 11,306 rows, and was downloaded and read directly:

| | |
|---|---|
| oxides | **W_SIO2 and W_FEO**, weight fraction g/g, plus MgO, Al₂O₃, CaO, TiO₂ |
| uncertainty | **45-element error matrix**; sqrt of the diagonal is the propagated uncertainty |
| coverage | latitude **−90 to +90**, longitude −180 to 180 — **global, poles included** |
| source | Prettyman et al. (2006), cited in the PDS label |

Measured directly from the table:

| | global | **85–90°S (the targets)** |
|---|---|---|
| cells | 11,306 | **24** |
| SiO₂ wt% | 20.57 – 66.44 (mean 43.10) | **42.74 – 47.53 (mean 44.88)** |
| FeO wt% | 0.00 – 30.75 (mean 7.38) | **4.49 – 5.99 (mean 5.18)** |
| HEALPix pixels per cell | 70 | **63** |

Those polar values are physically right for anorthositic highlands. **But the
target region holds only 24 distinct composition values over ~1,512 HEALPix
pixels, and the spread there is 10.4% of the global SiO₂ range and 4.9% of the
global FeO range.**

## (d) What composition is worth, and the recommendation

Current matchable dimensions, with `roughness_scaling_exponent` on HOLD and
Mars thermal already `matching_eligible: false`:

| pairing | now | with composition |
|---|---|---|
| **Earth–Moon** | 6 terrain + 2 thermal = **8** | **10** |
| **Earth–Mars** | 6 terrain + 0 thermal = **6** | **8** |

Cost to build:

| option | work | hours |
|---|---|---|
| Moon | LP-GRS already downloaded; parse, bin, validate, figures | **1–1.5** |
| Mars | mineral-stoichiometry table from 11 TES maps, + no geotransform, 27.7% fill, `Dust` > 1 | **3–5** |

**RECOMMENDATION: (b) — build composition for Earth and the Moon only.**

1. The Moon data is in hand, numeric, carries both oxides and a published
   error matrix, and **covers the poles** — the one thing the Clementine file
   could never do.
2. **Earth–Mars is already the weaker pairing**: its thermal layers are
   ineligible, so it sits at 6 dimensions, and composition there costs the
   most for the pairing that the MCD grid has already capped.
3. **The targets are lunar polar sites.** Earth–Moon is the pairing the
   project exists to serve, and composition takes it from 8 to 10.
4. The cube is due on the 10th with Phases 4–5 still to run. 1.5 hours is
   affordable; 5 is not.

**State this honestly when it is used.** Composition will be a *weak*
dimension at both ends:

- On the lunar side it is near-constant across the target region — 24 values,
  63 pixels each, a 4.8 wt% SiO₂ spread. It will act mostly as a fixed offset
  selecting Earth's mafic terrains (SiO₂ ≈ 45, FeO ≈ 5 points at basic igneous
  and mixed-sedimentary ground) rather than discriminating *between* lunar
  targets.
- On the Earth side it inherits the GLiM ceiling: **40% of independent rock
  points match the mapped class exactly, 64% allowing similar lithologies**.

A dimension with a 64% ceiling on one side and 24 distinct values on the other
is worth having for rank comparison and is not worth five hours. If Phase 4
runs late, **fall back to (c)** — drop composition from the matchable set,
keep the layers as reported context, and the counts return to 8 and 6.

---

# §B21 — HEALPIX GATE: **ADOPTED FOR v1**. Decided 2026-11-08.

**Criterion, stated before measuring:** total re-gridding under 3 hours AND
clean mask handling → HEALPix for v1; otherwise DEFERRED TO v2.

**Note on what this gate was.** HEALPix was already built when the gate was
run — 34 layers across Phases 1–3 — so these are production timings, not a
toy. No `Appendix F` exists in any document on disk; the questions were
answered as stated.

| question | measured answer |
|---|---|
| wall clock, one Earth variable | **5.3–6.3 s** (MOD11C3 LST, 25,920,000 cells → 12,582,912 pixels at Nside 1024) |
| worst case, full-resolution DEM | **9.3 min** (43,200 × 86,400 = **3,732,480,000** cells → Nside 1024, all pixels filled) |
| lines of code | **37 executable** (81 with docs) |
| does it generalise? | **For continuous variables, yes** — `HealpixAccumulator` is reused *unchanged* by `phase3_thermal`, `wb_impact`, `healpix_gate`. **For categorical variables, no**: majority vote needed a separate sparse `(pixel, class)` reduction, ~45 more lines. **The reader never generalises** — six datasets, six formats (HDF4, fixed-width ASCII, `\|\|`-separated ASCII, memmap, vector, equal-area table). |
| **total re-gridding** | **2.25 h for everything on disk** — and that is the *whole* build including Phase 2's summed-area-table window statistics. Pure binning is a small fraction of it. |

## Mask handling — clean, and structurally so

Against a hard 900 × 2000 NaN block in a constant field:

```
fully-supported pixels      10,990,934   max |drift| = 0.000e+00
edge-straddling pixels           1,705   max |drift| = 0.000e+00
pixels wholly inside block   1,177,641   NaN, support 0
```

**A cell maps to exactly one pixel, so a NaN can only remove weight from its
own pixel.** Neighbour contamination is not merely absent, it is structurally
impossible. This is a property of the accumulator design, not a lucky result.

## Lunar Prospector GRS re-binning — no distortion

LP cells are **equal-area** and HEALPix pixels are **equal-area**, so this is
an exact point-in-cell assignment: no area weighting, no projection
distortion. 11,306 cells → 786,432 pixels in ~30 s, **99.967% filled**, 10,440
distinct values surviving. It is an **upsample** (~70 pixels per cell), so
every pixel is `COPIED_FROM_COARSER`, never `BINNED`.

## DECISION

**HEALPix is ADOPTED for v1.** 2.25 h against a 3 h budget, masks provably
clean, and the equal-area-to-equal-area case handled without distortion. The
one caveat on the record: **categorical layers need their own binning code**,
and that is already written.

---

# §B22 — MOON COMPOSITION BUILT (option b). 2026-11-08.

Range gates stated before the run: SiO₂ 15–70 wt%, FeO 0–32 wt%. **Both
passed**, 99.967% of pixels assigned.

| | global | **85–90°S (targets)** |
|---|---|---|
| SiO₂ | 20.57 – 43.27 – 66.44 wt% | **42.74 – 44.66 – 47.53** |
| FeO | 0.00 – 5.50 – 30.75 wt% | **4.49 – 5.09 – 5.99** |
| SiO₂ σ (median) | 4.905 wt% | **1.416 wt%** |
| FeO σ (median) | 1.000 wt% | **0.292 wt%** |
| distinct levels | 8,322 / 10,440 | **24 / 24** |
| largest tie fraction | 0.0005 / 0.0003 | **0.0430** |

**The polar data is 3.4–3.5× MORE precise than global.** Lunar Prospector flew
a polar orbit, so the poles got far more counting time — the same geometry
that made Diviner's local-time sampling densest at the poles.

**But precision is not discrimination.** Spread ÷ median σ gives the number of
levels actually separable at the targets:

> **SiO₂: 3.4 effective levels** (nominal 24). **FeO: 5.1 effective levels.**

That is the honest figure, and it is the one to quote. Both weakness
statements are carried in all four composition manifest entries:

- **Moon side:** near-fixed offset pointing Earth matches at mafic terrain,
  not a discriminator between lunar targets.
- **Earth side:** GLiM's 40% exact / 64% similar ceiling.

### Correction carried into §B20

LP GRS was chosen over the Diviner CF-derived SiO₂ map **not because the CF
map is unavailable — it exists.** Lucey et al. (2021, JGR Planets,
doi 10.1029/2020JE006777) calibrated the Christiansen Feature against
synthetic glasses spanning 0.5–97.6 wt% and produced a global lunar SiO₂ map,
±3.4 wt%. An earlier note in this project called that product non-existent and
**that was wrong — a false "does not exist" closes a door that was open.**
LP GRS wins on three specific grounds: **both oxides from one instrument, on
one grid, with a published per-cell error matrix.** The CF map is SiO₂ only
and would need a second, differently-calibrated source for FeO.

---

# §B23 — THERMAL INERTIA COSTING: **DO NOT BUILD.** 2026-11-08.

Rule applied: under 3 h → build; over 3 h → ship at 8 and 6 and log this.

The physics argument is right — thermal inertia is a **material property**
(grain size, rock abundance, induration) and temperature is a **state** that
depends on latitude, season, local time and dust. For an analog question the
property is the better quantity. That is not what decides this.

## Mars — exists, and at the right scale

TES-derived thermal inertia (Putzig & Mellon), ASU Mars Global Data Sets:
dayside 2007, nightside 2007, nighttime 2005. **20 pixels per degree ≈ 3 km**,
7200 × 3600, simple cylindrical. Apparent thermal inertia computed in 10° Ls
seasons every 20° Ls, plus single global maps.

**3 km is FINER than the 6.79 km pixel, so it would BIN properly** — no copied
values, unlike MCD temperature at 355 km. This is the strongest part of the
case. Two unverified risks: coverage is quoted inconsistently (~60–63%,
variously 50°S–70°N or 80°S–80°N), and the distributed TIF **may be a colour
rendering** — the 2003 release offered raw VICAR separately, and this project
has now hit that trap twice (Clementine FeO, Diviner level-4).

## Moon — THE BLOCKER: cannot confirm a polar product exists

After two searches and three PDS fetches I **cannot confirm** that Diviner
rock abundance or the regolith H-parameter covers 85–90°S:

- `data_derived_gdr_l3/cylindrical/` contains only `img/` and `jp2/`
  subdirectories; no filenames, no labels at that level.
- The PDS landing page states no latitude range and does not mention rock
  abundance or H-parameter at all.
- `data_derived_prp/` (Polar Resource Products) holds `dlre_prp_south.tab`,
  **604 MB, 2,880,000 records, 15 columns whose meanings are NOT in the
  label** — they are in a `DLRE_PRP.FMT` and a `prpds.cat` not yet read. No
  `MAXIMUM_LATITUDE` / `MINIMUM_LATITUDE` anywhere.
- A secondary source states the products "were extended to 80 degrees N/S",
  which would **exclude every target**, but that is a paper abstract, not a
  label, and is NOT treated as established.

## Earth — a quantity mismatch, not just a cost

Apparent thermal inertia from (1 − albedo) / ΔT needs an albedo product
(MODIS MCD43) that sits behind **the same Earthdata Login wall as MYD11C3**.
Worse than the cost: **ATI is a crude proxy and TES inertia and Diviner H are
measured properties.** Pairing them would repeat precisely the air-versus-
surface-temperature error that the Terra/Aqua fix exists to remove. That is a
reason to hesitate even with unlimited time.

## THE NUMBER

| leg | hours if nothing goes wrong |
|---|---|
| Mars: verify TIF is numeric, download, bin, validate, figures | 1.0 – 1.5 |
| Moon: finish discovery, then 604 MB + 15 undocumented columns | 2.0 – 3.5, **unbounded if the columns are wrong** |
| Earth: albedo (blocked on login), ATI, validate | 1.0 – 1.5 |
| **TOTAL** | **4 – 6.5 h, with one unbounded leg** |

**What will go wrong: the Moon leg.** Three PDS fetches did not establish that
the product exists at the target latitudes. The pattern in this project is
that **lunar product discovery costs more than lunar product processing** —
the Clementine file was wrongly believed deleted and turned out to be a colour
image at ±70°, and the Diviner CF SiO₂ map was wrongly believed not to exist.
Two errors in opposite directions on lunar products in one week.

**DECISION: ship the cube at 8 (Earth–Moon) and 6 (Earth–Mars) dimensions —
10 and 8 with composition. Thermal inertia is logged as the stated next
upgrade with this costing attached.** The cube being validated on time on the
10th matters more than one extra dimension, and the one leg that would make
thermal inertia worth having for the pairing that matters — the Moon — is the
leg that cannot be costed.

---

# §B24 — PHASE 4 AND 5 COMPLETE. The headline result is NEGATIVE.

*2026-11-09. Dimension set: earth_moon, 10 dimensions.*

## (a) Calibration

| | value |
|---|---|
| Earth reference population | 3,260,787 pixels, **99.604% complete** across 11 candidates |
| whitening | inverse square root of the correlation matrix, eigenvalues floored at 0.10 |
| floored | 3 of 10 eigenvalues, holding **0.304% of total variance** |
| d_bar | **3.7161** (spread 0.641% over 6 seeds) |
| DI threshold | **0.1970** = 95th percentile of Earth's within-reference nearest-neighbour DI |

Whitening is what makes the redundant terrain family safe: slope and
roughness_10.5km correlate at **+0.9939**, and an unwhitened Euclidean
distance would count that one piece of terrain information twice. The
eigenvalue floor keeps every dimension available to any user-selected subset
while refusing to divide by a direction the data does not resolve. Single-
terrain selections have lambda_min near 0.60 and are untouched by it.

## (b) The Artemis III targets

Nine NASA regions, October 2024, named verbatim. NASA publishes **no
geometry** — no coordinates, bounds, polygon or shapefile — so each region is
placed at the IAU-gazetteer centre of the feature it is named after, as a
disc of equal area to NASA's stated 15 x 15 km (radius 8.46 km). Coordinates
planetographic, +East, -180..180, LOLA 2011.

| region | DI | margin vs threshold | p (5 seeds) |
|---|---|---|---|
| Peak near Cabeus B | 0.3000 | −52.3% | 0.898 |
| Haworth | 0.2854 | −44.9% | 0.913 |
| Malapert Massif | 0.1926 | **+2.2%** | 0.547 |
| Mons Mouton Plateau | 0.2757 | −40.0% | 0.867 |
| Mons Mouton | 0.2757 | −40.0% | 0.867 |
| Nobile Rim 1 | 0.2242 | −13.8% | 0.714 |
| Nobile Rim 2 | 0.2242 | −13.8% | 0.714 |
| de Gerlache Rim 2 | 0.1731 | +12.1% | 0.363 |
| Slater Plain | 0.1408 | +28.5% | **0.182** |

**Malapert Massif's "covered" verdict is NOT reportable.** Its margin is
+2.2% against a d_bar that moves 0.641% across seeds and a threshold that is
an estimated 95th percentile. Two regions are clearly covered, one sits on
the line, six are clearly outside.

## (c) THE NULL: nothing is significant

Null windows drawn in the same **ABSOLUTE-latitude** band (+/-2 deg) as each
target, from **both hemispheres**, at the same disc radius. 1,000 windows per
seed, 5 seeds, 5,000 per target.

Banding on |lat| and mirroring is not a detail. A disc's pixel count depends
on |lat|, not signed lat, so banding on signed latitude makes the matching
set two disjoint arcs drawn from a different population than the target.
That exact error produced a 95% rejection rate earlier in this project.

> **No region reaches p < 0.05. The best is Slater Plain at p = 0.182.**
> Seed spread 0.018 to 0.036, so the p-values are stable to about +/-0.02.

And the direction is the interesting part:

> **The targets sit on average +23.8% ABOVE their null medians.** Only Slater
> Plain and de Gerlache Rim 2 fall below. The Artemis candidate regions are,
> if anything, slightly WORSE Earth analogs than random lunar terrain at the
> same latitude.

**That is the correct result and it should not be spun.** NASA selected these
regions for illumination, permanently-shadowed-region access, communications
and slope safety — not for resemblance to Earth. There is no mechanism by
which they would be unusually Earth-like, and the null confirms they are not.

What the null also establishes is that **the DI differences between targets
are driven by latitude, not by site-specific properties.** The null median DI
is 0.184–0.197 in every band, nearly flat, while observed DIs range
0.141–0.300. Once latitude is controlled, the ranking between regions carries
little signal.

## (d) What the method DOES show

The Earth matches are geographically coherent and were not told to be:
interior Alaska and Yukon, the Taymyr peninsula, Severnaya Zemlya, the
Canadian Arctic archipelago, north Greenland. Every top match for every
region lies between 60 and 82 degrees NORTH. Nothing in the pipeline encodes
"lunar polar targets should resemble terrestrial Arctic terrain" — it falls
out of ten whitened dimensions, and it survived a rebuild of two of them.

The visible artefact of the target set is also exactly as predicted:
**Mons Mouton Plateau and Mons Mouton return identical DIs and identical
p-values, as do Nobile Rim 1 and Nobile Rim 2** — two NASA regions, one IAU
feature, so they are literally the same target computed twice.

## (e) The honest summary for the write-up

1. The cube is built and validated: 10 matchable dimensions Earth-Moon, 6
   Earth-Mars, all gated on range, coverage, support and (where categorical
   or copied) tie structure.
2. The matching machinery works and produces geographically sensible answers.
3. **The specific scientific claim "these Artemis regions have good Earth
   analogs" is NOT supported.** Two of nine fall inside Earth's coverage;
   none is significant against a latitude-matched null.
4. The strongest defensible claim is the negative one plus the method: a
   reproducible, gated pipeline that can test any target set, applied to
   NASA's own regions, returning a clear and falsifiable answer.


---

# §B25 — CLEAN-DATA PASS BEFORE THE HACKATHON. 2026-11-09.

**Nothing in the method changed.** Dimension sets unchanged: Earth–Moon 10,
Earth–Mars 6. The Earth thermal rebuild of 9 Nov (calendar 2025, Terra + Aqua,
four local times — see the manifest entries) left five loose ends. All five are
closed, each with its measurement.

## (a) Provenance refreshed after the thermal rebuild

The three Earth thermal layers were rebuilt on 9 Nov but their provenance
arrays still described the 22-month Terra build. `build/provenance.py --write`
re-derived them:

| layer | provenance array | ABSENT | BINNED | COPIED | NO_VALID |
|---|---|---|---|---|---|
| earth_temp_level, earth_temp_range_seasonal | `provenance_94a442c0fdc3` | 305,189 | 3,647,966 | 107,518 | 8,522,239 |
| earth_temp_range_diurnal | `provenance_6cb4ef59c25d` | 305,218 | 3,647,372 | 107,488 | 8,522,834 |

The two superseded arrays (`69772b93103f`, `f79fdb4abdd5`) were deleted and
logged in `cube/cleanup_log.json` under `later_removals`. One convention on
disk, the numbers in the log.

`provenance.py` itself needed three fixes, because the 8 Nov cleanup had
changed what is on disk under it:

1. Seventeen layers had their support arrays deleted as CONSTANT (value in the
   manifest). The script now rebuilds the support from that recorded constant
   instead of skipping the layer, so every geometric layer has provenance again.
2. Layers whose builder writes its own provenance array (moon composition,
   Köppen) are read as-is, not re-derived.
3. Manifest matching is exact key match. The old `endswith` rule had attached
   `moon_slope`'s provenance to the `smoke_moon_slope` entry.

Result: **36 layers → 12 distinct provenance arrays**, every data-layer entry
carries `provenance_file`.

## (b) Köppen-Geiger built — characterization only

Source: Beck et al. (2023), Scientific Data 10, 724; the 1991–2020
observational period at 30 arc-second (0.93 km), uint8 codes 1..30. Copied
from `D:\Projects\koppen_geiger_tif\1991_2020` into `sources/koppen_geiger`
(write-once folder; the pipeline never reads `D:\Projects` directly). SHA1 of
the copy equals the original: `d3fcb9a735edaaff525e1288d35dbfa928952c02`.

Categorical → **majority vote**, cos(lat)-weighted, same construction as
lithology. The source is finer than the pixel everywhere (0.93 km against
6.37 km), so every classified pixel is BINNED; nothing is copied.

`matching_eligible: false` **permanently**. The Moon and Mars have no Köppen
class, and a variable is a dimension only if both bodies in the pair have it.
Written into the manifest entry, the source manifest and CUBE_STATE.

Gates, stated before the run, and what they measured:

| gate | stated | measured |
|---|---|---|
| range | codes 1..30 | **PASS** — 0 non-zero cells outside, no code above 30 |
| coverage | — | 3,712,128 pixels = 29.50% of the sphere; 99.975% at 85–90°S (EF over the Antarctic ice sheet — Köppen classifies ice, the reference mask excludes it) |
| coverage of the reference population | — | **3,260,787 of 3,260,787 reference pixels carry a class — 100.000%**. Step 9 will never look up a site and find no class |
| support (winning share) | — | p50 1.000, mean 0.962; 22,287 pixels (0.6%) below 0.50; 3,086,027 pixels (83%) hold a single class; at most 8 classes in one pixel |
| ties | — | 30 distinct classes; largest tie BWh = 14.47% of classified pixels |

Class shares over the reference population (percent of classified reference
pixels, equal-area so these are area shares): BWh 16.3, Aw 13.4, Dfc 11.3,
Dfb 7.5, BSh 6.5, BSk 5.5, Af 5.1, ET 5.0, Cfa 4.7, BWk 3.7. Hot desert is
the single largest class of ice-free, water-free land, which is what one
expects and is worth saying in the write-up.

Files: `earth_koppen_class_nside1024.npy` (uint8), `..._support_...` (winning
share), `..._provenance_...` (1 = BINNED, 3 = NO_VALID_SOURCE i.e. ocean),
`cube/koppen_legend.json`, `cube/healpix/koppen_summary.json`,
`sources/koppen_geiger/manifest.json`. Build 3.2 min, 1.32 GiB peak.

## (c) Six arrays that had no manifest entry

`cube/healpix` held six arrays that no manifest entry pointed at. An array
whose definition lives only in the script that wrote it is not defensible.
`build/record_auxiliary.py` measured each as it is on disk and wrote the entry,
naming the builder and the file's own modification time:

| entry | what it is | measured |
|---|---|---|
| `earth_reference_mask` | fraction of pixel area that is reference land; member where > 0.5 | 3,260,787 pixels = 25.914% of the sphere — **matches phase4a exactly** |
| `earth_lithology_l3` | GLiM level-3 class, uint16, 65535 = none | 3,712,659 classified; 391 classes over all pixels (388 on land) |
| `earth_lithology_l1` | GLiM level-1 class, uint8, 255 = none, with the paper's own class meanings | 16 classes; footprint identical to l3 on every pixel |
| `earth_lithology_support` | winning share; also the support of earth_SiO2 / earth_FeO | finite on exactly the 3,712,659 classified pixels, p50 1.000 |
| `earth_thermal_nsamples` | months with data in 2025, of 12 | p50 0 (ocean), zero on 8,826,866 pixels |
| `moon_thermal_nsamples` | GCP local-time bins filled, of 96 | p50 58, never zero |

A lithology provenance array was written alongside (BINNED where classified,
NO_VALID_SOURCE where no polygon). Lithology and Köppen were built from two
unrelated land footprints and classify 3,712,659 and 3,712,128 pixels
respectively — a 0.014% difference. The per-pixel overlap was NOT measured; only
the counts are compared.

## (d) Phase 5 validation exists and passes

`build/cube_validate.py` checks the manifest against the disk with no layer
exempted by name: file exists, 12·Nside² entries, dtype matches, `n_valid`
on disk equals the recorded `n_valid`, values inside every gate that was
stated in advance, support array present or its constant recorded,
provenance array present, uint8, codes 0..3, and **agreeing pixel by pixel
with the values** (finite ⇔ BINNED or COPIED). Then: no orphan `.npy` in
`cube/healpix`, every layer in `provenance_encoding.json` in the manifest with
its file present, and the matchable sets derived from the manifest flags
alone must come out at the decided counts.

Result, 2026-11-09 11:57 UTC: **PASS**. 51 manifest entries, 0 layer
failures, 0 orphans, 0 encoding issues, Earth–Moon 10 and Earth–Mars 6 from
flags alone, 0 provenance disagreements on all 36 layers. Report in
`cube/cube_validation.json`; CUBE_STATE.md carries the verdict.

## (e) CUBE_STATE corrected

Health warnings 3 and 4 still described the two-sample, 22-month Earth
thermal build. They now describe the four-local-time, calendar-2025 build.
A new table lists every layer that must never rank (masks, filters,
characterization, diagnostics), generated from the manifest `role` field.

## (f) What is still open for Steps 1–2

In code: **nothing.** By decision, unchanged from before and NOT re-opened
here: sky view factor (Appendix H — a lat/lon horizon sweep at 89°S is wrong,
needs a polar-stereographic pass, 2–4 h), the optional TPI at 7 km (B1
secondary recommendation, ~1 h for three bodies, would add one dimension to
BOTH pairs), thermal inertia (B23 — do not build). Recommendation to
Sherozbek: add nothing before the hackathon; the day's value is in the cube
being clean, which it now measurably is.


---

# §B26 — TPI AT 7 km ADDED. Sherozbek's decision, 2026-11-09.

**This IS a method change, and it is recorded as one.** Dimension sets move
from Earth–Moon 10 / Earth–Mars 6 to **11 / 7**. The spec (rev 8, Step 2
Part A) still says 10 and 6 and needs the row added.

## The decision

After the clean-data pass (B25) the recommendation on the table was to add
nothing before the hackathon, with TPI at 7 km named as the one cheap, honest
option — B1's own secondary recommendation. Sherozbek chose to add it. Reason,
from B1: TPI is strongly scale-dependent; a 7 km window separates small
craters and rille floors that the 21 km window averages away, and the 7 km
window matches the slope baseline. The terrain family now carries form at two
scales (7, 21 km) and texture at four (5.25–42 km).

## How it was built — the same code path, by construction

`build/phase2b_tpi7.py` imports `sat3` and `window_stats_from_sat` from
`phase2_terrain.py` and calls them with a 7 km window: the band loop, the
halo, the east–west widening as 1/cos(lat), the 50% validity rule, the
cos(lat)-weighted binning and the three gates are phase 2's own. The manifest
entry is a copy of `tpi_21km`'s with the window fields changed, so the two
TPI layers cannot carry different conventions.

| body | cell | half | achieved window | EW rows capped | build | peak RAM |
|---|---|---|---|---|---|---|
| Moon | 0.4738 km | 7 | **7.107 km** | 4 of 11,520 | 1.2 min | 1.98 GiB |
| Mars | 0.4631 km | 7 | **6.946 km** | 4 of 23,040 | 6.1 min | 2.11 GiB |
| Earth | 0.4633 km | 7 | **6.950 km** | 4 of 43,200 | 16.3 min | 2.70 GiB |

Full-footprint convention, (2h+1)·cell, as for every window statistic. The
capped-row count is window/(π·cell) = 4.7–4.8 on all three bodies, so 4 rows
each — the radius cancels, exactly as the EW-saturation formula predicts.

## Gates

| | Moon | Mars | Earth |
|---|---|---|---|
| coverage | 100.000% everywhere, incl. 85–90°S | 100.000% | 100.000% |
| support | constant 1.0 → not written, constant recorded (8 Nov rule) | same | same |
| range (m) min / p50 / max | −565.2 / −1.13 / 379.6 | −375.4 / −0.25 / 483.4 | −421.6 / −0.13 / 573.6 |
| IQR (m) | 42.1 | 7.2 | 8.1 |
| provenance | BINNED on every pixel | same | same |

No range gate was stated in advance for TPI, as for the other geometric
layers: a difference of heights has no physical bound to state. The
statistics are recorded; the sanity check is that the medians sit at zero
(−1.1, −0.25, −0.13 m), which a difference-from-local-mean must do.

The lunar IQR is five times the terrestrial one. That is the Moon's
cratered surface at 7 km, not an artefact: the same ratio appears at 21 km.

## The B8 check — measured, not assumed

`build/tpi7_dimension_check.py`, on phase 4a's own reference population
(3,260,787 pixels; 3,247,889 complete across all 12 candidates, 99.604%;
tpi_7km is NaN on none of them). Phase 4 artifacts were NOT modified —
`percentiles.npy` still holds the 11-candidate B24 run.

Rank correlation of tpi_7km with every other candidate, Earth reference:

| tpi_21km | slope | roughness 5.25 / 10.5 / 21 / 42 | temp_level | diurnal | seasonal | SiO₂ | FeO |
|---|---|---|---|---|---|---|---|---|
| **+0.782** | −0.032 | −0.008 / −0.042 / −0.067 / −0.074 | −0.010 | −0.042 | −0.007 | −0.008 | −0.019 |

Per body, all valid pixels: ρ(tpi_7km, tpi_21km) = +0.852 Moon, +0.808 Mars,
+0.847 Earth; ρ with slope within ±0.03 on all three. The two TPI scales
behave as a family the way the four roughness scales do, and the family is
orthogonal to texture, thermal and composition.

| pairing | candidates | λ_min before → after | eigenvalues < 0.10 | variance below floor |
|---|---|---|---|---|
| Earth–Moon | 10 → 11 | 0.0023 → 0.0022 | 3 → 3 | 0.304% → 0.275% |
| Earth–Mars | 6 → 7 | 0.0023 → 0.0022 | 3 → 3 | 0.517% → 0.442% |

The smallest eigenvector loads on roughness_10.5km (−0.83), roughness_21km
(+0.38), roughness_5.25km (+0.29) and slope (+0.26); tpi_7km's loading is
−0.008. **tpi_7km adds no near-singular direction.** The three floored
eigenvalues are the roughness family, exactly as before B24's floor at 0.10
was introduced for them. Verdict under the B8 rule: **KEEP.**

## What changed in code, and what did not

Changed: `phase4a_percentile.py` CANDIDATES and EARTH_MARS, `phase4c_di.py`
SETS, `cube_validate.py` EXPECTED_PAIRS (11 / 7), HANDOVER.md dimension
table. CUBE_STATE regenerated from the manifest.

NOT rerun: phase 4a/4c/4d and the null (phase 5). Their stored outputs and
the B24 headline result are from the 10 / 6 sets. The next full run picks
tpi_7km up automatically through the lists above. The B24 numbers remain
true for the sets they were computed on and are not to be quoted as results
for 11 / 7.

## Validation

`build/cube_validate.py` after the addition: PASS, 54 manifest entries,
0 layer failures, 0 orphans, 0 encoding issues, pairings 11 / 7 derived
from the manifest flags alone. 39 layers now carry provenance, in 12 shared
arrays.


---

# §B27 — SKY VIEW FACTOR, MARS THERMAL AND MARS COMPOSITION. Sherozbek's decision, 2026-11-09.

**Method change, recorded as one.** Sherozbek's reasoning: the Earth–Mars set
was six, then seven, variables all derived from one elevation model, so it
is redundant by construction; a Mars analogy needs thermal and geological
information, and sky view factor is the openness dimension B2 specified.
Three additions were ordered: SVF on all three bodies, Mars thermal, Mars
composition. All three are built. What each one is, and is not, follows.

Dimension sets move from 11 / 7 to **Earth–Moon 12, Earth–Mars 10** (11 once
the Earth thermal-inertia partner exists — see (c)). Appendix H's "sky view
factor deferred" and B23's "thermal inertia do not build" are overridden by
this decision; both entries stay in the record.

## (a) Sky view factor — `svf_30km`, all three bodies

Formula and parameters from B2: SVF = 1 − (1/16) Σ sin(max(γᵢ, 0)), 16
azimuths, 30 km search radius, Zakšek et al. (2011) form (openness, not the
cosine-weighted radiative form). Computed at 0.93 km (0.95 km Moon), a 2×2
block mean of the working DEM; the 30 km radius is 32 cells.

**The polar problem is solved, not avoided.** |lat| ≤ 80° runs on the plate
carrée grid with the east–west ray step scaled by 1/cos(lat) per band so
the azimuths stay 22.5° apart. |lat| > 80° runs on polar-stereographic caps,
both poles, every body: the 463 m DEM is reprojected with an area-averaging
resampler onto a square 0.93 km grid, the SAME kernel runs with cos = 1,
and the result is binned to HEALPix with true-area weights 1/k². A horizon
sweep along a lat/lon row at 89°S follows a curved, converging path and its
azimuths are not what they claim — that is wrong, not imprecise, and
85–89.9°S is the lunar target band.

**Seam check, measured** (`build/svf_boundary_check.py`): for 78–80°, where
both methods can compute the same terrain, the cap is re-binned and compared
pixel by pixel with the built layer, which took those pixels from the
lat/lon sweep.

| body | pole | pixels | median abs diff | p95 | r | built IQR |
|---|---|---|---|---|---|---|
| Moon | S | 2,420 | 0.0031 | 0.0081 | 0.995 | 0.038 |
| Moon | N | 2,420 | 0.0036 | 0.0085 | 0.997 | 0.040 |
| Mars | S | 9,640 | 0.0006 | 0.0028 | 0.999 | 0.017 |
| Mars | N | 9,640 | 0.0005 | 0.0022 | 0.998 | 0.007 |

The two methods agree to under a tenth of the layer's own spread, with a
small positive bias (the cap reads ~0.003 higher: area-averaged
reprojection smooths rims). The polar method is interchangeable with the
global one; the seam at 80° is not a step.

Earth: cells outside the land mask are set to 0 m (the sea surface) before
the sweep. ETOPO carries bathymetry, and a coast looks at the sea, not the
seafloor. Inland water keeps its DEM value.

| body | cell | K cells → km | bands | build | SVF p1 / p50 / p99 | min |
|---|---|---|---|---|---|---|
| Moon | 0.948 km | 32 → 30.32 | 20 | 3.4 min | 0.803 / 0.942 / 0.998 | 0.622 |
| Mars | 0.926 km | 32 → 29.64 | 40 | 14.6 min | 0.883 / 0.988 / 0.999 | 0.695 |
| Earth | 0.927 km | 32 → 29.65 | 75 | see (a-cont.) | | |

Range gate [0, 1] stated in advance: 0 pixels outside on every body.
Coverage 100%, support constant 1.0 (recorded, not written). Mars is far
more open than the Moon at this scale (IQR 0.018 against 0.050): the Moon
is saturated with 10–50 km craters, Mars is not. That is the planet, not
the method.

**Limitation, stated:** sub-kilometre terrain is invisible. A 200 m pit or
boulder field does not lower this SVF. It measures basin-scale openness.
The cos(lat) for the ray step is taken at the band centre; at 80° the
azimuth error from that is under 2°.

## (b) Mars thermal — what exists and what does not

The source search of 9 Nov 2026 (build/ research, recorded here) found **no
public, gridded, measured Mars surface-temperature map at pixel scale**:

- TES bolometric temperatures exist only as per-observation records; no
  gridded 2 AM / 2 PM map was ever released by ASU or PDS.
- THEMIS Day/Night IR 100 m mosaics are contrast-stretched 8-bit renderings
  (USGS: "only a visual representation"), not kelvin.
- MCS and EMIRS surface temperatures are degrees-scale bins.

So `temp_level` and `temp_range_diurnal` for Mars remain the MCD layers,
flagged ineligible. The one measured Mars thermal product at the right
scale is **thermal inertia**, and it was already on disk: MGS TES, Putzig &
Mellon (2007), PDS MGS-M-TES-5-TIMAP-V1.0, 20 pixels per degree = 2.96 km,
three Mars years. It is a MATERIAL property (grain size, rock abundance,
induration), which B23 itself called the better quantity for an analog.

Built as `mars_thermal_inertia` (nightside, the candidate dimension) and
`mars_thermal_inertia_day` (dayside, diagnostic: day-minus-night apparent TI
flags heterogeneous surfaces). Read from the raw MSB int16 with the label
(rule A); nodata = outside the README's derived range 5–5000 OR the
interpolation mask = 0 (infilled, not measured), both counted:

| | night | day |
|---|---|---|
| cells not computed (0) | 835,853 | 822,403 |
| cells infilled, excluded | 2,193,603 (8.7% of in-range) | 1,761,830 (7.0%) |
| source cells kept | 88.3% (91.3% within 87°) | 90.0% |
| HEALPix coverage | 99.36%; 56% at 85–90°S | 99.72% |
| p1 / p50 / p99 tiu | 30 / 208 / 477 | 21 / 198 / 949 |
| range gate [5, 5000] | PASS, 0 outside | PASS |

The 2.96 km source is finer than the 6.79 km pixel, so every valid pixel is
BINNED; gaps are real (poleward of 87°, clusters of infilled cells).

**The Earth partner.** A dimension counts only if both bodies have it. Earth
has no measured thermal-inertia product anywhere (search confirmed). The
partner is apparent thermal inertia, ATI = (1 − albedo) / diurnal LST range
(Price 1977), from MODIS MCD43A3 albedo and the 2025 four-local-time LST
range already in the cube. `build/phase3e_earth_ati.py` is written and tested
on the albedo loader. **It is not built**: only three albedo months
(Aug–Oct 2025) are on disk, and an annual ratio from three autumn months
would be a seasonal artefact. It needs the other nine months exported the
same way (GEE, MCD43A3, 0.05°, bsa/wsa/n_composites). Measured on the
export: the scale is ×1e-4, not MCD43A3's native 0.001 — p50 1331–1798,
p99 8042–9030, max 9910 — and n_composites is the count of daily retrievals
in the month (max 31), so each file is ONE month of 2025, not a
climatology. Until then `mars_thermal_inertia` is a Mars characterization
layer by the intersection rule alone; no flag is needed.

B23's objection stands as a caveat and is written on both entries: the
Earth side is a PROXY, the Mars side a modelled-from-measurement quantity.
The rank transform compares WHERE each body is thermally sluggish, not the
number.

## (c) Mars composition — `mars_SiO2`, `mars_FeO`, the spec's option (b)

The search found no public Mars product giving oxide weight percent at
pixel scale. GRS is 300–600 km. OMEGA (40 ppd, 1.5 km) and CRISM MRDR (327
ppd) give band depths with no Earth counterpart and no published transfer
to abundance. The only numeric MINERAL-ABUNDANCE product is the TES mineral
maps (Bandfield 2002) at 4 ppd = 14.8 km, and eleven of its thirteen bands
were already on disk as JMARS exports (`Mars lithology/TES_*_numeric`, VICAR,
float32, −1 = no data; sulfate and carbonate bands absent). v1 had derived a
silica from them with an undocumented table; this is the documented rebuild.

**Route:** abundance-weighted mean of end-member oxide contents, normalised
over the MINERAL end-members. Dust is a mask (> 0.80 excluded), not a
component: it is a mantle, the rock is what GLiM gives on Earth. Cells
with RMS_Error > 0.0044 (v1's p95 rule, kept) or mineral sum < 0.10 (one
detection limit) are excluded. Orientation was checked before anything:
Tharsis dust 0.60 vs Syrtis 0.10, Syrtis pyroxene 0.18.

**The end-member table**, every value tagged, in the manifest entry:

| end-member | SiO₂ | FeO_T | tag | basis / alternatives |
|---|---|---|---|---|
| Quartz | 100 | 0 | DEFINITIONAL | |
| K-feldspar | 64.8 | 0 | DEFINITIONAL | KAlSi₃O₈ |
| Plagioclase | 53.0 | 0 | ASSUMED | An60; An70–An50 → 50.5–55.6 |
| Orthopyroxene | 56.3 | 13.5 | ASSUMED | En80; En70–En90 → SiO₂ 55.0–57.5, FeO 20.0–6.8 |
| Clinopyroxene | 53.2 | 12.7 | ASSUMED | augite Ca0.8Mg0.8Fe0.4; FeO 6–18 |
| Olivine | 37.6 | 27.0 | ASSUMED | Fo70; Fo50–Fo90 → SiO₂ 35.0–40.6, FeO 42.0–9.8 |
| Amphibole | 49.7 | 8.5 | ESTIMATE | hornblende; group spans actinolite–hornblende |
| Glass / sheet silicate | 60 | 5 | ESTIMATE | smectite ~50–60 to obsidian ~75; FeO 2–30 (nontronite) |
| Hematite | 0 | 90.0 | DEFINITIONAL | Fe₂O₃ as FeO_T |

**Sensitivity, measured** — every ASSUMED/ESTIMATE value moved to its low and
to its high alternative, the layer rebuilt, and the ORDER compared with the
base (what a rank transform depends on):

| | median shift | p95 shift | rank corr. base vs low | base vs high |
|---|---|---|---|---|
| SiO₂ | 9.8 wt% | 15.6 | **0.922** | **0.955** |
| FeO_T | 11.4 wt% | 17.6 | 0.992 | **0.720** |

The SiO₂ ordering survives the table's uncertainty. **The FeO ordering does
not fully survive it**: with the glass/sheet-silicate group at nontronite-like
iron (30 wt%) the ranking reorders (0.72). FeO on Mars is the weaker of the
two by a clear margin, and the glass/clay iron content is the single value
that decides it. This is for Sherozbek's review; the table is a
construction, like the Earth 98-row table, and is tagged as such.

**Gates and measurements:**

| | mars_SiO₂ | mars_FeO |
|---|---|---|
| source cells kept | 45.0% of 1,036,800 (RMS 5.1%, dust 10.4%, thin 31.3% of valid removed) | same |
| HEALPix coverage | 49.03%; 7.1% at 85–90°S | same |
| copied from coarser | 71.1% of valid pixels (14.8 km source, 6.79 km pixel) | same |
| distinct levels / largest tie | 432,231 / 0.00017 | 460,507 / 0.00017 |
| p1 / p50 / p99 wt% | 38.1 / 54.8 / 61.9 | 1.8 / 6.6 / 33.4 |
| range gate, stated | [35, 70]: **7,177 outside**, counted not clipped | [0, 45]: **2,396 outside** |

The gate failures are real and explained: hematite (SiO₂ = 0, FeO_T = 90)
dominating the mineral sum in the Meridiani-type hematite terrains pulls
SiO₂ to 1.4 wt% and FeO to 88. They are not errors in the data; they are
the end-member table meeting a non-silicate surface. The gates were stated
as silicate bounds and the failures stay on the record rather than the
bounds being widened.

**What this dimension is worth, stated plainly:** areal end-member fractions
with a 0.10–0.15 detection limit, on warm dust-free surfaces only (49% of
the planet, 7% of the south polar band), at 2.2× the pixel size so 71% of
pixels are copies, through an ASSUMED table. Weak at the Mars end as the
lunar composition is weak at the Moon end — and FeO weaker than SiO₂.
Mars targets in dusty or polar terrain will carry no composition and fall
back to the shared-dimension rule (minimum 3, count recorded).

## (d) Declined sources, with reasons (Appendix D material)

| source | why not |
|---|---|
| OMEGA Ody et al. 2012 global maps, 40 ppd | band depths, not abundance; no Earth counterpart; the pyroxene index tracks grain size as much as abundance (Riu 2019) |
| OMEGA Riu et al. 2019 M3 vol% / oxide maps, 32 ppd | scientifically the best match, but every primary link is dead (IAS 410, PSUP down), 45% of 60S–30N only |
| CRISM MRDR v4 summary products, 181 m | indices not abundance; ~1 TB over 1,764 tiles |
| Odyssey GRS elements, 2–10° bins | true wt% but 300–600 km and ±45° |
| TES Dust Cover Index, 16 ppd | a dust-mantling index, not chemistry — a candidate Mars characterization layer, not built |
| THEMIS Day/Night IR mosaics | stretched 8-bit DN, not kelvin |
| THEMIS 100 m quantitative TI | numeric but 24 × 2.5 GB cubes for ±60° only, when TES at 3 km already bins |
| MCS, EMIRS surface temperature | degrees-scale bins |

## (a-cont.) Earth sky view factor, and the seam on Earth

| body | cell | bands | build | peak RAM | SVF p1 / p50 / p99 (global) | min |
|---|---|---|---|---|---|---|
| Earth | 0.927 km | 75 | 31.3 min | 3.65 GiB | 1.000 / 1.000 / 1.000 — the ocean is a flat surface by the sea rule | 0.672 |

Over the **reference population** (ice-free, water-free land), which is what
ranks: p1 0.850, p25 0.971, p50 0.991, p75 0.997, p99 0.9997, IQR 0.026;
0.06% of reference pixels sit at exactly 1.0. Range gate [0, 1]: 0 outside.
Coverage 100%, support constant 1.0.

Seam 78–80° on Earth: N pole median |diff| 0.0000, p95 0.0053, max 0.033,
r 0.996. S pole median 0.0000, p95 0.0008, **max 0.161, r 0.805**. The low
correlation is arithmetic, not disagreement: the Antarctic plateau is flat,
both methods return ~1.0 everywhere, so r is computed on noise; the one
0.16 outlier sits where the sea-surface rule meets the ice-shelf edge and
the area-averaging reprojection blends land and 0 m sea differently from
the 2×2 block mean. Recorded; it affects pixels outside the reference
population.

## (e) The B8 check on the whole set — and what it says about SVF

`build/dimension_check.py` (generalises the TPI-7 check; candidate lists
read from phase4a so they cannot disagree), on phase 4a's reference
population, 3,247,889 complete cases across the 13 Earth candidates on
disk (`thermal_inertia` absent, left out as phase 4a would).

| pairing | candidates | λ_min | eigenvalues < 0.10 | variance below floor |
|---|---|---|---|---|
| Earth–Moon | 10 → 12 | 0.0023 → 0.0022 | 3 → **4** | 0.30% → 0.57% |
| Earth–Mars | 6 → 10 | 0.0023 → 0.0022 | 3 → **4** | 0.52% → 0.71% |

Rank correlations of the new candidates with the rest, Earth reference:

| new | strongest |
|---|---|
| tpi_7km | tpi_21km +0.78; everything else under 0.11 |
| **svf_30km** | **roughness_5.25km −0.970, roughness_10.5km −0.969, roughness_21km −0.954, slope −0.954** |
| SiO₂ | roughness/slope −0.14; nothing else above 0.05 |
| FeO | nothing above 0.05 |

**The finding that matters:** on Earth land at this scale, sky view factor is
the roughness family with the sign flipped. ρ = −0.97 against 5.25 km
roughness means about 6% of its variance is its own. It adds a fourth
eigenvalue below the floor. This is the redundancy the decision set out to
remove, and SVF makes it slightly worse rather than better. Part F had
excluded illumination for being "strongly correlated with sky visibility";
the measurement now says sky visibility at 1 km / 30 km is itself strongly
correlated with roughness. The reason is physical: at a 30 km search radius
the horizon is set by the same relief that the 5–42 km roughness windows
measure. A 7 km radius SVF, or an SVF computed from the 463 m DEM, might
separate from roughness — neither is built.

Composition on Mars is the opposite case: SiO₂ and FeO are orthogonal to
everything on the Earth side (|ρ| ≤ 0.14), exactly the independent
information the decision asked for, with the Mars-side weaknesses stated
in (c).

**Recommendation to Sherozbek, his call:** keep `svf_30km` built and in the
manifest, but set `matching_eligible: false` with the measured −0.97 as the
reason and carry it as a characterization layer ("openness"), or keep it
ranking and let the eigenvalue floor absorb it. The honest statement for
the write-up either way: openness at 30 km on Earth is not independent of
roughness. The 12 / 10 counts above assume it stays in.

## (f) Validation

`build/cube_validate.py`: **PASS** after two corrections to the validator
itself — a stated gate failure that the builder recorded with its exact
count (`range_gate_pass: false`, `pixels_outside_stated_gate` equal to the
count on disk) is reported as a warning, because the validator's question
is whether the claim matches the disk and it does; and the pairing logic
now sees phases 2c, 3d and 3e. 61 manifest entries, 0 layer failures,
2 recorded gate failures (mars_SiO₂ 7,177 and mars_FeO 2,396 pixels,
hematite terrain, (c)), 0 orphans, 46 layers with provenance in 15 shared
arrays, Earth–Moon 12 and Earth–Mars 10 from the manifest flags alone.

Phase 4 and the null were NOT rerun. The stored results remain B24's,
computed on 10 / 6.

## (g) DECIDED: SVF stays a ranking dimension. Sherozbek, 2026-11-09.

The recommendation in (e) was to demote `svf_30km` to characterization on
the measured −0.97 rank correlation with roughness. Sherozbek chose to keep
it ranking. Earth–Moon 12 and Earth–Mars 10 stand as the decided sets; the
redundancy is handled where the method handles it, in the whitening with
the eigenvalue floor at 0.10 (four floored directions now, all in the
terrain family, holding 0.57% / 0.71% of the variance). The measurement
stays on the record: openness at 30 km on Earth is not independent of
roughness, and the write-up says so. No manifest or code change follows
from this decision; the counts in `cube_validate.py` already assume it.

## (h) DECIDED: Mars FeO kept with the ESTIMATE tag. Sherozbek, 2026-11-09.

The glass/sheet-silicate iron value stays at 5 wt% FeO, tagged ESTIMATE with its 2-30 wt% range, and `mars_FeO` stays in the Earth-Mars set. The measured consequence stands on the record: FeO ordering on Mars depends on that one value (rank correlation 0.72 against the iron-rich alternative), so Mars FeO is the weaker of the two composition dimensions and is to be quoted as such.


---

# §B28 — MARS SURFACE TEMPERATURE AT PIXEL SCALE, MODELLED. 2026-11-09, late.

**Method change, on Sherozbek's instruction** ("rovers sent to Mars will
spend years in this temperature"): the three Mars thermal layers now carry
pixel-scale values and rank. Earth–Mars 10 → 13 (14 with Earth apparent
thermal inertia): temperature level, diurnal range AND seasonal range, the
last because Earth already carried a seasonal range that paired with nothing
(the Moon has no seasons) and the intersection rule now pairs it with Mars. The MCD layers of the same names are overwritten; one
convention on disk.

## (a) Why a model, and why not the MCD

The 9 Nov source search (B27b) found no measured, gridded Mars
surface-temperature map at pixel scale. A second search closed the other
door: **the MCD's own design document (v6.1 §7.3.1) states that its
high-resolution mode does not change surface temperature** — it rescales
pressure only. Every MCD temperature at our pixel is an interpolation of the
5.6 × 3.75° model grid, whatever the setting. The literature's method for
this exact problem (Mellon 2000, Putzig & Mellon 2007, Fergason 2006,
Kieffer 2013) is a 1-D surface heat-balance model read through a lookup
table over thermal inertia, albedo, pressure, latitude, dust and season.
That is what was built. Every output is labelled MODELLED, NOT MEASURED, in
the manifest `status` field, in these words:

> Surface temperature fields are MODELLED, not measured. Computed with a
> one-dimensional surface heat-balance model (NumPy port of KRC one-point
> mode, Kieffer 2013) driven by TES thermal inertia (Putzig & Mellon 2007),
> TES albedo (Christensen 2001), MOLA-derived surface pressure, latitude and
> the Montabone et al. (2015) dust climatology. No spacecraft measured a
> gridded surface-temperature climatology at this resolution. Expected
> error: a few kelvin in the mean, larger in the diurnal range and near the
> seasonal CO₂ caps. Agreement with the MCD was checked only at its grid.

## (b) The model — `build/mars_thermal_1d.py`

KRC (Kieffer 2013) is public Fortran; no compiler exists on this machine
and the sandbox would not fetch one. So the one-point mode's physics was
ported to NumPy, vectorised over cases: KRC's soil (1600 kg m⁻³, 647 J kg⁻¹
K⁻¹, k = I²/ρc, 21 layers from 0.18 skin depths at ratio 1.2, insulating
base), explicit scheme at 384 steps per sol, KRC's "jump" after sol 3, run
to 0.1 K RMS or 15 sols; Keplerian orbit; one grey atmosphere layer with
delta-Eddington two-stream solar (ω 0.90, g 0.5, dust opacity scaling with
pressure) and an IR layer (0.25 τ dust + 0.11 gas at 546 Pa) whose
temperature obeys its own heat balance; CO₂ frost at the James et al. 1992
frost point on the local partial pressure, frost albedo 0.65, latent heat
589,944 J kg⁻¹. Not ported: temperature-dependent conductivity, two
materials, far-field slope radiation, twilight, ice clouds, atmospheric
condensation, the seasonal pressure cycle.

**Validation, target stated before the run** (median |ΔT| < 3 K, non-polar
max < 8 K): against KRC's own one-point reference output shipped in its
tree (`sources/krc/doc/prt/Mone.prt`, 23 cases — Viking landers, Arsia
Mons, a polar cap point, spin-up tests):

| | value |
|---|---|
| median \|ΔT\| | **1.36 K** |
| mean ΔT | −1.08 K (the port runs slightly cold) |
| max \|ΔT\|, non-polar | 2.63 K |
| polar cap case | +2.60 K |

PASS. Record: `cube/phase4/mars_thermal_1d_validation.json`.

## (c) The table — `build/mars_temp_table.py`

12 Ls × 20 TI (log 20–2500) × 7 albedo (0.10–0.40) × 7 elevation (−8..20
km → pressure) × 30 latitude (−87..87) × 5 dust (0.05, 0.15, 0.30, 0.60,
1.00 visible at 546 Pa) × 12 local times = 1.76 million model runs, 174
min. Flat surfaces (slope is not an axis — recorded). Convergence residual
stored per case: non-converged cases (RMS > 0.5 K in 15 sols) are 0.6–2% of
each chunk, almost all with CO₂ frost, where KRC's documentation says the
one-point mode is unreliable too.

Inputs fetched 9 Nov (public, no login, manifests beside them): TES
bolometric albedo 8 ppd (`sources/tes_albedo`; the product is clipped to
0.06–0.32 by its producers, 3.2% of cells at each bound, orientation checked
on Syrtis 0.11 / Tharsis 0.32); Montabone et al. 2015 v2 kriged dust
climatology, four storm-free years MY29–MY32 (`sources/dust_climatology`,
daily 3° maps of 9.3 µm absorption CDOD at 610 Pa, converted to visible at
546 Pa by ×2.6 × 546/610 — the 2.6 is ASSUMED, literature range 2.0–2.6, a
25% change moves the daily mean 1–2 K); KRC source and documentation
(`sources/krc`); Mars elevation binned to HEALPix (`mars_elevation`, pressure
input, never ranks).

## (d) The layers — `build/phase3f_mars_temperature.py`

Per pixel: multilinear interpolation of the table at the pixel's TI,
albedo (binned, 468,056 pixels copied from the 7.4 km source), elevation,
latitude and per-Ls dust. Definitions kept from the MCD layers so the
cross-body contract holds: level = mean over 12 Ls of the daily mean;
diurnal = mean over Ls of max − min over 12 local times (Earth 4, Mars 12,
Moon 96, unchanged); seasonal = max − min over Ls of the daily mean.

| | mars_temp_level | mars_temp_range_diurnal | mars_temp_range_seasonal |
|---|---|---|---|
| coverage | 99.361% (TI gaps; 56% at 85–90°S) | same | same |
| p1 / p50 / p99 (K) | 176.1 / 204.9 / 224.0 | 10.9 / 83.5 / 135.0 | 10.3 / 51.8 / 101.1 |
| range gate (the MCD layer's) | [120, 310] PASS | [0, 200] PASS | [0, 150] PASS |
| support | thermal-inertia support (p50 1.0, mean 0.93) | same | same |

Table-edge clipping: TI 15,541 pixels, elevation 6, latitude 341, dust 0
(the 0.05 level was added for this: before it 5.3 M season-cells sat below
the floor); albedo extrapolated below 0.10 on 7,529 pixels. Non-converged in
some season: 112,378 pixels (3.6%), flagged in `mars_temp_model_rms`;
CO₂-frost seasons per pixel in `mars_temp_frost_seasons`.

**Coarse-scale check against the MCD, which was overwritten** (both
averaged onto the MCD's 5.625 × 3.75° cells, 2,944 cells with ≥ 50 pixels):

| | mean diff | median \|diff\| | p95 | r |
|---|---|---|---|---|
| level | −0.69 K | 4.58 K | 11.7 | 0.976 |
| diurnal | +3.37 K | 5.23 K | 15.0 | 0.982 |
| seasonal | +5.90 K | 4.94 K | 16.2 | 0.978 |

A 1-D model with climatological dust against a GCM: agreement at r ≈ 0.98
with a few kelvin of bias is what the literature reports for this
comparison. Recorded on each entry under `superseded_mcd_layer`, with the
MCD layer's old validation numbers.

## (e) What the new layers measure, by rank correlation on Mars

Over pixels with all inputs: level vs |latitude| −0.80 (insolation);
diurnal range vs thermal inertia −0.61 and vs albedo +0.43 (the physics:
fine bright dust swings most); level vs slope +0.22, vs roughness_21km
+0.25, vs SVF −0.27. **The thermal family is not a copy of the terrain
family on Mars**, which is what the decision set out to get. On Earth's
reference population the two Mars-pairable thermal layers correlate with
terrain at |ρ| ≤ 0.33 (B8 check, `cube/phase4/dimension_check.json`);
Earth–Mars λ_min 0.0023 → 0.0022, floored directions 3 → 4, all still the
roughness family.

## (f) Validation and counts

`cube_validate.py` PASS: 0 layer failures, 0 orphans (the MCD provenance
array was removed and logged), 48 layers with provenance in 16 arrays.
**Earth–Moon 12, Earth–Mars 13** from the manifest flags alone. Phase 4 and
the null not rerun; B24's stored results remain for 10 / 6.

## (g) Honest limits, for the write-up

Modelled, not measured, with a 1 K cold bias against KRC and 5 K typical
disagreement with the MCD at coarse scale. Flat surfaces. One typical-year
dust climatology, not the observed year. Polar-cap edges unreliable. 3.6%
of pixels carry a convergence flag. The MCD layers, now gone, held 3,072
values for the planet; these hold a value per pixel driven by measured
thermal inertia and albedo — that is the gain, and the price is the word
"modelled" on every output.


---

# §B29 — EARTH APPARENT THERMAL INERTIA BUILT; the TI pairing measured. 2026-11-09, night.

Sherozbek downloaded ten MCD43A3 albedo months (Jan–May, Aug–Dec 2025;
June and July fail in GEE for the polar-night reason in HANDOVER §5 item 13
and need the fixed script in docs/DOWNLOADS §D). They were copied into
`sources/mcd43a3_albedo/` and `build/phase3e_earth_ati.py --allow-partial`
was run. **Partial record, stated:** ten months, not twelve; the manifest
entry carries `partial_record` and the month list. Rebuild when June and
July arrive.

| | earth_thermal_inertia (ATI = (1 − A)/ΔT, Price 1977) |
|---|---|
| albedo annual mean | 10 months, valid on 38.9% of 0.05° cells (land + sea ice) |
| ΔT | the 2025 four-local-time diurnal LST range, recomputed at 0.05°; floored at 1 K on 4,331 cells |
| coverage | 29.72% of the sphere (land); 100% at 85–90°S |
| p1 / p50 / p99 | 0.022 / 0.059 / 0.223 K⁻¹ |
| range gate (0, 1] | PASS |
| provenance | BINNED 3,632,815 · COPIED 106,960 · NO_VALID 8,537,382 · ABSENT 305,755 |

Validation PASS: 49 layers, 17 provenance arrays, **Earth–Moon 12,
Earth–Mars 14** from the manifest flags alone.

## The measurement that matters — the pairing is nearly circular

On Earth's reference population, rank correlation of `thermal_inertia`
(ATI) with `temp_range_diurnal` is **−0.960**. This is arithmetic, not
discovery: ATI = (1 − A)/ΔT, and albedo varies little in rank terms over
ice-free land, so ATI is close to the inverse rank of the diurnal range it
was built from. On Mars the partner is measured TES TI, but the Mars
diurnal range is now MODELLED from that TI (B28), so there ρ = −0.61. In
both pairings, thermal inertia and diurnal range carry largely the same
information. Earth–Mars λ_min 0.0023 → 0.0022, floored directions 3 → 5
(the roughness family plus this pair), variance below the floor 0.69%.

B23 predicted the quantity mismatch; the measurement adds a redundancy on
top. Options for Sherozbek: (1) keep `thermal_inertia` ranking and let the
eigenvalue floor absorb it, as decided for SVF in B27(g); (2) set
`matching_eligible: false` on the pair and carry Mars TES TI as a
characterization layer (measured, valuable for step 9) with Earth ATI
beside it. The 14 stands until he decides.

## DECIDED: thermal inertia stays a ranking dimension. Sherozbek, 2026-11-09.

Same reasoning as SVF in B27(g): the redundancy is handled where the method handles it, in the whitening with the eigenvalue floor at 0.10, now five floored directions holding 0.69% of the variance. The measured -0.96 between Earth apparent thermal inertia and Earth diurnal range stays on the record and in the write-up. Earth-Moon 12, Earth-Mars 14 stand. No code or manifest change follows; cube_validate already expects 14.

## B29 addendum — DECIDED: ten months is final. Sherozbek, 2026-11-09.

June and July cannot be exported from Google Earth Engine (polar-night tiles, the item-13 trap), so the Earth apparent thermal inertia built from Jan-May and Aug-Dec 2025 is accepted as final. Recorded on the manifest entry (`partial_record`). Consequence: the annual albedo under-weights northern summer; small for a rank transform, because albedo barely moves ATI's ordering (-0.96 with the diurnal range).

---

# §B30 — PHASE 4a–4c RERUN ON THE 12 / 14 CUBE. Smoke test, 2026-11-09, night.

Sherozbek's call: rerun the data-preparation phases now, leave the targets,
the null, selection, characterization and the weight check for the hackathon
team. Both scripts ran without error on the first attempt.

| | Earth–Moon (12) | Earth–Mars (14) |
|---|---|---|
| complete cases in the reference population | 3,244,963 of 3,260,787 (99.515%) | same |
| percentile IQR gate (B8, >= 0.15) | all PASS (0.49–0.52) | all PASS |
| lambda_min of the rank correlation | 0.0022 | 0.0022 |
| eigenvalues floored at 0.10 | 4 of 12, 0.574% of variance | 5 of 14, 0.690% |
| d_bar (median pairwise, 5,000 pixels) | 4.0303, seed spread 1.37% | 4.3501, seed spread 1.46% |
| DI threshold (95th pct within-reference NN DI) | 0.2394 | 0.2621 |

Against B24 (10 / 6): d_bar 3.72 → 4.03 and threshold 0.197 → 0.239 for
Earth–Moon, because distances grow with dimension count — the contract's
rule that DI figures are never comparable across different dims_used holds
here too. The floored directions are the roughness family plus the two
pairs recorded in B27(e) and B29 (SVF–roughness, ATI–diurnal range), as
decided. `cube/phase4/percentiles.npy`, `phase4a_summary.json`,
`phase4c_summary.json`, the whitening matrices and centres are now CURRENT
for 12 / 14. `phase4d_targets.json` and `phase5_null.json` remain B24's
10 / 6 results and must be regenerated on the day.


---

# §B31 — ANTARCTIC GEOLOGY AND THE CHECK OF THE COMPOSITION VALUES. 2026-11-10.

Sherozbek's call (10 Nov): fill in Antarctic geology, check the Earth
composition values, and do it before the hackathon. Engine work stays for the
day. Three things were built and one thing was found.

## (a) The lookup values were checked against one million analysed rocks

B16(e) left a debt: the lookup's weight percents carried `[UNVERIFIED-VALUE]`
because the publishers refused automated access. The check is now done against
Gard, Hasterok & Halpin (2019), 1,022,092 samples, 665,114 with usable SiO₂ and
430,750 with usable total iron (`build/gard_verify.py`,
`cube/gard_verification.json`).

**The rule was fixed before the database was opened**, and is in the script's
docstring: a value is VERIFIED when it lies inside the measured interquartile
range of the matching rock class, with at least 200 samples. A verified value
is kept. An outside value is reported; replacing it is a method decision.

| class | lookup SiO₂ | measured p25 / median / p75 | lookup FeO_T | measured p25 / median / p75 | n (SiO₂) | verdict |
|---|---|---|---|---|---|---|
| va acid volcanic | 72.5 | 66.3 / 70.3 / 74.2 | 2.10 | 1.74 / 2.92 / 4.21 | 69,748 | VERIFIED |
| vi intermediate volcanic | 58.5 | 53.8 / 56.2 / 59.3 | 6.20 | 5.53 / 7.08 / 8.87 | 112,242 | VERIFIED |
| vb basic volcanic | 49.5 | 47.9 / 49.5 / 50.6 | 10.20 | 9.36 / 10.70 / 11.90 | 176,366 | VERIFIED |
| pa acid plutonic | 71.5 | 67.6 / 71.1 / 73.9 | 2.70 | 1.39 / 2.22 / 3.40 | 75,566 | VERIFIED |
| pi intermediate plutonic | 57.5 | 54.6 / 57.7 / 60.5 | 6.60 | 5.18 / 6.44 / 8.08 | 35,262 | VERIFIED |
| pb basic plutonic | 48.5 | 47.3 / 48.9 / 50.3 | 9.40 | 8.04 / 10.08 / 12.18 | 32,760 | VERIFIED |
| py pyroclastics | 63.0 | 60.3 / 69.1 / 74.3 | 4.20 | 1.96 / 3.26 / 6.05 | 9,686 | VERIFIED |
| ss siliciclastic | 68.0 | 55.4 / 62.1 / 69.8 | 3.80 | 3.42 / 5.41 / 6.91 | 1,504 | VERIFIED |
| sc carbonate | 6.0 | 2.3 / 7.1 / 21.0 | 0.80 | 0.62 / 1.09 / 2.23 | 5,427 | VERIFIED |
| mt metamorphics | 64.0 | 48.6 / 57.6 / 69.1 | 5.40 | 3.48 / 6.54 / 10.35 | 48,468 | VERIFIED |
| su unconsolidated | 65.0 | 51.8 / 62.8 / 71.4 | 4.60 | 2.20 / 4.44 / 7.72 | 613 | VERIFIED |
| ssss coarse siliciclastic | 76.0 | 63.4 / 72.6 / 83.9 | 2.20 | 1.17 / 3.00 / 5.31 | 8,464 | VERIFIED |
| sssh fine siliciclastic | 60.0 | 48.9 / 60.8 / 67.8 | 5.20 | 2.81 / 4.73 / 6.91 | 8,365 | VERIFIED |
| **sm mixed sedimentary** | **45.0** | 2.4 / 7.5 / 20.4 | **3.10** | 0.96 / 1.62 / 2.84 | 1,018 | **OUTSIDE** |
| ev evaporites | 1.0 | 0.7 / 1.8 / 4.4 | 0.15 | 0.03 / 0.08 / 0.28 | 24 | no verdict (n < 200) |
| laterite, loess | 37.0, 63.0 | no samples under those names | 22.0, 4.70 | none | 0 | no verdict |

**13 of the 14 classes that could be tested are VERIFIED on both oxides.**
The check that does not use silica at all agrees too: rocks *named* basalt
measure 50.0 / 10.76 (lookup 49.5 / 10.20), andesite 58.7 / 6.35 (58.5 / 6.20),
diorite 57.3 / 6.71 (57.5 / 6.60), gabbro 48.9 / 10.17 (48.5 / 9.40).

**`sm` is the one miss, and the miss is in the comparison class, not obviously
in the value.** GLiM's `sm` is "sediments where carbonate is mentioned but not
dominant, plus sediments of unknown type" (B19e). The only names the database
offers for it are "marl" and "calcareous …", and rocks so named are
carbonate-dominated: they measure the same as limestone (7.5 against 7.1). So
the test compared a mostly-siliciclastic class with a mostly-carbonate sample.
The lookup's 45.0 sits between siliciclastic (68) and carbonate (6), which is
what "mixed" means. **The value is KEPT and stays rated HIGH uncertainty.
`sm` is 15.6% of ice-free land and is now the largest part of the lookup with
no independent support.** That sentence belongs in the write-up.

**Outcome: no GLiM value changed.** `sources/glim_composition_lookup_v2.csv`
carries the same 98 rows with the evidence beside each: sample count, measured
p25 / median / p75, verdict. The 80 model rows of B19 inherit their base's
verdict; their endmembers and pull weights remain this project's construction.

Two things this check does NOT establish. The database is where geologists
sampled, not an area-weighted crust. And for the six igneous classes the SiO₂
median is the middle of a range the class is *defined* by, so only their FeO_T
is an independent test; the named-rock rows above are the independent SiO₂ test.

## (b) Antarctic outcrop geology from SCAR GeoMAP

`build/geomap_antarctica.py`. Cox et al. (2023), 99,080 polygons at 1:250,000.
Same convention as B19's GLiM read, never a second one: categorical, so
**majority vote**, winning share stored as support. Polygons are rasterised at
100 m in EPSG:3031; each cell is weighted by its true ground area (1/k², the
polar stereographic area scale), not by its map area.

| gate, stated before running | result |
|---|---|
| G1 rasterised planar area within 2% of the polygons' own area | rock 1.0000, moraine 0.9999, ice 0.9995 — **pass** |
| G2 ~~every pixel with data lies south of 60°S~~ | ~~**FAILED** on the first run: northernmost pixel −53.96°~~ |
| G2 restated: every pixel with data lies south of 53°S | **pass** |
| G3 rock fraction ≤ 1.02 | max 1.0090 — **pass** |
| G4 analytic area scale = pyproj's to 1e-6 at three latitudes | **pass** |

**The G2 correction.** My premise was wrong, not the data: GeoMAP also maps
South Georgia (1,285 polygons, source Curtis 2011a, 54–55°S, 167 pixels). The
failed run wrote nothing. The gate was restated at 53°S and the first failure
is kept in `geomap_summary.json`.

The census matches the published figures exactly: 99,080 polygons; 41,648 km²
rock, 8,925 km² moraine, 1,007 km² seasonal water and ice. True (not planar)
area: 42,042 km² rock, 9,175 km² moraine.

Layers (Nside 1024, never ranking): `earth_geomap_lithcode` (winning rock
class), `earth_geomap_simpcode`, `earth_geomap_support`,
`earth_geomap_rock_fraction` (exposed rock + moraine as a share of the pixel).
**15,587 pixels get a rock class.** Median support 1.00, 10th percentile 0.60.

## (c) Earth composition rebuilt: one pixel, one source

`build/composition_earth.py`. The original builder was not on disk. The
re-implementation was first proved exact against the layers as they stood
(identical NaN pattern, maximum difference 0.0 over 3,352,458 pixels), then
extended.

**Rule, stated before running:** where GeoMAP names a rock class in a pixel,
GeoMAP is used; everywhere else GLiM. Never a blend.

The GeoMAP class table (`sources/geomap_composition_lookup.csv`, 25 rows) has
three kinds of row, fixed before any layer was built:

- **SAME-AS-GLIM** (19 rows): the class is the same rock as a GLiM row and
  takes its value, so the two maps speak one language. Each was checked to lie
  inside the measured interquartile range where the database has the class.
  All did.
- **MEAN-OF-GLIM** (4 rows): undifferentiated classes ("felsic to mafic
  volcanic") take the mean of the GLiM rows they span. One of the four, mafic
  to ultramafic intrusive (5 pixels), averages the GLiM gabbro row with the
  measured ultramafic median.
- **GARD-MEDIAN** (2 rows): quartzite 84.6 / 1.30 and metavolcanic
  49.7 / 10.10, which GLiM has no row for.

Antarctic samples in the database agree with the global values: felsic
intrusive south of 60°S measure 71.4 / 2.23 (lookup 71.5 / 2.70, n = 1,348);
mafic intrusive 50.0 / 9.98 (lookup 48.5 / 9.40, n = 1,340).

| measured on the built layers | before | after |
|---|---|---|
| pixels with composition | 3,352,458 | 3,354,807 |
| reference pixels with composition | 3,247,986 | 3,248,233 |
| reference pixels south of 53°S with composition | not counted | 4,914 of 4,991 (2,836 from GeoMAP, 2,078 from GLiM) |
| reference pixels whose value changed | | 2,046, median absolute SiO₂ change 8.1 wt% |
| pixels changed north of 53°S | | **0** |
| `distinct_levels` SiO₂ / FeO_T | 66 / 71 | 69 / 74 |
| `largest_tie_fraction` | 0.1167 | 0.1143 |

What changed on the ground, read from the layers:

| place | GLiM said | GeoMAP says | SiO₂ / FeO_T before → after |
|---|---|---|---|
| Wright Valley, Dry Valleys | mixed sediment, glacial | cover sediments, till (support 0.48) | 46.4 / 3.19 → 64.8 / 4.57 |
| Mount Erebus flank | basic volcanic | intermediate volcanic | 49.5 / 10.20 → 58.5 / 6.20 |
| Vestfold Hills | ice | gneiss (rock fraction 0.70) | none → 64.0 / 5.40 |
| South Georgia | ice | volcanogenic sediments | none → 64.7 / 4.64 |

A caution that belongs with the Dry Valleys row: the winner there is till on
the valley floor with a share of 0.48. The valley walls are dolerite,
sandstone and granite. A 6.4 km pixel takes one class; the support says how
much of the pixel that class is.

New layers: `earth_composition_source` (0 none, 1 GLiM subclass row, 2 GLiM
level-1 row, 3 GeoMAP) and `earth_composition_support` (the winning share of
whichever vote supplied the class). `provenance.py` now reads the latter.

## (d) Downstream, rerun the same evening

| | Earth–Moon (12) | Earth–Mars (14) |
|---|---|---|
| complete cases | 3,244,963 → **3,245,179** | same |
| eigenvalues floored | 4 → 4 | 5 → 5 |
| d_bar | 4.0303 → 4.0303 | 4.3501 → 4.3459 |
| DI threshold | 0.2394 → 0.2397 | 0.2621 → 0.2625 |

Nothing moved beyond the third digit, as a change to about 2,000 of 3.2
million pixels should. `cube_validate.py`: **PASS**, 0 failures, 0 orphans,
12 / 14. Regenerated: `CUBE_STATE.md`, the provenance arrays, the contract
examples (an Antarctic site now reports `lithology.source: "GeoMAP"`), the
website tiles, `contract/control_fixtures.json`, the atlas.

## (e) THE FINDING: the ice mask is wrong in Antarctica, in both directions

The reference mask calls a pixel ice-free where ETOPO surface minus bed is
thin (phase 1b). GeoMAP measures exposed ground directly. South of 60°S:

| | value |
|---|---|
| ice-free land by the mask | 148,098 km² |
| exposed rock + moraine by GeoMAP | 49,878 km² |
| reference pixels (mask > 0.5) | 3,155 |
| of those, pixels where GeoMAP finds any rock | 2,791 |
| median exposed-rock share in those | **about 8%** |
| pixels GeoMAP says are more than 50% exposed rock | 390 |
| of those, pixels the mask has in the reference population | 285 |

So the mask does two wrong things. It admits about 2,870 pixels that are
mostly ice with a nunatak in them. And it **leaves out 105 genuinely rocky
pixels**, among them the Vestfold Hills (mask 0.00, GeoMAP 0.70), one of the
best-known Antarctic oases.

**Nothing was changed.** The mask defines the reference population, the
percentiles and the whitening, so changing it is a method decision. It is
Sherozbek's. The numbers for it:

- **Option A — keep the mask.** No rerun. Antarctic "ice-free" pixels are
  mostly ice, their terrain and temperature values are ice-sheet values, and
  the Vestfold Hills cannot be found. `earth_geomap_rock_fraction` is shown on
  every Antarctic site so the reader sees it.
- **Option B — south of 60°S, define ice-free land by GeoMAP: rock fraction
  above 0.5.** 390 pixels replace 3,155. Removes about 2,870, adds 105. That
  is 0.09% of the reference population; the phase 4a–4c rerun takes minutes.
  It matches the decision already taken ("exposed rock, not the ice sheet").
- **Option C — the same at rock fraction above 0.25:** 1,264 pixels (631
  already in). More sites, each up to three-quarters ice.

**Recommendation: B.** It is the only one of the three where "an Antarctic
analog site" means rock a rover could stand on.

## (f) Also written on 10 Nov — documents, not results

`contract/` frozen at 2.0 (per-group distances, worst group, click payload,
presets); `export/site_assets/` (six display layers per body in three views,
basemaps, three catalogues as GeoJSON); `docs/TEST_SPEC_2026-11-10.md`
(load tests, 25 property tests, the two controls with fixed pixels and pass
criteria written in advance, three open decisions);
`docs/NULL_TABLE_DESIGN_2026-11-10.md`; `docs/TEAM_PLAN_2026-11-10.md`.
No distance, DI or p-value was computed. `phase4d_targets.json` and
`phase5_null.json` are still B24's 10 / 6 prototypes.

## (g) DECISION on (e): option B — taken by Sherozbek and built, 10 Nov 2026, late

Sherozbek chose option B ("Yes, use GeoMAP"). South of 60°S the reference
mask is now the exposed rock + moraine share of the pixel measured by SCAR
GeoMAP. North of 60°S nothing changed. ~~"Nothing was changed"~~ in (e)
describes the state before this decision.

**One builder.** `build/reference_mask.py` writes the mask and its manifest
entry with both rules. `phase4a_percentile.py` used to bin the mask itself
when the file was missing; it now refuses and names the builder, because a
silent rebuild there would drop the Antarctic rule. The after-the-fact mask
block in `record_auxiliary.py` is disabled for the same reason.

| gate, stated before running | result |
|---|---|
| G1 the 8 Nov construction is reproduced exactly north of the rule | max difference 0.0 — **pass** |
| G2 south of 60°S the population is exactly GeoMAP rock fraction above 0.5 | **pass** |
| G3 no pixel north of 60°S changes membership | **pass** |

| | before | after |
|---|---|---|
| reference pixels, whole Earth | 3,260,787 | **3,258,022** |
| reference pixels south of 60°S | 3,155 | **390** (285 kept, 105 added, 2,870 removed) |
| area of those pixels | 127,892 km² | 15,809 km² |
| complete cases (all 14 dimensions) | 3,245,179 | **3,242,477** |
| eigenvalues floored, Earth–Moon / Earth–Mars | 4 / 5 | 4 / 5 |
| d_bar Earth–Moon (five-seed range) | 4.0303 (4.026–4.065) | 4.0548 (4.026–4.065) |
| d_bar Earth–Mars (five-seed range) | 4.3459 (4.316–4.359) | 4.3526 (4.320–4.373) |
| DI threshold Earth–Moon / Earth–Mars | 0.2397 / 0.2625 | 0.2380 / 0.2613 |

The single-seed d_bar moved by 0.6% on Earth–Moon while its five-seed range
did not move. That is the 5,000-pixel subsample landing on different pixels
once the population changed size, not a change in the population itself.

What the 390 Antarctic pixels are, measured:

- **373 of 390 are complete in all 14 dimensions.** 10 lack the temperature
  layers and 17 lack thermal inertia (no usable albedo or land-surface
  temperature there).
- **19 of 390 have no Köppen class**; the Köppen footprint does not reach
  them. Reference pixels with a class: 99.9994%, no longer 100%. Step 9
  reports "no class" for these and does not guess one.
- The Dry Valleys stay in (rock fraction 0.86). The Vestfold Hills are now in.

**The limit that goes in the write-up.** GeoMAP maps 49,878 km² of exposed
ground south of 60°S. Only 10,966 km² of it, 22%, lies in pixels that are more
than half rock. The rest is nunataks and ridges smaller than a 6.4 km pixel.
The method can find the large Antarctic oases and cannot find a small one.
Option C (rock fraction above 0.25, 1,264 pixels) would trade that for sites
that are up to three-quarters ice; it was not taken.

The 8 Nov mask is kept as a copy in `cube/_work/reference_mask_before_B31e/`.
It is not part of the cube. `cube/mask_provenance.json` records both counts.

A power cut interrupted the whitening rerun (`phase4c_di.py`) half-way: the
Earth–Moon matrices were rewritten and the Earth–Mars ones were not. Every
file written before the cut was reloaded and checked, then `phase4c_di.py`
was rerun in full. `cube_validate.py`: **PASS**, 0 failures, 12 / 14.
Regenerated after the mask change: Köppen and composition reference
statistics, `dimension_check.json`, phase 4a and 4c outputs, `CUBE_STATE.md`,
`contract/control_fixtures.json`, the contract examples, the website tiles,
the atlas and the rev 9 specification.


---

# §B32 — THE PRESET TARGETS AND THE THREE TEST DECISIONS. 2026-11-10, late.

Sherozbek handed these over ("can you do them by yourself"). Everything here
is a pixel set or a rule. No distance, DI or p-value was computed.

## (a) The nine Artemis III regions — published polygons, not proxies

Until today each region was a 15 × 15 km disc at the IAU centre of the feature
it is named after (`sources/artemis3_regions.csv`, B24), and said so. That file
is kept and superseded.

**Source found:** LROC QuickMap publishes the nine regions of NASA's 28 October
2024 update as polygons: layer "A3: Candidate Landing Regions 2024", file
`A3_9regions-lonlat-simplified.geojson`, 3,545 bytes, Last-Modified 28 Oct
2024. Copy in `sources/artemis3_regions_2024/` (MD5
9d7a9b2c296dca3da3c4ba8463f7027e), with the 2022 thirteen-region file beside
it. NASA's own release carries a map image and no coordinates. The file states
no licence. It is not hosted on nasa.gov.

**Gate, stated before running** (`build/targets_moon_csv.py`): in south polar
stereographic every region must be an axis-aligned rectangle whose area equals
the file's own `Area_km2` to 0.1%. **All nine pass.** That is also the proof
that the edges are straight in that plane, so `build/targets.py` rebuilds them
there, not in longitude / latitude.

| region | centre lat | centre lon | size, km | cells | old proxy was off by |
|---|---|---|---|---|---|
| Peak near Cabeus B | −83.64 | −68.75 | 20 × 20 | 7 | 67 km |
| Haworth | −86.76 | −22.78 | 29.8 × 29.8 | 15 | 34 km |
| Malapert Massif | −85.99 | −0.24 | 21 × 21 | 6 | 3 km |
| Mons Mouton Plateau | −84.33 | 30.59 | 76.9 × 57.9 | 90 | 8 km (and it shared its point with Mons Mouton) |
| Mons Mouton | −85.43 | 31.74 | 16 × 16 | 5 | 25 km |
| Nobile Rim 1 | −85.44 | 37.35 | 20 × 20 | 9 | 39 km |
| Nobile Rim 2 | −83.95 | 58.82 | 20 × 20 | 10 | 43 km |
| de Gerlache Rim 2 | −88.23 | −64.63 | 20 × 20 | 7 | 22 km |
| Slater Plain | −87.16 | 125.54 | 20 × 20 | 7 | 33 km |

The last column is the great-circle distance between the old proxy centre and the published region centre, measured.

What this fixes from B24:

- **The two collapses are gone.** B24 had Mons Mouton and Mons Mouton Plateau
  on one coordinate, and Nobile Rim 1 and Rim 2 on another. They are now four
  different pixel sets. Nine regions, nine targets.
- **NASA's "about 15 by 15 km" does not describe these polygons.** They are
  16 to 30 km squares and one 77 × 58 km plateau. The old disc had the wrong
  size as well as the wrong place.
- Every cell of every region carries all 12 dimensions. k = 5 for all nine.
- Two overlaps remain and are real: the Plateau shares 3 cells with Mons
  Mouton, and Mons Mouton shares 1 with Nobile Rim 1. They are recorded in
  `contract/targets_moon.json`. Results for those pairs are not independent.

**One convention for "which pixels":** a pixel belongs to a target when its
centre is inside the region. The 9 Nov prototype did this; the contract
example used "any overlap" and got twice as many cells. Both now read
`contract/targets_moon.json`.

## (b) Six Mars targets — NASA's Exploration Zones

**Source:** NASA's 2015 workshop on human landing sites (LPI, Houston). Teams
proposed Exploration Zones. NASA's definition, read in the First Announcement:
a collection of regions of interest "within approximately 100 kilometers of a
centralized landing site". 44 proposals with coordinates are in
`sources/mars_site_candidates_v1.csv`, with the seven SpaceX / JPL candidate
sites of Golombek et al. (2021) and nine landed or selected missions.

**Geometry: nothing invented.** Each target is a disc of NASA's own 100 km
radius, centred where the proposing team wrote its centre. About 680 cells.

**Choice of six, by source, written down before any distance exists:**

- **A. Every 2015 zone inside which a rover has since driven.** Four.
- **B. One zone in each of the two mid-latitude ice provinces that drew
  several independent proposals.** Erebus Montes, because the 2021 SpaceX / JPL
  prime site EM-16 lies inside it; Deuteronilus Mensae, the proposal that
  states an explicit centre.

Data coverage was not a criterion. It was measured afterwards:

| target | centre (lat, lon E) | abstract | rover or later site inside | cells | cells with composition |
|---|---|---|---|---|---|
| Jezero crater | 17.747, 77.037 | 1034, Mustard | Perseverance, 47 km from centre | 680 | 553 (81%) |
| Gale crater | −4.5965, 137.4019 | 1020, Calef | Curiosity, 2 km | 681 | 188 (28%) |
| Meridiani Planum, Endeavour | −3.174, 355.483 | 1057, Clarke | Opportunity landed 94 km away, drove to Endeavour | 682 | 596 (87%) |
| Gusev crater | −14.5, 175.4 | 1008, Longo | Spirit, 6 km | 683 | 105 (15%) |
| Erebus Montes, Arcadia | 39.0, 192.1 | 1011, Viola | SpaceX / JPL prime site EM-16, 53 km | 684 | 17 (2.5%) |
| Deuteronilus Mensae | 39.11, 23.199 | 1033, Head | none; radar-mapped glacier ice | 680 | 271 (40%) |

The six centres were read in the abstract text twice (the research pass, then
a search of the saved extracts, kept in `sources/mars_ez_2015/`).

**The consequence, and the rule that follows.** Composition is patchy on Mars:
dusty ground is masked, and that is where the ice sites are. No zone has it on
90% of its cells. So:

> **Every Mars preset runs on two constructions.** PRIMARY: terrain + thermal,
> 12 dimensions, over every cell of the zone. All six are then comparable with
> each other. SECOND: all 14 dimensions, over the cells that have composition.
> The difference between the two is printed.

This is invariant 3 of the spec ("no result from a single construction")
doing real work. It also means a third dimension set. `phase4c_di.py` now
calibrates it as `earth_mars_no_composition`:

| dimension set | dims | floored | d_bar | DI threshold |
|---|---|---|---|---|
| earth_moon | 12 | 4 | 4.0548 | 0.2380 |
| earth_mars | 14 | 5 | 4.3526 | 0.2613 |
| **earth_mars_no_composition** | **12** | 5 | **3.8198** | 0.2418 |

Three sets, three whitening matrices, three d_bars, three nulls. A DI from one
is never compared with a DI from another. Mars pixels complete in the 12:
3,125,612 of 3,145,728. Complete in all 14: 1,539,882.

**Limits to state.** (1) A Mars target is a ZONE, 31,416 km², larger than any
Artemis region (the largest is 4,452 km²). It holds crater floor, rim and
plains together, so it is easier to match than a small region; the null draws
equally large patches, which keeps the test fair but not the map sharp.
(2) No abstract says whether its latitude is planetocentric or planetographic.
The two differ by at most 0.33° (about 20 km) at 39°N. Recorded, not corrected.
(3) For Erebus the 14-dimension construction rests on 17 cells, 2.5% of the
zone. It is reported, and it says nothing about the zone as a whole.

## (c) The three test decisions

Taken as recommended, before any distance exists. Full text in
`docs/TEST_SPEC_2026-11-10.md` section 6.

1. **The Apollo control is measured against the six Apollo landing sites.**
   The same statistic against the nine Artemis regions is reported beside it
   with no pass mark.
2. **A Mars target without composition runs on 12 dimensions and says so.**
   Never refused. Presets run both constructions, as in (b).
3. **One line for significance: p < 0.05.** p is always printed. No
   "marginal" band.

## (d) Where things are

`contract/targets_moon.json`, `contract/targets_mars.json` (pixel sets,
coverage, both constructions, sources) — written by `build/targets.py`.
`export/site_assets/catalogue/targets_*.geojson` for the website.
The negative control (coldest lunar patch) shares no cell with any region; it
lies on the floor of Haworth crater, 19 km outside the "Haworth" region, which
is on the rim. `cube_validate.py`: PASS.


---

# §B33 — ONE POOLED SCALE PER VARIABLE. Sherozbek's decision, 2026-11-11.

**This changes step 3 of the method. It supersedes per-body ranking
everywhere the method compares two bodies.**

## (a) The decision, in his words

"I want one combined scale as main result and the only result." One scale per
variable, for the Earth–Moon system and the Earth–Mars system separately.

His reason, as an example: 40 units is the 95th percentile on Mars and 50 is
the 95th on Earth. With separate scales the Mars place is matched to the Earth
place at 50, and the Earth place that really is at 40 is ranked as a worse
match. Separate scales answer "does this place play the same role on its own
world". He wants "is this place physically alike".

## (b) What separate scales were doing — measured on the cube

Raw values, reference population on Earth, every finite cell on the body:

| variable | Earth p1 / median / p99 | Moon p1 / median / p99 | chance a Moon cell is above an Earth cell |
|---|---|---|---|
| slope, degrees | 0.01 / 0.39 / 7.45 | 0.12 / 3.60 / 16.20 | 0.85 |
| roughness 21 km, m | 1.4 / 35 / 563 | 15 / 356 / 1252 | 0.88 |
| roughness 42 km, m | 2.5 / 52 / 722 | 28 / 543 / 1655 | 0.90 |
| sky view factor | 0.85 / 0.99 / 1.00 | 0.80 / 0.94 / 1.00 | 0.18 |
| SiO₂, wt% | 4.8 / 64.0 / 87.0 | 30.6 / 43.3 / 54.2 | 0.19 |
| FeO, wt% | 0.62 / 3.80 / 10.20 | 2.14 / 5.50 / 23.98 | 0.77 |
| temperature level, K | 258 / 293 / 307 | 151 / 233 / 245 | **0.00** |
| diurnal range, K | 3.7 / 13.6 / 30.5 | 182 / 283 / 301 | **1.00** |

The last column is 0.5 when the two bodies are fully mixed and 0 or 1 when
they do not overlap at all.

- **Terrain.** The median lunar cell is ten times rougher than the median
  Earth cell at 21 km. Separate scales paired them. For a rover test that is
  the wrong ground.
- **Composition.** Median lunar silica is 43% (basalt-like). Its rank mapped
  to Earth's median, 64% (granite-like). The wrong rock.
- **Temperature.** No overlap at all, for the Moon and for Mars (Mars
  temperature level 176 / 205 / 224 K). Separate scales hid this completely.
  Mars terrain, by contrast, overlaps Earth's almost fully (chance 0.56–0.64).

## (c) The transform

For one variable and one pairing, with Earth values E (reference population,
complete cases) and body values B (every finite cell):

    F_E(x) = share of E below x, ties counted as half
    F_B(x) = the same for B
    p(x)   = 0.5 · F_E(x) + 0.5 · F_B(x)      the pooled position, 0..1
    z(x)   = inverse normal of p(x)           the normal score

One function of the physical value, applied to both bodies. Two cells with the
same physical value get the same z whichever body they are on.

- **Equal weight per body.** Earth has 3.2 million cells and the Moon 0.8
  million. Pooling by cell count would let the grid sizes set the scale.
- **The normal score.** The spec has always said z = Φ⁻¹(p) in step 3. The
  calibration built on 9–10 Nov stopped at the percentile; HANDOVER marked
  the step done. That gap is closed here.
- **It stays a rank transform.** Outliers and skew still cannot dominate, and
  ties still share one value. What changed is whose ranks.

`build/phase4b_pooled_scale.py`. Gates, stated before running, all pass for
all 25 variable–pairing combinations that were pooled:

| gate | result |
|---|---|
| G1 both layers carry the same unit | 12 of 12 Moon, 13 of 14 Mars; **thermal inertia refused** |
| G2 0 < p < 1, every z finite | pass |
| G3 z never decreases when the value increases | pass |
| G4 mean p over Earth + mean p over the body = 1 (an identity of the equal-weight pool) | 1.0000000 on every variable |

## (d) Thermal inertia leaves the ranking

Earth's layer is APPARENT thermal inertia, (1 − albedo) / diurnal range, in
K⁻¹. Mars's is TES thermal inertia in tiu. They are different quantities and
cannot share an axis. Asked directly, Sherozbek chose to drop it from ranking
rather than keep one variable on per-body ranks.

- Earth–Mars: 14 → **13** dimensions. Without composition: 12 → **11**.
- Both layers stay as characterization, shown per site.
- Little is lost: on Earth it is −0.96 with diurnal range, which stays.
- This reverses "keep thermal inertia ranking" (B29) for a reason that did
  not exist then. B29's measurements stand.

## (e) Steps 3 and 4 rebuilt

`phase4a_percentile.py` → `phase4b_pooled_scale.py` → `phase4c_di.py`.

| dimension set | dims | complete Earth cells | floored | d_bar (five-seed range) | DI threshold |
|---|---|---|---|---|---|
| earth_moon | 12 | 3,245,417 | 4 | 3.9922 (3.988–4.028) | 0.2646 |
| earth_mars | 13 | 3,245,417 | 4 | 4.2396 (4.225–4.252) | 0.2680 |
| earth_mars_no_composition | 11 | 3,245,417 | 4 | 3.7353 (3.719–3.747) | 0.2433 |

Complete cases rose from 3,242,477 because thermal inertia is no longer
required. Whitening is still Earth's correlation matrix with the 0.10 floor,
now measured in pooled-z space.

Files the engine reads, all in `cube/phase4/`:
`pooled_z_earth_<body>.npy` (Earth, per pairing), `pooled_z_<body>.npy` (the
target body), `whiten_<set>.npy`, `center_<set>.npy`, `phase4c_summary.json`.
`pooled_scale_<body>.npz` converts a single value for a cell outside the
stored arrays. **`percentiles.npy` is now DIAGNOSTIC ONLY** (per-body ranks,
for the Spearman redundancy check). The engine must never read it.

## (f) What the pooled scale shows — one real example

The Dry Valleys (Wright Valley cell) against the Haworth region, values read
from the cube, positions on the pooled scale:

| variable | Earth | target | pooled gap | verdict |
|---|---|---|---|---|
| slope | 7.80° | 7.53° | +0.007 | agrees |
| roughness 5.25 km | 348 m | 243 m | +0.074 | agrees |
| roughness 21 km | 531 m | 734 m | −0.078 | agrees |
| roughness 42 km | 490 m | 1275 m | −0.264 | differs |
| temperature level | 246 K | 129 K | +0.497 | differs |
| diurnal range | 3.1 K | 161 K | −0.499 | differs |
| SiO₂ | 64.8% | 46.1% | +0.298 | differs |

Slope agrees because it IS the same slope. Temperature differs because it is
116 K apart. Under separate scales the earlier example of this pair (10 Nov,
old target disc) read "agrees" on temperature level.

## (g) Consequences to state in the write-up

1. **Earth has no thermal analog for the Moon or Mars, and the method now
   says so.** Every Earth cell sits on one side of every target cell. The
   thermal group still ranks Earth sites (the coldest Earth cell is the
   nearest), but its distance is never small. This is the "Earth's limits"
   point of the challenge, now measured instead of asserted.
2. **A gap is bounded.** The pooled position runs 0..1, so two non-overlapping
   bodies are at most about 0.5 apart on a variable. The thermal group cannot
   swamp terrain without limit; it is a transform property, not a tuning.
3. **Instrument differences now count as physical differences.** Earth's
   diurnal range comes from four satellite overpasses, the Moon's from a full
   diurnal curve, Mars's from a model. Separate scales absorbed that. The
   pooled scale does not. For temperature the gap is so large that it does not
   matter; for a future variable with a small gap it would.
4. **The verdict thresholds (agrees below 0.10, differs above 0.25) now mean
   something physical.** They were not re-tuned.
5. The per-group display matters more than before: terrain and composition
   say where the match is; thermal says there is none.

## (h) Changed with it

Contract **2.1**: `run.scale = "pooled"` is required; `earth_percentile` and
`target_percentile` are positions on the pooled scale; examples regenerated.
`contract/targets_mars.json`: constructions are now 11 and 13 dimensions.
`contract/control_fixtures.json` regenerated. `cube_validate.py` expects
12 / 13 and passes. The test specification and the null-table design carry
the new sets. ~~The method spec docx (rev 9) still describes per-body ranking in
its step 3 text; this section governs until the document is revised.~~
**Revised the same day:** `docs/analog_finder_method_spec_rev10.docx`
(`build/spec_rev10.py`) carries a "Revision 10" block at the head of step 3.

## (i) What the spec had said about pooling — found while revising it

Revision 8's step 3 has a section "Why per body, and not pooled together".
It calls pooling "a real option and it is tempting" and rejects it for two
reasons it calls fatal: per-body ranking cancels instrument bias while
pooling turns that bias into a fake finding; and pooling needs a mixing
weight "nobody can justify". When Sherozbek asked what the file said, he was
told only that it ranked per body. He was not told that it had weighed
pooling and argued against it. That was an omission in the answer he got
before deciding; it is recorded here and he was told on 11 Nov.

The decision stands on the measurements in (b). Revision 10 answers both
objections in the open: instrument bias is accepted as a stated cost
(consequence 3 above); the mixing weight is one half per body, a choice,
written down so it can be challenged, and the only setting that does not
depend on grid size. Revision 8's own step 3 also asks for a per-variable
overlap figure and keeps the raw cube so the transform can be re-run
"as z-score, min-max or pooled"; both are now delivered.


---

# §B34 — STEP 4 REBUILT GROUP-WISE, AS THE SPEC DECIDES. 2026-11-11.

## (a) The mismatch

The spec's step 4 ("The group-weight conflict") decides **block-diagonal
whitening**: terrain variables are decorrelated among themselves, thermal
among themselves, composition among themselves, and correlation between
groups is left alone. Its reason: after a joint whitening every axis is a
blend of all variables, so no difference can be assigned to a group, and
group weights cannot be applied.

`phase4c_di.py` whitened all dimensions of a set **together**, from its first
run (B24) to this morning. Nothing recorded that as a decision; it was never
checked against step 4. The output contract's per-group index, "worst group"
and the four presets all assume the groups are kept apart, so the joint
matrices could not serve the engine. Found on 11 Nov while explaining step 4;
Sherozbek confirmed the rebuild.

This is the second gap of this kind (the first was the missing normal score,
B33c). Both were found by reading the spec section before explaining it.

## (b) What is built now

For a set, with pooled normal scores z (B33):

    u   = (z − Earth mean) / Earth sd
    v_g = u_g · W_g          W_g = inverse square root of group g's Earth
                             correlation matrix, eigenvalues floored at 0.10
    d_g = distance in group g's columns
    d   = sqrt( Σ_g  w_g · d_g² )

`whiten_<set>.npy` is the block-diagonal matrix of the W_g. With every weight
1 the combined distance is one matrix product and one Euclidean distance, as
before. That is the spec's "run A" (step 10).

- **The floor, not a ridge.** The spec's step 4 text says "add a small ridge".
  B8 (accepted 6 Nov) chose the eigenvalue floor at 0.10 and the Revision 9
  block cites it. The floor stands; it is applied inside each group.
- **Presets are group weights**: balanced 1 / 1 / 1; mobility terrain 2;
  thermal 2; geology composition 2. Only ratios matter, because a DI divides
  by the d_bar computed with the same weights.

| | Earth–Moon (12) | Earth–Mars (13) | Earth–Mars, no composition (11) |
|---|---|---|---|
| floored eigenvalues, terrain / thermal / composition | 4 / 0 / 0 | 4 / 0 / 0 | 4 / 0 / — |
| d_bar, all weights 1 | 4.0088 | 4.2292 | 3.7262 |
| the same under joint whitening (this morning) | 3.9922 | 4.2396 | 3.7353 |
| d_bar terrain / thermal / composition | 2.8342 / 1.7291 / 1.6830 | 2.8367 / 2.1808 / 1.6887 | 2.8427 / 2.1714 / — |
| d_bar mobility / thermal / geology | 4.9489 / 4.4369 / 4.4361 | 5.1342 / 4.8207 / 4.6376 | 4.7178 / 4.3715 / — |
| largest correlation left between groups | 0.23 | 0.29 | 0.29 |
| DI threshold | 0.2628 | 0.2654 | 0.2430 |

**d_bar moved by under 0.5%.** The groups are only weakly correlated with each
other (at most 0.29), so leaving that correlation alone costs almost
nothing. The spec predicted this ("a sparse structure, where block-diagonal
whitening is exactly right"). All four floored directions are in terrain: the
slope-and-roughness family.

## (c) What "balanced" means, measured

With every group weight 1, the squared distance between two Earth cells
splits as:

| | terrain | thermal | composition |
|---|---|---|---|
| Earth–Moon | 55% | 23% | 23% |
| Earth–Mars | 49% | 30% | 21% |
| Earth–Mars, no composition | 62% | 38% | — |

Terrain carries about half. It has eight variables, but after whitening they
are worth about four independent directions, against two or three for thermal
and two for composition. So "balanced" is equal WEIGHT per group, not equal
INFLUENCE per group. That is what the spec's step 10 defines (run A, all
weights 1) and tests (terrain doubled). It is recorded here because the phrase
"equal weight on every variable group" can be read either way.

This is among Earth cells. For a Mars target the picture differs: B33's
diagnostic found 96% of the offset between a typical Mars cell and Earth's
centre is thermal. Both statements are true; one is about how Earth varies,
the other about where Mars sits.

## (d) Changed with it

`cube/phase4/whiten_*.npy`, `center_*.npy`, `phase4c_summary.json` (now with
`groups`, `d_bar_by_preset`, per-group d_bar). Test specification: load-test
numbers and three new distance tests. Contract descriptions: d_bar is the
MEAN pairwise distance (the text said median; the code and Meyer & Pebesma
use the mean) and is per preset. Spec revision 10: a step 4 block.
The joint summary is kept in `cube/_work/phase4c_summary_joint_before_B34.json`.


---

# §B35 — THE WEIGHT CHECK AND THE PRESETS ARE REMOVED FROM VERSION 1. Sherozbek's decision, 2026-11-11.

## (a) The decision

Reviewing the animated explainer, Sherozbek asked: "what if we skip the
weights part ... remove it from the whole architecture and propose all
sensitivity analysis as future steps". Asked whether that meant the step 10
weight check alone or the four weight presets as well, he chose both.

- **Step 10 (the weight check) is not built.** No second run with terrain
  doubled, no rank interval, no weight-sensitive flag.
- **The four presets are gone** (balanced, mobility, thermal, geology).
  Every group counts with weight 1. One target and one dimension set give one
  result.
- **All sensitivity analysis is future work**, named so it is not forgotten:
  the group weights; the half-and-half pooling weight of B33; and the number
  of nearest target cells (5), which is under 1% of a 680-cell Mars zone.

This reverses "presets, not sliders" (10 Nov) and removes what B34 stored per
preset. B34's group-wise whitening stands: the per-group index and "worst
group" need the groups apart and need no weights.

## (b) What it costs, stated plainly

- **The spec's third invariant is relaxed.** "No result is reported from a
  single construction" no longer holds for a lunar target, which now has one.
  A Mars preset target keeps two, with and without composition (B32b), but
  that is a data-coverage question, not a weighting one. Revision 10 of the
  spec says so at the invariant itself.
- **"Every group counts once" is a choice whose effect is unmeasured.** B34(c)
  measured what it means between Earth cells: terrain about half, thermal and
  composition a quarter each. How much the site list would move under other
  weights is not known. That sentence belongs in the limits of the write-up.

## (c) What it saves

One calibration constant per dimension set instead of four. A smaller output
contract. A null table of 84 distributions instead of 336. One fewer step to
build and test on the hackathon day.

## (d) Changed with it

| where | change |
|---|---|
| `build/phase4c_di.py` | presets removed; d_bar and thresholds are IDENTICAL to B34 (checked: equal to the last digit) |
| `contract/` | **2.2**: `run.preset`, `groups.*.weight`, `rank_alt`, `rank_interval`, `weight_sensitive` removed from both schemas; examples regenerated and valid |
| `docs/TEST_SPEC_2026-11-10.md` | tests on presets removed; a section "Removed on 11 November"; the combined distance is the plain distance between whitened vectors |
| `docs/NULL_TABLE_DESIGN_2026-11-10.md` | the preset axis is gone: 3 sets × 7 bands × 4 sizes = 84 |
| `docs/analog_finder_method_spec_rev10.docx` | a Revision 10 block at step 10, at the third invariant, and in step 4; decisions log updated |
| the animated explainer | version 2 already has no weights chapter; its last beat names weight checks as later work |

---

# §B36 — RANK ONLY ON WHAT EARTH CAN MATCH; EVERY TARGET CELL COUNTS; PERCENTILE BANDS; TWO SITE RULES. Sherozbek's decisions, 2026-11-11.

## (a) The decisions, in his words

Asked whether to rank on overlap, he answered: "yes, we should rank on
overlap, percentile bands on the map, and all cells instead of 5. And at the
same time, we should give percentile based live and dynamic map."

On the site list he proposed a slider for the top X% with no autocorrelation
("pretty deterministic option with user autonomy"). Asked to choose, he said:
"Let's do both patches of top X% and autocorrelation. I mean we would test and
find the best one in the day of hackathon. And maybe there are even more
things that would be better to decide during the hackathon day."

Four changes follow. All are calibration, contract and specification. No
distance from an Earth cell to a target, no DI map, no p-value and no site
was computed.

## (b) Rank only on what Earth can match

**The rule.** For one target and one variable, take the median of the
target's cells in physical units. If it lies outside the whole range (minimum
to maximum) of Earth's reference population, the variable is REPORTED as one
of Earth's limits, with the gap in its own unit, and LEFT OUT of every
distance for that target. No parameter. `out_of_range()` in
`build/ranking_sets.py`.

**Why.** A variable no Earth cell reaches adds a large distance to every
Earth cell. It cannot say which site is the better match. With no group
weights (B35) it would push every ranking the same way.

**Result on the presets** (`contract/targets_ranking.json`):

| targets | ranked | Earth's limits |
|---|---|---|
| nine Artemis III regions | 10: terrain 8, SiO2, FeO | temperature level 127–181 K (Earth's coldest reference cell 232.14 K); day–night range 161–210 K (Earth's largest 44.00 K) |
| six Mars zones, without composition | 9: terrain 8, seasonal range | temperature level 199–223 K; day–night range 78–100 K |
| six Mars zones, with composition | 11 (Meridiani 10: its FeO is above every Earth value) | the same two |

**Calibration.** Each ranked list is calibrated exactly as B34 does its parent
set: group-wise whitening, eigenvalue floor 0.10, d_bar, d_bar per group.
Eight lists are on disk (`cube/phase4/ranking_sets.json`, `whiten_<id>.npy`,
`center_<id>.npy`), four used by presets and four by control patches. d_bar:
Artemis regions 3.4568; Mars zones 3.1631 (no composition), 3.7315 (with),
3.4636 (Meridiani with). The three parent sets of B34 stay on disk unchanged.

**The control patches are targets, so the rule applies to them.** The six
Apollo landing-site patches keep temperature level (just inside Earth's range
near the lunar equator) and lose the day–night range. The coldest lunar patch
loses temperature level and keeps the day–night range (small in permanent
shadow). The coldest Mars patch loses temperature level and the seasonal
range. **The Atacama positive control is Earth ground, so the rule alone would
keep every variable and the control would pass only because the Moon is cold.
It therefore runs on the ranked lists the preset targets use.** That was
decided here, before any result, and is in the test specification.

**What it costs.**
- A lunar polar result has no thermal score. `di_group.thermal` is null.
- Index values from targets with different ranked lists cannot be compared.
- The rule is all-or-nothing at Earth's extreme. A target just inside Earth's
  range keeps the variable and is then ranked on Earth's few most extreme
  cells. Stated as a limit.

**Correction.** ~~The lunar day–night swing is inside, or at the edge of,
Earth's range~~ (said to Sherozbek earlier on 11 Nov). That was read off the
pooled scale. In kelvin the Artemis regions swing 161–210 K against an Earth
maximum of 44 K. Both thermal variables leave the ranking for every Artemis
region.

## (c) Every target cell counts

**The decision.** The score of an Earth cell is its mean distance to ALL
distinct cells of the target, divided by d_bar of the ranked list. This
replaces `k = min(5, distinct)`.

**What the spec says, and what was measured before the decision was
confirmed.** Step 6 of the spec argues against this setting: "k = all CANNOT
TELL THEM APART" (an Earth cell that copies the crater floor and one that
resembles nothing both score 0.6). Claude had not shown him that passage when
he first proposed "all cells". The measurement below was then made on target
cells only (`build/b36_target_spread.py` → `cube/phase4/target_spread_b36.json`):

- **spread**: mean distance between two cells of the target / d_bar. 1.0 is
  two random Earth cells.
- **copy, all**: what an exact copy of one target cell would score under "all
  cells" (median over the target's cells, and the best cell).
- **copy, 5**: the same under the spec's five nearest.

| target | ranked | distinct cells | spread | copy, all: median | best | copy, 5: median |
|---|---|---|---|---|---|---|
| Peak near Cabeus B | 10 | 7 | 1.80 | 1.57 | 1.22 | 1.11 |
| Haworth | 10 | 15 | 1.13 | 1.00 | 0.81 | 0.56 |
| Malapert Massif | 10 | 6 | 1.45 | 1.18 | 1.00 | 0.96 |
| Mons Mouton Plateau | 10 | 90 | 1.59 | 1.54 | 1.14 | 0.45 |
| Mons Mouton | 10 | 5 | 1.28 | 0.92 | 0.87 | 0.92 |
| Nobile Rim 1 | 10 | 9 | 1.57 | 1.26 | 1.05 | 0.63 |
| Nobile Rim 2 | 10 | 10 | 1.48 | 1.25 | 1.07 | 0.72 |
| de Gerlache Rim 2 | 10 | 7 | 1.69 | 1.40 | 1.09 | 1.06 |
| Slater Plain | 10 | 7 | 0.88 | 0.71 | 0.58 | 0.51 |
| Jezero crater | 9 | 680 | 0.97 | 0.91 | 0.73 | 0.18 |
| Jezero crater (with composition) | 11 | 553 | 0.89 | 0.84 | 0.66 | 0.19 |
| Gale crater | 9 | 681 | 1.24 | 1.19 | 0.91 | 0.21 |
| Gale crater (with composition) | 11 | 188 | 1.10 | 1.07 | 0.83 | 0.29 |
| Meridiani Planum, Endeavour | 9 | 681 | 0.83 | 0.78 | 0.59 | 0.17 |
| Meridiani Planum, Endeavour (with composition) | 10 | 596 | 0.77 | 0.71 | 0.55 | 0.17 |
| Gusev crater | 9 | 683 | 1.12 | 1.07 | 0.84 | 0.20 |
| Gusev crater (with composition) | 11 | 105 | 0.98 | 0.93 | 0.76 | 0.26 |
| Erebus Montes, Arcadia | 9 | 684 | 0.87 | 0.81 | 0.63 | 0.17 |
| Erebus Montes, Arcadia (with composition) | 11 | 17 | 0.88 | 0.79 | 0.71 | 0.42 |
| Deuteronilus Mensae | 9 | 680 | 1.22 | 1.16 | 0.89 | 0.21 |
| Deuteronilus Mensae (with composition) | 11 | 271 | 1.17 | 1.12 | 0.87 | 0.29 |

The targets are varied inside. Under "all cells" an exact copy of one part of
a target scores 0.7 to 1.6, about what a random Earth cell scores. Under five
nearest it scores about 0.2 on a Mars zone and 0.5 to 1.1 on a lunar region,
where five cells is most of the region.

**Shown these numbers, with "closest cell" recommended, Sherozbek kept "all
cells".** The question the tool answers is therefore: which Earth place is
like the region as a whole.

**Consequences, written into the test specification and the contract README:**
- An index near 1 can be a perfect match to one part of the target. The index
  is read as "like the target on average". Ranks and bands lead the result
  page, not the index value.
- `d_bar_target` (the target's own spread) is printed beside every index.
- The chance test changes meaning: a uniform patch scores lower than a varied
  one whatever Earth looks like. So every null patch's own spread is recorded
  beside its minimum, and the target's spread is shown against them next to p.
- B35(a) listed "the number of nearest target cells (5)" as future
  sensitivity work. It is no longer a parameter.

**Cost, timing only** (stand-in rows, distances thrown away): one map of
3,245,417 Earth cells takes 0.4 s for 15 target cells, 1.8 s for 90, 5.6 s for
300, 13.5 s for 680. 1,000 null draws: 0.2, 0.9, 2.8, 6.9 minutes.

## (d) Percentile bands and the slider

Each scored reference cell gets a rank: the share of reference cells with a
smaller index. The map shows the best 1% and 5% as bands; the website has a
slider. New raster `rank_combined`: 8-bit grey v, rank = (v / 255)², so the
browser thresholds it with no call to the backend. `run.rank_bands` =
[0.01, 0.05]. One percent of the reference population is about 32,000 cells,
1.3 million km².

This is a rank, not a threshold on the index, so it keeps the spec's "No
threshold — here or anywhere", which already allows "a slider — with the
chance baseline displayed beside it". A best 1% exists for every target.

His other idea, a threshold such as "60% alike", is not adopted: no quantity
in the method means "percent alike", and a cut on the index is what the spec
removed.

## (e) Two site rules, chosen on the day

- **A. Patches of the best share.** Take the best X of reference cells
  (default 1%). Cells that touch form one patch. One entry per patch: best
  cell, cell count, area. At most 20 listed, total stated. No parameter but X.
  It is geographic adjacency, not clustering in variable space.
- **B. Spacing by decorrelation length.** The spec's step 8, unchanged.

Checks written before either list exists (test specification, section 2):
no place listed twice; first entry is the best cell on Earth; 3 to 20 entries
at the default; for B, R was measured and not the fallback. The rule passing
more checks on the two controls and Haworth is used; on a tie, A. Never
chosen by which list holds more known analog sites (invariant 1).

The test specification has a new section 7, "Left for the day, on purpose",
which lists what is open and, as firmly, what is not.

## (f) Min-max scaling — asked, measured, not adopted

Sherozbek asked again whether min-max normalisation would preserve structure
better. Measured on the pooled values of each pairing
(`build/b36_overlap_and_minmax.py`):

| variable family | share of the 0–1 scale that holds the middle 98% of cells | where the median cell lands |
|---|---|---|
| slope, roughness | 20–44% | about 0.02 |
| landform position | 15–21% | — |
| temperature, silica | 86–96% | — |

Terrain has long tails. Min-max lets a handful of extreme cells set the
scale, and ordinary ground is squeezed into a few percent of it: the median
terrain cell would sit at 0.02. The pooled rank scale spreads the cells
evenly by construction. Recommendation given: keep the pooled scale. Where a
variable is out of Earth's range it is now reported in physical units anyway,
which is the structure min-max was meant to keep.

## (g) Changed with it

| where | change |
|---|---|
| `build/ranking_sets.py` (new) | the rule, the calibration of each ranked list, the control patches |
| `build/targets.py`, `build/export_site_assets.py` | `k` removed; a target needs one usable cell |
| `contract/` | **2.3**: `run.k` removed; `run.target_cells_used`, `run.ranking`, `run.rank_bands`, `run.site_rule`, `site_top_share`, `patches_total` added; `ranked` on every variable row; raster `rank_combined`; `patch_cells`, `patch_area_km2` on a site; `targets_ranking.json`; examples regenerated and valid |
| `docs/TEST_SPEC_2026-11-10.md` | section 1a (ranking sets), tests 4, 4a, 6, 9, 12–12d, R1–R5, 20a–20d, the positive control's variables, section 7 |
| `docs/NULL_TABLE_DESIGN_2026-11-10.md` | the null uses the target's ranked list and all patch cells; 4 lists × 7 bands × 4 sizes = 112; cost re-measured (about 2 hours); each patch's spread recorded |
| `docs/analog_finder_method_spec_rev10.docx` | Revision 10 blocks at step 6 and step 8; step 3, 4, 9, 10 blocks and the decisions log updated |
| the animated explainer | version 3, 30 beats: temperature shown as Earth's limit; the score beat draws all 15 lines; a slider beat; site option A and option B |

## (h) For the write-up, under limits

1. Temperature does not rank for any preset target. The tool finds terrain
   and rock analogs and states the thermal gap in kelvin.
2. The index measures likeness to the region as a whole. It cannot single out
   a place that copies one part of a varied region.
3. "Best 1%" is an order, not a quality.
4. The overlap rule is all-or-nothing at Earth's extreme.

---

# §B37 — TWO RANKING SYSTEMS, ONE KEPT ON THE HACKATHON DAY. Sherozbek's decision, 2026-11-11, evening.

## (a) The decision, in his words

A few hours after B36 he wrote: "maybe we should keep them just as they're. I
mean we should also check maybe although variables do not overlap. I know it
will produce the same area but this is the honesty." Asked what should stay
as it is, he answered: "Two ranking systems tested practically and choosen in
actual hacathon day after experimentation. All our assumptions will be
untested ideas, TBH".

**This amends B36(b).** "Rank only on what Earth can match" is no longer THE
ranking. It is one of two.

## (b) The two systems

| system | `run.ranking.system` | what ranks | calibration |
|---|---|---|---|
| 1 | `all_variables` | every variable of the parent set, also those no Earth cell reaches | the parent sets of B34: d_bar 4.0088 (Earth–Moon, 12), 4.2292 (Earth–Mars, 13), 3.7262 (without composition, 11) |
| 2 | `earth_reachable_only` | the parent minus every variable Earth cannot reach (the rule of B36b) | the ranking sets of B36: 10 for an Artemis region, 9 or 11 for a Mars zone |

Both were already calibrated; nothing new was computed. The engine takes the
system as one argument. Both systems report the out-of-range variables as
Earth's limits, in physical units.

## (c) What is fixed in advance, so the choice cannot be bent to a result

He wants the choice made by looking at real maps, not by a rule. So no rule
forces it. What is fixed:

- **For every preset target both systems are run and both results are
  printed, p-values included.** Never only the better one.
- **Three questions are answered for both systems and go in the write-up**
  (test specification, section 7): Does the answer depend on the target (the
  share of cells that the best 1% for Haworth and for Mons Mouton Plateau have
  in common)? Do the controls behave? Which group carries the result at the
  best cell?

Expectation, recorded before any map: under system 1 the lunar polar targets
will probably all point at Earth's coldest rough ground. He knows ("it will
produce the same area") and considers showing that the honest result.

## (d) The controls

Unchanged. They are run under both systems and every outcome is printed.
One reading note was added to the test specification: under system 2 the cold
patches are ranked without their temperature level, so a "significant" there
says their terrain and rock have matches on Earth, not that the test is
broken. Under system 1 the original reading holds.

Open: he asked whether the controls could be dropped for "just plain
p-value". Not decided. Claude's recommendation: keep at least the Atacama
control, because the prototype found nothing significant (B24) and without a
control "Earth has no standout match" cannot be told from "the test is broken".

## (e) The site rules — a fifth check

His point about option B (spacing by decorrelation length): it "just chooses
an area but it doesn't choose those which are highly similar". That is right:
a later pick can be listed because it is far from the others, not because it
ranks high. A fifth check was added to the four of B36(e): every listed site
lies inside the best 1% of Earth. It was already unit test R4.

## (f) Changed with it

| where | change |
|---|---|
| `contract/output_schema.json` | `run.ranking.system` (required). The version stays **2.3**: the field was added the same evening, before anyone built against 2.3 |
| `build/ranking_sets.py` | a `systems` block in `ranking_sets.json` and `contract/targets_ranking.json` |
| `docs/TEST_SPEC_2026-11-10.md` | section 1a (two systems), tests 12e, 12f, the controls under both, check (v), section 7 |
| `docs/NULL_TABLE_DESIGN_2026-11-10.md` | the table is built only for the system kept on the day |
| `contract/README.md` | the result page must be able to show either system |
| `docs/analog_finder_method_spec_rev10.docx` | step 6 block: "Two ranking systems, one kept on the day"; steps 3, 4, 8, 9 and the decisions log follow |
| the animated explainer | version 4: the temperature gap is reported; whether it also ranks is tested both ways |

## (g) What it costs

Two ranking systems and two site rules are four combinations to build, run
and compare in one day, on top of the controls. The engine difference between
the systems is one argument, so the cost is in comparing and presenting, not
in code. Stated to Sherozbek on 11 Nov.

---

# §B38 — THE FINAL DECISIONS OF 11 NOVEMBER: MIN-MAX SCALE, ONE CONTROL, PATCHES, THE USE TABLE. Sherozbek, 2026-11-11, night.

## (a) The decisions, in his words

Given a list of what was decided, open and suspicious, he answered point by
point:

1. "The ranking system is min-max instead of percentile ranking because it's
   kept from. That's the point" — the structure of the real values is kept.
2. "Controls are stripped except for Atacama."
3. "The use table for 9 is for all variables and by three categories
   (terrain, thermal, composition). And we can also add use-cases of site,
   explaining where the analog fails, succeeds, and where the Earth's limits."
4. "'All cells' score should be the main. I know it's absurd but for the sake
   of representation. K=5 has its own risks. You should also explain why k=5
   which is kinda difficult."
5. "The chance tests should be showed just as they're without hyping. Maybe
   they will show something insignificant and that's ok."
6. "The overlap rule is where we actually decide on hackathon and this is
   only thing we decide on hackathon. But, TBH, there are two things: hyping
   or honesty. And I choose honesty. And frankly, Antarctica can be best place
   for Moon data. And top 5% may include places beyond Antarctica."
7. "I have no idea on unmeasured choices."
8. "You can also open spec files in Word."

Claude's readings, stated to him: (1) means the step 3 scale, replacing the
pooled percentile and the normal score of B33; (6) means the site rule is no
longer a day-of choice, and since he had called option B a rule that "just
chooses an area but it doesn't choose those which are highly similar" and
option A "a good option even if it produces the same results", the site rule
is A, patches.

No distance from an Earth cell to a target, no DI map, no p-value and no site
was computed.

## (b) Step 3 is a min-max scale

**The transform.** For one variable and one pairing: lo and hi are the
smallest and largest value over Earth's complete reference cells and every
finite cell of the body. position = (x − lo) / (hi − lo). One straight line
for both worlds. B33's principle stands (one shared scale per pairing); its
rank transform, its half-and-half weight and its normal score are gone.
`build/phase4b_minmax_scale.py`; gates G1 same units, G2 positions in 0..1
with both ends reached, G3 round trip to 1e-5 of the range: all pass.
`phase4b_pooled_scale.py` is frozen; its outputs are parked in
`cube/_work/pooled_scale_before_B38/`.

**What Claude had measured before he decided** (B36f): on a min-max scale the
middle 98% of Earth's cells occupy a small part of the terrain scales. He
decided knowing it: "That's the point".

**Found while building it — lo and hi cancel.** Step 4 standardises by
Earth's mean and standard deviation and whitens. A straight-line rescaling
cancels there. So no distance depends on lo or hi: the distance is the same
as on the raw physical values. lo and hi set what is DISPLAYED (positions,
gaps, verdicts). An absurd extreme cell can squeeze a display; it cannot move
a ranking.

**The scale, Earth + Moon** (`cube/phase4/minmax_scale_summary.json`,
`minmax_description_b38.json`). Last column: where the typical cell of the
nine Artemis regions lies, in Earth standard deviations from Earth's mean.

| variable | lo – hi | hi set by | Earth median position | Moon median position | Earth middle 98% | one tenth of the scale | Artemis medians, Earth sd |
|---|---|---|---|---|---|---|---|
| slope | 0 – 28.67 deg | moon | 0.013 | 0.126 | 0.000 – 0.258 | 2.87 | +2.1 to +10.7 |
| roughness at 21 km | 2.729e-05 – 2463 m | moon | 0.014 | 0.144 | 0.001 – 0.227 | 246 | +3.1 to +10.8 |
| landform position at 21 km | -2406 – 2033 m | moon | 0.542 | 0.541 | 0.492 – 0.605 | 444 | +1.0 to +14.7 |
| sky view | 0.6218 – 1 dim | Earth | 0.976 | 0.847 | 0.608 – 0.999 | 0.0378 | -2.9 to -0.7 |
| temperature level | 39.86 – 314.3 K | Earth | 0.922 | 0.703 | 0.795 – 0.972 | 27.4 | -12.0 to -8.0 |
| day–night range | 0.6217 – 345.8 K | moon | 0.038 | 0.817 | 0.009 – 0.087 | 34.5 | +20.7 to +27.7 |
| SiO2 | 1 – 87 wt% | Earth | 0.733 | 0.492 | 0.044 – 1.000 | 8.6 | -0.7 to -0.6 |
| FeO | 0 – 30.75 wt% | moon | 0.124 | 0.179 | 0.020 – 0.332 | 3.07 | +0.3 to +0.5 |

**Consequences, measured:**
- **Large gaps now reach the distance.** The rank scale bounded every gap.
  On real values the Artemis regions lie 2 to 15 Earth standard deviations
  out on terrain, 8 to 12 on temperature level, 21 to 28 on the day–night
  range.
- **Calibration** (`phase4c_di.py`, rerun): d_bar 3.7247 (Earth–Moon, 12),
  3.9898 (Earth–Mars, 13), 3.4586 (without composition, 11). Floored
  eigenvalues 4 / 5 / 5: the fifth, in the two Mars sets, is in the
  THERMAL group (eigenvalue 0.096): on real values Earth's three temperature
  variables are close to redundant. d_bar moves up to 3% between seeds (was
  1%), because real values have long tails.
- **Ranking sets** (`ranking_sets.py`, rerun; the overlap rule is on physical
  values and did not change):

| ranking set | variables | floored | d_bar |
|---|---|---|---|
| `earth_mars__minus__FeO__temp_level__temp_range_diurnal` | 10 | 4 | 3.0903 |
| `earth_mars__minus__temp_level__temp_range_diurnal` | 11 | 4 | 3.3599 |
| `earth_mars_no_composition__minus__temp_level__temp_range_diurnal` | 9 | 4 | 2.7225 |
| `earth_moon__minus__temp_level__temp_range_diurnal` | 10 | 4 | 2.9682 |

- **The spec's reason for ranks is given up knowingly.** Step 3 chose ranks
  so that "outliers and skew cannot dominate".
- **A suspicious value, flagged and not changed:** the largest FeO on Mars is
  87.7 wt%, and its 99th percentile is
  33 wt%. Not believable for bulk rock. It stretches the display of
  FeO for Earth–Mars and enters distances only for Mars cells that carry it.
  To check after the hackathon (B27 layer).
- **One unmeasured choice disappeared:** min-max needs no mixing weight.

## (c) "All cells", re-measured on the new scale

His reason, recorded: k = 5 is a number hard to justify; "all" has none, and
every cell is represented. The cost on real values is larger than B36(c)
measured on ranks (`build/b36_target_spread.py`, rerun):

| target | ranked | distinct cells | spread | exact copy, all cells (median) | exact copy, 5 nearest (median) |
|---|---|---|---|---|---|
| Peak near Cabeus B | 10 | 7 | 5.21 | 3.83 | 2.90 |
| Haworth | 10 | 15 | 2.80 | 2.59 | 1.46 |
| Malapert Massif | 10 | 6 | 4.83 | 4.07 | 3.39 |
| Mons Mouton Plateau | 10 | 90 | 4.43 | 4.22 | 1.33 |
| Mons Mouton | 10 | 5 | 4.01 | 2.85 | 2.85 |
| Nobile Rim 1 | 10 | 9 | 4.93 | 3.99 | 2.55 |
| Nobile Rim 2 | 10 | 10 | 4.21 | 3.63 | 2.13 |
| de Gerlache Rim 2 | 10 | 7 | 3.00 | 2.77 | 1.90 |
| Slater Plain | 10 | 7 | 2.20 | 1.81 | 1.37 |
| Jezero crater | 9 | 680 | 1.51 | 1.30 | 0.30 |
| Jezero crater (with composition) | 11 | 553 | 1.48 | 1.32 | 0.33 |
| Gale crater | 9 | 681 | 3.03 | 2.73 | 0.54 |
| Gale crater (with composition) | 11 | 188 | 2.37 | 2.23 | 0.62 |
| Meridiani Planum, Endeavour | 9 | 681 | 0.73 | 0.57 | 0.11 |
| Meridiani Planum, Endeavour (with composition) | 10 | 596 | 0.64 | 0.51 | 0.11 |
| Gusev crater | 9 | 683 | 2.03 | 1.83 | 0.40 |
| Gusev crater (with composition) | 11 | 105 | 1.61 | 1.33 | 0.34 |
| Erebus Montes, Arcadia | 9 | 684 | 0.42 | 0.30 | 0.04 |
| Erebus Montes, Arcadia (with composition) | 11 | 17 | 0.55 | 0.45 | 0.20 |
| Deuteronilus Mensae | 9 | 680 | 2.30 | 2.07 | 0.38 |
| Deuteronilus Mensae (with composition) | 11 | 271 | 2.58 | 2.46 | 0.45 |

On real values the cells of an Artemis region differ from each other 2 to 5
times more than two random Earth cells do. The DI of an Artemis region will
be well above 1 everywhere on Earth. He kept it: "I know it's absurd but for
the sake of representation." The result page therefore leads with ranks and
bands, and prints the target's own spread beside every DI.

## (d) One control

Only the Atacama patch is run. The negative controls (coldest lunar and
martian patch) and the Apollo training-site control are removed; with them
goes "Decision 1" of 10 Nov. `ranking_sets.py` no longer calibrates lists for
them (4 ranking sets instead of 8). `control_fixtures.json` keeps the pixels;
only `positive_atacama` is used.

What the control is for, as told to him: if every target comes back "not
significant", it separates "Earth has no standout match" from "the test
cannot see one". Under the overlap system it runs on the preset targets'
ranking sets; under the all-variables system on the parent set, where it
passes mostly because the Moon is cold.

**Wording** (decision 5): results are printed as they come out. "Not
significant" as plainly as "significant".

## (e) Sites are patches of the best 1%

Rule A of B36(e) is the rule. The spec's step 8 (decorrelation length, greedy
spacing, the 100 km fallback) is not built in version 1. B36(e)'s "two rules,
chosen on the day" and its checks are withdrawn.

## (f) The one choice left for the day

Which ranking system is the main result: all variables, or only those Earth
can match (B37). Both are still run and printed for every preset target, and
the three questions of B37(c) are still answered for both. He leans to "all
variables" for honesty. Recorded before any map: under that system, on real
values, the day–night range is 21 to 28 Earth standard deviations out and
temperature level 8 to 12, so temperature will carry most of every distance.
Whether the best ground is then Antarctica (coldest) or the places with
Earth's largest day–night swing is not known and was not computed.

## (g) The use table

`contract/use_table.json`, drafted by Claude on his instruction, for his
review. Ten rows covering all thirteen ranking variables, in three groups;
each row has a sentence for "agrees", for "differs" and for "beyond Earth".
Each site carries three lists: succeeds, fails, beyond Earth. The engine
writes no sentence of its own. Thermal inertia is not in the table. Every
sentence is limited to what a 6 to 7 km cell can say.

## (h) Changed with it

| where | change |
|---|---|
| `build/phase4b_minmax_scale.py` (new), `phase4c_di.py`, `ranking_sets.py`, `b36_target_spread.py` | the scale and everything calibrated on it |
| `contract/` | **2.4**: `run.scale` = `minmax`; `earth_position`, `target_position`, `position_gap` (renamed); one control; `site_rule` fixed, `exclusion_*` gone; `use` block replaces `use_case`; `use_table.json`; README rewritten |
| `docs/TEST_SPEC_2026-11-10.md`, `docs/NULL_TABLE_DESIGN_2026-11-10.md` | **rewritten clean**: they state only what is decided now. The patched versions are in `cube/_work/docs_before_B38/` |
| `docs/analog_finder_method_spec_rev10.docx` | Revision 10 blocks rewritten for steps 3, 4, 6, 8, 9, 10; a new block at step 7; a min-max figure; the page header now says Revision 10. **Opened in Word 16: no repair prompt, 93 pages; the pages of steps 3, 6 and 9 were read from Word's own PDF export** |
| the animated explainer | version 5, 28 beats: the min-max beat, no bell-shaped score, a control beat, one site rule |

## (i) For the write-up, under limits

1. On real values a few extreme cells set the ends of each scale; ordinary
   ground occupies a small part of the terrain scales.
2. The index measures likeness to the region as a whole; for the Artemis
   regions it is above 1 everywhere.
3. "Every group counts once" and the eigenvalue floor are choices whose
   effect is not measured (his answer: "I have no idea on unmeasured
   choices"; they stay listed as future work).
4. One control, a positive one. Nothing checks that the test stays quiet
   where it should.

---

# §B39 — THE ENGINE, THE FIRST RESULTS, AND THE MAIN RANKING SYSTEM. Hackathon day 1, 2026-11-14.

## (a) What was built on the day

The engine (spec steps 5 to 9 and 11) was written on 14 November to
`docs/TEST_SPEC_2026-11-10.md`, in `engine/`: `analog_engine.py` (presets,
custom targets, both ranking systems, chance test, control, patches,
description, click payload), `render.py` (maps, the rank image), runners,
`api.py` (a FastAPI layer), and tests. 60 of 61 specification tests pass; the
API passes 15 of 15 checks; a user-drawn circle and rectangle on Mars pass 5
of 5. Everything is public at https://github.com/Sherozbek2805/avenguarde.

**The one failing test, stated as it is:** `di_terrain` differs by 0.9%
between the two ranking systems. The terrain distance is identical; each
calibration estimated its group d_bar on its own 5,000-cell subsample (2.2031
against 2.1834). Ranks are not affected. Not fixed.

## (b) The results, as they came out — 42 preset runs

Every preset target was run under both ranking systems. Nothing was left out.

**Moon, nine Artemis III regions** (12 variables / 10 variables):

| region | cells | own spread | p, all variables | best cell (lat, lon) | p, Earth-reachable | best cell |
|---|---|---|---|---|---|---|
| Peak near Cabeus B | 7 | 4.20 | 0.993 | 19.83, -155.39 | 0.981 | 15.02, -24.39 |
| Haworth | 15 | 2.49 | 0.710 | -20.34, -69.04 | 0.676 | -7.90, 126.30 |
| Malapert Massif | 6 | 3.94 | 0.991 | 19.43, -155.57 | 0.976 | 14.98, -24.43 |
| Mons Mouton Plateau | 90 | 3.72 | 0.935 | -20.30, -69.17 | 0.904 | 18.60, -74.05 |
| Mons Mouton | 5 | 3.39 | 0.770 | -20.34, -69.04 | 0.886 | -3.21, 126.08 |
| Nobile Rim 1 | 9 | 4.16 | 0.967 | 19.47, -155.52 | 0.946 | -7.71, 126.08 |
| Nobile Rim 2 | 10 | 3.52 | 0.752 | -25.16, -68.03 | 0.854 | -16.57, -71.15 |
| de Gerlache Rim 2 | 7 | 2.50 | 0.854 | -25.16, -68.03 | 0.739 | -8.16, 115.36 |
| Slater Plain | 7 | 1.90 | 0.721 | -25.16, -68.03 | 0.453 | 1.19, 34.59 |

**Mars, six zones, whole zone without composition** (11 / 9 variables):

| zone | cells | own spread | p, all variables | best cell | p, Earth-reachable | best cell |
|---|---|---|---|---|---|---|
| Jezero crater | 680 | 1.36 | 0.247 | -18.13, -69.21 | 0.825 | 23.36, 56.87 |
| Gale crater | 681 | 2.51 | 0.132 | -18.21, -69.39 | 0.941 | 51.64, 104.91 |
| Meridiani Planum, Endeavour | 681 | 0.75 | 0.287 | -18.13, -69.21 | 0.350 | 28.72, 16.30 |
| Gusev crater | 683 | 1.86 | 0.270 | -18.13, -69.21 | 0.920 | 39.84, 92.94 |
| Erebus Montes, Arcadia | 684 | 0.45 | 0.789 | -18.13, -69.21 | 0.219 | 65.98, 117.50 |
| Deuteronilus Mensae | 680 | 1.95 | 0.729 | -18.13, -69.21 | 0.957 | 51.01, 90.48 |

**Mars, the cells that have composition** (13 / 11 variables):

| zone | cells | own spread | p, all variables | best cell | p, Earth-reachable | best cell |
|---|---|---|---|---|---|---|
| Jezero crater | 553 | 1.38 | 0.279 | -18.13, -69.21 | 0.814 | 10.73, 37.22 |
| Gale crater | 188 | 2.08 | 0.095 | -18.37, -69.39 | 0.924 | -30.52, -70.80 |
| Meridiani Planum, Endeavour | 596 | 1.55 | 0.447 | -15.91, -71.02 | 0.148 | 28.21, -100.85 |
| Gusev crater | 105 | 1.64 | 0.196 | -18.13, -69.21 | 0.799 | 41.66, 89.03 |
| Erebus Montes, Arcadia | 17 | 0.51 | 0.818 | -18.13, -69.21 | 0.090 | 70.40, 112.03 |
| Deuteronilus Mensae | 271 | 2.24 | 0.784 | -21.78, -67.98 | 0.995 | 44.65, 100.66 |

**No target is significant** (p < 0.05) in any of the 42 runs.

## (c) The control

The Atacama patch, treated as a target on the other body:

| pairing and system | p | outcome |
|---|---|---|
| Earth–Moon, all variables | 0.000999 | passed |
| Earth–Moon, Earth-reachable only | 0.1069 | **FAILED** |
| Earth–Mars without composition, all variables | 0.000999 | passed |
| Earth–Mars without composition, Earth-reachable only | 0.7113 | **FAILED** |
| Earth–Mars with composition, all variables | 0.000999 | passed |
| Earth–Mars with composition, Earth-reachable only | 0.5075 | **FAILED** |

By the rule written before the day, every p-value under "Earth-reachable only"
carries the sentence that the control failed and the test has no power there.
Each output file says so in `limits`.

**Why it fails, measured.** With the "all cells" score (B36c, B38c) a patch's
best Earth score follows the patch's own spread: rank correlation 0.99 across
the 1,000 random lunar patches under "Earth-reachable only", 0.60 under "all
variables". A smooth lunar plain is uniform inside, so it scores lower than
the Atacama patch whatever Earth looks like. The chance test then asks mostly
"is this target more uniform than other patches", which B36(c) had predicted.
The Artemis regions are more varied than a typical polar patch (spread 2.2 to
5.2 against a null median near 2.5), which is why their p-values are high.

**Why it passes under "all variables", also stated in advance (B38d):** no
lunar or martian patch is as warm as the Atacama, so every random patch is far
from Earth. That pass says little about the test's power.

## (d) The three questions of the test specification, for both systems

| question | Moon, all variables | Moon, Earth-reachable | Mars, all variables | Mars, Earth-reachable |
|---|---|---|---|---|
| share of best-1% cells two targets have in common (median over pairs) | 0.69 | 0.52 | 0.95 | 0.00 |
| cells in the best 1% of EVERY target | 12,240 | 3,541 | 27,805 | 0 |
| control | passed | failed | passed | failed |
| group that carries the score at the best cell | thermal (16–19; terrain 2.5–6.7) | terrain (2.0–4.7) | thermal (7–9; terrain 1.6–2.8) | terrain (0.3–2.6) |

Under "all variables" 8 of the 12 Mars runs have the SAME best cell
(18.13°S, 69.21°W, Altiplano), and most lunar runs point at the
Atacama–Altiplano or Mauna Loa. Under "Earth-reachable only" the best cells
are spread out (eastern Indonesia, Cape Verde, Haiti, Oman, Ethiopia, Libya,
south of Lake Baikal).

Sherozbek's expectation of 11 Nov ("Antarctica can be best place for Moon
data") did not hold: under "all variables" the day–night range is the largest
gap, and the best ground is the high dry plateaus where Earth's own swing is
largest, not the coldest ground.

## (e) The decision: the main result is "all variables"

Shown the comparison above, with Claude recommending "Earth-reachable only" as
the main result (it tells targets apart), Sherozbek answered: **"All
variables"**. That is the main result. "Earth-reachable only" is the second
view. Both are still run and shown for every target. This closes the one
choice B37 and B38(f) left for the day.

**What the choice costs, to be said on the result page and in the write-up:**
1. The answer depends little on the target: two Mars zones share 95% of their
   best 1% of Earth, two lunar regions 69%. The tool then says "the most
   Moon-like or Mars-like ground on Earth", more than "the analog of THIS
   place".
2. Temperature carries the score. Terrain and rock decide little.
3. The control passes for a cheap reason.
4. No target is significant.

## (f) Changed with it

| where | change |
|---|---|
| `engine/analog_engine.py` | `MAIN_SYSTEM = "all_variables"`; the `limits` text of every run names the main result |
| the 50 finished `output.json` files (42 preset runs, published in `runs/`; 8 custom test runs, kept local) | ONE sentence of `limits` replaced: "neither is 'the' result until the team names one" → which system is main and whether this file is it. No number changed |
| `runs/*_system_comparison.json` | `main_system` added |
| `README.md`, `runs/README.md`, `contract/README.md`, `docs/TEST_SPEC`, `docs/NULL_TABLE_DESIGN`, `docs/TEAM_PLAN`, `HANDOVER.md` | the choice is recorded as made |
| `docs/analog_finder_method_spec_rev10.docx` | step 6 block and the decisions log: the main result counts every variable |
| the animated explainer (local files) | one sentence |

## (g) Flagged on the day, not acted on

- Two custom lunar tests came out significant under "all variables": a 43 km
  circle on Tycho (p = 0.001) and a 14 km circle near Copernicus (p = 0.001).
  Not examined. A plausible reading, untested: young rocky craters keep more
  heat at night, so their day–night range is closer to Earth's than typical
  lunar ground at the same latitude.
- A warning from `astropy_healpix.neighbours` (invalid value) appeared once
  during the Mars batch; outputs validated.

# §B40 — THE WEBSITE AND ITS SERVER. Hackathon days 1–2, 2026-11-14 to 15.

Written from the frontend chat (Shohruxbek with Claude). The early part of
that chat is known only from Claude's summary notes; everything from the AWS
work onward is on record in full.

## (a) Decisions made by the team (Shohruxbek)

**Look and content**

- Google Earth dark style, with a globe for targets and a flat Earth map for
  results.
- The team's own hero picture, white square buttons, and the methodology in
  four steps.
- A separate page for each place: picture on top, numbers below, with a
  variable-by-variable chart.
- Removed: "Do not use it for", the Rectangle and Circle tools, the hero
  labels, "Team AvenGuarde" on the opening screen, and the general limits
  paragraph on the place page.
- Added: the logo, a bigger headline, and picking any place on the Moon.
- The shorter methodology and its order: distance, then whitening, then
  outputs, then the p-test.

**Infrastructure**

- AWS rather than Supabase or Google Cloud.
- Three spending approvals, the last for the server with the cache layer.
- The domain `avenguarde.eengineer.net`.
- GitHub: Claude pushes only after the team approves.

## (b) Decisions made by Claude

- **Build:** plain HTML, CSS and JavaScript with Canvas, no framework.
- **Place pictures:** Sentinel-2 cloudless from EOX, with NASA Blue Marble as
  fallback. Its licence is non-commercial and it is not a NASA source; one
  setting switches to NASA only.
- **Server:** Lightsail in Sydney (the only region the account allows), and
  the upload route with a token. The first server choice was wrong: it was
  throttled and slow, and it was replaced.
- **Cache of the chance-test draws:** Claude's proposal, approved by the team.
- **Live search behaviour:** the stored result shows first, and a live result
  replaces it only on success.
- **"Your place":** circle only, Moon only, radius 10–30 km, default 15 km.
- **Methodology details:** which scenes to keep, the new variables scene (it
  still names temperature and rock), and keeping the Team block in Notes.
- **Unasked extras:** version marks on style and script links, and a
  local-server tweak for the repository layout.

One thing to review: the contract says the "fails" list should be shown next
to "succeeds". The removal of "Do not use it for" goes against that.

## (c) Results

- **Site:** live at https://avenguarde.eengineer.net with HTTPS. It shows 15
  NASA targets (9 Moon, 6 Mars). None passes the chance test; the Atacama
  control passes in 15 of 15.
- **Engine on AWS:** it reproduces the stored p for all 18 Moon and 24 Mars
  warm-up runs.
- **Speed:**

| Search | Before | Now |
|---|---|---|
| Moon target (Haworth) | 145.7 s on the first server | 14–20 s |
| Mars target | up to 8 min | 14–49 s |
| New place on the Moon, 15 km | — | 40.5 s |
| New place on the Moon, 50 km | — | 129 s (so the limit is 30 km) |

- **A significant result:** a 20 km circle at the centre of Tycho crater gives
  p < 0.001, in line with the engine's own Tycho test (§B39 g).
- **Methodology on the site:** 28 scenes cut to 19.

## (d) Infrastructure

**AWS**

- **Account:** the free plan with $100 of credits, valid until 14 May 2027.
  It allows new servers only in the Sydney region (ap-southeast-2), so
  everything is there.
- **Service:** Amazon Lightsail, AWS's simple virtual servers. Everything was
  created and configured through the AWS connector, without the AWS console
  or SSH.
- **Not used:** S3 storage, a CDN (CloudFront), a database, or a load
  balancer.

| Server | Size | List price | Role |
|---|---|---|---|
| `avenguarde-web` | 4 CPUs, 8 GB | $84 a month (about $2.80 a day) | The one in use: website and engine |
| `analog-engine-fast` | 4 CPUs, 8 GB | $84 a month | Old; engine only, no cache |
| `analog-engine` | 2 CPUs with a burst limit, 8 GB | $44 a month | Old; the slow first try |

The server in use also has a fixed address (a Lightsail static IP,
54.252.12.127) and a firewall that opens only the web ports (80 and 443).

**What runs on `avenguarde-web`**

- **Setup:** one script runs at first boot on Ubuntu 24.04. It clones this
  repository from GitHub (commit `cdc51c7`), installs Python, rebuilds the
  calibration files, and copies the stored results.
- **Web server (Caddy):** it serves the website and the stored result files,
  passes `/api` requests to the engine, and gets the HTTPS certificate by
  itself.
- **Engine:** this repository's own FastAPI program, unchanged, running one
  search at a time.
- **Cache layer:** a small wrapper that keeps the chance test's 1,000 random
  draws on disk, plus the warm-up that filled it for all 15 targets. The
  draws depend only on the body, the variable set, the patch size, the
  latitude band and the fixed seed. The result file still says
  `null_source: "live"`.
- **Upload door:** an address that accepts a new version of the website when
  the request carries the secret token. The token is not in this repository.

**How a visit works**

1. The browser opens `avenguarde.eengineer.net`; the GoDaddy DNS record points
   to the fixed address.
2. The server sends the pages and the stored result for the chosen target.
3. A live search goes to `/api`; the engine reads the data cube on the
   server's disk and returns a new result.

**Outside AWS**

- **GoDaddy:** the DNS record for the domain.
- **GitHub:** the source the server was built from.
- **EOX and NASA GIBS:** the satellite pictures on the place page, loaded by
  the visitor's browser.
- **Shohruxbek's computer:** the local test server, also used to upload new
  versions.

**Limits to know**

- It is one server with no backup copy and no monitoring; if it stops, the
  site stops.
- A restart of the server was not tested.
- All costs so far are paid from the credits. The two old servers still use
  about $4.30 of them a day.

## (e) Still open

- The two old servers still run; they are deleted only on the team's word.
- GitHub push of the website: waiting for approval and the destination
  folder.
- Not tested on the public site: Firefox, Safari, phones, and the live button
  on five of the six Mars targets.
- Not started: the pitch deck, the prompt files, and a list of ready-made
  known places.
