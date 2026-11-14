# Terrestrial Analog Finder

NASA Space Apps Challenge 2026. Where on Earth is most like a place on the Moon or Mars?

Give the tool a region on the Moon or Mars. It scores every piece of Earth's ice-free land against it, ranks the result, tests the best match against chance, and says where the match holds, where it breaks, and what no place on Earth can offer.

**State on 14 November 2026:** the data cube, the calibration, the output contract and the specifications are finished. The engine (score, chance test, sites, description) is written on the hackathon days, 14–15 November.

## Start here

| if you are | read |
|---|---|
| anyone | the animated explainer: `docs/Analog_Finder_Explained.html` (open in a browser) |
| writing the engine | `docs/TEST_SPEC_2026-11-10.md`, top to bottom. Then `docs/NULL_TABLE_DESIGN_2026-11-10.md` |
| building the website | `contract/README.md`, then the three `contract/example_*.json` files |
| checking a decision | `VARIABLES.md`, the decision log. Sections B33 to B38 hold the method as it stands |
| looking for a source | `SOURCES.md` |

The full method is `docs/analog_finder_method_spec_rev10.docx`.

## The method in ten lines

1. **Grid.** Earth, the Moon and Mars on equal-area cells (HEALPix), about 6 to 7 km across on all three.
2. **Variables.** Terrain (slope, roughness at four scales, landform position, open sky), temperature (level, day–night swing, seasonal swing on Mars), rock (silica, iron oxide). 12 for Earth–Moon, 13 for Earth–Mars.
3. **One scale.** Each variable is put on one min-max scale shared by Earth and the target world.
4. **Whitening.** Double counting is removed inside each group of variables, using Earth's own pattern.
5. **Target.** Nine Artemis III regions and six NASA Exploration Zones on Mars are built in; a user can draw their own.
6. **Score.** An Earth cell's score is its mean distance to every cell of the target. Cells are then ranked: the best 1%, the best 5%.
7. **Chance test.** 1,000 random patches of the same size and latitude; one control (a patch of the Atacama).
8. **Sites.** Cells of the best 1% that touch each other are one place.
9. **Describe.** Every variable, its gap in real units, and three lists per site: succeeds, fails, beyond Earth.
10. **Output.** One JSON file and a few maps per run (`contract/`).

## What is in this repository

| path | what |
|---|---|
| `build/` | the scripts that built the cube and the calibration. One script per step; run them one at a time |
| `cube/healpix/` | the cube: 131 layers, one `.npy` file each (12 × Nside² values; Nside 1024 Earth, 256 Moon, 512 Mars) |
| `cube/cube_manifest.json` | every layer: units, source, gates, provenance |
| `cube/phase4/` | the calibration: reference population, whitening matrices, typical distances |
| `contract/` | the output contract (version 2.4), examples, preset targets, the use table |
| `docs/` | specifications, the method spec, figures, the explainer |
| `export/site_assets/` | map tiles of the layers and the catalogues, for the website |
| `sources/` | only the small tables this project wrote (targets, lookups, the analog-site catalogue) |

## What is NOT here, and how to get it

- **Three calibration files over GitHub's 100 MB limit.** Rebuild them in about 30 seconds:

  ```bash
  python build/phase4b_minmax_scale.py
  ```

  It writes `cube/phase4/minmax_earth_moon.npy`, `minmax_earth_mars.npy` and `minmax_mars.npy` from the layers in `cube/healpix/`.
- **The raw downloads** (about 30 GB) and the full-resolution elevation grids (30 GB). `SOURCES.md` lists where each came from. They are needed only to rebuild a layer, not to run the engine.
- `cube/phase4/percentiles.npy`, a diagnostic the engine must not read.

## Check your copy

```bash
python build/cube_validate.py
```

It must print `PASS`. Python 3.11 or later with `numpy`, `scipy`, `astropy`, `astropy-healpix`, `jsonschema`.

The scripts find the project folder from their own location. To point them elsewhere, set `ANALOG_ROOT`.

## Honest limits

- No place on Earth copies lunar or martian gravity, air pressure, radiation or day length. Every site is a partial analog.
- Mars temperatures are modelled, not measured. Earth's rock chemistry is a lookup by rock class.
- One cell is 6 to 7 km across. Nothing here describes boulders or soil.
- The examples in `contract/` carry real cube values and PLACEHOLDER scores and p-values. Results exist only after the engine has run.

## Data sources

All input data is public. Each derived layer names its source in `cube/cube_manifest.json` and `SOURCES.md`: LOLA and MOLA elevation, ETOPO 2022, MODIS land-surface temperature, LRO Diviner, Lunar Prospector, TES, GLiM (Hartmann & Moosdorf 2012), SCAR GeoMAP (Cox et al. 2023), Gard et al. 2019, the Artemis III candidate regions (NASA, 28 October 2024) and NASA's 2015 Exploration Zone workshop.

## AI use

Built with Claude (Anthropic) under the team's direction; every method decision was made by the team and is recorded in `VARIABLES.md`.
