# Variable menu — what else the cube can carry, and at what cost

Written 9 Nov 2026 from two source searches (primary sources only: PDS, USGS,
ASU, LP DAAC, ESA PSA, Zenodo, PANGAEA, GitHub repositories, LMD documents).
Nothing was downloaded. Where a site refused automated access the fact is
marked "not verified". This is the decision list; the measurements that
follow any decision go to VARIABLES.md.

The rule that sorts everything: **a variable ranks only if both bodies in a
pair have a measured, gridded, numeric product at roughly 10 km or finer.**
Everything else is a characterization layer — it describes a site after it
is found, changes no number, and answers the challenge's word "characterize".

## 0. What the cube has tonight

| | Earth–Moon (12) | Earth–Mars (10) |
|---|---|---|
| terrain | slope, roughness ×4, TPI 21, TPI 7, SVF | same 8 |
| thermal | temperature level, diurnal range | **none** — Mars thermal inertia built, Earth partner waits on albedo |
| composition | SiO₂, FeO (LP GRS) | SiO₂, FeO (TES mineral maps, weak, 49% of Mars) |

The challenge's dimensions of analogy, against that: geology ✓ (weak),
terrain ✓, temperature ✗ for Mars, illumination ✗, water/ice ✗, dust/wind ✗,
habitability ✗ (Earth-only by nature), caves/subsurface ✗ (catalogues on disk,
not wired), operations ✓ partly (slope, roughness, SVF, TI).

## 1. Mars temperature — the one finding that changes the plan

**No measured, gridded Mars surface-temperature map exists at pixel scale.**
TES temperatures are per-observation only; THEMIS mosaics are stretched
8-bit pictures; MCS and EMIRS are degrees-scale. And the Mars Climate
Database cannot be sharpened: its design document (v6.1, §7.3.1) states that
the high-resolution mode leaves surface temperature untouched — it only
rescales pressure. Every MCD temperature at our pixel is an interpolation
of the 355 km model grid. That door is closed.

**The defensible route is to run a thermal model ourselves.** KRC (Kieffer
2013, JGR Planets) is public Fortran, 3.5 ms per point, and is the model
the TES thermal-inertia maps were derived with — so running it forward from
thermal inertia, albedo, MOLA pressure, latitude, slope and aspect is
self-consistent. The literature does exactly this with lookup tables
(Mellon 2000, Putzig & Mellon 2007, Fergason 2006). Plan: build a table over
TI × albedo × pressure × latitude (× slope) for 12 Ls × 24 local times,
interpolate onto the 6.8 km grid, derive annual mean, diurnal range at fixed
local times, seasonal range of the daily mean. Use the MCD only for dust
opacity and as a coarse-scale check. Fallback if KRC will not build on
Windows: a NumPy port of Schorghofer's `mars_thermal1d` physics (~300 lines).

Cost: about two days. Output must be labelled **MODELLED, not measured**,
with the stated approximations (one-layer grey atmosphere, climatological
dust, no slope winds, albedo and TI from different years, one scale height).
Gain: Mars temperature level, diurnal range and seasonal range become
eligible for Earth–Mars, 10 → 13. This is the single largest addition
available and the one that answers "rovers spend years in this temperature".

## 2. Pairable additions — can rank on both bodies

| variable | Mars | Earth | Moon | effort | caveat to record |
|---|---|---|---|---|---|
| **Albedo** | TES bolometric 8 ppd (7.4 km), 32-bit float, global, PDS, no login — verified | MCD43C3 0.05°, 12 monthly files → annual mean; Earthdata login; or your GEE export, which is already the ATI input | LOLA LDAM 1064 nm, 4/8/10 ppd global + 1 km polar to 50°, PDS, no login — verified | low (Mars, Moon 1 h each; Earth 3–4 h once the files exist) | wavelengths differ: Moon 1064 nm, Mars bolometric, Earth shortwave or NIR. Pair Moon with Earth Band 2 (858 nm), Mars with Earth shortwave. Record it. |
| **Dust-storm frequency** | MDAD v1.1, 0.1° per-sol masks MY28–32, Zenodo, sum to frequency — verified | MODFDS_MON_GLB_L3, 0.1° monthly dust-storm frequency 2000–2022, GES DISC, Earthdata login — verified via CMR | none | medium (4 h) | 0.1° is coarser than the pixel on both (copied values); Earth is land-only; both are frequency-of-detection, a comparable quantity |
| **Hectometre roughness** | MOLA pulse-width, slope-corrected, 8 ppd GMT grid, PGDA — verified | Geomorpho90m roughness / TRI at 250 m, OpenTopography / PANGAEA, CC BY — verified | LOLA LDRM 16 ppd global + 240 m and 40 m polar — verified | medium (4–6 h, Earth tiles) | baselines differ: Moon 25–120 m, Mars ~150 m footprint, Earth 90–250 m. Same word, different quantity — the project's recurring trap. Rank-normalisation hides it; the manifest must not. |
| Dune presence | MGD3 vector, 65S–65N + polar caps, USGS (403 to scripts; manual download) | GSDS30, 30 m global, 1.1 GB, Zenodo CC BY — verified | none | medium (3–4 h) | categorical → dune-area fraction per pixel; a filter/characterization more than a dimension |
| Ground-ice likelihood | SWIM 2.0 ice consistency, 3 km, ±60°, PSI — verified | Obu 2019 permafrost probability, 1 km, Northern Hemisphere ≥25°N only — verified | LPNS hydrogen 0.5° (15 km, borderline) | low–medium | **recommend characterization, not ranking**: "ice consistency" and "permafrost probability" are different quantities, and Earth has no southern hemisphere, so a ranking would favour the north for an artificial reason |

## 3. Characterization only — one body, describes a site

| layer | body | source | effort | why it matters |
|---|---|---|---|---|
| Polar illumination (average visibility, permanent shadow, Earth visibility) | Moon | LOLA illumination 240 m / 60 m, PDS and PGDA COG, no login — verified | low (1 h) | the quantity NASA chose Artemis sites on. Describes every lunar target directly. |
| Dust cover index | Mars | TES DCI 16 ppd (3.5 km), float, ASU, no login — verified | low (1 h) | says whether a Mars target is dust-mantled, which decides what composition and TI mean there |
| Hydrogen / water-equivalent | Mars, Moon | Odyssey GRS/NS 2–5°; LPNS 0.5°; LAMP polar 240 m | low (2 h) | resource context; too coarse to rank |
| Rockiness / bare ground | Earth | SoilGrids coarse fragments 250 m; CGLS bare-cover fraction 100 m — verified | low (2 h) | the Earth side of mobility; Mars rock abundance (Nowicki 2007) is **not public**, so it cannot pair |
| Aridity index | Earth | Global AI v3.1, 30 arcsec, figshare, no login — verified | low (1 h) | habitability / extremophile context; pairs with Köppen |
| Land cover | Earth | MCD12C1 0.05°, Earthdata login | low (1 h) | the spec's Part C filter "exclude vegetated ground" — not yet built |
| Geologic unit class | all three | Tanaka 2014 SIM 3292 (790 MB gdb), Unified Moon map (224 MB), GLiM on disk; USGS blocks scripts, manual download | medium–high (6 h) | categorical "volcanic / impact / sedimentary" match for step 9; age is still not composition |
| Caves, pits, karst | all three | MGC3 (on disk), LROC pits atlas (HTML table, scrape), WOKAM (BGR, licence not verified) | medium (3 h) | the challenge names caves and lava tubes explicitly |
| Dune presence | Mars, Earth | as above | medium | mobility hazard (Spirit) |

## 4. Looked for and not available

TES rock abundance (never released as numeric) · Kreslavsky & Head roughness
grids (RGB picture only) · gridded TES or THEMIS temperature (none) ·
LEND gridded hydrogen (not archived) · M3 water map (archive link dead) ·
PASSC impact database (HTML only) · Earth km-scale roughness from ICESat
(none) · login-free Earth albedo climatology at 0.05° (none verified).

## 5. Two items from your own literature folder

- **Gard, Hasterok & Halpin 2019**, global whole-rock geochemical database
  (ESSD): a primary source to verify the Earth 98-row lookup's wt% values —
  the "[UNVERIFIED-VALUE]" item in Appendix H. Median SiO₂ and FeO per rock
  type straight from measured samples.
- **PTAL** (Dypvik et al. 2021): a vetted list of lithological Mars analogue
  sites with chemistry. Feeds the known-analog catalogue with citations.

## 6. Recommendation, five days out

Build in this order; stop wherever the clock says.

1. **KRC Mars temperatures** (2 days). Earth–Mars 10 → 13, modelled, flagged.
2. **Albedo on all three** (1 day once Earth files exist). Both pairings +1.
   The same Earth files finish the Earth apparent-TI partner, Earth–Mars +1.
3. **Moon polar illumination, Mars DCI, Earth aridity and land cover** (half
   a day, all no-login except land cover). Characterization that makes step 9
   read like a site report.
4. **Dust-storm frequency** (half a day). Earth–Mars +1; the dust dimension.
5. Hectometre roughness only if time remains, with the baseline caveat.

What only you can do: the Earthdata downloads (MCD43C3 twelve monthly files,
or a GEE export with shortwave and Band 2 albedo for all twelve months;
MODFDS; MCD12C1), the USGS zips the site blocks for scripts (Tanaka, Unified
Moon map, MGD3), and the KRC build if gfortran is not on this machine.
