# Appendix B — Glossary

Every technical term in this document, in plain English. If a term here is
still unclear, ask — it means the definition needs rewriting, not that you
missed something.

---

## 1. The grid and geometry

| Term | Meaning |
|---|---|
| **Grid cell / pixel** | One patch of the lattice we cut each body into. A measurement bucket, not a place. Ours are HEALPix pixels: 6.37 km on Earth, 6.95 km on the Moon, 6.79 km on Mars. |
| **HEALPix** | An equal-area grid of the sphere, borrowed from astronomy. Every pixel covers exactly the same area and there are no special points at the poles. **Adopted 5 November 2026** after a seven-test gate passed 7/7. |
| **Nside** | The HEALPix resolution dial. Earth 1024, Moon 256, Mars 512 — chosen so the three pixel sizes land within 9% of each other. Pixel count is always 12 × Nside². |
| **NESTED** | The HEALPix pixel-numbering scheme we use. Neighbouring pixels get nearby numbers, which makes spatial operations fast. |
| **Equal-area** | Every pixel covers the same ground. This is why **no latitude weighting appears anywhere** in the pipeline — the thing area weighting used to correct for no longer exists. |
| **Area weighting** | Multiplying each cell by its true surface area before averaging. Required on a lat/lon grid, where polar cells are ~1,000× smaller than equatorial ones. In this project it survives at **exactly one step**: binning from a lat/lon source into HEALPix. Nothing downstream uses it. |
| **Physical baseline** | Measuring something over a fixed real distance instead of "one cell". Slope uses **7 km**; roughness uses **5.25, 10.5, 21 and 42 km**. Required so the same word means the same thing on three bodies. |
| **Binning** | Combining many fine source measurements into one coarser pixel. **Only valid when the source is finer than the target.** When it is coarser, we copy instead, and mark every copied pixel. |
| **Working grid** | The intermediate lat/lon grid each body's terrain is computed on before binning: Earth 1/240°, Moon 1/64°, Mars 1/128°. |
| **Summed-area table (SAT)** | A precomputed running-total array that returns the sum inside any rectangle in constant time. Lets us get all four roughness scales and TPI from a single pass over the elevation data. |
| **DEM** | Digital Elevation Model — a grid of ground heights. Everything about terrain is computed from one. |
| **Plate carrée** | The map projection most source data arrives in. Latitude goes straight onto the vertical axis. **Not uniformly coarse**: a 0.5° cell is 15.2 km north–south but only about 0.7 km east–west at 87°S. |
| **Polar stereographic** | A projection that views a pole from directly above. Used for every figure covering the lunar and martian south poles, because plate carrée smears that region into unreadable streaks. |
| **Mercator** | A projection we do **not** use. It stretches to infinity at the poles, and the web version cuts off at ±85.05° — which would hide our lunar polar results entirely. |
| **Latitude variance artifact** | A flaw in the old lat/lon design: polar cells held fewer measurements, so their values were noisier and landed in the distribution's tails for no geographic reason — about 2.4× noisier at 80° than at the equator. **Removed by HEALPix.** Kept here because it appears in the project's history. |

---

## 2. The variables

| Term | Meaning |
|---|---|
| **Dimension** | A variable that drives the similarity score. **Earth–Moon has 10; Earth–Mars has 6.** A variable only counts as a dimension if *both* bodies in the pair have it. |
| **Filter** | A layer that decides which pixels are eligible at all, before any distance is computed. Never scored. |
| **Characterization layer** | A layer that describes a site *after* it has been found. Changes no number. Köppen-Geiger is one. |
| **`matching_eligible`** | A flag on every layer saying whether it may enter the dimension set. Mars thermal is `false` — the layers exist and are reported, but the source grid is too coarse to discriminate. |
| **Slope** | How steep the ground is, measured over a 7 km baseline. |
| **Roughness** | How far the surface departs from a smooth plane, measured at four window sizes: 5.25, 10.5, 21 and 42 km. Not four copies of one thing — the *differences between the scales* carry the texture of the terrain. |
| **TPI (Topographic Position Index)** | How high a place sits relative to its surroundings, over 21 km. Negative means a basin or crater floor; positive means a ridge or peak. |
| **Scaling exponent (H)** | The slope of log-roughness against log-scale. Intended to capture how terrain texture changes with scale. **On HOLD** — the maps show it is measuring something real, but the signal-to-noise is only 2.12× and does not improve under any filter. Built and stored; not used. |
| **Temperature level** | The average surface temperature over a full cycle. |
| **Diurnal swing** | The temperature range within one rotation of that body — 24 h on Earth, about 29.5 Earth days on the Moon, 24.66 h on Mars. Defined consistently as **maximum minus minimum over the available local times**, with sample counts of 4 (Earth), 12 (Mars) and 96 (Moon). |
| **Seasonal range** | The temperature range across a year. Exists on Earth and Mars. **The Moon has none worth measuring**, so this is not an Earth–Moon dimension. |
| **Thermal inertia** | How strongly the ground resists changing temperature. High means solid rock; low means dust or fine sand. A *material property* rather than a state, which makes it a strong analog variable. **Not built** — a candidate Earth–Mars upgrade. |
| **Apparent thermal inertia (ATI)** | A proxy for thermal inertia computed as (1 − albedo) ÷ day-night temperature difference. Standard remote sensing since the 1970s. Cruder than a measured value, but comparable once both are ranked within their own body. |
| **Albedo** | The fraction of sunlight a surface reflects. Snow is high, basalt is low. Needed for ATI. |
| **Sky visibility / sky view factor** | What fraction of the sky is unobstructed by surrounding terrain. One number covering communications, solar power and radiation shielding. **Deferred** — computing it on a lat/lon grid at the lunar south pole is wrong, not merely imprecise; it needs a polar stereographic sweep. |
| **Concavity** | Whether a place sits inside a bowl. Detects craters, calderas and closed basins — *form* rather than texture. **Not built.** |
| **Silica (SiO₂)** | Bulk surface chemistry. Low means basalt-like; high means granite-like. On Earth it is derived from rock type; on the Moon it is measured directly from orbit. |
| **FeO / FeO_T** | Iron oxide content. **FeO_T** means *total iron reported as FeO*, which is what lunar and martian orbital spectroscopy publishes. Mixing FeO_T with FeO-only would be the same class of error as mixing Celsius with Kelvin. |
| **Mafic / felsic** | Mafic rock is silica-poor and iron-rich — basalt, gabbro. Felsic is silica-rich and iron-poor — granite, rhyolite. The lunar south pole is mafic (SiO₂ ≈ 45%, FeO ≈ 5%). |
| **wt%** | Weight percent. The unit for both oxides. |
| **Lithology** | Rock type as a category name. Earth's composition data arrives this way, so lithology is the **route** to Earth's SiO₂ and FeO — each of 98 rock classes is assigned a representative chemistry. The Moon and Mars skip this step entirely, because orbital spectroscopy measures chemistry directly. |
| **Majority vote** | How a categorical layer is binned. A pixel takes the class that covers most of it, and the winning class's share becomes that pixel's support. Averaging rock-type codes would be meaningless. |
| **Reducer** | The statistic used to collapse many values into one — mean, median, midrange, maximum. Part of a dataset's identity, not an implementation detail. |
| **Reference population** | The set of Earth pixels every rank and every covariance is computed against: ice-free, water-free land. Stored as `earth_land_reference`. |

---

## 3. The data and the instruments

| Term | Meaning |
|---|---|
| **ETOPO** | The global Earth elevation dataset. Published as both a surface model and a bedrock model; the difference between them is how the ice sheets are identified. |
| **LOLA** | Lunar Orbiter Laser Altimeter, on LRO. The Moon's elevation data. |
| **MOLA** | Mars Orbiter Laser Altimeter, on Mars Global Surveyor. Mars elevation, used blended with HRSC stereo imagery. |
| **Diviner** | The infrared radiometer on LRO. Source of all lunar temperature data. |
| **tbol** | Bolometric temperature — the temperature Diviner reports, integrated across its channels. `tbol_max` and `tbol_min` give the lunar diurnal range. |
| **Diviner GCP** | The Diviner gridded product binned by local time: 0.5° spatially, 0.25 h in local time, **global to ±90° and 100% valid**. The source of our lunar thermal layers. Not to be confused with the DGDR cylindrical product, which covers only ±60° and holds *anomalies* rather than temperatures. |
| **Local time bin** | Which part of the lunar or martian day an observation was taken in. The Moon has 96 bins of which a typical pixel fills 62 — sparse sampling biases the maximum low and the minimum high. |
| **LP GRS** | Lunar Prospector Gamma Ray Spectrometer. Gives lunar SiO₂ and FeO in weight percent, pole to pole, at 2° resolution, with a published per-cell error matrix. |
| **MOD11C3 / MYD11C3** | MODIS monthly land surface temperature at 0.05°. **MOD** is the Terra satellite (overpasses ~10:30 and ~22:30); **MYD** is Aqua (~13:30 and ~01:30). Using both gives four local times a day. |
| **LST** | Land Surface Temperature — the temperature of the ground itself, not the air above it. The correct Earth counterpart to Diviner and to martian surface temperature. |
| **MCD43A3** | The MODIS albedo product. **Warning:** "MCD" here means *MODIS Combined* and has nothing to do with the Mars Climate Database below. Two unrelated things share three letters. |
| **MCD (Mars Climate Database)** | A global circulation model of the martian atmosphere. Our martian temperatures come from it. Its grid is the model's own, 5.625° × 3.75° — about 355 km, which is why Mars thermal cannot be a matching dimension. |
| **Ls (solar longitude)** | Where Mars is in its orbit — the martian season marker. Ls = 0 is northern spring equinox. Our martian temperatures are sampled at 12 values of Ls. |
| **TES** | Thermal Emission Spectrometer on Mars Global Surveyor. Source of martian mineral abundance maps and of a measured thermal inertia product at about 3 km. |
| **GLiM** | The Global Lithological Map (Hartmann & Moosdorf, 2012). 1.23 million polygons, 16 top-level rock classes and 434 subclasses. **Its own validation says 40% of classes match independent rock descriptions exactly, 64% allowing similar lithologies** — that is the accuracy ceiling on anything we derive from it. |
| **Köppen-Geiger** | The standard climate classification — BWh for hot desert, ET for tundra, and so on. Used only to *describe* sites, never to match them, since the Moon and Mars have no Köppen class. |
| **Robbins catalogue** | Published databases of named and measured impact craters on the Moon and on Mars. Supplies crater geometry. |
| **Artemis III candidate landing regions** | NASA's own published shortlist of sites near the lunar south pole for the first crewed Artemis landing. **Nine regions as of the October 2024 update.** These are our lunar targets — the challenge asks for "permanent Moon base locations" and this is NASA's answer to that question. An older list of thirteen is still visible on one NASA page and is out of date. |
| **PSR (permanently shadowed region)** | A crater floor near a lunar pole that never receives direct sunlight. The coldest places in the inner solar system, and where water ice is expected. |

---

## 4. The method

| Term | Meaning |
|---|---|
| **Percentile transform** | Replacing a value with its rank inside its own body's distribution. Turns Kelvin, degrees and weight-percent into comparable numbers between 0 and 1. |
| **Rank** | The fraction of places with a smaller value. A rank of 0.9 means "larger than 90% of this world". |
| **Tie** | Two or more cells holding exactly the same value. Common here — flat ground, quantized storage, copied categorical values. Handled with midpoint rank. |
| **Normal score transform** | Converting a rank into the value sitting at that percentile of a standard normal distribution: *z* = inverse normal CDF of *p*. Rank 0.5 → 0, rank 0.84 → +1. Restores the tails that ranking flattened. |
| **Covariance** | A measure of how two variables move together. Positive means they rise together; zero means they are unrelated. |
| **Whitening** | Transforming the variable space so the axes become independent, which stops correlated variables being counted twice. |
| **Mahalanobis distance** | Distance measured after whitening. Asks *"how surprising is this combination of differences"* rather than *"how far apart are these numbers"*. |
| **Block-diagonal** | Whitening applied inside each variable group separately rather than across all variables at once, so the groups stay identifiable and can still be weighted. |
| **Ridge term** | A small number added to a matrix's diagonal so it can be inverted. Needed when two variables are almost perfectly correlated. |
| **VIF (variance inflation factor)** | How much one variable is explained by all the others. A **diagnostic here, not a pruning rule** — whitening already handles redundancy. |
| **λ_min (smallest eigenvalue)** | The real guard. Whitening handles correlation but not *near*-singularity: when two variables correlate at 0.999, the whitening step **amplifies** that degenerate direction instead of shrinking it. A variable is dropped only if λ_min falls below 0.10. |
| **Effective dimensionality** | How many genuinely independent directions the variables span, which is usually fewer than the number of variables. The real limit on the method — not the raw count. |
| **Curse of dimensionality** | In many dimensions with few points, everything becomes roughly equidistant and distance stops carrying information. The reason the dimension count is bounded. |
| **AOA (Area of Applicability)** | A published method in spatial machine learning (Meyer & Pebesma) for deciding where a model may be trusted. The closest existing relative of this work. It uses importance-weighted *Euclidean* distance, not Mahalanobis — ours is an extension, and we say so. |
| **Target** | The place on the Moon or Mars we are finding analogs for. Becomes a cloud of points in the dimension space. |
| **Distinct cell count** | How many separate target cells there are. The real sample size, and the number every size comparison uses. |
| **Target spread** | The median pairwise distance among the target's own cells. Tells you whether the choice of *k* matters. |
| **k** | How many nearest target cells each Earth cell is scored against. Set to min(5, distinct cells) — a dial, not a constant. |
| **KD-tree** | A data structure that finds nearest neighbours quickly, so every target cell can be used instead of a subsample. |
| **DI (dissimilarity index)** | The mean distance to the *k* nearest target cells, divided by a typical distance. **DI = 1 means "as different as two random places are from each other".** Reported against two denominators: DI_earth and DI_target. |
| **d-bar** | The denominator in DI — the *median* pairwise distance within Earth's reference population, or within the target. |
| **Decorrelation length (R)** | How far apart two Earth cells must be before their DI values stop being related. Measured per run. |
| **Exclusion radius** | The minimum spacing between selected sites, set to the measured decorrelation length so the output is a list of distinct places rather than one place listed many times. |
| **No threshold** | A standing rule. Nothing in this method passes or fails a cut. Sites are chosen by rank; evidence is reported as a p-value and an effect size. |

---

## 5. Quality gates and evidence

Each gate exists because the one before it was caught giving a clean answer on
broken data.

| Term | Meaning |
|---|---|
| **Range gate** | *Are the values physically plausible?* Checked against bounds stated **before** the run, never widened afterwards to fit the data. A gate adjusted to pass is not a gate. |
| **Coverage gate** | *Did the pixel receive any data at all?* Caught a Mars elevation grid that passed the range gate while only 0.3% of the planet was valid. |
| **Support** | *How much of the pixel actually contributed?* The share of a pixel's underlying cells that supplied usable data — or, for categorical layers, the winning class's share. Caught pixels reporting "100% valid" while resting on three source cells out of 215. |
| **Tie diagnostics** | `distinct_levels` and `largest_tie_fraction`. *How many different values does this layer actually hold, and how much of the world shares one of them?* The only gate that sees a layer where every check passes but 27% of land carries an identical number. |
| **Provenance** | A per-pixel label recording how its value was produced: **BINNED** (averaged from finer source data), **COPIED_FROM_COARSER** (duplicated from a coarser source), or **ABSENT**. Kept as an explicit array rather than inferred from a support value. |
| **Null model** | A deliberately uninformative version of the comparison, used to see what score chance alone produces. Ours is a random compact patch of the same size on the same body. |
| **Compact patch** | The shape a fake target takes in the null test — a contiguous blob, not scattered cells, so the comparison is fair. |
| **p-value** | How often chance alone would produce a result at least this good. It does **not** say the theory is true, and it does **not** say the match is good — only that it is unlikely by chance. |
| **Positive control** | A case where the answer is already known to be yes. Ours is the Atacama. A second one: nine Apollo field-training sites that NASA itself judged lunar-like. If these fail, the test has no power. |
| **Negative control** | A case where the answer is already known to be no. Ours is an unreachable lunar cold trap. If it comes back significant, the test is finding things that are not there. |
| **Effect size** | How large the result actually is, in real units. Always printed next to a p-value, because a statistically solid weak match is still a weak match. |
| **Construction** | One complete set of method choices — a transform, a distance, a weighting. |
| **Median rank / rank interval** | A site's middle rank across constructions, and the best and worst it reached. Narrow means robust; wide means the answer depends on choices we cannot justify. |
| **Monte Carlo** | Repeating a computation many times with randomised choices to see how much the answer moves. |
| **Novelty label** | Whether a result already appears in the published analog literature. Marked, never used to hide results. |
| **KMO** | Kaiser–Meyer–Olkin measure of sampling adequacy. Reported to show, with a number, why PCA is not appropriate here. |
| **p-hacking** | Re-running an analysis with different choices until the p-value is small, then reporting only that run. The reason the null test promises *in advance* not to re-run a non-significant result. |
| **HOLD** | A status meaning a layer was built, measured, stored and documented — and deliberately not used. Not a failure, and not hidden. |
