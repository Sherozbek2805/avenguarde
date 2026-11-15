# CUBE STATE

*Generated 2026-11-11 18:13 UTC by `build/cube_state.py` from `cube/cube_manifest.json`. Do not edit by hand -- re-run it.*

**VARIABLES.md is the decision LOG and explains WHY. This file says WHAT, and only what is true now.**

## Matchable dimensions

| pairing | count | dimensions |
|---|---|---|
| **Earth-Moon** | **12** | FeO, SiO2, roughness_10.5km, roughness_21km, roughness_42km, roughness_5.25km, slope, svf_30km, temp_level, temp_range_diurnal, tpi_21km, tpi_7km |
| **Earth-Mars** | **13** | FeO, SiO2, roughness_10.5km, roughness_21km, roughness_42km, roughness_5.25km, slope, svf_30km, temp_level, temp_range_diurnal, temp_range_seasonal, tpi_21km, tpi_7km |

These are the sets the engine ranks with. Correlated variables (the four roughness scales, for example) are not dropped: double counting is removed by group-wise whitening (VARIABLES.md B34).

## Per body

| body | Nside | pixel | matchable | held back | ineligible |
|---|---|---|---|---|---|
| earth | 1024 | 6.37 km | **13** | roughness_scaling_exponent | - |
| moon | 256 | 6.95 km | **12** | roughness_scaling_exponent | - |
| mars | 512 | 6.79 km | **13** | roughness_scaling_exponent | - |

## Excluded, and why

| what | why |
|---|---|
| `roughness_scaling_exponent` (all 3 bodies) | **HOLD.** Signal-to-noise 2.12x against its own estimator noise; 21.8% of pixels exceed H=1, detecting discrete features rather than fractal texture. It is NOT redundant with ruggedness (measured -0.157) -- the B8 prediction was wrong. Built and stored. VARIABLES.md B12, B15. |
| Mars thermal (3 layers) | **Built, MODELLED.** Three layers from a thermal model driven by TES thermal inertia and albedo (VARIABLES.md B28). The coarse climate grid first considered (B17a) is not used. |
| Mars composition | **Built where the maps have data.** `mars_SiO2` and `mars_FeO` from the TES mineral maps (VARIABLES.md B27c). |
| `temp_range_seasonal` on the Moon | The Moon has no meaningful seasonal cycle (axial tilt 1.54 deg). Correctly absent. |
| Thermal inertia | **Stored, never ranked.** Earth's layer and Mars's layer are different quantities and cannot share one scale (VARIABLES.md B27, B38). |

## Health warnings that must travel with the data

1. **Never test `support` against zero to decide usability.** `support == 0.0` means COPIED_FROM_COARSER on some layers and NO_VALID_SOURCE on others. Read `provenance_file` against `cube/provenance_encoding.json`. VARIABLES.md B21/Task 2.
2. **Composition is a WEAK dimension at both ends.** Moon: ~3.4 effective levels for SiO2 at the targets (nominal 24), acting as a near-fixed offset toward mafic terrain. Earth: GLiM's 40% exact / 64% similar ground-truth ceiling.
3. **Earth's `temp_range_diurnal` is max minus min over FOUR local times** (Terra ~10:30/22:30 + Aqua ~13:30/01:30) -- the same quantity the Moon (96 local times) and Mars (12) carry. Four fixed overpass times are still not the true daily extremes, so Earth's value is a LOWER BOUND, loosest at high latitude. Rebuilt 9 Nov 2026; the earlier two-sample Terra day-minus-night could go negative and is gone.
4. **Earth thermal is calendar 2025 only, 12 months, Terra AND Aqua** -- one year, not climatology, so a single anomalous season is not averaged out. Chosen so the four local times share one time span.
5. **Aggregation is the area-weighted MEAN, not the median** the spec originally specified. Deliberate; VARIABLES.md B13.

## Never ranked: masks, filters, characterization, diagnostics

These describe, select or qualify. None may enter a dimension set.

| body | layer | role |
|---|---|---|
| earth | `koppen_class` | characterization |
| earth | `lithology_l1` | filter and composition route |
| earth | `lithology_l3` | filter and composition route |
| earth | `lithology_support` | filter and composition route |
| earth | `reference_mask` | mask |
| earth | `thermal_inertia` | characterization: thermal inertia, shown per site, never ranked (B33) |
| earth | `thermal_nsamples` | diagnostic: sampling support of the thermal layers |
| moon | `thermal_nsamples` | diagnostic: sampling support of the thermal layers |
| mars | `albedo` | input: albedo for the thermal model; characterization (not a ranking dimension by decision of 9 Nov 2026) |
| mars | `temp_frost_seasons` | diagnostic of the modelled thermal layers |
| mars | `temp_model_rms` | diagnostic of the modelled thermal layers |
| mars | `thermal_inertia` | characterization: thermal inertia, shown per site, never ranked (B33) |
| mars | `thermal_inertia_day` | diagnostic: dayside apparent thermal inertia |

## Validation

`build/cube_validate.py` last ran 2026-11-11T18:13:56Z: **PASS** -- 0 layer failures, 0 orphan files, 0 encoding issues, 0 pairing mismatches. Details in `cube/cube_validation.json`.

## Gates every layer carries

| gate | question |
|---|---|
| range | are the values plausible? (stated BEFORE each run) |
| coverage | did the pixel get anything? |
| support | how much of the pixel contributed? |
| distinct_levels / largest_tie_fraction | categorical and copied layers only -- the other three are blind to copied values |

## Files

```
cube/cube_manifest.json        every layer, every decision
cube/provenance_encoding.json  the 4 provenance codes, ONE named place
cube/dead_files.json           files that look like data and are not
cube/cube_validation.json      build/cube_validate.py report: manifest vs disk
cube/koppen_legend.json        Koppen class code -> symbol -> description
cube/healpix/                  the cube
cube/dem/                      working-resolution DEMs and masks
SOURCES.md                     context sources and what they are NOT for
VARIABLES.md                   the decision log (B1-B39)
```

Manifest entries by phase: 0 smoke = 2, 1 DEMs = 5, 1b ice = 2, 2 terrain = 27, 2c sky view factor = 3, 3 thermal = 7, 3b composition = 9, 3c characterization = 1, 3d Mars thermal inertia = 2, 3e Earth apparent TI = 1, 3f Mars temperature, modelled = 6, 3g = 6, None = 1
